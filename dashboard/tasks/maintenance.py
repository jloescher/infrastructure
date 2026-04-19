"""
System maintenance tasks.

Phase 4 automation for:
- Old deployment cleanup
- Log rotation and cleanup
- Docker resource cleanup
- Disk space monitoring
- Temporary file cleanup
"""

import os
import sys
import subprocess
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app
import database as db

# Cleanup thresholds
DEPLOYMENT_RETENTION_DAYS = 30
LOG_RETENTION_DAYS = 7
TEMP_FILE_RETENTION_DAYS = 1

# Disk space thresholds
DISK_WARNING_THRESHOLD = 85  # Percent
DISK_CRITICAL_THRESHOLD = 95  # Percent


@celery_app.task
def cleanup_old_deployments(days: int = DEPLOYMENT_RETENTION_DAYS) -> Dict:
    """
    Clean up old deployment records and logs.
    
    Args:
        days: Delete deployments older than this many days
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'deployments_removed': 0,
        'steps_removed': 0,
        'hooks_removed': 0,
        'started_at': datetime.utcnow().isoformat()
    }
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    try:
        with db.get_db() as conn:
            # Get deployments to delete
            rows = conn.execute('''
                SELECT id FROM deployments
                WHERE status IN ('success', 'failed', 'cancelled')
                AND datetime(finished_at) < datetime(?)
            ''', (cutoff.isoformat(),)).fetchall()
            
            deployment_ids = [row['id'] for row in rows]
            results['deployments_removed'] = len(deployment_ids)
            
            if deployment_ids:
                # Remove deployment steps
                placeholders = ','.join('?' * len(deployment_ids))
                cursor = conn.execute(f'''
                    DELETE FROM deployment_steps
                    WHERE deployment_id IN ({placeholders})
                ''', deployment_ids)
                results['steps_removed'] = cursor.rowcount
                
                # Remove hook executions
                cursor = conn.execute(f'''
                    DELETE FROM hook_executions
                    WHERE deployment_id IN ({placeholders})
                ''', deployment_ids)
                results['hooks_removed'] = cursor.rowcount
                
                # Remove deployments
                conn.execute(f'''
                    DELETE FROM deployments
                    WHERE id IN ({placeholders})
                ''', deployment_ids)
            
            conn.commit()
        
        results['success'] = True
        results['finished_at'] = datetime.utcnow().isoformat()
        
        print(f"[{datetime.utcnow().isoformat()}] Deployment cleanup complete: "
              f"removed={results['deployments_removed']} deployments, "
              f"{results['steps_removed']} steps, {results['hooks_removed']} hooks")
        
        return results
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
        results['finished_at'] = datetime.utcnow().isoformat()
        return results


@celery_app.task
def cleanup_old_logs(days: int = LOG_RETENTION_DAYS) -> Dict:
    """
    Clean up old log files on all servers.
    
    Args:
        days: Delete logs older than this many days
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'logs_removed': 0,
        'space_freed': 0,
        'servers': {},
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Log directories to clean
    log_dirs = [
        '/var/log/haproxy',
        '/var/log/postgresql',
        '/var/log/redis',
        '/var/log/supervisor',
    ]
    
    # Get all servers
    servers = db.list_servers()
    
    for server in servers:
        server_name = server['name']
        server_ip = server['ip']
        
        server_result = {
            'logs_removed': 0,
            'space_freed': 0,
            'errors': []
        }
        
        for log_dir in log_dirs:
            try:
                # Find and remove old log files
                cmd = (
                    f"ssh root@{server_ip} "
                    f"'find {log_dir} -name \"*.log.*\" -mtime +{days} "
                    f"-type f -exec rm -v {{}} \\; 2>/dev/null || true'"
                )
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                
                if result.stdout:
                    # Count removed files
                    removed_files = result.stdout.strip().split('\n')
                    removed_count = len([f for f in removed_files if f])
                    server_result['logs_removed'] += removed_count
                    
            except subprocess.TimeoutExpired:
                server_result['errors'].append(f"Timeout cleaning {log_dir}")
            except Exception as e:
                server_result['errors'].append(str(e))
        
        results['servers'][server_name] = server_result
        results['logs_removed'] += server_result['logs_removed']
    
    # Send alert if errors
    if any(s['errors'] for s in results['servers'].values()):
        send_maintenance_alert('log_cleanup', results)
    
    results['success'] = True
    results['finished_at'] = datetime.utcnow().isoformat()
    
    print(f"[{datetime.utcnow().isoformat()}] Log cleanup complete: "
          f"removed={results['logs_removed']} logs across {len(results['servers'])} servers")
    
    return results


