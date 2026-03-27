"""
WebSocket reconnection recovery module.

This module handles client reconnection scenarios:
- State synchronization for reconnecting clients
- Missed event replay
- Graceful degradation when events are unavailable
"""

import logging
import time
from typing import Dict, Optional, List
from flask_socketio import emit
from flask import request

logger = logging.getLogger(__name__)


def handle_reconnection(socket_id: str, deployment_id: str, last_event_id: str = None) -> Dict:
    """
    Handle client reconnection for a deployment room.
    
    When a client reconnects, this function:
    1. Retrieves current deployment state from SQLite
    2. Gets all steps from SQLite
    3. Calculates current progress
    4. Checks Redis for missed events
    5. Sends complete state as 'state_sync' event
    
    Args:
        socket_id: WebSocket socket ID
        deployment_id: Unique deployment identifier
        last_event_id: Last event ID received by client (optional)
        
    Returns:
        Dictionary with recovery status and state
    """
    try:
        # Import database functions
        import database as paas_db
        from .progress import get_progress_manager
        
        # Get deployment from database
        deployment = paas_db.get_deployment(deployment_id)
        
        if not deployment:
            logger.warning(f"Deployment {deployment_id} not found for reconnection")
            return {
                'status': 'not_found',
                'deployment_id': deployment_id
            }
        
        # Get all steps from database
        steps = paas_db.get_deployment_steps(deployment_id)
        
        # Get current progress
        progress = paas_db.get_deployment_progress(deployment_id)
        
        # Build state dictionary
        state = {
            'deployment': deployment,
            'steps': steps,
            'progress': progress,
            'recovered_at': time.time()
        }
        
        # Check for missed events if client provided last_event_id
        missed_events = []
        if last_event_id:
            try:
                # Parse last_event_id: "deployment_id:timestamp:sequence"
                parts = last_event_id.split(':')
                if len(parts) >= 2:
                    last_timestamp = float(parts[1]) / 1000  # Convert from ms
                    
                    progress_manager = get_progress_manager()
                    missed_events = progress_manager.get_missed_events(
                        deployment_id,
                        last_timestamp
                    )
                    
                    logger.info(f"Found {len(missed_events)} missed events for {deployment_id}")
                    
            except Exception as e:
                logger.warning(f"Could not parse last_event_id: {e}")
        
        # Save state to Redis for quick recovery
        progress_manager = get_progress_manager()
        progress_manager.save_state(deployment_id, state)
        
        return {
            'status': 'recovered',
            'deployment_id': deployment_id,
            'state': state,
            'missed_events': missed_events,
            'event_count': len(missed_events)
        }
        
    except Exception as e:
        logger.error(f"Reconnection recovery failed for {deployment_id}: {e}")
        return {
            'status': 'error',
            'deployment_id': deployment_id,
            'error': str(e)
        }


def emit_state_sync(deployment_id: str, socket_id: str = None, last_event_id: str = None):
    """
    Emit a state_sync event for a reconnecting client.
    
    This function is called when a client explicitly requests
    a state sync after reconnection.
    
    Args:
        deployment_id: Unique deployment identifier
        socket_id: Socket ID to emit to (optional, defaults to current)
        last_event_id: Last event ID received by client (optional)
    """
    try:
        # Get recovery data
        recovery = handle_reconnection(
            socket_id or request.sid,
            deployment_id,
            last_event_id
        )
        
        if recovery['status'] == 'not_found':
            emit('error', {
                'type': 'deployment_not_found',
                'deployment_id': deployment_id,
                'message': 'Deployment not found'
            })
            return
        
        # Emit state sync event
        emit('state_sync', {
            'type': 'state_sync',
            'deployment_id': deployment_id,
            'state': recovery['state'],
            'missed_events': recovery.get('missed_events', []),
            'timestamp': time.time()
        })
        
        logger.info(f"Emitted state_sync for {deployment_id}")
        
    except Exception as e:
        logger.error(f"Failed to emit state_sync for {deployment_id}: {e}")
        emit('error', {
            'type': 'recovery_failed',
            'deployment_id': deployment_id,
            'error': str(e)
        })


def get_deployment_state_for_display(deployment_id: str) -> Dict:
    """
    Get deployment state formatted for UI display.
    
    This function provides a simplified state view for the UI,
    including only essential information.
    
    Args:
        deployment_id: Unique deployment identifier
        
    Returns:
        Dictionary with deployment state for UI
    """
    try:
        import database as paas_db
        
        # Get deployment
        deployment = paas_db.get_deployment(deployment_id)
        if not deployment:
            return None
        
        # Get progress
        progress = paas_db.get_deployment_progress(deployment_id)
        
        # Get recent events
        from .progress import get_progress_manager
        progress_manager = get_progress_manager()
        recent_events = progress_manager.get_recent_events(deployment_id, count=10)
        
        # Format for display
        return {
            'deployment_id': deployment_id,
            'app_id': deployment['app_id'],
            'environment': deployment['environment'],
            'status': deployment['status'],
            'branch': deployment['branch'],
            'commit': deployment.get('commit'),
            'started_at': deployment['started_at'],
            'completed_at': deployment.get('completed_at'),
            'progress': progress,
            'recent_events': recent_events[-5:] if recent_events else []  # Last 5 events
        }
        
    except Exception as e:
        logger.error(f"Failed to get display state for {deployment_id}: {e}")
        return None


