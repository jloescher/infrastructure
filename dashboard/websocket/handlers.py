"""
WebSocket event handlers for deployment progress.

This module defines handlers for client connection, disconnection,
and room management for deployment progress streaming.
"""

from flask_socketio import join_room, leave_room, emit
from flask import request
import logging

logger = logging.getLogger(__name__)


def register_handlers(socketio):
    """
    Register all WebSocket event handlers.
    
    Args:
        socketio: SocketIO instance
    """
    
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection."""
        logger.info(f"Client connected: {request.sid}")
        emit('connected', {'status': 'ok', 'sid': request.sid})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection."""
        logger.info(f"Client disconnected: {request.sid}")
    
    @socketio.on('join_deployment')
    def handle_join_deployment(data):
        """
        Join a deployment room to receive progress updates.
        
        Clients call this after initiating a deployment to receive
        real-time progress events.
        
        Expected data:
            {
                'deployment_id': 'uuid-string'
            }
        """
        deployment_id = data.get('deployment_id')
        
        if not deployment_id:
            emit('error', {'message': 'deployment_id required'})
            return
        
        room = f"deployment:{deployment_id}"
        join_room(room)
        
        logger.info(f"Client {request.sid} joined deployment room: {deployment_id}")
        emit('joined', {'deployment_id': deployment_id, 'room': room})
        
        # Try to send any existing progress from the database
        try:
            import database as paas_db
            progress = paas_db.get_deployment_progress(deployment_id)
            if progress:
                emit('deployment_progress', {
                    'type': 'progress_recovery',
                    'deployment_id': deployment_id,
                    'progress': progress
                })
        except Exception as e:
            logger.warning(f"Could not recover progress for {deployment_id}: {e}")
    
    @socketio.on('leave_deployment')
    def handle_leave_deployment(data):
        """
        Leave a deployment room.
        
        Expected data:
            {
                'deployment_id': 'uuid-string'
            }
        """
        deployment_id = data.get('deployment_id')
        
        if not deployment_id:
            return
        
        room = f"deployment:{deployment_id}"
        leave_room(room)
        
        logger.info(f"Client {request.sid} left deployment room: {deployment_id}")
    
    @socketio.on('ping')
    def handle_ping():
        """Handle ping for connection keepalive."""
        emit('pong', {'timestamp': __import__('time').time()})
    
    @socketio.on_error_default
    def default_error_handler(e):
        """Handle any WebSocket errors."""
        logger.error(f"WebSocket error: {e}")
        emit('error', {'message': str(e)})