@celery_app.task
def cleanup_docker_resources() -> Dict:
    """
    Clean up unused Docker resources.
    
    Runs on servers that might have Docker installed.
    
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'images_removed': 0,
        'containers_removed': 0,
        'volumes_removed': 0,
        'space_freed': 0,
        'servers': {},
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Servers that may have Docker
    docker_servers = [
        ('router-01', '100.102.220.16'),
        ('router-02', '100.116.175.9'),
        ('re-db', '100.92.26.38'),
        ('re-node-02', '100.89.130.19'),
    ]
    
    for server_name, server_ip in docker_servers:
        server_result = {
            'images_removed': 0,
            'containers_removed': 0,
            'volumes_removed': 0,
            'space_freed': 0
        }
        
        try:
            # Check if Docker is installed
            check_cmd = f"ssh root@{server_ip} 'which docker'"
            check_result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True, timeout=10)
            
            if check_result.returncode != 0:
                # Docker not installed, skip
                results['servers'][server_name] = {'skipped': True, 'reason': 'Docker not installed'}
                continue
            
            # Remove dangling images
            cmd = f"ssh root@{server_ip} 'docker image prune -f 2>/dev/null'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if 'Deleted' in result.stdout:
                server_result['images_removed'] = result.stdout.count('Deleted')
            
            # Remove stopped containers
            cmd = f"ssh root@{server_ip} 'docker container prune -f 2>/dev/null'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if 'Deleted' in result.stdout:
                server_result['containers_removed'] = result.stdout.count('Deleted')
            
            # Remove unused volumes (be careful with this)
            cmd = f"ssh root@{server_ip} 'docker volume prune -f 2>/dev/null'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
            if 'Deleted' in result.stdout:
                server_result['volumes_removed'] = result.stdout.count('Deleted')
            
            # Get space freed
            cmd = f"ssh root@{server_ip} 'docker system df --format \"{{{{.Size}}}}\" 2>/dev/null'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            # Parse reclaimable space (simplified)
            
            results['servers'][server_name] = server_result
            results['images_removed'] += server_result['images_removed']
            results['containers_removed'] += server_result['containers_removed']
            results['volumes_removed'] += server_result['volumes_removed']
            
        except subprocess.TimeoutExpired:
            results['servers'][server_name] = {'error': 'Timeout'}
        except Exception as e:
            results['servers'][server_name] = {'error': str(e)}
    
    results['success'] = True
    results['finished_at'] = datetime.utcnow().isoformat()
    
    print(f"[{datetime.utcnow().isoformat()}] Docker cleanup complete: "
          f"images={results['images_removed']}, containers={results['containers_removed']}, "
          f"volumes={results['volumes_removed']}")
    
    return results


@celery_app.task
def cleanup_temp_files() -> Dict:
    """
    Clean up temporary files on all servers.
    
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'files_removed': 0,
        'servers': {},
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Temp patterns to clean
    temp_patterns = [
        '/tmp/*.tmp',
        '/tmp/*.temp',
        '/var/tmp/*.tmp',
        '/var/tmp/*.temp',
    ]
    
    # Get all servers
    servers = db.list_servers()
    
    for server in servers:
        server_name = server['name']
        server_ip = server['ip']
        
        server_result = {'files_removed': 0}
        
        for pattern in temp_patterns:
            try:
                # Remove files matching pattern older than 1 day
                cmd = (
                    f"ssh root@{server_ip} "
                    f"'find {os.path.dirname(pattern)} -name \"{os.path.basename(pattern)}\" "
                    f"-mtime +{TEMP_FILE_RETENTION_DAYS} -type f -delete -print 2>/dev/null || true'"
                )
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
                
                if result.stdout.strip():
                    removed = len(result.stdout.strip().split('\n'))
                    server_result['files_removed'] += removed
                    
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
        
        results['servers'][server_name] = server_result
        results['files_removed'] += server_result['files_removed']
    
    results['success'] = True
    results['finished_at'] = datetime.utcnow().isoformat()
    
    return results


