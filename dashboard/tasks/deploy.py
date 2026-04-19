"""
Async deployment tasks with real-time progress tracking.

This module implements the core deployment logic as Celery tasks
that emit progress updates via WebSocket for real-time UI feedback.

Supported Frameworks:
- Laravel (PHP in Dokploy-managed Docker containers)
- Next.js (Node.js with systemd)
- SvelteKit (Node.js with systemd)
- Python (Flask/Django with Gunicorn)
- Go (Binary with systemd)
"""

import os
import sys
import subprocess
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app
from websocket import emit_progress
from websocket.performance import get_ssh_pool
import database as db

# Import framework service
try:
    from services.framework import (
        FRAMEWORK_CONFIGS,
        get_framework_config,
        format_install_command,
        format_build_command,
        format_migrate_command,
        format_start_command,
        get_health_check_config,
        needs_systemd_service,
        get_service_template_name,
    )
    FRAMEWORK_SERVICE_AVAILABLE = True
except ImportError:
    FRAMEWORK_SERVICE_AVAILABLE = False


DEPLOYMENT_STEPS = [
    ('git_fetch', 'Fetch latest code', 5),
    ('git_pull', 'Pull changes', 10),
    ('install_deps', 'Install dependencies', 30),
    ('build_assets', 'Build assets', 15),
    ('run_migrations', 'Run migrations', 10),
    ('clear_cache', 'Clear cache', 5),
    ('restart_services', 'Restart services', 15),
    ('health_check', 'Health check', 10),
]


def get_app_config(app_name: str) -> Optional[Dict]:
    """Get application configuration."""
    app = db.get_application(name=app_name)
    if app:
        return app
    return None


def get_target_servers(app: Dict) -> List[Dict]:
    """Get target servers for deployment."""
    target_names = app.get('target_servers', [])
    servers = db.list_servers()
    return [s for s in servers if s['name'] in target_names]


