"""
Backup Action for PaaS.

This module provides the BackupAction class for creating database backups
with:
- PostgreSQL database dumps
- Backup rotation and cleanup
- Progress tracking
- Compression support
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base import BaseAction, ActionResult
from websocket.performance import get_ssh_pool
import database as paas_db


class BackupAction(BaseAction):
    """
    Create a database backup.
    
    This action handles the complete backup workflow:
    1. Validate database exists
    2. Create backup directory
    3. Execute pg_dump with compression
    4. Verify backup integrity
    5. Rotate old backups
    
    Example:
        action = BackupAction(
            db_name='myapp_production',
            backup_type='full'
        )
        
        result = action.execute()
        
        if result.success:
            print(f"Backup created: {result.data['backup_path']}")
        else:
            print(f"Backup failed: {result.error}")
    """
    
    action_type = "backup"
    
    # Backup types
    BACKUP_TYPES = ['full', 'schema', 'data']
    
    # Default backup settings
    DEFAULT_BACKUP_DIR = '/var/backups/postgresql'
    DEFAULT_RETENTION_DAYS = 30
    DEFAULT_COMPRESSION = 'gzip'
    
    def __init__(self, db_name: str, backup_type: str = 'full',
                 backup_dir: str = None, retention_days: int = None,
                 compress: bool = True, emit_progress: bool = True):
        """
        Initialize the backup action.
        
        Args:
            db_name: Database name to backup
            backup_type: 'full', 'schema', or 'data'
            backup_dir: Custom backup directory (optional)
            retention_days: Days to retain backups (optional)
            compress: Whether to compress the backup
            emit_progress: Whether to emit WebSocket progress
        """
        super().__init__(emit_progress=emit_progress)
        self.db_name = db_name
        self.backup_type = backup_type
        self.backup_dir = backup_dir or self.DEFAULT_BACKUP_DIR
        self.retention_days = retention_days or self.DEFAULT_RETENTION_DAYS
        self.compress = compress
        
        # Populated during execution
        self.backup_path: Optional[str] = None
        self.backup_filename: Optional[str] = None
        self.db_server: Optional[Dict[str, Any]] = None
    
    def validate(self) -> List[str]:
        """
        Validate backup parameters.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Validate backup type
        if self.backup_type not in self.BACKUP_TYPES:
            errors.append(f"Invalid backup type: {self.backup_type}. "
                         f"Must be one of: {', '.join(self.BACKUP_TYPES)}")
        
        # Validate database exists (via database server connection)
        if not self.db_name:
            errors.append("Database name is required")
        
        # Get database server
        servers = paas_db.list_servers()
        self.db_server = next(
            (s for s in servers if 'database' in s.get('role', '').lower()),
            None
        )
        
        if not self.db_server:
            errors.append("No database server found in server list")
        
        return errors
    
    def pre_execute(self) -> bool:
        """
        Prepare for backup.
        
        Creates backup directory if needed.
        
        Returns:
            True to proceed with backup
        """
        if not super().pre_execute():
            return False
        
        # Generate backup filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        extension = '.sql.gz' if self.compress else '.sql'
        self.backup_filename = f"{self.db_name}_{self.backup_type}_{timestamp}{extension}"
        self.backup_path = f"{self.backup_dir}/{self.db_name}/{self.backup_filename}"
        
        # Store rollback data
        self.store_rollback_data('db_name', self.db_name)
        self.store_rollback_data('backup_path', self.backup_path)
        
        return True
    
    def _execute(self) -> ActionResult:
        """
        Execute the backup.
        
        Returns:
            ActionResult with backup outcome
        """
        results = {
            'db_name': self.db_name,
            'backup_type': self.backup_type,
            'backup_path': self.backup_path,
            'steps': {}
        }
        
        # Step 1: Create backup directory
        self.add_step('mkdir', 'running', 'Creating backup directory')
        
        mkdir_result = self._create_backup_directory()
        results['steps']['mkdir'] = mkdir_result
        
        if not mkdir_result['success']:
            self.add_step('mkdir', 'failed', mkdir_result.get('error'))
            
            return ActionResult(
                success=False,
                message="Failed to create backup directory",
                error=mkdir_result.get('error'),
                data=results
            )
        
        self.add_step('mkdir', 'success', "Backup directory created")
        
        # Step 2: Execute pg_dump
        self.add_step('dump', 'running', 'Creating database dump')
        
        dump_result = self._execute_pg_dump()
        results['steps']['dump'] = dump_result
        
        if not dump_result['success']:
            self.add_step('dump', 'failed', dump_result.get('error'))
            
            return ActionResult(
                success=False,
                message="Database dump failed",
                error=dump_result.get('error'),
                data=results
            )
        
        self.add_step('dump', 'success', 
                     f"Database dump created ({dump_result.get('size', 'unknown size')})")
        
        # Step 3: Verify backup
        self.add_step('verify', 'running', 'Verifying backup integrity')
        
        verify_result = self._verify_backup()
        results['steps']['verify'] = verify_result
        
        if not verify_result['success']:
            self.add_step('verify', 'failed', verify_result.get('error'))
            
            return ActionResult(
                success=False,
                message="Backup verification failed",
                error=verify_result.get('error'),
                data=results
            )
        
        self.add_step('verify', 'success', "Backup verified")
        
        # Step 4: Rotate old backups
        self.add_step('rotate', 'running', 'Rotating old backups')
        
        rotate_result = self._rotate_backups()
        results['steps']['rotate'] = rotate_result
        
        self.add_step('rotate', 'success', 
                     f"Rotated {rotate_result.get('removed', 0)} old backups")
        
        return ActionResult(
            success=True,
            message=f"Backup created successfully: {self.backup_filename}",
            data={
                **results,
                'backup_filename': self.backup_filename,
                'backup_size': dump_result.get('size'),
                'backup_size_human': dump_result.get('size_human')
            }
        )
    
    def _create_backup_directory(self) -> Dict[str, Any]:
        """
        Create backup directory on database server.
        
        Returns:
            Dictionary with success status
        """
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect to database server'}
        
        try:
            # Create backup directory
            cmd = f'mkdir -p {self.backup_dir}/{self.db_name}'
            stdin, stdout, stderr = conn.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            
            pool.release_connection(conn)
            
            if exit_code == 0:
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': stderr.read().decode()
                }
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def _execute_pg_dump(self) -> Dict[str, Any]:
        """
        Execute pg_dump command on database server.
        
        Returns:
            Dictionary with success status and backup details
        """
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect to database server'}
        
        try:
            # Build pg_dump command
            if self.backup_type == 'full':
                pg_dump_opts = ''
            elif self.backup_type == 'schema':
                pg_dump_opts = '--schema-only'
            elif self.backup_type == 'data':
                pg_dump_opts = '--data-only'
            
            # Build full command
            if self.compress:
                cmd = (
                    f'pg_dump {pg_dump_opts} -d {self.db_name} | '
                    f'gzip > {self.backup_path}'
                )
            else:
                cmd = f'pg_dump {pg_dump_opts} -d {self.db_name} > {self.backup_path}'
            
            # Execute backup
            stdin, stdout, stderr = conn.exec_command(cmd, timeout=3600)  # 1 hour timeout
            exit_code = stdout.channel.recv_exit_status()
            error = stderr.read().decode()
            
            if exit_code != 0:
                pool.release_connection(conn)
                return {
                    'success': False,
                    'error': error or 'pg_dump failed'
                }
            
            # Get backup file size
            size_cmd = f'stat -c %s {self.backup_path}'
            stdin, stdout, stderr = conn.exec_command(size_cmd)
            size = stdout.read().decode().strip()
            
            pool.release_connection(conn)
            
            try:
                size_bytes = int(size)
                size_human = self._format_size(size_bytes)
            except ValueError:
                size_bytes = 0
                size_human = 'unknown'
            
            return {
                'success': True,
                'size': size_bytes,
                'size_human': size_human
            }
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def _verify_backup(self) -> Dict[str, Any]:
        """
        Verify backup file integrity.
        
        Returns:
            Dictionary with success status
        """
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect to database server'}
        
        try:
            # Check if file exists and is not empty
            if self.compress:
                cmd = f'gzip -t {self.backup_path} && stat -c %s {self.backup_path}'
            else:
                cmd = f'test -s {self.backup_path} && stat -c %s {self.backup_path}'
            
            stdin, stdout, stderr = conn.exec_command(cmd)
            exit_code = stdout.channel.recv_exit_status()
            
            pool.release_connection(conn)
            
            if exit_code == 0:
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': 'Backup file is empty or corrupted'
                }
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def _rotate_backups(self) -> Dict[str, Any]:
        """
        Remove old backups beyond retention period.
        
        Returns:
            Dictionary with success status and removed count
        """
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect to database server'}
        
        try:
            # Find and delete old backups
            cmd = (
                f'find {self.backup_dir}/{self.db_name} '
                f'-name "{self.db_name}_{self.backup_type}_*.sql*" '
                f'-mtime +{self.retention_days} '
                f'-type f -delete -print'
            )
            
            stdin, stdout, stderr = conn.exec_command(cmd)
            output = stdout.read().decode()
            
            pool.release_connection(conn)
            
            # Count removed files
            removed = len([l for l in output.strip().split('\n') if l])
            
            return {
                'success': True,
                'removed': removed
            }
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def _format_size(self, size_bytes: int) -> str:
        """
        Format size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Human-readable size string
        """
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} PB"
    
    def rollback(self) -> ActionResult:
        """
        Rollback by deleting the created backup.
        
        Returns:
            ActionResult with rollback outcome
        """
        if not self.backup_path:
            return ActionResult(
                success=False,
                message="No backup to rollback"
            )
        
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return ActionResult(
                success=False,
                message="Could not connect to database server"
            )
        
        try:
            # Delete backup file
            cmd = f'rm -f {self.backup_path}'
            stdin, stdout, stderr = conn.exec_command(cmd)
            stdout.channel.recv_exit_status()
            
            pool.release_connection(conn)
            
            return ActionResult(
                success=True,
                message=f"Backup deleted: {self.backup_filename}"
            )
        
        except Exception as e:
            pool.release_connection(conn)
            return ActionResult(
                success=False,
                message=f"Failed to delete backup: {str(e)}"
            )