@celery_app.task
def rotate_logs() -> Dict:
    """
    Rotate log files on all servers.
    
    Returns:
        Dictionary with rotation results
    """
    results = {
        'servers': {},
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Get all servers
    servers = db.list_servers()
    
    for server in servers:
        server_name = server['name']
        server_ip = server['ip']
        
        try:
            # Run logrotate
            cmd = f"ssh root@{server_ip} 'logrotate /etc/logrotate.conf 2>/dev/null || true'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            results['servers'][server_name] = {
                'success': True,
                'output': result.stdout[:500] if result.stdout else None
            }
            
        except subprocess.TimeoutExpired:
            results['servers'][server_name] = {'success': False, 'error': 'Timeout'}
            results['errors'].append(f"{server_name}: Timeout")
        except Exception as e:
            results['servers'][server_name] = {'success': False, 'error': str(e)}
            results['errors'].append(f"{server_name}: {str(e)}")
    
    results['success'] = len(results['errors']) == 0
    results['finished_at'] = datetime.utcnow().isoformat()
    
    return results


@celery_app.task
def check_disk_space() -> Dict:
    """
    Check disk space on all servers and alert if low.
    
    Returns:
        Dictionary with disk space check results
    """
    results = {
        'servers': {},
        'warnings': [],
        'critical': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Get all servers
    servers = db.list_servers()
    
    for server in servers:
        server_name = server['name']
        server_ip = server['ip']
        
        try:
            # Get disk usage
            cmd = f"ssh root@{server_ip} 'df -h / | tail -1'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Parse df output
                # Format: Filesystem Size Used Avail Use% Mounted on
                parts = result.stdout.strip().split()
                if len(parts) >= 5:
                    usage_percent = int(parts[4].replace('%', ''))
                    
                    server_info = {
                        'filesystem': parts[0],
                        'size': parts[1],
                        'used': parts[2],
                        'available': parts[3],
                        'usage_percent': usage_percent,
                        'status': 'ok'
                    }
                    
                    if usage_percent >= DISK_CRITICAL_THRESHOLD:
                        server_info['status'] = 'critical'
                        results['critical'].append({
                            'server': server_name,
                            'usage': usage_percent
                        })
                    elif usage_percent >= DISK_WARNING_THRESHOLD:
                        server_info['status'] = 'warning'
                        results['warnings'].append({
                            'server': server_name,
                            'usage': usage_percent
                        })
                    
                    results['servers'][server_name] = server_info
                    
        except subprocess.TimeoutExpired:
            results['servers'][server_name] = {'error': 'Timeout'}
        except Exception as e:
            results['servers'][server_name] = {'error': str(e)}
    
    # Send alerts if needed
    if results['critical']:
        send_disk_alert(results, 'critical')
    elif results['warnings']:
        send_disk_alert(results, 'warning')
    
    results['success'] = True
    results['finished_at'] = datetime.utcnow().isoformat()
    
    return results


@celery_app.task
def check_service_status() -> Dict:
    """
    Check status of critical services on all servers.
    
    Returns:
        Dictionary with service status results
    """
    results = {
        'servers': {},
        'issues': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Services to check by server role
    services_by_role = {
        'app': ['docker'],
        'database': ['patroni', 'etcd', 'redis-server'],
        'router': ['haproxy', 'prometheus', 'grafana-server'],
        'monitoring': ['prometheus', 'grafana-server', 'alertmanager']
    }
    
    # Get all servers
    servers = db.list_servers()
    
    for server in servers:
        server_name = server['name']
        server_ip = server['ip']
        server_role = server.get('role', 'app')
        
        services_to_check = services_by_role.get(server_role, [])
        server_result = {'services': {}, 'issues': []}
        
        for service in services_to_check:
            try:
                cmd = f"ssh root@{server_ip} 'systemctl is-active {service} 2>/dev/null'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                
                status = result.stdout.strip()
                is_active = status == 'active'
                
                server_result['services'][service] = {
                    'status': status,
                    'active': is_active
                }
                
                if not is_active:
                    server_result['issues'].append(service)
                    results['issues'].append({
                        'server': server_name,
                        'service': service,
                        'status': status
                    })
                    
            except subprocess.TimeoutExpired:
                server_result['services'][service] = {'status': 'timeout', 'active': False}
                server_result['issues'].append(service)
            except Exception as e:
                server_result['services'][service] = {'status': 'error', 'error': str(e)}
        
        results['servers'][server_name] = server_result
    
    # Send alert if issues
    if results['issues']:
        send_service_alert(results)
    
    results['success'] = True
    results['finished_at'] = datetime.utcnow().isoformat()
    
    return results


@celery_app.task
def run_all_maintenance() -> Dict:
    """
    Run all maintenance tasks.
    
    Returns:
        Dictionary with all maintenance results
    """
    results = {
        'started_at': datetime.utcnow().isoformat(),
        'tasks': {}
    }
    
    # Run maintenance tasks sequentially
    results['tasks']['deployments'] = cleanup_old_deployments()
    results['tasks']['logs'] = cleanup_old_logs()
    results['tasks']['docker'] = cleanup_docker_resources()
    results['tasks']['temp'] = cleanup_temp_files()
    results['tasks']['disk'] = check_disk_space()
    results['tasks']['services'] = check_service_status()
    
    results['success'] = all(
        t.get('success', False) for t in results['tasks'].values()
    )
    results['finished_at'] = datetime.utcnow().isoformat()
    
    return results


# =============================================================================
# Helper Functions
# =============================================================================

def send_maintenance_alert(task_type: str, results: Dict) -> None:
    """
    Send maintenance alert notification.
    
    Args:
        task_type: Type of maintenance task
        results: Task results dictionary
    """
    from services.notifications import NotificationService
    
    message = f"""
⚠️ Maintenance Alert - {task_type}

Task: {task_type}
Status: {'Success' if results.get('success') else 'Failed'}

Details:
{json.dumps(results, indent=2, default=str)[:500]}
"""
    
    NotificationService._send_notifications({
        'title': f'⚠️ Maintenance Alert: {task_type}',
        'task_type': task_type,
        'results': results,
        'timestamp': datetime.utcnow().isoformat()
    }, f'maintenance_{task_type}')


def send_disk_alert(results: Dict, severity: str) -> None:
    """
    Send disk space alert.
    
    Args:
        results: Check results dictionary
        severity: Alert severity (warning, critical)
    """
    from services.notifications import NotificationService
    
    emoji = '🚨' if severity == 'critical' else '⚠️'
    
    issues = results['critical'] if severity == 'critical' else results['warnings']
    
    message = f"""
{emoji} Low Disk Space Alert - {severity.upper()}

{chr(10).join(f"  {s['server']}: {s['usage']}% used" for s in issues)}

Action required: Please clean up old files or expand storage.
"""
    
    NotificationService._send_notifications({
        'title': f'{emoji} Disk Space Alert',
        'severity': severity,
        'issues': issues,
        'timestamp': datetime.utcnow().isoformat()
    }, f'disk_{severity}')


def send_service_alert(results: Dict) -> None:
    """
    Send service status alert.
    
    Args:
        results: Service check results dictionary
    """
    from services.notifications import NotificationService
    
    message = f"""
🚨 Service Status Alert

Services down:
{chr(10).join(f"  - {i['server']}: {i['service']} ({i['status']})" for i in results['issues'])}

Action required: Check and restart affected services.
"""
    
    NotificationService._send_notifications({
        'title': '🚨 Service Status Alert',
        'issues': results['issues'],
        'timestamp': datetime.utcnow().isoformat()
    }, 'service_down')


# Register with Celery Beat
CELERYBEAT_SCHEDULE = {
    'cleanup-old-deployments': {
        'task': 'tasks.maintenance.cleanup_old_deployments',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days': DEPLOYMENT_RETENTION_DAYS}
    },
    'cleanup-old-logs': {
        'task': 'tasks.maintenance.cleanup_old_logs',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days': LOG_RETENTION_DAYS}
    },
    'cleanup-docker-resources': {
        'task': 'tasks.maintenance.cleanup_docker_resources',
        'schedule': 604800.0,  # Weekly
    },
    'check-disk-space': {
        'task': 'tasks.maintenance.check_disk_space',
        'schedule': 21600.0,  # Every 6 hours
    },
    'check-service-status': {
        'task': 'tasks.maintenance.check_service_status',
        'schedule': 3600.0,  # Hourly
    },
    'run-all-maintenance': {
        'task': 'tasks.maintenance.run_all_maintenance',
        'schedule': 86400.0,  # Daily at specified time
    }
}
