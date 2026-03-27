"""
API routes for backup management.

Phase 4 endpoints for:
- Backup status and history
- Backup schedule configuration
- Manual backup triggers
- Backup restore operations
"""

from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta

try:
    import database as paas_db
    PAAS_DB_AVAILABLE = True
except ImportError:
    PAAS_DB_AVAILABLE = False

try:
    from tasks.backup import (
        backup_all_databases,
        backup_database,
        backup_all_services,
        cleanup_old_backups,
        get_all_databases,
        init_backup_schema
    )
    BACKUP_TASKS_AVAILABLE = True
except ImportError:
    BACKUP_TASKS_AVAILABLE = False

# Create blueprint
backup_bp = Blueprint('backup', __name__, url_prefix='/api')


# =============================================================================
# Backup Status
# =============================================================================

@backup_bp.route('/backup/status', methods=['GET'])
def api_backup_status():
    """
    Get backup status for all databases and services.
    
    Returns:
        JSON with backup status for all resources
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    status = {
        'databases': [],
        'services': [],
        'next_scheduled': None,
        'last_run': None
    }
    
    try:
        # Ensure backup schema exists
        init_backup_schema()
        
        # Get database backup status
        databases = get_all_databases()
        
        for db_info in databases:
            last_backup = get_last_database_backup(db_info['id'])
            
            status['databases'].append({
                'id': db_info['id'],
                'name': db_info['name'],
                'last_backup': last_backup.get('created_at') if last_backup else None,
                'last_backup_size': last_backup.get('backup_size') if last_backup else None,
                'last_backup_status': 'success' if last_backup and last_backup.get('success') else 'failed' if last_backup else None,
                'backup_schedule': db_info.get('backup_schedule', 'daily'),
                'backup_enabled': db_info.get('backup_enabled', True),
                'backup_retention_days': db_info.get('backup_retention_days', 30)
            })
        
        # Get service backup status
        services = paas_db.get_all_services()
        
        for service in services:
            backups = paas_db.get_service_backups(service['id'], limit=1)
            last_backup = backups[0] if backups else None
            
            status['services'].append({
                'id': service['id'],
                'type': service['type'],
                'app_name': service.get('app_name'),
                'environment': service.get('environment'),
                'last_backup': last_backup.get('timestamp') if last_backup else None,
                'last_backup_status': 'success' if last_backup and last_backup.get('success') else 'failed' if last_backup else None
            })
        
        # Get last backup run time
        with paas_db.get_db() as conn:
            row = conn.execute('''
                SELECT MAX(created_at) as last_run FROM database_backups
            ''').fetchone()
            
            if row and row['last_run']:
                status['last_run'] = row['last_run']
        
        return jsonify({
            'success': True,
            'status': status,
            'checked_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@backup_bp.route('/backup/history', methods=['GET'])
def api_backup_history():
    """
    Get backup history.
    
    Query params:
        - type: 'database' or 'service' (default: all)
        - limit: Number of results (default: 50)
        
    Returns:
        JSON with backup history
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    backup_type = request.args.get('type', 'all')
    limit = request.args.get('limit', 50, type=int)
    
    history = {
        'databases': [],
        'services': []
    }
    
    try:
        init_backup_schema()
        
        if backup_type in ('all', 'database'):
            with paas_db.get_db() as conn:
                rows = conn.execute('''
                    SELECT db.*, d.name as database_name
                    FROM database_backups db
                    JOIN databases d ON db.database_id = d.id
                    ORDER BY db.created_at DESC
                    LIMIT ?
                ''', (limit,)).fetchall()
                
                history['databases'] = [dict(row) for row in rows]
        
        if backup_type in ('all', 'service'):
            with paas_db.get_db() as conn:
                rows = conn.execute('''
                    SELECT sb.*, s.type as service_type, a.name as app_name
                    FROM service_backups sb
                    JOIN services s ON sb.service_id = s.id
                    JOIN applications a ON s.app_id = a.id
                    ORDER BY sb.created_at DESC
                    LIMIT ?
                ''', (limit,)).fetchall()
                
                history['services'] = [dict(row) for row in rows]
        
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Database Backup Configuration
# =============================================================================