class RestoreAction(BaseAction):
    """
    Restore a database from backup.
    
    This action handles the complete restore workflow:
    1. Validate backup file exists
    2. Create pre-restore backup
    3. Drop and recreate database
    4. Restore from backup
    5. Verify restore
    
    Example:
        action = RestoreAction(
            db_name='myapp_production',
            backup_path='/var/backups/postgresql/myapp_production/full_20240101.sql.gz'
        )
        
        result = action.execute()
    """
    
    action_type = "restore"
    
    def __init__(self, db_name: str, backup_path: str,
                 create_pre_backup: bool = True,
                 emit_progress: bool = True):
        """
        Initialize the restore action.
        
        Args:
            db_name: Database name to restore
            backup_path: Path to backup file
            create_pre_backup: Create backup before restore
            emit_progress: Whether to emit WebSocket progress
        """
        super().__init__(emit_progress=emit_progress)
        self.db_name = db_name
        self.backup_path = backup_path
        self.create_pre_backup = create_pre_backup
        
        self.db_server: Optional[Dict[str, Any]] = None
        self.pre_backup_path: Optional[str] = None
    
    def validate(self) -> List[str]:
        """
        Validate restore parameters.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        if not self.db_name:
            errors.append("Database name is required")
        
        if not self.backup_path:
            errors.append("Backup path is required")
        
        # Get database server
        servers = paas_db.list_servers()
        self.db_server = next(
            (s for s in servers if 'database' in s.get('role', '').lower()),
            None
        )
        
        if not self.db_server:
            errors.append("No database server found")
        
        return errors
    
    def pre_execute(self) -> bool:
        """Prepare for restore."""
        if not super().pre_execute():
            return False
        
        # Verify backup exists
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return False
        
        stdin, stdout, stderr = conn.exec_command(f'test -f {self.backup_path}')
        exit_code = stdout.channel.recv_exit_status()
        
        pool.release_connection(conn)
        
        if exit_code != 0:
            self.add_step('validate', 'failed', 'Backup file not found')
            return False
        
        return True
    
    def _execute(self) -> ActionResult:
        """Execute the restore."""
        results = {
            'db_name': self.db_name,
            'backup_path': self.backup_path,
            'steps': {}
        }
        
        # Step 1: Create pre-restore backup
        if self.create_pre_backup:
            self.add_step('pre_backup', 'running', 'Creating pre-restore backup')
            
            pre_backup = BackupAction(
                db_name=self.db_name,
                backup_type='full',
                emit_progress=False
            )
            pre_result = pre_backup.execute()
            results['steps']['pre_backup'] = pre_result.to_dict()
            
            if pre_result.success:
                self.pre_backup_path = pre_result.data.get('backup_path')
                self.add_step('pre_backup', 'success', 'Pre-restore backup created')
            else:
                self.add_step('pre_backup', 'failed', pre_result.error)
                return ActionResult(
                    success=False,
                    message="Pre-restore backup failed",
                    error=pre_result.error,
                    data=results
                )
        
        # Step 2: Drop and recreate database
        self.add_step('recreate', 'running', 'Recreating database')
        recreate_result = self._recreate_database()
        
        if not recreate_result['success']:
            self.add_step('recreate', 'failed', recreate_result.get('error'))
            return ActionResult(
                success=False,
                message="Database recreation failed",
                error=recreate_result.get('error'),
                data=results
            )
        
        self.add_step('recreate', 'success', 'Database recreated')
        
        # Step 3: Restore from backup
        self.add_step('restore', 'running', 'Restoring from backup')
        restore_result = self._restore_database()
        
        if not restore_result['success']:
            self.add_step('restore', 'failed', restore_result.get('error'))
            return ActionResult(
                success=False,
                message="Database restore failed",
                error=restore_result.get('error'),
                data=results
            )
        
        self.add_step('restore', 'success', 'Database restored')
        
        return ActionResult(
            success=True,
            message=f"Database {self.db_name} restored successfully",
            data=results
        )
    
    def _recreate_database(self) -> Dict[str, Any]:
        """Drop and recreate database."""
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect'}
        
        try:
            # Terminate connections and recreate
            commands = [
                f"psql -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{self.db_name}' AND pid <> pg_backend_pid()\"",
                f"dropdb --if-exists {self.db_name}",
                f"createdb {self.db_name}"
            ]
            
            for cmd in commands:
                stdin, stdout, stderr = conn.exec_command(cmd)
                exit_code = stdout.channel.recv_exit_status()
                if exit_code != 0:
                    error = stderr.read().decode()
                    pool.release_connection(conn)
                    return {'success': False, 'error': error}
            
            pool.release_connection(conn)
            return {'success': True}
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def _restore_database(self) -> Dict[str, Any]:
        """Restore database from backup file."""
        pool = get_ssh_pool()
        conn = pool.get_connection(self.db_server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect'}
        
        try:
            # Build restore command
            if self.backup_path.endswith('.gz'):
                cmd = f'gunzip -c {self.backup_path} | psql -d {self.db_name}'
            else:
                cmd = f'psql -d {self.db_name} < {self.backup_path}'
            
            stdin, stdout, stderr = conn.exec_command(cmd, timeout=3600)
            exit_code = stdout.channel.recv_exit_status()
            error = stderr.read().decode()
            
            pool.release_connection(conn)
            
            # psql returns 0 even with some errors, check for critical errors
            if exit_code != 0 and 'FATAL' in error:
                return {'success': False, 'error': error}
            
            return {'success': True, 'output': error}
        
        except Exception as e:
            pool.release_connection(conn)
            return {'success': False, 'error': str(e)}
    
    def rollback(self) -> ActionResult:
        """Rollback by restoring pre-restore backup."""
        if not self.pre_backup_path:
            return ActionResult(
                success=False,
                message="No pre-restore backup available"
            )
        
        # Restore from pre-restore backup
        restore = RestoreAction(
            db_name=self.db_name,
            backup_path=self.pre_backup_path,
            create_pre_backup=False
        )
        
        return restore.execute()


# Convenience functions
def create_backup(db_name: str, backup_type: str = 'full') -> ActionResult:
    """
    Create a database backup with default settings.
    
    Args:
        db_name: Database name
        backup_type: 'full', 'schema', or 'data'
        
    Returns:
        ActionResult with backup outcome
    """
    action = BackupAction(db_name=db_name, backup_type=backup_type)
    return action.execute()


def restore_backup(db_name: str, backup_path: str) -> ActionResult:
    """
    Restore a database from backup with default settings.
    
    Args:
        db_name: Database name
        backup_path: Path to backup file
        
    Returns:
        ActionResult with restore outcome
    """
    action = RestoreAction(db_name=db_name, backup_path=backup_path)
    return action.execute()