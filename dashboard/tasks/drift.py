"""
Celery tasks for drift detection.

Scheduled tasks:
- check_configuration_drift: Check all servers for drift
- cleanup_old_drift_history: Remove old history records
"""

import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app
from services.drift.reporter import DriftReporter
from services.drift.detector import check_all_servers
import database as db


@celery_app.task
def check_configuration_drift() -> dict:
    """
    Check all servers for configuration drift.
    
    This task runs hourly (configured in Celery Beat).
    It:
    1. Connects to each server via SSH
    2. Reads actual configuration values
    3. Compares against expected baselines
    4. Stores results in database
    5. Sends alerts for critical drift
    
    Returns:
        Dictionary with check results
    """
    reporter = DriftReporter()
    
    try:
        results = reporter.check_all_servers()
        
        # Log results
        print(f"[{datetime.utcnow().isoformat()}] Drift check complete:")
        print(f"  - Total drifts: {results['total_drifts']}")
        print(f"  - Critical: {results['critical']}")
        print(f"  - Warning: {results['warning']}")
        print(f"  - Info: {results['info']}")
        print(f"  - Servers checked: {results['servers_checked']}")
        
        if results.get('errors'):
            print(f"  - Errors: {len(results['errors'])}")
        
        return {
            'success': True,
            'total_drifts': results['total_drifts'],
            'critical': results['critical'],
            'warning': results['warning'],
            'checked_at': results['checked_at']
        }
        
    except Exception as e:
        print(f"[{datetime.utcnow().isoformat()}] Drift check failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'checked_at': datetime.utcnow().isoformat()
        }


@celery_app.task
def cleanup_old_drift_history(days: int = 30) -> dict:
    """
    Clean up old drift history records.
    
    Args:
        days: Delete records older than this many days
        
    Returns:
        Dictionary with cleanup results
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    with db.get_db() as conn:
        cursor = conn.execute('''
            DELETE FROM drift_history 
            WHERE checked_at < ?
        ''', (cutoff.isoformat(),))
        
        deleted = cursor.rowcount
        conn.commit()
    
    return {
        'success': True,
        'deleted_count': deleted,
        'message': f'Removed {deleted} drift history records older than {days} days'
    }


@celery_app.task
def get_drift_summary() -> dict:
    """
    Get current drift summary.
    
    Returns:
        Dictionary with drift summary
    """
    reporter = DriftReporter()
    return reporter.get_drift_summary()


@celery_app.task
def check_specific_server(server_name: str) -> dict:
    """
    Check a specific server for drift.
    
    Args:
        server_name: Server name to check
        
    Returns:
        Dictionary with check results
    """
    from services.drift.detector import check_drift_for_server
    
    try:
        results = check_drift_for_server(server_name)
        
        return {
            'success': True,
            'server': server_name,
            'drifts': [r.to_dict() for r in results],
            'count': len(results),
            'checked_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'success': False,
            'server': server_name,
            'error': str(e),
            'checked_at': datetime.utcnow().isoformat()
        }


# Register with Celery Beat
# This would be in the Celery config, but defining here for reference
CELERYBEAT_SCHEDULE = {
    'check-configuration-drift': {
        'task': 'tasks.drift.check_configuration_drift',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-drift-history': {
        'task': 'tasks.drift.cleanup_old_drift_history',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days': 30}
    }
}