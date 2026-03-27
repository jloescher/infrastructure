"""
Automated backup tasks.

Phase 4 automation for:
- Database backup scheduling (hourly, daily, weekly)
- Add-on service backups
- Backup cleanup and retention management
- Backup status tracking and alerts
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

# PostgreSQL connection info
PG_HOST = os.environ.get('PG_HOST', '100.102.220.16')
PG_PORT = int(os.environ.get('PG_PORT', 5000))
PG_USER = os.environ.get('PG_USER', 'patroni_superuser')
PG_PASSWORD = os.environ.get('PG_PASSWORD', '2e7vBpaaVK4vTJzrKebC')

# Backup directory
BACKUP_BASE_DIR = os.environ.get('BACKUP_DIR', '/var/backups')

# Default retention days
DEFAULT_RETENTION_DAYS = 30


@celery_app.task
def backup_all_databases() -> Dict:
    """
    Backup all databases according to their backup schedule.
    
    This task runs every 6 hours (configured in Celery Beat).
    It:
    1. Gets all databases with backup enabled
    2. Checks if backup is needed based on schedule
    3. Creates backups for databases due
    4. Records backup status in database
    5. Sends alerts for failures
    
    Returns:
        Dictionary with backup results
    """
    results = {
        'backed_up': 0,
        'skipped': 0,
        'failed': 0,
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    try:
        # Ensure backup tables exist
        init_backup_schema()
        
        # Get all databases
        databases = get_all_databases()
        
        for db_info in databases:
            db_name = db_info['name']
            
            # Check if backup is enabled
            if not db_info.get('backup_enabled', True):
                results['skipped'] += 1
                continue
            
            # Check if backup is needed based on schedule
            if not should_backup(db_info):
                results['skipped'] += 1
                continue
            
            try:
                backup_result = backup_database(db_name, db_info)
                
                if backup_result['success']:
                    results['backed_up'] += 1
                    
                    # Record backup
                    record_database_backup(db_info['id'], backup_result)
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'database': db_name,
                        'error': backup_result.get('error', 'Unknown error'),
                        'type': 'backup_failed'
                    })
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'database': db_name,
                    'error': str(e),
                    'type': 'backup_exception'
                })
        
        # Send alert if failures
        if results['failed'] > 0:
            send_backup_alert(results, 'database_backup_failed')
        
        results['success'] = True
        results['finished_at'] = datetime.utcnow().isoformat()
        
        print(f"[{datetime.utcnow().isoformat()}] Database backup complete: "
              f"backed_up={results['backed_up']}, skipped={results['skipped']}, "
              f"failed={results['failed']}")
        
        return results
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
        results['finished_at'] = datetime.utcnow().isoformat()
        return results


@celery_app.task
def backup_database(db_name: str, db_info: Dict = None) -> Dict:
    """
    Backup a single database.
    
    Args:
        db_name: Database name to backup
        db_info: Optional database info dictionary
        
    Returns:
        Dictionary with backup result
    """
    if db_info is None:
        db_info = get_database_by_name(db_name)
    
    backup_dir = os.path.join(BACKUP_BASE_DIR, 'postgresql', db_name)
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(backup_dir, f'{timestamp}.sql.gz')
    
    try:
        # Create pg_dump via SSH to PG host
        cmd = (
            f"ssh root@{PG_HOST} "
            f"'PGPASSWORD={PG_PASSWORD} pg_dump -h localhost -p {PG_PORT} "
            f"-U {PG_USER} {db_name} | gzip' > {backup_path}"
        )
        
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=1800  # 30 minute timeout
        )
        
        if result.returncode == 0:
            # Get backup size
            backup_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
            
            return {
                'success': True,
                'database': db_name,
                'backup_path': backup_path,
                'backup_size': backup_size,
                'backup_size_human': format_size(backup_size),
                'backed_up_at': datetime.utcnow().isoformat()
            }
        else:
            return {
                'success': False,
                'database': db_name,
                'error': result.stderr or result.stdout or 'Unknown pg_dump error'
            }
            
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'database': db_name,
            'error': 'Backup timeout (30 minutes exceeded)'
        }
    except Exception as e:
        return {
            'success': False,
            'database': db_name,
            'error': str(e)
        }


@celery_app.task
def backup_all_services() -> Dict:
    """
    Backup all add-on services (Redis, etc.).
    
    Returns:
        Dictionary with backup results
    """
    results = {
        'backed_up': 0,
        'skipped': 0,
        'failed': 0,
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    try:
        # Get all services
        services = db.get_all_services()
        
        for service in services:
            service_id = service['id']
            service_type = service['type']
            
            # Check if backup is enabled
            if not should_backup_service(service):
                results['skipped'] += 1
                continue
            
            try:
                backup_result = backup_service(service)
                
                if backup_result['success']:
                    results['backed_up'] += 1
                    
                    # Record backup
                    db.record_service_backup({
                        'service_id': service_id,
                        'timestamp': datetime.utcnow().isoformat(),
                        'backup_path': backup_result.get('backup_path'),
                        'success': True
                    })
                else:
                    results['failed'] += 1
                    results['errors'].append({
                        'service': f"{service_type} ({service.get('app_name', 'unknown')})",
                        'error': backup_result.get('error', 'Unknown error'),
                        'type': 'service_backup_failed'
                    })
                    
            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'service': f"{service_type} ({service.get('app_name', 'unknown')})",
                    'error': str(e),
                    'type': 'service_backup_exception'
                })
        
        # Send alert if failures
        if results['failed'] > 0:
            send_backup_alert(results, 'service_backup_failed')
        
        results['success'] = True
        results['finished_at'] = datetime.utcnow().isoformat()
        
        return results
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
        results['finished_at'] = datetime.utcnow().isoformat()
        return results


@celery_app.task
def backup_service(service: Dict) -> Dict:
    """
    Backup a single service.
    
    Args:
        service: Service dictionary
        
    Returns:
        Dictionary with backup result
    """
    service_type = service['type']
    service_id = service['id']
    app_name = service.get('app_name', 'unknown')
    
    backup_dir = os.path.join(BACKUP_BASE_DIR, 'services', service_type, app_name)
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    
    try:
        if service_type == 'redis':
            return backup_redis_service(service, backup_dir, timestamp)
        elif service_type == 'meilisearch':
            return backup_meilisearch_service(service, backup_dir, timestamp)
        else:
            return {
                'success': False,
                'service': service_type,
                'error': f'Backup not supported for service type: {service_type}'
            }
            
    except Exception as e:
        return {
            'success': False,
            'service': service_type,
            'error': str(e)
        }


def backup_redis_service(service: Dict, backup_dir: str, timestamp: str) -> Dict:
    """
    Backup a Redis service.
    
    Args:
        service: Service dictionary
        backup_dir: Backup directory
        timestamp: Timestamp string
        
    Returns:
        Dictionary with backup result
    """
    server_ip = service.get('server_ip')
    port = service.get('port', 6379)
    
    if not server_ip:
        return {
            'success': False,
            'service': 'redis',
            'error': 'No server IP configured'
        }
    
    backup_path = os.path.join(backup_dir, f'{timestamp}.rdb')
    
    try:
        # Trigger BGSAVE on Redis
        cmd = f"ssh root@{server_ip} 'redis-cli -p {port} BGSAVE'"
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        # Wait for BGSAVE to complete
        import time
        time.sleep(2)
        
        # Copy RDB file
        rdb_path = f'/var/lib/redis/dump.rdb'
        copy_cmd = f"ssh root@{server_ip} 'cat {rdb_path}' > {backup_path}"
        result = subprocess.run(copy_cmd, shell=True, capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            backup_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
            
            return {
                'success': True,
                'service': 'redis',
                'backup_path': backup_path,
                'backup_size': backup_size,
                'backup_size_human': format_size(backup_size)
            }
        else:
            return {
                'success': False,
                'service': 'redis',
                'error': result.stderr or 'Failed to copy RDB file'
            }
            
    except Exception as e:
        return {
            'success': False,
            'service': 'redis',
            'error': str(e)
        }


def backup_meilisearch_service(service: Dict, backup_dir: str, timestamp: str) -> Dict:
    """
    Backup a Meilisearch service.
    
    Args:
        service: Service dictionary
        backup_dir: Backup directory
        timestamp: Timestamp string
        
    Returns:
        Dictionary with backup result
    """
    server_ip = service.get('server_ip')
    port = service.get('port', 7700)
    
    if not server_ip:
        return {
            'success': False,
            'service': 'meilisearch',
            'error': 'No server IP configured'
        }
    
    backup_path = os.path.join(backup_dir, f'{timestamp}.msb')
    
    try:
        # Trigger backup via Meilisearch API
        import requests
        
        url = f"http://{server_ip}:{port}/dumps"
        response = requests.post(url, timeout=30)
        
        if response.status_code in (200, 202):
            dump_info = response.json()
            dump_uid = dump_info.get('taskUid')
            
            # Wait for dump to complete
            import time
            for _ in range(30):  # Wait up to 30 seconds
                status_url = f"http://{server_ip}:{port}/tasks/{dump_uid}"
                status_response = requests.get(status_url, timeout=10)
                
                if status_response.status_code == 200:
                    task = status_response.json()
                    if task.get('status') == 'succeeded':
                        # Copy dump file
                        dump_file = task.get('output', {}).get('dumpFilePath', '')
                        if dump_file:
                            copy_cmd = f"ssh root@{server_ip} 'cat {dump_file}' > {backup_path}"
                            subprocess.run(copy_cmd, shell=True, capture_output=True, text=True, timeout=120)
                            
                            backup_size = os.path.getsize(backup_path) if os.path.exists(backup_path) else 0
                            
                            return {
                                'success': True,
                                'service': 'meilisearch',
                                'backup_path': backup_path,
                                'backup_size': backup_size,
                                'backup_size_human': format_size(backup_size)
                            }
                        break
                    elif task.get('status') == 'failed':
                        return {
                            'success': False,
                            'service': 'meilisearch',
                            'error': task.get('error', 'Dump failed')
                        }
                
                time.sleep(1)
            
            return {
                'success': False,
                'service': 'meilisearch',
                'error': 'Dump timed out'
            }
        else:
            return {
                'success': False,
                'service': 'meilisearch',
                'error': f'API returned {response.status_code}'
            }
            
    except Exception as e:
        return {
            'success': False,
            'service': 'meilisearch',
            'error': str(e)
        }


@celery_app.task
def cleanup_old_backups(days: int = DEFAULT_RETENTION_DAYS) -> Dict:
    """
    Remove backups older than N days.
    
    Args:
        days: Retention period in days
        
    Returns:
        Dictionary with cleanup results
    """
    results = {
        'backups_removed': 0,
        'space_freed': 0,
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    try:
        # Clean up database backups
        db_backup_dir = os.path.join(BACKUP_BASE_DIR, 'postgresql')
        removed, space = cleanup_backup_directory(db_backup_dir, cutoff)
        results['backups_removed'] += removed
        results['space_freed'] += space
        
        # Clean up service backups
        service_backup_dir = os.path.join(BACKUP_BASE_DIR, 'services')
        removed, space = cleanup_backup_directory(service_backup_dir, cutoff)
        results['backups_removed'] += removed
        results['space_freed'] += space
        
        # Clean up backup records in database
        cleanup_old_backup_records(days)
        
        results['success'] = True
        results['space_freed_human'] = format_size(results['space_freed'])
        results['finished_at'] = datetime.utcnow().isoformat()
        
        print(f"[{datetime.utcnow().isoformat()}] Backup cleanup complete: "
              f"removed={results['backups_removed']}, space_freed={results['space_freed_human']}")
        
        return results
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
        results['finished_at'] = datetime.utcnow().isoformat()
        return results


def cleanup_backup_directory(directory: str, cutoff: datetime) -> tuple:
    """
    Clean up old backup files in a directory.
    
    Args:
        directory: Directory to clean
        cutoff: Remove files older than this date
        
    Returns:
        Tuple of (files_removed, bytes_freed)
    """
    removed = 0
    space_freed = 0
    
    if not os.path.exists(directory):
        return removed, space_freed
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            
            try:
                # Check file modification time
                mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                if mtime < cutoff:
                    file_size = os.path.getsize(file_path)
                    os.remove(file_path)
                    removed += 1
                    space_freed += file_size
                    
            except Exception as e:
                print(f"Warning: Could not remove {file_path}: {e}")
    
    return removed, space_freed


def cleanup_old_backup_records(days: int) -> int:
    """
    Remove old backup records from database.
    
    Args:
        days: Retention period in days
        
    Returns:
        Number of records removed
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    with db.get_db() as conn:
        cursor = conn.execute('''
            DELETE FROM database_backups
            WHERE created_at < ?
        ''', (cutoff.isoformat(),))
        
        removed = cursor.rowcount
        conn.commit()
    
    return removed


