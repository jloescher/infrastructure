"""
Deployment hooks execution.

Runs custom scripts before and after deployments:
- pre_deploy: Run before deployment, can cancel deployment if fails
- post_deploy: Run after successful deployment
- pre_rollback: Run before rollback
- post_rollback: Run after rollback

Hooks are stored in the database and executed on target servers.
"""

import os
import json
import subprocess
import signal
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


# Default timeout for hooks (5 minutes)
DEFAULT_HOOK_TIMEOUT = 300

# Hook types
HOOK_TYPES = ['pre_deploy', 'post_deploy', 'pre_rollback', 'post_rollback']


class HookExecutionError(Exception):
    """Exception raised when a hook execution fails."""
    
    def __init__(self, hook_id: str, message: str, output: str = None, exit_code: int = None):
        self.hook_id = hook_id
        self.message = message
        self.output = output
        self.exit_code = exit_code
        super().__init__(message)


class HookExecutor:
    """
    Execute deployment hooks on servers.
    
    Hooks are custom scripts that run at specific deployment stages:
    - pre_deploy: Before deployment starts (can cancel deployment)
    - post_deploy: After deployment succeeds
    - pre_rollback: Before rollback starts
    - post_rollback: After rollback completes
    """
    
    @classmethod
    def execute_hooks(cls, app_id: str, hook_type: str, environment: str,
                      servers: List[Dict], deployment_id: str = None,
                      stop_on_failure: bool = True) -> Dict[str, Any]:
        """
        Execute all hooks of a specific type for an app.
        
        Args:
            app_id: Application ID
            hook_type: One of HOOK_TYPES
            environment: 'production' or 'staging'
            servers: List of server dicts with 'name' and 'ip'
            deployment_id: Optional deployment ID for logging
            stop_on_failure: If True, stop on first failure (for pre_deploy)
            
        Returns:
            Dict with 'success', 'hooks_executed', 'hooks_failed', and results
        """
        if hook_type not in HOOK_TYPES:
            return {
                'success': False,
                'error': f'Invalid hook type: {hook_type}'
            }
        
        # Get hooks for this app and type
        hooks = cls.get_hooks(app_id, hook_type, environment)
        
        if not hooks:
            return {
                'success': True,
                'hooks_executed': 0,
                'hooks_failed': 0,
                'message': f'No {hook_type} hooks configured'
            }
        
        results = {
            'success': True,
            'hook_type': hook_type,
            'hooks_executed': 0,
            'hooks_failed': 0,
            'hooks': []
        }
        
        for hook in hooks:
            if not hook.get('enabled', True):
                results['hooks'].append({
                    'hook_id': hook['id'],
                    'status': 'skipped',
                    'message': 'Hook is disabled'
                })
                continue
            
            hook_result = cls.execute_hook(
                hook=hook,
                servers=servers,
                deployment_id=deployment_id
            )
            
            results['hooks'].append(hook_result)
            results['hooks_executed'] += 1
            
            if not hook_result['success']:
                results['hooks_failed'] += 1
                results['success'] = False
                
                if stop_on_failure:
                    results['stopped_early'] = True
                    results['message'] = f'Stopped on failed hook: {hook["command"]}'
                    break
        
        # Log to deployment if provided
        if deployment_id:
            cls._log_hook_results(deployment_id, hook_type, results)
        
        return results
    
    @classmethod
    def execute_hook(cls, hook: Dict, servers: List[Dict],
                     deployment_id: str = None) -> Dict[str, Any]:
        """
        Execute a single hook on all target servers.
        
        Args:
            hook: Hook dict from database
            servers: List of server dicts
            deployment_id: Optional deployment ID
            
        Returns:
            Dict with 'success', 'hook_id', 'servers', and outputs
        """
        hook_id = hook['id']
        command = hook['command']
        timeout = hook.get('timeout', DEFAULT_HOOK_TIMEOUT)
        
        result = {
            'hook_id': hook_id,
            'hook_type': hook['hook_type'],
            'command': command,
            'success': True,
            'servers': {},
            'started_at': datetime.utcnow().isoformat()
        }
        
        for server in servers:
            server_name = server['name']
            server_ip = server['ip']
            
            # Execute on server
            exec_result = cls._run_ssh_command(
                server_ip=server_ip,
                command=command,
                timeout=timeout,
                hook_id=hook_id
            )
            
            result['servers'][server_name] = {
                'success': exec_result['success'],
                'exit_code': exec_result.get('exit_code'),
                'output': exec_result.get('output', ''),
                'error': exec_result.get('error', ''),
                'duration_seconds': exec_result.get('duration', 0)
            }
            
            if not exec_result['success']:
                result['success'] = False
                result['error'] = f'Hook failed on {server_name}'
        
        result['finished_at'] = datetime.utcnow().isoformat()
        
        # Store hook execution result
        cls._store_hook_execution(hook, result, deployment_id)
        
        return result
    
    @classmethod
    def get_hooks(cls, app_id: str, hook_type: str = None, 
                  environment: str = None) -> List[Dict]:
        """
        Get hooks for an application.
        
        Args:
            app_id: Application ID
            hook_type: Filter by hook type (optional)
            environment: Filter by environment (optional, None = all)
            
        Returns:
            List of hook dicts
        """
        with db.get_db() as conn:
            if hook_type and environment:
                rows = conn.execute('''
                    SELECT * FROM deployment_hooks 
                    WHERE app_id = ? AND hook_type = ? 
                    AND (environment = ? OR environment IS NULL)
                    AND enabled = 1
                    ORDER BY created_at
                ''', (app_id, hook_type, environment)).fetchall()
            elif hook_type:
                rows = conn.execute('''
                    SELECT * FROM deployment_hooks 
                    WHERE app_id = ? AND hook_type = ?
                    AND enabled = 1
                    ORDER BY created_at
                ''', (app_id, hook_type)).fetchall()
            elif environment:
                rows = conn.execute('''
                    SELECT * FROM deployment_hooks 
                    WHERE app_id = ? 
                    AND (environment = ? OR environment IS NULL)
                    AND enabled = 1
                    ORDER BY created_at
                ''', (app_id, environment)).fetchall()
            else:
                rows = conn.execute('''
                    SELECT * FROM deployment_hooks 
                    WHERE app_id = ? AND enabled = 1
                    ORDER BY created_at
                ''', (app_id,)).fetchall()
            
            return [dict(row) for row in rows]
    
    @classmethod
    def create_hook(cls, app_id: str, hook_type: str, command: str,
                    environment: str = None, timeout: int = DEFAULT_HOOK_TIMEOUT,
                    enabled: bool = True) -> str:
        """
        Create a new deployment hook.
        
        Args:
            app_id: Application ID
            hook_type: One of HOOK_TYPES
            command: Shell command to execute
            environment: 'production', 'staging', or None for all
            timeout: Timeout in seconds
            enabled: Whether hook is active
            
        Returns:
            Hook ID
        """
        if hook_type not in HOOK_TYPES:
            raise ValueError(f'Invalid hook type: {hook_type}')
        
        hook_id = db.generate_id()
        now = datetime.utcnow().isoformat()
        
        with db.get_db() as conn:
            conn.execute('''
                INSERT INTO deployment_hooks 
                (id, app_id, hook_type, environment, command, timeout, enabled, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                hook_id, app_id, hook_type, environment, command, 
                timeout, 1 if enabled else 0, now
            ))
            conn.commit()
        
        return hook_id
    
    @classmethod
    def update_hook(cls, hook_id: str, updates: Dict[str, Any]) -> bool:
        """Update a deployment hook."""
        allowed_fields = ['hook_type', 'environment', 'command', 'timeout', 'enabled']
        updates = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        if 'enabled' in updates:
            updates['enabled'] = 1 if updates['enabled'] else 0
        
        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [hook_id]
        
        with db.get_db() as conn:
            conn.execute(f'UPDATE deployment_hooks SET {set_clause} WHERE id = ?', values)
            conn.commit()
        
        return True
    
    @classmethod
    def delete_hook(cls, hook_id: str) -> bool:
        """Delete a deployment hook."""
        with db.get_db() as conn:
            conn.execute('DELETE FROM deployment_hooks WHERE id = ?', (hook_id,))
            conn.commit()
        return True
    
    @classmethod
    def get_hook_executions(cls, deployment_id: str = None, 
                            hook_id: str = None,
                            limit: int = 50) -> List[Dict]:
        """
        Get hook execution history.
        
        Args:
            deployment_id: Filter by deployment ID
            hook_id: Filter by hook ID
            limit: Maximum results
            
        Returns:
            List of execution records
        """
        with db.get_db() as conn:
            if deployment_id:
                rows = conn.execute('''
                    SELECT he.*, h.command, h.hook_type
                    FROM hook_executions he
                    JOIN deployment_hooks h ON he.hook_id = h.id
                    WHERE he.deployment_id = ?
                    ORDER BY he.started_at DESC
                    LIMIT ?
                ''', (deployment_id, limit)).fetchall()
            elif hook_id:
                rows = conn.execute('''
                    SELECT he.*, h.command, h.hook_type
                    FROM hook_executions he
                    JOIN deployment_hooks h ON he.hook_id = h.id
                    WHERE he.hook_id = ?
                    ORDER BY he.started_at DESC
                    LIMIT ?
                ''', (hook_id, limit)).fetchall()
            else:
                rows = conn.execute('''
                    SELECT he.*, h.command, h.hook_type
                    FROM hook_executions he
                    JOIN deployment_hooks h ON he.hook_id = h.id
                    ORDER BY he.started_at DESC
                    LIMIT ?
                ''', (limit,)).fetchall()
            
            return [dict(row) for row in rows]
    
    @classmethod
    def _run_ssh_command(cls, server_ip: str, command: str, 
                         timeout: int = DEFAULT_HOOK_TIMEOUT,
                         hook_id: str = None) -> Dict[str, Any]:
        """Run a command on a remote server via SSH."""
        start_time = datetime.utcnow()
        
        try:
            ssh_key = os.environ.get('SSH_KEY_PATH', '/root/.ssh/id_vps')
            
            # Wrap command in timeout
            full_command = [
                'ssh', '-i', ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                f'root@{server_ip}',
                f'timeout {timeout} bash -c {repr(command)}'
            ]
            
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout + 30  # Extra buffer for SSH overhead
            )
            
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            return {
                'success': result.returncode == 0,
                'exit_code': result.returncode,
                'output': result.stdout,
                'error': result.stderr,
                'duration': duration
            }
            
        except subprocess.TimeoutExpired:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            return {
                'success': False,
                'exit_code': 124,  # timeout exit code
                'output': '',
                'error': f'Hook timed out after {timeout} seconds',
                'duration': duration
            }
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            return {
                'success': False,
                'exit_code': -1,
                'output': '',
                'error': str(e),
                'duration': duration
            }
    
    @classmethod
    def _store_hook_execution(cls, hook: Dict, result: Dict, 
                              deployment_id: str = None):
        """Store hook execution result in database."""
        execution_id = db.generate_id()
        
        with db.get_db() as conn:
            conn.execute('''
                INSERT INTO hook_executions 
                (id, hook_id, deployment_id, success, servers_json, 
                 started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                execution_id,
                hook['id'],
                deployment_id,
                1 if result['success'] else 0,
                json.dumps(result['servers']),
                result['started_at'],
                result['finished_at']
            ))
            conn.commit()
    
    @classmethod
    def _log_hook_results(cls, deployment_id: str, hook_type: str, 
                          results: Dict):
        """Log hook results to deployment logs."""
        log_entry = f"\n[{datetime.utcnow().isoformat()}] {hook_type} hooks:\n"
        
        for hook_result in results.get('hooks', []):
            status = 'SUCCESS' if hook_result['success'] else 'FAILED'
            log_entry += f"  - {hook_result['command']}: {status}\n"
            
            for server, details in hook_result.get('servers', {}).items():
                server_status = 'ok' if details['success'] else 'failed'
                log_entry += f"    [{server}] {server_status}\n"
                if details.get('output'):
                    log_entry += f"    Output: {details['output'][:200]}\n"
                if details.get('error') and not details['success']:
                    log_entry += f"    Error: {details['error'][:200]}\n"
        
        # Append to deployment logs
        with db.get_db() as conn:
            conn.execute('''
                UPDATE deployments 
                SET logs = COALESCE(logs, '') || ?
                WHERE id = ?
            ''', (log_entry, deployment_id))
            conn.commit()


