"""
WebSocket module for real-time deployment progress.

This module provides SocketIO integration for broadcasting deployment
progress events to connected clients in real-time with performance
optimizations including:
- SSH connection pooling
- Progress update batching
- Event persistence for reconnection recovery
- Prometheus metrics

Performance Targets:
- 100+ concurrent connections
- <500ms latency for progress updates
- 80% SSH connection overhead reduction
- <1s reconnection state recovery
- <500MB memory for WebSocket layer
"""

from flask_socketio import SocketIO
import redis
import os
import logging

logger = logging.getLogger(__name__)

# Redis configuration for SocketIO message queue
REDIS_HOST = os.environ.get("REDIS_HOST", "100.126.103.51")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk")

# SocketIO instance (initialized in app.py)
socketio = None


# ============================================================================
# Prometheus Metrics
# ============================================================================

# Lazy-load prometheus_client to avoid import errors if not installed
_metrics = None


def _get_metrics():
    """Lazy-load Prometheus metrics."""
    global _metrics
    if _metrics is None:
        try:
            from prometheus_client import Gauge, Counter, Histogram
            
            _metrics = {
                'connections_active': Gauge(
                    'websocket_connections_active',
                    'Active WebSocket connections'
                ),
                'messages_sent': Counter(
                    'websocket_messages_sent_total',
                    'Total WebSocket messages sent',
                    ['event_type']
                ),
                'message_latency': Histogram(
                    'websocket_message_latency_seconds',
                    'Message delivery latency',
                    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
                ),
                'ssh_pool_size': Gauge(
                    'ssh_pool_connections',
                    'Active SSH connections in pool',
                    ['server']
                ),
                'ssh_pool_active': Gauge(
                    'ssh_pool_active_connections',
                    'Currently in-use SSH connections',
                    ['server']
                ),
                'progress_batch_size': Histogram(
                    'progress_batch_size',
                    'Number of events in progress batches',
                    buckets=[1, 5, 10, 20, 50, 100]
                ),
                'reconnection_count': Counter(
                    'websocket_reconnections_total',
                    'Total WebSocket reconnections'
                ),
                'events_persisted': Counter(
                    'websocket_events_persisted_total',
                    'Total events persisted to Redis',
                    ['deployment_id']
                ),
            }
        except ImportError:
            logger.warning("prometheus_client not installed, metrics disabled")
            _metrics = {}
    
    return _metrics


def increment_metric(metric_name: str, labels: dict = None, value: float = 1):
    """
    Increment a Prometheus counter.
    
    Args:
        metric_name: Name of the metric
        labels: Optional labels dictionary
        value: Value to increment by (default: 1)
    """
    metrics = _get_metrics()
    if metric_name in metrics:
        metric = metrics[metric_name]
        if labels:
            metric.labels(**labels).inc(value)
        else:
            metric.inc(value)


def set_gauge(metric_name: str, value: float, labels: dict = None):
    """
    Set a Prometheus gauge value.
    
    Args:
        metric_name: Name of the metric
        value: Value to set
        labels: Optional labels dictionary
    """
    metrics = _get_metrics()
    if metric_name in metrics:
        metric = metrics[metric_name]
        if labels:
            metric.labels(**labels).set(value)
        else:
            metric.set(value)


def observe_histogram(metric_name: str, value: float, labels: dict = None):
    """
    Observe a value in a Prometheus histogram.
    
    Args:
        metric_name: Name of the metric
        value: Value to observe
        labels: Optional labels dictionary
    """
    metrics = _get_metrics()
    if metric_name in metrics:
        metric = metrics[metric_name]
        if labels:
            metric.labels(**labels).observe(value)
        else:
            metric.observe(value)


# ============================================================================
# SocketIO Initialization
# ============================================================================

def init_socketio(app):
    """
    Initialize SocketIO with Flask app.
    
    Uses Redis as a message queue for multi-worker support.
    This allows Celery workers to emit events that are received
    by all connected Flask-SocketIO workers.
    
    Performance optimizations:
    - Redis DB 0 for message queue
    - Redis DB 3 for progress events (separate from cache)
    - Connection pooling for SSH
    - Event batching for reduced network traffic
    
    Args:
        app: Flask application instance
        
    Returns:
        SocketIO instance
    """
    global socketio
    
    # Redis URL for message queue (DB 0)
    redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
    
    # Optimized SocketIO configuration
    socketio = SocketIO(
        app,
        cors_allowed_origins="*",
        async_mode='threading',
        message_queue=redis_url,
        ping_timeout=60,
        ping_interval=25,
        # Performance tuning
        max_http_buffer_size=10 * 1024 * 1024,  # 10MB for large batches
        engineio_logger=False,  # Reduce logging overhead
    )
    
    # Register event handlers
    from .handlers import register_handlers
    register_handlers(socketio)
    
    # Register recovery handlers
    from .recovery import register_recovery_handlers
    register_recovery_handlers(socketio)
    
    # Initialize progress manager with socketio instance
    from .progress import get_progress_manager
    get_progress_manager(socketio)
    
    # Initialize SSH pool health monitoring
    from .performance import get_ssh_pool
    get_ssh_pool()
    
    logger.info("WebSocket initialized with performance optimizations")
    
    return socketio