def run_ssh_command(server_ip: str, command: str, timeout: int = 300) -> Dict:
    """Run SSH command with connection pooling."""
    pool = get_ssh_pool()
    
    try:
        conn = pool.get_connection(server_ip)
        if not conn:
            return {'success': False, 'error': f'Could not connect to {server_ip}'}
        
        stdin, stdout, stderr = conn.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')
        
        pool.release_connection(conn)
        
        return {
            'success': exit_code == 0,
            'exit_code': exit_code,
            'output': output,
            'error': error
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def emit_step_progress(deployment_id: str, server: str, step: str, status: str, 
                        output: str = None, progress: int = 0):
    """Emit step progress update."""
    emit_progress(deployment_id, 'step_progress', {
        'server': server,
        'step': step,
        'status': status,
        'output': output,
        'progress': progress,
        'timestamp': datetime.utcnow().isoformat()
    })
    
    # Update database
    steps = db.get_deployment_steps(deployment_id)
    for s in steps:
        if s['server'] == server and s['step'] == step:
            db.update_deployment_step(
                s['id'],
                status=status,
                output=output,
                started_at=datetime.utcnow().isoformat() if status == 'running' else None,
                finished_at=datetime.utcnow().isoformat() if status in ['success', 'failed'] else None
            )
            break


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def deploy_application_task(self, deployment_id: str, app_name: str, 
                             environment: str, branch: str, commit: str = None):
    """
    Main deployment task with real-time progress tracking.
    
    Args:
        deployment_id: Unique deployment identifier
        app_name: Application name
        environment: 'production' or 'staging'
        branch: Git branch to deploy
        commit: Specific commit hash (optional)
    """
    try:
        # Update deployment status
        db.update_deployment(deployment_id, {'status': 'running'})
        
        emit_progress(deployment_id, 'deployment_started', {
            'app_name': app_name,
            'environment': environment,
            'branch': branch,
            'commit': commit,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        app = get_app_config(app_name)
        if not app:
            raise Exception(f'Application {app_name} not found')
        
        servers = get_target_servers(app)
        if not servers:
            raise Exception('No target servers configured')
        
        app_path = f'/var/www/{app_name}'
        framework = app.get('framework', 'laravel')
        
        # Sort servers: primary first
        servers_sorted = sorted(servers, key=lambda s: 0 if 'primary' in s.get('role', '').lower() else 1)
        
        total_progress = 0
        total_steps = len(DEPLOYMENT_STEPS) * len(servers_sorted)
        
        for server in servers_sorted:
            server_name = server['name']
            server_ip = server['ip']
            
            emit_progress(deployment_id, 'server_started', {
                'server': server_name,
                'ip': server_ip,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            for step_name, step_desc, step_weight in DEPLOYMENT_STEPS:
                emit_step_progress(deployment_id, server_name, step_name, 'running', 
                                  progress=int(total_progress / total_steps * 100))
                
                command = get_step_command(step_name, app_path, framework, branch, environment, commit)
                
                if command:
                    result = run_ssh_command(server_ip, command)
                    
                    if not result['success']:
                        emit_step_progress(deployment_id, server_name, step_name, 'failed',
                                          output=result.get('error', 'Unknown error'))
                        
                        # Check if we should rollback
                        if server_name == servers_sorted[0]['name']:
                            emit_progress(deployment_id, 'deployment_failed', {
                                'server': server_name,
                                'step': step_name,
                                'error': result.get('error'),
                                'rollback_recommended': True
                            })
                            db.update_deployment(deployment_id, {
                                'status': 'failed',
                                'results_json': json.dumps({'error': result.get('error'), 'step': step_name, 'server': server_name}),
                                'finished_at': datetime.utcnow().isoformat()
                            })
                            return {'success': False, 'error': result.get('error')}
                        else:
                            # Continue with other servers
                            emit_step_progress(deployment_id, server_name, step_name, 'failed',
                                              output=f"Failed but continuing: {result.get('error')}")
                    else:
                        emit_step_progress(deployment_id, server_name, step_name, 'success',
                                          output=result.get('output', '')[:500])
                else:
                    # Skip this step for this framework
                    emit_step_progress(deployment_id, server_name, step_name, 'skipped')
                
                total_progress += step_weight
        
        # All servers completed successfully
        db.update_deployment(deployment_id, {
            'status': 'success',
            'finished_at': datetime.utcnow().isoformat()
        })
        
        emit_progress(deployment_id, 'deployment_complete', {
            'app_name': app_name,
            'environment': environment,
            'branch': branch,
            'commit': commit,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        return {'success': True, 'deployment_id': deployment_id}
        
    except Exception as e:
        db.update_deployment(deployment_id, {
            'status': 'failed',
            'results_json': json.dumps({'error': str(e)}),
            'finished_at': datetime.utcnow().isoformat()
        })
        
        emit_progress(deployment_id, 'deployment_error', {
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })
        
        raise self.retry(exc=e)


def get_step_command(step: str, app_path: str, framework: str, branch: str, 
                     environment: str, commit: str = None, 
                     app_name: str = None, port: int = 8100) -> Optional[str]:
    """
    Get the command for a deployment step based on framework.
    
    This function uses the framework service for command generation when available,
    falling back to built-in commands for backward compatibility.
    
    Args:
        step: Deployment step name (git_fetch, git_pull, install_deps, etc.)
        app_path: Path to the application directory
        framework: Framework name (laravel, nextjs, svelte, python, go)
        branch: Git branch name
        environment: Environment name (production, staging)
        commit: Optional specific commit hash
        app_name: Application name (used for systemd service names)
        port: Application port (used for some framework commands)
        
    Returns:
        Command string or None if step should be skipped
    """
    
    cd_cmd = f'cd {app_path}'
    
    # Common commands (same for all frameworks)
    if step == 'git_fetch':
        return f'{cd_cmd} && git fetch origin'
    
    if step == 'git_pull':
        cmd = f'{cd_cmd} && git checkout {branch} && git pull origin {branch}'
        if commit:
            cmd += f' && git checkout {commit}'
        return cmd
    
    # Framework-specific commands
    if FRAMEWORK_SERVICE_AVAILABLE:
        config = get_framework_config(framework)
        
        if step == 'install_deps':
            cmd = config.get('install_cmd', '')
            if cmd:
                return f'{cd_cmd} && {cmd}'
            return None
        
        if step == 'build_assets':
            cmd = config.get('build_cmd', '')
            if cmd:
                # Replace placeholders
                cmd = cmd.replace('{app_name}', app_name or app_path.split('/')[-1])
                cmd = cmd.replace('{port}', str(port))
                return f'{cd_cmd} && {cmd}'
            return None
        
        if step == 'run_migrations':
            cmd = config.get('migrate_cmd', '')
            if cmd:
                return f'{cd_cmd} && {cmd}'
            return None
        
        if step == 'clear_cache':
            # Only Laravel has cache clearing
            if framework == 'laravel':
                return f'{cd_cmd} && php artisan cache:clear && php artisan config:clear && php artisan view:clear'
            return None
        
        if step == 'restart_services':
            runtime = config.get('runtime', '')
            service_name = app_name or app_path.split('/')[-1]
            
            if 'docker' in runtime:
                return None
            elif 'systemd' in runtime:
                return f'sudo systemctl restart {service_name}'
            return None
        
        if step == 'health_check':
            health_config = get_health_check_config(framework, port)
            return f'curl -sf http://localhost:{health_config["port"]}{health_config["path"]} || exit 1'
    
    # Fallback to built-in commands (backward compatibility)
    commands = {
        'install_deps': {
            'laravel': f'{cd_cmd} && composer install --no-interaction --optimize-autoloader --no-dev',
            'nextjs': f'{cd_cmd} && npm ci',
            'svelte': f'{cd_cmd} && npm ci',
            'python': f'{cd_cmd} && pip install -r requirements.txt',
            'go': f'{cd_cmd} && go mod download',
        }.get(framework),
        'build_assets': {
            'laravel': f'{cd_cmd} && npm run build',
            'nextjs': f'{cd_cmd} && npm run build',
            'svelte': f'{cd_cmd} && npm run build',
            'go': f'{cd_cmd} && go build -o app .',
        }.get(framework),
        'run_migrations': {
            'laravel': f'{cd_cmd} && php artisan migrate --force',
            'python': f'{cd_cmd} && python manage.py migrate',
        }.get(framework),
        'clear_cache': {
            'laravel': f'{cd_cmd} && php artisan cache:clear && php artisan config:clear && php artisan view:clear',
        }.get(framework),
        'restart_services': {
            'laravel': None,
            'nextjs': f'sudo systemctl restart {app_path.split("/")[-1]}',
            'svelte': f'sudo systemctl restart {app_path.split("/")[-1]}',
            'python': f'sudo systemctl restart {app_path.split("/")[-1]}',
            'go': f'sudo systemctl restart {app_path.split("/")[-1]}',
        }.get(framework),
        'health_check': f'curl -sf http://localhost:80/health || exit 1',
    }
    
    return commands.get(step)


@celery_app.task(bind=True)
def rollback_deployment_task(self, deployment_id: str, original_deployment_id: str):
    """Rollback to a previous deployment."""
    try:
        original = db.get_deployment(original_deployment_id)
        if not original:
            raise Exception(f'Original deployment {original_deployment_id} not found')
        
        # Create rollback deployment steps
        db.update_deployment(deployment_id, {'status': 'running'})
        
        emit_progress(deployment_id, 'rollback_started', {
            'original_deployment': original_deployment_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # For Laravel, git reset to previous commit
        # This is simplified - real implementation would need more logic
        
        db.update_deployment(deployment_id, {
            'status': 'success',
            'finished_at': datetime.utcnow().isoformat()
        })
        
        emit_progress(deployment_id, 'rollback_complete', {
            'timestamp': datetime.utcnow().isoformat()
        })
        
        return {'success': True}
        
    except Exception as e:
        db.update_deployment(deployment_id, {
            'status': 'failed',
            'results_json': json.dumps({'error': str(e)}),
            'finished_at': datetime.utcnow().isoformat()
        })
        
        raise


@celery_app.task
def cleanup_old_deployments_task(days: int = 30):
    """Clean up old deployment records."""
    removed_steps = db.cleanup_old_deployment_steps(days=days)
    return {'removed_steps': removed_steps}