def execute_pre_deploy_hooks(app_id: str, environment: str, 
                             servers: List[Dict], deployment_id: str = None) -> Dict[str, Any]:
    """Execute pre-deploy hooks (stops deployment on failure)."""
    return HookExecutor.execute_hooks(
        app_id=app_id,
        hook_type='pre_deploy',
        environment=environment,
        servers=servers,
        deployment_id=deployment_id,
        stop_on_failure=True
    )


def execute_post_deploy_hooks(app_id: str, environment: str,
                              servers: List[Dict], deployment_id: str = None) -> Dict[str, Any]:
    """Execute post-deploy hooks."""
    return HookExecutor.execute_hooks(
        app_id=app_id,
        hook_type='post_deploy',
        environment=environment,
        servers=servers,
        deployment_id=deployment_id,
        stop_on_failure=False
    )


def execute_pre_rollback_hooks(app_id: str, environment: str,
                               servers: List[Dict], deployment_id: str = None) -> Dict[str, Any]:
    """Execute pre-rollback hooks."""
    return HookExecutor.execute_hooks(
        app_id=app_id,
        hook_type='pre_rollback',
        environment=environment,
        servers=servers,
        deployment_id=deployment_id,
        stop_on_failure=True
    )


def execute_post_rollback_hooks(app_id: str, environment: str,
                                servers: List[Dict], deployment_id: str = None) -> Dict[str, Any]:
    """Execute post-rollback hooks."""
    return HookExecutor.execute_hooks(
        app_id=app_id,
        hook_type='post_rollback',
        environment=environment,
        servers=servers,
        deployment_id=deployment_id,
        stop_on_failure=False
    )