def get_socketio():
    """
    Get the SocketIO instance.
    
    Returns:
        SocketIO instance or None if not initialized
    """
    return socketio


# ============================================================================
# Progress Emission Functions
# ============================================================================

def emit_progress(deployment_id, event_type, data):
    """
    Emit a progress event to a deployment room.
    
    This function is used by Celery tasks to broadcast progress updates.
    It can be called from any worker process.
    
    Performance optimizations:
    - Uses ProgressManager for throttling
    - Persists events to Redis for reconnection recovery
    - Batches small updates automatically
    
    Args:
        deployment_id: Unique deployment identifier
        event_type: Type of event (e.g., 'step_progress', 'step_complete', 'deployment_complete')
        data: Event data dictionary
        
    Returns:
        bool: True if emission successful
    """
    global socketio
    
    if socketio is None:
        # Create a SocketIO instance just for emitting (Celery worker context)
        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
        socketio = SocketIO(message_queue=redis_url)
    
    # Use progress manager for optimized emission
    from .progress import get_progress_manager
    progress_manager = get_progress_manager(socketio)
    
    try:
        # Handle different event types
        if event_type in ('step_complete', 'error', 'deployment_complete'):
            # Critical events - emit immediately
            if event_type == 'step_complete':
                progress_manager.emit_step_complete(
                    deployment_id,
                    data.get('server'),
                    data.get('step'),
                    data.get('output')
                )
            elif event_type == 'error':
                progress_manager.emit_error(
                    deployment_id,
                    data.get('error', 'Unknown error'),
                    data.get('server'),
                    data.get('step')
                )
            elif event_type == 'deployment_complete':
                progress_manager.emit_deployment_complete(
                    deployment_id,
                    data.get('success', False),
                    data.get('duration')
                )
                # Cleanup progress data
                progress_manager.cleanup(deployment_id)
        else:
            # Regular progress - may be throttled/batched
            progress_manager.emit_progress(deployment_id, {
                'event_type': event_type,
                **data
            })
        
        # Increment metrics
        increment_metric('messages_sent', {'event_type': event_type})
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to emit progress for {deployment_id}: {e}")
        return False


def emit_to_all(event_name, data):
    """
    Emit an event to all connected clients.
    
    Args:
        event_name: Name of the event
        data: Event data dictionary
    """
    global socketio
    
    if socketio is None:
        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
        socketio = SocketIO(message_queue=redis_url)
    
    socketio.emit(event_name, data)
    increment_metric('messages_sent', {'event_type': event_name})


# ============================================================================
# SSH Connection Pool Functions
# ============================================================================

def get_ssh_connection(server_ip: str):
    """
    Get an SSH connection from the pool.
    
    This function provides access to the SSH connection pool
    for deployment tasks.
    
    Args:
        server_ip: Server IP address (Tailscale IP)
        
    Returns:
        SSHClient instance or None if connection failed
        
    Example:
        connection = get_ssh_connection('100.92.26.38')
        if connection:
            try:
                stdin, stdout, stderr = connection.exec_command('ls -la')
                output = stdout.read().decode()
            finally:
                release_ssh_connection(connection, '100.92.26.38')
    """
    from .performance import get_ssh_pool
    
    pool = get_ssh_pool()
    connection = pool.get_connection(server_ip)
    
    if connection:
        # Update metrics
        stats = pool.get_stats()
        if server_ip in stats['servers']:
            set_gauge('ssh_pool_active', 
                     stats['servers'][server_ip]['active'], 
                     {'server': server_ip})
    
    return connection


def release_ssh_connection(connection, server_ip: str):
    """
    Release an SSH connection back to the pool.
    
    Args:
        connection: The SSH connection to release
        server_ip: Server IP address
    """
    from .performance import get_ssh_pool
    
    pool = get_ssh_pool()
    pool.release_connection(connection, server_ip)
    
    # Update metrics
    stats = pool.get_stats()
    if server_ip in stats['servers']:
        set_gauge('ssh_pool_active', 
                 stats['servers'][server_ip]['active'], 
                 {'server': server_ip})


# ============================================================================
# Health Check Functions
# ============================================================================

def get_websocket_health() -> dict:
    """
    Get health status of WebSocket components.
    
    Returns:
        Dictionary with health status of each component
    """
    from .performance import health_check
    return health_check()


def get_websocket_metrics() -> dict:
    """
    Get WebSocket performance metrics.
    
    Returns:
        Dictionary with metrics for monitoring
    """
    from .performance import get_ssh_pool, get_progress_batcher
    
    ssh_pool = get_ssh_pool()
    batcher = get_progress_batcher()
    
    return {
        'ssh_pool': ssh_pool.get_stats(),
        'batcher': batcher.get_stats(),
        'socketio': {
            'initialized': socketio is not None
        }
    }


# ============================================================================
# Export public API
# ============================================================================

__all__ = [
    'init_socketio',
    'get_socketio',
    'emit_progress',
    'emit_to_all',
    'get_ssh_connection',
    'release_ssh_connection',
    'get_websocket_health',
    'get_websocket_metrics',
    'increment_metric',
    'set_gauge',
    'observe_histogram',
]