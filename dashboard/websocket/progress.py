"""
Progress management module for WebSocket deployment updates.

This module provides intelligent progress update management with:
- Throttling to prevent message spam
- Critical event prioritization
- Event ID tracking for reconnection
- Redis-backed event history
"""

import time
import json
import logging
import threading
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
import redis
import os

logger = logging.getLogger(__name__)

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "100.126.103.51")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk")
REDIS_DB = 3  # Separate DB for SocketIO/progress events

# Event TTL in Redis (1 hour)
EVENT_TTL = 3600


class ProgressManager:
    """
    Manage deployment progress updates efficiently.
    
    This class handles:
    - Throttling regular updates to prevent spam
    - Immediate emission of critical events
    - Event persistence for reconnection recovery
    - Progress aggregation across multiple servers
    
    Performance Characteristics:
    - Regular updates: max 2 per second (throttled)
    - Critical events: immediate (no throttle)
    - Event history: 1 hour TTL in Redis
    - Reconnection: < 1 second state recovery
    
    Usage:
        manager = ProgressManager(socketio)
        manager.emit_progress(deployment_id, {'progress': 25, 'message': 'Cloning repo'})
        manager.emit_step_complete(deployment_id, 're-db', 'git_clone')
        manager.emit_error(deployment_id, 'Deployment failed')
    """
    
    # Throttle configuration
    MIN_UPDATE_INTERVAL = 0.5  # Max 2 updates per second
    BATCH_WINDOW = 1.0  # Batch window for small updates
    
    # Redis key prefixes
    EVENT_KEY_PREFIX = "deploy:events:"
    STATE_KEY_PREFIX = "deploy:state:"
    
    def __init__(self, socketio=None):
        """
        Initialize ProgressManager.
        
        Args:
            socketio: Flask-SocketIO instance
        """
        self.socketio = socketio
        self._redis_client = None
        self._last_update: Dict[str, float] = {}  # deployment_id -> last_update_time
        self._lock = threading.Lock()
        
        # Initialize progress batcher
        from .performance import get_progress_batcher
        self._batcher = get_progress_batcher()
        self._batcher.set_emit_callback(self._emit_batch)
    
    @property
    def redis_client(self):
        """Get or create Redis client."""
        if self._redis_client is None:
            self._redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                retry_on_timeout=True
            )
        return self._redis_client
    
    def emit_progress(self, deployment_id: str, update: Dict, throttle: bool = True):
        """
        Emit a progress update with optional throttling.
        
        This method:
        1. Checks if throttling should apply
        2. Adds to batch queue if within throttle window
        3. Emits immediately if throttle expired or disabled
        
        Args:
            deployment_id: Unique deployment identifier
            update: Progress update dictionary
                - progress: 0-100 progress percentage
                - message: Human-readable message
                - server: Server name (optional)
                - step: Current step name (optional)
            throttle: Whether to apply throttling (default: True)
        """
        current_time = time.time()
        
        with self._lock:
            # Check throttle
            if throttle and deployment_id in self._last_update:
                time_since_last = current_time - self._last_update[deployment_id]
                
                if time_since_last < self.MIN_UPDATE_INTERVAL:
                    # Add to batch queue
                    self._batcher.add_update(deployment_id, {
                        'type': 'progress',
                        'deployment_id': deployment_id,
                        **update
                    })
                    return
            
            # Update last emission time
            self._last_update[deployment_id] = current_time
        
        # Emit immediately
        self._emit_event(deployment_id, {
            'type': 'progress',
            'deployment_id': deployment_id,
            **update
        })
    
    def emit_step_complete(self, deployment_id: str, server: str, step: str, output: str = None):
        """
        Emit step completion immediately (no throttle).
        
        Step completions are critical events that should always
        be sent immediately to provide real-time feedback.
        
        Args:
            deployment_id: Unique deployment identifier
            server: Server name
            step: Step name that completed
            output: Optional step output
        """
        self._emit_event(deployment_id, {
            'type': 'step_complete',
            'deployment_id': deployment_id,
            'server': server,
            'step': step,
            'output': output,
            'timestamp': time.time()
        }, critical=True)
        
        # Clear throttle after critical event
        with self._lock:
            self._last_update[deployment_id] = time.time()
    
    def emit_step_start(self, deployment_id: str, server: str, step: str):
        """
        Emit step start event immediately.
        
        Args:
            deployment_id: Unique deployment identifier
            server: Server name
            step: Step name starting
        """
        self._emit_event(deployment_id, {
            'type': 'step_start',
            'deployment_id': deployment_id,
            'server': server,
            'step': step,
            'timestamp': time.time()
        }, critical=True)
        
        # Clear throttle
        with self._lock:
            self._last_update[deployment_id] = time.time()
    
    def emit_error(self, deployment_id: str, error: str, server: str = None, step: str = None):
        """
        Emit error immediately (no throttle).
        
        Errors are critical events that must be delivered
        immediately for debugging and user feedback.
        
        Args:
            deployment_id: Unique deployment identifier
            error: Error message
            server: Server where error occurred (optional)
            step: Step where error occurred (optional)
        """
        self._emit_event(deployment_id, {
            'type': 'error',
            'deployment_id': deployment_id,
            'error': error,
            'server': server,
            'step': step,
            'timestamp': time.time()
        }, critical=True)
    
    def emit_deployment_complete(self, deployment_id: str, success: bool, duration: float = None):
        """
        Emit deployment completion event.
        
        Args:
            deployment_id: Unique deployment identifier
            success: Whether deployment succeeded
            duration: Total deployment duration in seconds (optional)
        """
        self._emit_event(deployment_id, {
            'type': 'deployment_complete',
            'deployment_id': deployment_id,
            'success': success,
            'duration': duration,
            'timestamp': time.time()
        }, critical=True)
        
        # Clean up throttle state
        with self._lock:
            self._last_update.pop(deployment_id, None)
    
    def _emit_event(self, deployment_id: str, event: Dict, critical: bool = False):
        """
        Emit an event to WebSocket clients and persist to Redis.
        
        Args:
            deployment_id: Unique deployment identifier
            event: Event dictionary
            critical: If True, bypass batching
        """
        # Generate event ID
        event_id = f"{deployment_id}:{int(time.time() * 1000)}:{id(event)}"
        event['event_id'] = event_id
        
        # Persist to Redis for reconnection recovery
        self._persist_event(deployment_id, event_id, event)
        
        # Emit to WebSocket room
        if self.socketio:
            room = f"deployment:{deployment_id}"
            try:
                self.socketio.emit('deployment_progress', event, room=room)
                logger.debug(f"Emitted {event['type']} event for {deployment_id}")
            except Exception as e:
                logger.error(f"Failed to emit event for {deployment_id}: {e}")
    
    def _emit_batch(self, deployment_id: str, events: List[Dict]):
        """
        Emit a batch of events as a single message.
        
        Args:
            deployment_id: Unique deployment identifier
            events: List of event dictionaries
        """
        if not events:
            return
        
        # Persist all events
        for event in events:
            self._persist_event(deployment_id, event['event_id'], event)
        
        # Emit batch
        if self.socketio:
            room = f"deployment:{deployment_id}"
            try:
                self.socketio.emit('deployment_progress_batch', {
                    'type': 'batch',
                    'deployment_id': deployment_id,
                    'events': events,
                    'timestamp': time.time()
                }, room=room)
                
                logger.debug(f"Emitted batch of {len(events)} events for {deployment_id}")
            except Exception as e:
                logger.error(f"Failed to emit batch for {deployment_id}: {e}")
    
    def _persist_event(self, deployment_id: str, event_id: str, event: Dict):
        """
        Persist event to Redis for reconnection recovery.
        
        Events are stored in a Redis sorted set with timestamp as score,
        allowing efficient range queries for missed events.
        
        Args:
            deployment_id: Unique deployment identifier
            event_id: Unique event identifier
            event: Event dictionary
        """
        try:
            key = f"{self.EVENT_KEY_PREFIX}{deployment_id}"
            score = time.time()
            
            # Add to sorted set
            self.redis_client.zadd(key, {json.dumps(event): score})
            
            # Set TTL
            self.redis_client.expire(key, EVENT_TTL)
            
            # Keep only last 1000 events per deployment
            self.redis_client.zremrangebyrank(key, 0, -1001)
            
        except Exception as e:
            logger.error(f"Failed to persist event {event_id}: {e}")
    
    def get_missed_events(self, deployment_id: str, since_timestamp: float) -> List[Dict]:
        """
        Get events since a specific timestamp.
        
        Used for reconnection recovery to fetch missed events.
        
        Args:
            deployment_id: Unique deployment identifier
            since_timestamp: Unix timestamp to get events after
            
        Returns:
            List of event dictionaries
        """
        try:
            key = f"{self.EVENT_KEY_PREFIX}{deployment_id}"
            
            # Get events after timestamp
            events = self.redis_client.zrangebyscore(
                key,
                min=since_timestamp,
                max='+inf',
                withscores=False
            )
            
            return [json.loads(e) for e in events]
            
        except Exception as e:
            logger.error(f"Failed to get missed events for {deployment_id}: {e}")
            return []
    
    def get_recent_events(self, deployment_id: str, count: int = 50) -> List[Dict]:
        """
        Get most recent events for a deployment.
        
        Args:
            deployment_id: Unique deployment identifier
            count: Number of events to retrieve
            
        Returns:
            List of event dictionaries (most recent last)
        """
        try:
            key = f"{self.EVENT_KEY_PREFIX}{deployment_id}"
            
            # Get last N events
            events = self.redis_client.zrange(
                key,
                start=-count,
                end=-1,
                withscores=False
            )
            
            return [json.loads(e) for e in events]
            
        except Exception as e:
            logger.error(f"Failed to get recent events for {deployment_id}: {e}")
            return []
    
    def save_state(self, deployment_id: str, state: Dict):
        """
        Save deployment state for reconnection recovery.
        
        This is a snapshot of the complete deployment state,
        used when events are not sufficient for recovery.
        
        Args:
            deployment_id: Unique deployment identifier
            state: Complete state dictionary
        """
        try:
            key = f"{self.STATE_KEY_PREFIX}{deployment_id}"
            self.redis_client.setex(key, EVENT_TTL, json.dumps(state))
            logger.debug(f"Saved state for {deployment_id}")
        except Exception as e:
            logger.error(f"Failed to save state for {deployment_id}: {e}")
    
    def get_state(self, deployment_id: str) -> Optional[Dict]:
        """
        Get saved deployment state.
        
        Args:
            deployment_id: Unique deployment identifier
            
        Returns:
            State dictionary or None if not found
        """
        try:
            key = f"{self.STATE_KEY_PREFIX}{deployment_id}"
            state_json = self.redis_client.get(key)
            
            if state_json:
                return json.loads(state_json)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get state for {deployment_id}: {e}")
            return None
    
    def cleanup(self, deployment_id: str):
        """
        Clean up Redis data for a completed deployment.
        
        Args:
            deployment_id: Unique deployment identifier
        """
        try:
            # Delete event history
            event_key = f"{self.EVENT_KEY_PREFIX}{deployment_id}"
            self.redis_client.delete(event_key)
            
            # Delete state
            state_key = f"{self.STATE_KEY_PREFIX}{deployment_id}"
            self.redis_client.delete(state_key)
            
            # Clean up throttle state
            with self._lock:
                self._last_update.pop(deployment_id, None)
            
            logger.debug(f"Cleaned up progress data for {deployment_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup for {deployment_id}: {e}")


# Global progress manager instance
_progress_manager: Optional[ProgressManager] = None


def get_progress_manager(socketio=None) -> ProgressManager:
    """
    Get or create the global progress manager.
    
    Args:
        socketio: Flask-SocketIO instance (only needed on first call)
        
    Returns:
        ProgressManager instance
    """
    global _progress_manager
    if _progress_manager is None:
        _progress_manager = ProgressManager(socketio)
    elif socketio is not None:
        _progress_manager.socketio = socketio
    return _progress_manager