# =============================================================================
# Helper Functions
# =============================================================================

def init_backup_schema():
    """Initialize backup-related database tables."""
    with db.get_db() as conn:
        # Database backups table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS database_backups (
                id TEXT PRIMARY KEY,
                database_id TEXT NOT NULL,
                database_name TEXT NOT NULL,
                backup_path TEXT,
                backup_size INTEGER,
                success INTEGER DEFAULT 1,
                error TEXT,
                duration_seconds INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (database_id) REFERENCES databases(id) ON DELETE CASCADE
            )
        ''')
        
        # Add backup columns to databases table
        try:
            conn.execute('ALTER TABLE databases ADD COLUMN backup_enabled INTEGER DEFAULT 1')
        except:
            pass
        
        try:
            conn.execute('ALTER TABLE databases ADD COLUMN backup_schedule TEXT DEFAULT "daily"')
        except:
            pass
        
        try:
            conn.execute('ALTER TABLE databases ADD COLUMN backup_retention_days INTEGER DEFAULT 30')
        except:
            pass
        
        try:
            conn.execute('ALTER TABLE databases ADD COLUMN last_backup_at TEXT')
        except:
            pass
        
        # Create indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_database_backups_db ON database_backups(database_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_database_backups_created ON database_backups(created_at)')
        
        conn.commit()


def get_all_databases() -> List[Dict]:
    """Get all databases."""
    with db.get_db() as conn:
        rows = conn.execute('SELECT * FROM databases ORDER BY name').fetchall()
        return [dict(row) for row in rows]


def get_database_by_name(db_name: str) -> Optional[Dict]:
    """Get database by name."""
    with db.get_db() as conn:
        row = conn.execute('SELECT * FROM databases WHERE name = ?', (db_name,)).fetchone()
        return dict(row) if row else None


def should_backup(db_info: Dict) -> bool:
    """
    Check if database needs backup based on schedule.
    
    Args:
        db_info: Database info dictionary
        
    Returns:
        True if backup is needed
    """
    schedule = db_info.get('backup_schedule', 'daily')
    last_backup = db_info.get('last_backup_at')
    
    if not last_backup:
        return True
    
    try:
        last = datetime.fromisoformat(last_backup)
    except (ValueError, TypeError):
        return True
    
    now = datetime.utcnow()
    elapsed = (now - last).total_seconds()
    
    # Check based on schedule
    if schedule == 'hourly':
        return elapsed >= 3600
    elif schedule == 'daily':
        return elapsed >= 86400
    elif schedule == 'weekly':
        return elapsed >= 604800
    elif schedule == 'monthly':
        return elapsed >= 2592000  # 30 days
    
    return False


def should_backup_service(service: Dict) -> bool:
    """
    Check if service needs backup.
    
    Args:
        service: Service info dictionary
        
    Returns:
        True if backup is needed
    """
    # Get service backup config from credentials or default to daily
    schedule = 'daily'  # Services backup daily by default
    
    # Get last backup
    service_id = service['id']
    with db.get_db() as conn:
        row = conn.execute('''
            SELECT timestamp FROM service_backups
            WHERE service_id = ?
            ORDER BY timestamp DESC LIMIT 1
        ''', (service_id,)).fetchone()
        
        if row:
            try:
                last = datetime.fromisoformat(row['timestamp'])
                elapsed = (datetime.utcnow() - last).total_seconds()
                return elapsed >= 86400  # Daily
            except:
                pass
    
    return True


def record_database_backup(db_id: str, backup_result: Dict) -> str:
    """
    Record a database backup.
    
    Args:
        db_id: Database ID
        backup_result: Backup result dictionary
        
    Returns:
        Backup record ID
    """
    backup_id = db.generate_id()
    
    with db.get_db() as conn:
        # Insert backup record
        conn.execute('''
            INSERT INTO database_backups 
            (id, database_id, database_name, backup_path, backup_size, success, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            backup_id,
            db_id,
            backup_result.get('database'),
            backup_result.get('backup_path'),
            backup_result.get('backup_size'),
            1 if backup_result.get('success') else 0,
            backup_result.get('error'),
            datetime.utcnow().isoformat()
        ))
        
        # Update last_backup_at on database
        conn.execute('''
            UPDATE databases SET last_backup_at = ? WHERE id = ?
        ''', (datetime.utcnow().isoformat(), db_id))
        
        conn.commit()
    
    return backup_id


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes is None:
        return '0 B'
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    
    return f"{size_bytes:.2f} PB"


