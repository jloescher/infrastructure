"""
Deployment scheduling with Celery Beat.

Allows scheduling deployments for future execution.
Scheduled deployments are checked every 5 minutes.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app
from tasks.deploy import deploy_application_task
from websocket import emit_progress
import database as db


# Check interval in minutes
SCHEDULE_CHECK_INTERVAL = 5


@celery_app.task
def process_scheduled_deployments():
    """
    Check for and execute scheduled deployments.
    
    This task runs every 5 minutes (configured in Celery Beat).
    It queries for deployments with:
    - scheduled_at in the past
    - status = 'scheduled'
    
    For each found deployment, it:
    1. Updates status to 'pending'
    2. Triggers the actual deployment task
    """
    now = datetime.utcnow()
    
    # Find scheduled deployments that are due
    with db.get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name, a.framework
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.status = 'scheduled'
            AND d.scheduled_at IS NOT NULL
            AND datetime(d.scheduled_at) <= datetime(?)
            ORDER BY d.scheduled_at ASC
        ''', (now.isoformat(),)).fetchall()
        
        scheduled = [dict(row) for row in rows]
    
    if not scheduled:
        return {'processed': 0, 'message': 'No scheduled deployments due'}
    
    results = {
        'processed': 0,
        'triggered': 0,
        'failed': 0,
        'deployments': []
    }
    
    for deployment in scheduled:
        deployment_id = deployment['id']
        app_name = deployment['app_name']
        environment = deployment['environment']
        branch = deployment['branch']
        commit = deployment.get('commit')
        
        try:
            # Update status to pending
            db.update_deployment(deployment_id, {
                'status': 'pending',
                'logs': f"[{now.isoformat()}] Scheduled deployment triggered\n"
            })
            
            # Trigger the deployment task
            deploy_application_task.delay(
                deployment_id=deployment_id,
                app_name=app_name,
                environment=environment,
                branch=branch,
                commit=commit
            )
            
            # Emit WebSocket event
            emit_progress(deployment_id, 'scheduled_deployment_triggered', {
                'app_name': app_name,
                'environment': environment,
                'branch': branch,
                'scheduled_at': deployment['scheduled_at'],
                'triggered_at': now.isoformat()
            })
            
            results['triggered'] += 1
            results['deployments'].append({
                'deployment_id': deployment_id,
                'app_name': app_name,
                'environment': environment,
                'status': 'triggered'
            })
            
        except Exception as e:
            # Mark deployment as failed
            db.update_deployment(deployment_id, {
                'status': 'failed',
                'results_json': json.dumps({'error': str(e)}),
                'finished_at': now.isoformat()
            })
            
            results['failed'] += 1
            results['deployments'].append({
                'deployment_id': deployment_id,
                'app_name': app_name,
                'environment': environment,
                'status': 'failed',
                'error': str(e)
            })
        
        results['processed'] += 1
    
    return results


@celery_app.task
def schedule_deployment(app_id: str, environment: str, branch: str,
                        scheduled_at: datetime, commit: str = None,
                        created_by: str = None) -> Dict[str, Any]:
    """
    Schedule a deployment for future execution.
    
    Args:
        app_id: Application ID
        environment: 'production' or 'staging'
        branch: Git branch to deploy
        scheduled_at: When to run the deployment
        commit: Optional specific commit
        created_by: User who scheduled (optional)
        
    Returns:
        Dict with 'success', 'deployment_id', and 'scheduled_at'
    """
    # Validate app exists
    app = db.get_application(app_id=app_id)
    if not app:
        return {'success': False, 'error': f'Application {app_id} not found'}
    
    # Validate scheduled time is in the future
    now = datetime.utcnow()
    if scheduled_at <= now:
        return {
            'success': False,
            'error': 'Scheduled time must be in the future'
        }
    
    # Create deployment record with scheduled status
    deployment_id = db.generate_id()
    
    with db.get_db() as conn:
        conn.execute('''
            INSERT INTO deployments 
            (id, app_id, environment, branch, commit, status, 
             scheduled_at, is_scheduled, deployed_at)
            VALUES (?, ?, ?, ?, ?, 'scheduled', ?, 1, ?)
        ''', (
            deployment_id,
            app_id,
            environment,
            branch,
            commit,
            scheduled_at.isoformat(),
            now.isoformat()
        ))
        conn.commit()
    
    # Emit WebSocket event
    emit_progress(deployment_id, 'deployment_scheduled', {
        'app_name': app['name'],
        'environment': environment,
        'branch': branch,
        'commit': commit,
        'scheduled_at': scheduled_at.isoformat(),
        'created_by': created_by
    })
    
    return {
        'success': True,
        'deployment_id': deployment_id,
        'scheduled_at': scheduled_at.isoformat(),
        'message': f"Deployment scheduled for {scheduled_at.isoformat()}"
    }


@celery_app.task
def cancel_scheduled_deployment(deployment_id: str) -> Dict[str, Any]:
    """
    Cancel a scheduled deployment.
    
    Args:
        deployment_id: Deployment ID to cancel
        
    Returns:
        Dict with 'success' and message
    """
    with db.get_db() as conn:
        row = conn.execute(
            'SELECT * FROM deployments WHERE id = ? AND status = ?',
            (deployment_id, 'scheduled')
        ).fetchone()
        
        if not row:
            return {
                'success': False,
                'error': 'Deployment not found or not in scheduled status'
            }
        
        deployment = dict(row)
        
        # Update status to cancelled
        conn.execute('''
            UPDATE deployments 
            SET status = 'cancelled', finished_at = ?
            WHERE id = ?
        ''', (datetime.utcnow().isoformat(), deployment_id))
        conn.commit()
    
    # Emit WebSocket event
    emit_progress(deployment_id, 'scheduled_deployment_cancelled', {
        'deployment_id': deployment_id,
        'cancelled_at': datetime.utcnow().isoformat()
    })
    
    return {
        'success': True,
        'message': 'Scheduled deployment cancelled'
    }


@celery_app.task
def get_upcoming_scheduled_deployments(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get deployments scheduled in the next N hours.
    
    Args:
        hours: Number of hours to look ahead
        
    Returns:
        List of scheduled deployments
    """
    now = datetime.utcnow()
    cutoff = now + timedelta(hours=hours)
    
    with db.get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.status = 'scheduled'
            AND d.scheduled_at IS NOT NULL
            AND datetime(d.scheduled_at) BETWEEN datetime(?) AND datetime(?)
            ORDER BY d.scheduled_at ASC
        ''', (now.isoformat(), cutoff.isoformat())).fetchall()
        
        return [dict(row) for row in rows]


@celery_app.task
def cleanup_old_scheduled_deployments(days: int = 7) -> Dict[str, Any]:
    """
    Clean up old cancelled scheduled deployments.
    
    Args:
        days: Delete deployments older than this many days
        
    Returns:
        Dict with count of deleted deployments
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    with db.get_db() as conn:
        cursor = conn.execute('''
            DELETE FROM deployments 
            WHERE status = 'cancelled'
            AND is_scheduled = 1
            AND datetime(deployed_at) < datetime(?)
        ''', (cutoff.isoformat(),))
        
        deleted = cursor.rowcount
        conn.commit()
    
    return {
        'success': True,
        'deleted_count': deleted,
        'message': f'Removed {deleted} old cancelled scheduled deployments'
    }


def reschedule_deployment(deployment_id: str, new_scheduled_at: datetime) -> Dict[str, Any]:
    """
    Reschedule a scheduled deployment to a new time.
    
    Args:
        deployment_id: Deployment ID
        new_scheduled_at: New scheduled time
        
    Returns:
        Dict with 'success' and updated info
    """
    now = datetime.utcnow()
    
    if new_scheduled_at <= now:
        return {
            'success': False,
            'error': 'New scheduled time must be in the future'
        }
    
    with db.get_db() as conn:
        row = conn.execute(
            'SELECT * FROM deployments WHERE id = ? AND status = ?',
            (deployment_id, 'scheduled')
        ).fetchone()
        
        if not row:
            return {
                'success': False,
                'error': 'Deployment not found or not in scheduled status'
            }
        
        conn.execute('''
            UPDATE deployments 
            SET scheduled_at = ?
            WHERE id = ?
        ''', (new_scheduled_at.isoformat(), deployment_id))
        conn.commit()
    
    # Emit WebSocket event
    emit_progress(deployment_id, 'scheduled_deployment_rescheduled', {
        'deployment_id': deployment_id,
        'new_scheduled_at': new_scheduled_at.isoformat()
    })
    
    return {
        'success': True,
        'deployment_id': deployment_id,
        'new_scheduled_at': new_scheduled_at.isoformat()
    }