@backup_bp.route('/databases/<db_name>/backup-config', methods=['GET', 'PUT'])
def api_database_backup_config(db_name):
    """
    Get or update backup configuration for a database.
    
    GET: Get current backup configuration
    PUT: Update backup configuration
        
    PUT body:
        {
            "enabled": true,
            "schedule": "daily",
            "retention_days": 30
        }
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    # Get database
    with paas_db.get_db() as conn:
        row = conn.execute(
            'SELECT * FROM databases WHERE name = ?',
            (db_name,)
        ).fetchone()
        
        if not row:
            return jsonify({'success': False, 'error': 'Database not found'}), 404
        
        database = dict(row)
    
    if request.method == 'PUT':
        data = request.json or {}
        
        # Validate schedule
        valid_schedules = ['hourly', 'daily', 'weekly', 'monthly']
        schedule = data.get('schedule', database.get('backup_schedule', 'daily'))
        
        if schedule not in valid_schedules:
            return jsonify({
                'success': False,
                'error': f'Invalid schedule. Must be one of: {", ".join(valid_schedules)}'
            }), 400
        
        # Update configuration
        updates = {}
        
        if 'enabled' in data:
            updates['backup_enabled'] = 1 if data['enabled'] else 0
        
        if 'schedule' in data:
            updates['backup_schedule'] = data['schedule']
        
        if 'retention_days' in data:
            updates['backup_retention_days'] = data['retention_days']
        
        if updates:
            set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
            values = list(updates.values()) + [database['id']]
            
            with paas_db.get_db() as conn:
                conn.execute(
                    f'UPDATE databases SET {set_clause} WHERE id = ?',
                    values
                )
                conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Backup configuration updated',
            'config': {
                'enabled': updates.get('backup_enabled', database.get('backup_enabled', 1)) == 1,
                'schedule': updates.get('backup_schedule', database.get('backup_schedule', 'daily')),
                'retention_days': updates.get('backup_retention_days', database.get('backup_retention_days', 30))
            }
        })
    
    # GET
    return jsonify({
        'success': True,
        'database': db_name,
        'config': {
            'enabled': database.get('backup_enabled', 1) == 1,
            'schedule': database.get('backup_schedule', 'daily'),
            'retention_days': database.get('backup_retention_days', 30),
            'last_backup': database.get('last_backup_at')
        }
    })


@backup_bp.route('/databases/<db_name>/backups', methods=['GET'])
def api_database_backups(db_name):
    """
    Get backup history for a specific database.
    
    Query params:
        - limit: Number of results (default: 20)
        
    Returns:
        JSON with backup list
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    limit = request.args.get('limit', 20, type=int)
    
    try:
        with paas_db.get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM database_backups
                WHERE database_name = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (db_name, limit)).fetchall()
            
            backups = [dict(row) for row in rows]
        
        return jsonify({
            'success': True,
            'database': db_name,
            'backups': backups
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Backup Operations
# =============================================================================

@backup_bp.route('/backup/run', methods=['POST'])
def api_run_backup():
    """
    Manually trigger backup for all databases.
    
    Returns:
        JSON with task ID
    """
    if not BACKUP_TASKS_AVAILABLE:
        return jsonify({'success': False, 'error': 'Backup tasks not available'}), 500
    
    try:
        # Queue the task
        result = backup_all_databases.delay()
        
        return jsonify({
            'success': True,
            'task_id': result.id,
            'message': 'Backup started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@backup_bp.route('/databases/<db_name>/backup', methods=['POST'])
def api_backup_single_database(db_name):
    """
    Manually trigger backup for a specific database.
    
    Returns:
        JSON with task ID
    """
    if not BACKUP_TASKS_AVAILABLE:
        return jsonify({'success': False, 'error': 'Backup tasks not available'}), 500
    
    try:
        # Queue the task
        result = backup_database.delay(db_name)
        
        return jsonify({
            'success': True,
            'task_id': result.id,
            'database': db_name,
            'message': f'Backup started for {db_name}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@backup_bp.route('/services/backup', methods=['POST'])
def api_backup_all_services():
    """
    Manually trigger backup for all services.
    
    Returns:
        JSON with task ID
    """
    if not BACKUP_TASKS_AVAILABLE:
        return jsonify({'success': False, 'error': 'Backup tasks not available'}), 500
    
    try:
        # Queue the task
        result = backup_all_services.delay()
        
        return jsonify({
            'success': True,
            'task_id': result.id,
            'message': 'Service backup started'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@backup_bp.route('/backup/cleanup', methods=['POST'])
def api_cleanup_backups():
    """
    Manually trigger backup cleanup.
    
    Query params:
        - days: Retention period in days (default: 30)
        
    Returns:
        JSON with task ID
    """
    if not BACKUP_TASKS_AVAILABLE:
        return jsonify({'success': False, 'error': 'Backup tasks not available'}), 500
    
    days = request.args.get('days', 30, type=int)
    
    try:
        # Queue the task
        result = cleanup_old_backups.delay(days=days)
        
        return jsonify({
            'success': True,
            'task_id': result.id,
            'message': f'Backup cleanup started (retention: {days} days)'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Backup Restore (Future)
# =============================================================================

@backup_bp.route('/databases/<db_name>/restore', methods=['POST'])
def api_restore_database(db_name):
    """
    Restore a database from a backup.
    
    Body:
        {
            "backup_path": "/var/backups/postgresql/db_name/20260327_120000.sql.gz"
        }
        
    Returns:
        JSON with restore result
    """
    data = request.json or {}
    backup_path = data.get('backup_path')
    
    if not backup_path:
        return jsonify({
            'success': False,
            'error': 'backup_path is required'
        }), 400
    
    # This is a dangerous operation - require confirmation
    confirm = data.get('confirm', False)
    if not confirm:
        return jsonify({
            'success': False,
            'error': 'Restore requires confirmation. Set confirm: true in request body.',
            'warning': 'This will overwrite the current database!'
        }), 400
    
    # TODO: Implement restore logic
    # For now, return not implemented
    return jsonify({
        'success': False,
        'error': 'Database restore not yet implemented',
        'backup_path': backup_path
    }), 501


# =============================================================================
# Backup Statistics
# =============================================================================

@backup_bp.route('/backup/stats', methods=['GET'])
def api_backup_stats():
    """
    Get backup statistics.
    
    Query params:
        - days: Number of days to analyze (default: 30)
        
    Returns:
        JSON with backup statistics
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    days = request.args.get('days', 30, type=int)
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    stats = {
        'period_days': days,
        'databases': {
            'total_backups': 0,
            'successful': 0,
            'failed': 0,
            'total_size': 0,
            'avg_size': 0
        },
        'services': {
            'total_backups': 0,
            'successful': 0,
            'failed': 0
        }
    }
    
    try:
        init_backup_schema()
        
        # Database backup stats
        with paas_db.get_db() as conn:
            row = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
                    SUM(backup_size) as total_size,
                    AVG(backup_size) as avg_size
                FROM database_backups
                WHERE created_at >= ?
            ''', (cutoff.isoformat(),)).fetchone()
            
            if row:
                stats['databases'] = {
                    'total_backups': row['total'] or 0,
                    'successful': row['successful'] or 0,
                    'failed': row['failed'] or 0,
                    'total_size': row['total_size'] or 0,
                    'avg_size': row['avg_size'] or 0
                }
        
        # Service backup stats
        with paas_db.get_db() as conn:
            row = conn.execute('''
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed
                FROM service_backups
                WHERE created_at >= ?
            ''', (cutoff.isoformat(),)).fetchone()
            
            if row:
                stats['services'] = {
                    'total_backups': row['total'] or 0,
                    'successful': row['successful'] or 0,
                    'failed': row['failed'] or 0
                }
        
        return jsonify({
            'success': True,
            'stats': stats,
            'generated_at': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# Helper Functions
# =============================================================================

def get_last_database_backup(db_id: str):
    """Get the last backup for a database."""
    with paas_db.get_db() as conn:
        row = conn.execute('''
            SELECT * FROM database_backups
            WHERE database_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (db_id,)).fetchone()
        
        return dict(row) if row else None


def register_backup_routes(app):
    """
    Register backup blueprint with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(backup_bp)