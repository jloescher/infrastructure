"""
Celery configuration for async deployment tasks.

This module configures Celery to use Redis as the message broker
and result backend, enabling async deployment processing with
real-time progress updates via WebSocket.
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_HOST = os.environ.get('REDIS_HOST', '100.126.103.51')
REDIS_PORT = int(os.environ.get('REDIS_PORT', 6379))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', 'CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk')

BROKER_URL = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/4'
RESULT_BACKEND = f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/5'

celery_app = Celery(
    'quantyra_paas',
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=['tasks.deploy', 'tasks.scheduler']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    broker_transport_options={
        'visibility_timeout': 3600,
        'max_connections': 10,
    },
    result_backend_transport_options={
        'retry_policy': {
            'timeout': 5.0,
        }
    },
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_queue='deployments',
)

# Celery Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    'process-scheduled-deployments': {
        'task': 'tasks.scheduler.process_scheduled_deployments',
        'schedule': crontab(minute='*/5'),  # Check every 5 minutes
    },
    'cleanup-old-scheduled-deployments': {
        'task': 'tasks.scheduler.cleanup_old_scheduled_deployments',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM UTC
    },
    'cleanup-old-deployment-steps': {
        'task': 'tasks.deploy.cleanup_old_deployments_task',
        'schedule': crontab(hour=4, minute=0),  # Daily at 4 AM UTC
    },
}


class TaskBase(celery_app.Task):
    """Base task class with progress tracking and error handling."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called when task succeeds."""
        pass
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails."""
        from websocket import emit_progress
        deployment_id = kwargs.get('deployment_id') or (args[0] if args else None)
        if deployment_id:
            emit_progress(deployment_id, 'deployment_failed', {
                'error': str(exc),
                'task_id': task_id
            })
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried."""
        from websocket import emit_progress
        deployment_id = kwargs.get('deployment_id') or (args[0] if args else None)
        if deployment_id:
            emit_progress(deployment_id, 'deployment_retry', {
                'error': str(exc),
                'task_id': task_id,
                'retry_count': self.request.retries
            })


celery_app.Task = TaskBase