def send_backup_alert(results: Dict, alert_type: str) -> None:
    """
    Send backup failure alert.
    
    Args:
        results: Backup results dictionary
        alert_type: Type of alert
    """
    from services.notifications import NotificationService
    
    message = f"""
⚠️ Backup Alert - {alert_type}

Backed up: {results['backed_up']}
Skipped: {results['skipped']}
Failed: {results['failed']}

Errors:
{chr(10).join(f"  - {e.get('database') or e.get('service')}: {e['error']}" for e in results['errors'][:10])}
"""
    
    NotificationService._send_notifications({
        'title': f'⚠️ Backup Alert',
        'alert_type': alert_type,
        'results': results,
        'timestamp': datetime.utcnow().isoformat()
    }, alert_type)


# Register with Celery Beat
CELERYBEAT_SCHEDULE = {
    'backup-all-databases': {
        'task': 'tasks.backup.backup_all_databases',
        'schedule': 21600.0,  # Every 6 hours
    },
    'backup-all-services': {
        'task': 'tasks.backup.backup_all_services',
        'schedule': 86400.0,  # Daily
    },
    'cleanup-old-backups': {
        'task': 'tasks.backup.cleanup_old_backups',
        'schedule': 86400.0,  # Daily
        'kwargs': {'days': DEFAULT_RETENTION_DAYS}
    }
}