def check_deployment_active(deployment_id: str) -> bool:
    """
    Check if a deployment is still active (pending or running).
    
    Args:
        deployment_id: Unique deployment identifier
        
    Returns:
        True if deployment is active, False otherwise
    """
    try:
        import database as paas_db
        
        deployment = paas_db.get_deployment(deployment_id)
        if not deployment:
            return False
        
        return deployment['status'] in ('pending', 'running')
        
    except Exception as e:
        logger.error(f"Failed to check deployment status for {deployment_id}: {e}")
        return False


def get_active_deployments_for_client() -> List[Dict]:
    """
    Get all active deployments for the connected client.
    
    This is used when a client connects to see all in-progress
    deployments they might be interested in.
    
    Returns:
        List of active deployment states
    """
    try:
        import database as paas_db
        
        active_deployments = paas_db.get_active_deployments()
        
        states = []
        for deployment in active_deployments:
            state = get_deployment_state_for_display(deployment['id'])
            if state:
                states.append(state)
        
        return states
        
    except Exception as e:
        logger.error(f"Failed to get active deployments: {e}")
        return []


def register_recovery_handlers(socketio):
    """
    Register recovery-related WebSocket event handlers.
    
    Args:
        socketio: SocketIO instance
    """
    
    @socketio.on('request_state_sync')
    def handle_request_state_sync(data):
        """
        Handle client request for state sync.
        
        Expected data:
            {
                'deployment_id': 'uuid-string',
                'last_event_id': 'optional-last-event-id'
            }
        """
        deployment_id = data.get('deployment_id')
        last_event_id = data.get('last_event_id')
        
        if not deployment_id:
            emit('error', {'message': 'deployment_id required'})
            return
        
        logger.info(f"Client {request.sid} requested state sync for {deployment_id}")
        emit_state_sync(deployment_id, request.sid, last_event_id)
    
    @socketio.on('get_active_deployments')
    def handle_get_active_deployments():
        """
        Handle client request for all active deployments.
        
        Returns a list of currently active deployments.
        """
        active = get_active_deployments_for_client()
        emit('active_deployments', {
            'deployments': active,
            'count': len(active),
            'timestamp': time.time()
        })
    
    @socketio.on('check_deployment_status')
    def handle_check_deployment_status(data):
        """
        Check if a deployment is still active.
        
        Expected data:
            {
                'deployment_id': 'uuid-string'
            }
        """
        deployment_id = data.get('deployment_id')
        
        if not deployment_id:
            emit('error', {'message': 'deployment_id required'})
            return
        
        is_active = check_deployment_active(deployment_id)
        emit('deployment_status', {
            'deployment_id': deployment_id,
            'is_active': is_active,
            'timestamp': time.time()
        })


# Client-side recovery protocol
"""
Client-Side Implementation Guide
================================

For optimal reconnection recovery, clients should implement:

1. Event ID Tracking:
   - Store the last received event_id for each deployment
   - Send this in reconnection requests

2. Reconnection Flow:
   ```javascript
   socket.on('connect', () => {
       // If previously watching a deployment
       if (currentDeploymentId) {
           socket.emit('request_state_sync', {
               deployment_id: currentDeploymentId,
               last_event_id: lastEventId
           });
       }
   });
   ```

3. State Sync Handling:
   ```javascript
   socket.on('state_sync', (data) => {
       // Replace local state with server state
       updateDeploymentState(data.state);
       
       // Replay missed events
       if (data.missed_events && data.missed_events.length > 0) {
           data.missed_events.forEach(event => {
               handleProgressEvent(event);
           });
       }
   });
   ```

4. Progress Event Handling:
   ```javascript
   socket.on('deployment_progress', (event) => {
       // Store event_id for reconnection
       lastEventId = event.event_id;
       
       // Handle event by type
       switch (event.type) {
           case 'progress':
               updateProgressBar(event.progress);
               break;
           case 'step_start':
               showStepStarting(event.server, event.step);
               break;
           case 'step_complete':
               showStepComplete(event.server, event.step);
               break;
           case 'error':
               showError(event.error);
               break;
           case 'deployment_complete':
               showDeploymentComplete(event.success);
               break;
       }
   });
   ```

5. Batch Event Handling:
   ```javascript
   socket.on('deployment_progress_batch', (data) => {
       // Process all events in batch
       data.events.forEach(event => {
           lastEventId = event.event_id;
           handleProgressEvent(event);
       });
   });
   ```
"""