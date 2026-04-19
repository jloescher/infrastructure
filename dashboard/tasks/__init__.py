"""
Celery configuration for async deployment tasks.

This module configures Celery to use PostgreSQL as the message broker
and result backend, enabling async deployment processing with
real-time progress updates via WebSocket.

Phase 4 additions:
- SSL certificate auto-renewal tasks
- Database and service backup tasks
- System maintenance tasks
- Configuration drift detection
"""

import os
from celery import Celery
from celery.schedules import crontab

PG_HOST = os.environ.get('PG_HOST', '100.102.220.16')
PG_PORT = int(os.environ.get('PG_PORT', 5000))
PG_USER = os.environ.get('PG_USER', 'patroni_superuser')
PG_PASSWORD = os.environ.get('PG_PASSWORD', '2e7vBpaaVK4vTJzrKebC')
PG_DATABASE = os.environ.get('PG_DATABASE', 'celery')

BROKER_URL = f'db+postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}'
RESULT_BACKEND = f'db+postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}'

celery_app = Celery(
    'quantyra_paas',
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        'tasks.deploy',
        'tasks.scheduler',
        'tasks.ssl',
        'tasks.backup',
        'tasks.maintenance',
        'tasks.drift',
    ]
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
    # =============================================================================
    # Deployment Scheduling (Phase 2)
    # =============================================================================
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
    
    # =============================================================================
    # SSL Certificate Management (Phase 4)
    # =============================================================================
    'check-ssl-expiration': {
        'task': 'tasks.ssl.check_ssl_expiration',
        'schedule': crontab(hour='0,12', minute=0),  # Twice daily
    },
    
    # =============================================================================
    # Backup Management (Phase 4)
    # =============================================================================
    'backup-all-databases': {
        'task': 'tasks.backup.backup_all_databases',
        'schedule': crontab(hour='*/6', minute=0),  # Every 6 hours
    },
    'backup-all-services': {
        'task': 'tasks.backup.backup_all_services',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM UTC
    },
    'cleanup-old-backups': {
        'task': 'tasks.backup.cleanup_old_backups',
        'schedule': crontab(hour=4, minute=30),  # Daily at 4:30 AM UTC
        'kwargs': {'days': 30}
    },
    
    # =============================================================================
    # System Maintenance (Phase 4)
    # =============================================================================
    'cleanup-old-deployments': {
        'task': 'tasks.maintenance.cleanup_old_deployments',
        'schedule': crontab(hour=3, minute=30),  # Daily at 3:30 AM UTC
        'kwargs': {'days': 30}
    },
    'cleanup-old-logs': {
        'task': 'tasks.maintenance.cleanup_old_logs',
        'schedule': crontab(hour=5, minute=0),  # Daily at 5 AM UTC
        'kwargs': {'days': 7}
    },
    'cleanup-docker-resources': {
        'task': 'tasks.maintenance.cleanup_docker_resources',
        'schedule': crontab(day_of_week=0, hour=5, minute=30),  # Weekly on Sunday at 5:30 AM
    },
    'check-disk-space': {
        'task': 'tasks.maintenance.check_disk_space',
        'schedule': crontab(hour='*/6', minute=15),  # Every 6 hours at :15
    },
    'check-service-status': {
        'task': 'tasks.maintenance.check_service_status',
        'schedule': crontab(minute=30),  # Hourly at :30
    },
    
    # =============================================================================
    # Configuration Drift Detection (Phase 3)
    # =============================================================================
    'check-configuration-drift': {
        'task': 'tasks.drift.check_configuration_drift',
        'schedule': crontab(minute=30),  # Hourly at :30
    },
    'cleanup-old-drift-history': {
        'task': 'tasks.drift.cleanup_old_drift_history',
        'schedule': crontab(hour=6, minute=0),  # Daily at 6 AM UTC
        'kwargs': {'days': 30}
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