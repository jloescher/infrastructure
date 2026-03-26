# PaaS Backend Patterns

> Backend implementation patterns for the Quantyra PaaS, adapted from Coolify analysis.

## Overview

This document covers Python backend patterns, API design, SSH management, and job queue implementation for the enhanced PaaS dashboard.

## Action Class Pattern

### Base Action Class

```python
# actions/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime
import traceback

@dataclass
class ActionResult:
    """Standard result object for all actions."""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

class BaseAction(ABC):
    """
    Abstract base class for infrastructure actions.
    
    All actions follow the same pattern:
    1. Initialize with parameters
    2. Validate in pre_execute
    3. Execute the main logic
    4. Cleanup in post_execute
    5. Return ActionResult
    """
    
    def __init__(self, app_name: str, server_ip: str, **kwargs):
        self.app_name = app_name
        self.server_ip = server_ip
        self.kwargs = kwargs
        self._start_time: Optional[datetime] = None
        self._ssh_client = None
    
    @property
    def ssh(self):
        """Lazy-loaded SSH connection."""
        if self._ssh_client is None:
            from services.ssh import SSHConnectionPool
            self._ssh_client = SSHConnectionPool().get_connection(self.server_ip)
        return self._ssh_client
    
    def execute(self) -> ActionResult:
        """Main execution method with error handling and timing."""
        self._start_time = datetime.utcnow()
        
        try:
            # Pre-execution validation
            if not self.pre_execute():
                return ActionResult(
                    success=False,
                    message="Pre-execution validation failed",
                    error="Validation failed"
                )
            
            # Execute main logic
            result = self._execute()
            
            # Post-execution cleanup
            self.post_execute(result)
            
            # Add duration
            if result.duration_ms is None:
                duration = (datetime.utcnow() - self._start_time).total_seconds() * 1000
                result.duration_ms = int(duration)
            
            return result
            
        except Exception as e:
            error_msg = str(e)
            stack_trace = traceback.format_exc()
            
            return ActionResult(
                success=False,
                message=f"Action failed: {error_msg}",
                error=stack_trace
            )
    
    @abstractmethod
    def _execute(self) -> ActionResult:
        """Implement actual action logic."""
        pass
    
    def pre_execute(self) -> bool:
        """Override for pre-execution validation."""
        return True
    
    def post_execute(self, result: ActionResult) -> None:
        """Override for post-execution cleanup."""
        pass
    
    def run_command(self, command: str, timeout: int = 300) -> tuple:
        """Execute SSH command and return (stdout, stderr, exit_code)."""
        from services.ssh import SSHConnectionPool
        return SSHConnectionPool().execute(self.server_ip, command, timeout)
```

### Deploy Action

```python
# actions/deploy.py
from actions.base import BaseAction, ActionResult
from typing import List, Optional
import json

class DeployApplicationAction(BaseAction):
    """
    Deploy an application to a server.
    
    Steps:
    1. Backup database
    2. Pull latest code
    3. Install dependencies
    4. Run migrations
    5. Restart services
    6. Health check
    """
    
    def __init__(
        self, 
        app_name: str, 
        server_ip: str,
        branch: str,
        environment: str,
        commit_sha: Optional[str] = None,
        skip_migrations: bool = False
    ):
        super().__init__(app_name, server_ip)
        self.branch = branch
        self.environment = environment
        self.commit_sha = commit_sha
        self.skip_migrations = skip_migrations
        
        # Determine deploy path
        self.deploy_path = f"/opt/apps/{app_name}"
        if environment == "staging":
            self.deploy_path = f"/opt/apps/{app_name}-staging"
    
    def pre_execute(self) -> bool:
        """Validate before deployment."""
        # Check if app directory exists
        stdout, stderr, code = self.run_command(f"test -d {self.deploy_path}")
        if code != 0:
            # First deploy - directory will be created
            self.kwargs['is_first_deploy'] = True
        return True
    
    def _execute(self) -> ActionResult:
        """Execute deployment steps."""
        steps = []
        
        # Step 1: Git pull or clone
        step_result = self._git_pull()
        steps.append(("git_pull", step_result))
        if not step_result['success']:
            return ActionResult(
                success=False,
                message="Git pull failed",
                error=step_result['error'],
                data={'steps': steps}
            )
        
        # Step 2: Install dependencies
        step_result = self._install_dependencies()
        steps.append(("install_deps", step_result))
        if not step_result['success']:
            return ActionResult(
                success=False,
                message="Dependency installation failed",
                error=step_result['error'],
                data={'steps': steps}
            )
        
        # Step 3: Run migrations
        if not self.skip_migrations:
            step_result = self._run_migrations()
            steps.append(("migrations", step_result))
            if not step_result['success']:
                return ActionResult(
                    success=False,
                    message="Migration failed",
                    error=step_result['error'],
                    data={'steps': steps}
                )
        
        # Step 4: Restart services
        step_result = self._restart_services()
        steps.append(("restart", step_result))
        if not step_result['success']:
            return ActionResult(
                success=False,
                message="Service restart failed",
                error=step_result['error'],
                data={'steps': steps}
            )
        
        # Step 5: Health check
        step_result = self._health_check()
        steps.append(("health_check", step_result))
        if not step_result['success']:
            return ActionResult(
                success=False,
                message="Health check failed",
                error=step_result['error'],
                data={'steps': steps}
            )
        
        return ActionResult(
            success=True,
            message=f"Successfully deployed {self.app_name} to {self.server_ip}",
            data={'steps': steps, 'commit': self.commit_sha}
        )
    
    def _git_pull(self) -> dict:
        """Pull or clone repository."""
        if self.kwargs.get('is_first_deploy'):
            # Clone repository
            app_config = self._get_app_config()
            cmd = f"git clone --branch {self.branch} {app_config['git_repo']} {self.deploy_path}"
        else:
            # Pull latest
            cmd = f"cd {self.deploy_path} && git fetch origin && git reset --hard origin/{self.branch}"
        
        stdout, stderr, code = self.run_command(cmd, timeout=120)
        
        if code == 0:
            # Get current commit
            stdout, _, _ = self.run_command(f"cd {self.deploy_path} && git rev-parse HEAD")
            self.commit_sha = stdout.strip()
        
        return {
            'success': code == 0,
            'output': stdout,
            'error': stderr if code != 0 else None
        }
    
    def _install_dependencies(self) -> dict:
        """Install framework-specific dependencies."""
        app_config = self._get_app_config()
        framework = app_config.get('framework', 'laravel')
        
        if framework == 'laravel':
            cmd = f"cd {self.deploy_path} && sudo -u webapps composer install --no-interaction --optimize-autoloader"
        elif framework in ['nextjs', 'svelte']:
            cmd = f"cd {self.deploy_path} && sudo -u webapps npm ci"
        elif framework == 'python':
            cmd = f"cd {self.deploy_path} && sudo -u webapps pip install -r requirements.txt"
        elif framework == 'go':
            cmd = f"cd {self.deploy_path} && sudo -u webapps go mod download"
        else:
            return {'success': True, 'output': 'No dependency installation needed'}
        
        stdout, stderr, code = self.run_command(cmd, timeout=600)
        return {
            'success': code == 0,
            'output': stdout,
            'error': stderr if code != 0 else None
        }
    
    def _run_migrations(self) -> dict:
        """Run database migrations."""
        app_config = self._get_app_config()
        framework = app_config.get('framework', 'laravel')
        
        if framework != 'laravel':
            return {'success': True, 'output': 'No migrations needed'}
        
        # Backup database first
        self._backup_database()
        
        cmd = f"cd {self.deploy_path} && php artisan migrate --force"
        stdout, stderr, code = self.run_command(cmd, timeout=120)
        
        return {
            'success': code == 0,
            'output': stdout,
            'error': stderr if code != 0 else None
        }
    
    def _restart_services(self) -> dict:
        """Restart application services."""
        app_config = self._get_app_config()
        framework = app_config.get('framework', 'laravel')
        
        if framework == 'laravel':
            # Reload PHP-FPM and nginx
            cmd = f"systemctl reload php8.5-fpm && systemctl reload nginx"
        else:
            # Restart systemd service
            service_name = f"{self.app_name}" if self.environment == 'production' else f"{self.app_name}-staging"
            cmd = f"systemctl restart {service_name}"
        
        stdout, stderr, code = self.run_command(cmd, timeout=30)
        return {
            'success': code == 0,
            'output': stdout,
            'error': stderr if code != 0 else None
        }
    
    def _health_check(self) -> dict:
        """Check application health."""
        import time
        
        app_config = self._get_app_config()
        port = app_config.get(f'port_{self.environment}', 8100)
        path = app_config.get('health_check_path', '/')
        
        # Wait for service to start
        time.sleep(5)
        
        # Health check
        cmd = f"curl -sf http://localhost:{port}{path} -o /dev/null"
        stdout, stderr, code = self.run_command(cmd, timeout=30)
        
        return {
            'success': code == 0,
            'output': f"Health check passed on port {port}",
            'error': stderr if code != 0 else None
        }
    
    def _backup_database(self) -> None:
        """Backup database before migration."""
        # Implementation for database backup
        pass
    
    def _get_app_config(self) -> dict:
        """Load application configuration."""
        from models.applications import get_application
        return get_application(self.app_name)


class RollbackAction(BaseAction):
    """Rollback to previous deployment."""
    
    def __init__(self, app_name: str, server_ip: str, target_commit: str, environment: str):
        super().__init__(app_name, server_ip)
        self.target_commit = target_commit
        self.environment = environment
    
    def _execute(self) -> ActionResult:
        """Execute rollback."""
        deploy_path = f"/opt/apps/{self.app_name}"
        if self.environment == "staging":
            deploy_path = f"/opt/apps/{self.app_name}-staging"
        
        # Reset to target commit
        cmd = f"cd {deploy_path} && git reset --hard {self.target_commit}"
        stdout, stderr, code = self.run_command(cmd)
        
        if code != 0:
            return ActionResult(
                success=False,
                message="Git reset failed",
                error=stderr
            )
        
        # Restart services
        cmd = "systemctl reload php8.5-fpm && systemctl reload nginx"
        stdout, stderr, code = self.run_command(cmd)
        
        if code != 0:
            return ActionResult(
                success=False,
                message="Service restart failed",
                error=stderr
            )
        
        return ActionResult(
            success=True,
            message=f"Rolled back to {self.target_commit[:8]}"
        )
```

## SSH Connection Management

### Connection Pool

```python
# services/ssh/pool.py
import paramiko
from typing import Dict, Optional, Tuple
from contextlib import contextmanager
import threading
import time
from dataclasses import dataclass

@dataclass
class SSHConnectionConfig:
    host: str
    username: str = "root"
    port: int = 22
    key_path: str = "/root/.ssh/id_vps"
    timeout: int = 30
    keepalive: int = 60

class SSHConnectionPool:
    """
    Thread-safe SSH connection pool for efficient remote execution.
    
    Features:
    - Connection reuse across requests
    - Automatic reconnection on failure
    - Connection health checks
    - Graceful cleanup
    """
    
    _instance = None
    _lock = threading.Lock()
    _pool: Dict[str, paramiko.SSHClient] = {}
    _last_used: Dict[str, float] = {}
    _config: Dict[str, SSHConnectionConfig] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @contextmanager
    def get_connection(self, host: str, config: Optional[SSHConnectionConfig] = None):
        """
        Get SSH connection from pool.
        
        Usage:
            with ssh_pool.get_connection("100.92.26.38") as client:
                stdin, stdout, stderr = client.exec_command("ls")
        """
        config = config or SSHConnectionConfig(host=host)
        key = f"{config.username}@{config.host}:{config.port}"
        
        client = None
        try:
            # Check if connection exists and is healthy
            if key in self._pool:
                client = self._pool[key]
                if self._is_connection_healthy(client):
                    self._last_used[key] = time.time()
                    yield client
                    return
                else:
                    # Remove unhealthy connection
                    self._close_connection(key)
            
            # Create new connection
            client = self._create_connection(config)
            self._pool[key] = client
            self._last_used[key] = time.time()
            self._config[key] = config
            yield client
            
        except Exception as e:
            # Remove failed connection
            if key in self._pool:
                self._close_connection(key)
            raise
    
    def execute(
        self, 
        host: str, 
        command: str, 
        timeout: int = 300,
        config: Optional[SSHConnectionConfig] = None
    ) -> Tuple[str, str, int]:
        """
        Execute command on remote host.
        
        Returns:
            (stdout, stderr, exit_code)
        """
        config = config or SSHConnectionConfig(host=host)
        
        with self.get_connection(host, config) as client:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            return (
                stdout.read().decode('utf-8', errors='replace'),
                stderr.read().decode('utf-8', errors='replace'),
                exit_code
            )
    
    def execute_script(self, host: str, script: str, timeout: int = 300) -> Tuple[str, str, int]:
        """Execute multi-line script on remote host."""
        # Use heredoc for multi-line scripts
        command = f"bash -s << 'EOF'\n{script}\nEOF"
        return self.execute(host, command, timeout)
    
    def upload_file(self, host: str, local_path: str, remote_path: str) -> bool:
        """Upload file to remote host via SFTP."""
        config = SSHConnectionConfig(host=host)
        
        with self.get_connection(host, config) as client:
            sftp = client.open_sftp()
            try:
                sftp.put(local_path, remote_path)
                return True
            finally:
                sftp.close()
    
    def download_file(self, host: str, remote_path: str, local_path: str) -> bool:
        """Download file from remote host via SFTP."""
        config = SSHConnectionConfig(host=host)
        
        with self.get_connection(host, config) as client:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, local_path)
                return True
            finally:
                sftp.close()
    
    def _create_connection(self, config: SSHConnectionConfig) -> paramiko.SSHClient:
        """Create new SSH connection."""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=config.host,
            port=config.port,
            username=config.username,
            key_filename=config.key_path,
            timeout=config.timeout,
            allow_agent=False,
            look_for_keys=False
        )
        
        # Set keepalive
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(config.keepalive)
        
        return client
    
    def _is_connection_healthy(self, client: paramiko.SSHClient) -> bool:
        """Check if connection is still healthy."""
        try:
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                return False
            
            # Send keepalive
            transport.send_ignore()
            return True
        except Exception:
            return False
    
    def _close_connection(self, key: str):
        """Close and remove connection from pool."""
        if key in self._pool:
            try:
                self._pool[key].close()
            except Exception:
                pass
            del self._pool[key]
            if key in self._last_used:
                del self._last_used[key]
    
    def cleanup_idle_connections(self, max_idle_seconds: int = 300):
        """Remove connections idle for too long."""
        now = time.time()
        for key, last_used in list(self._last_used.items()):
            if now - last_used > max_idle_seconds:
                self._close_connection(key)
    
    def close_all(self):
        """Close all connections (for shutdown)."""
        for key in list(self._pool.keys()):
            self._close_connection(key)


# Singleton instance
ssh_pool = SSHConnectionPool()
```

### SSH Command Builder

```python
# services/ssh/commands.py
from typing import List, Optional

class SSHCommandBuilder:
    """Build complex SSH commands safely."""
    
    def __init__(self):
        self._commands: List[str] = []
    
    def cd(self, path: str) -> 'SSHCommandBuilder':
        self._commands.append(f"cd {self._quote(path)}")
        return self
    
    def git_pull(self, branch: str = "main") -> 'SSHCommandBuilder':
        self._commands.append(f"git pull origin {self._quote(branch)}")
        return self
    
    def git_reset(self, commit: str) -> 'SSHCommandBuilder':
        self._commands.append(f"git reset --hard {self._quote(commit)}")
        return self
    
    def composer_install(self, production: bool = True) -> 'SSHCommandBuilder':
        flags = "--no-interaction --optimize-autoloader"
        if production:
            flags += " --no-dev"
        self._commands.append(f"composer install {flags}")
        return self
    
    def npm_install(self) -> 'SSHCommandBuilder':
        self._commands.append("npm ci")
        return self
    
    def artisan(self, command: str, *args) -> 'SSHCommandBuilder':
        cmd = f"php artisan {command}"
        if args:
            cmd += " " + " ".join(args)
        self._commands.append(cmd)
        return self
    
    def systemctl(self, action: str, service: str) -> 'SSHCommandBuilder':
        self._commands.append(f"systemctl {action} {self._quote(service)}")
        return self
    
    def curl(self, url: str, options: str = "-sf") -> 'SSHCommandBuilder':
        self._commands.append(f"curl {options} {self._quote(url)}")
        return self
    
    def env_export(self, key: str, value: str) -> 'SSHCommandBuilder':
        self._commands.append(f"export {key}={self._quote(value)}")
        return self
    
    def sudo(self, user: str, command: str) -> 'SSHCommandBuilder':
        self._commands.append(f"sudo -u {user} {command}")
        return self
    
    def if_exists(self, path: str, command: str) -> 'SSHCommandBuilder':
        self._commands.append(f"[ -f {self._quote(path)} ] && {command}")
        return self
    
    def build(self) -> str:
        """Build final command string."""
        return " && ".join(self._commands)
    
    def build_script(self) -> str:
        """Build as multi-line script."""
        return "\n".join(self._commands)
    
    @staticmethod
    def _quote(s: str) -> str:
        """Safely quote string for shell."""
        if not s:
            return "''"
        if s.isalnum() or s in ('/', '-', '_', '.'):
            return s
        return f"'{s.replace(\"'\", \"'\\''\")}'"


# Usage
cmd = (SSHCommandBuilder()
    .cd("/opt/apps/myapp")
    .git_pull("main")
    .sudo("webapps", "composer install --no-interaction")
    .artisan("migrate", "--force")
    .systemctl("reload", "php8.5-fpm")
    .build())

# Output: cd /opt/apps/myapp && git pull origin main && sudo -u webapps composer install --no-interaction && php artisan migrate --force && systemctl reload php8.5-fpm
```

## Celery Job Queue

### Configuration

```python
# tasks/__init__.py
from celery import Celery
import os

# Celery app configuration
app = Celery('quantyra')

app.conf.update(
    # Broker (Redis)
    broker_url=os.environ.get(
        'CELERY_BROKER_URL',
        'redis://:CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk@100.126.103.51:6379/1'
    ),
    
    # Result backend (Redis)
    result_backend=os.environ.get(
        'CELERY_RESULT_BACKEND',
        'redis://:CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk@100.126.103.51:6379/2'
    ),
    
    # Task settings
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='UTC',
    enable_utc=True,
    
    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit
    
    # Result expiration
    result_expires=86400,  # 24 hours
    
    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=2,
    
    # Task routing
    task_routes={
        'tasks.deploy.*': {'queue': 'deploy'},
        'tasks.backup.*': {'queue': 'backup'},
        'tasks.ssl.*': {'queue': 'ssl'},
    },
    
    # Beat schedule (periodic tasks)
    beat_schedule={
        'cleanup-old-deployments': {
            'task': 'tasks.maintenance.cleanup_old_deployments',
            'schedule': 86400.0,  # Daily
        },
        'check-ssl-expiration': {
            'task': 'tasks.ssl.check_ssl_expiration',
            'schedule': 43200.0,  # Twice daily
        },
        'backup-databases': {
            'task': 'tasks.backup.backup_all_databases',
            'schedule': 3600.0,  # Hourly
        },
    },
)
```

### Deploy Task

```python
# tasks/deploy.py
from celery import shared_task, current_task
from celery.result import AsyncResult
import redis
import json
from datetime import datetime
from typing import List, Optional

# Redis for progress updates
redis_client = redis.Redis(
    host='100.126.103.51',
    port=6379,
    password='CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk',
    db=3
)

def emit_progress(task_id: str, step: str, status: str, data: dict = None):
    """Emit progress update to Redis pub/sub."""
    channel = f"deploy:{task_id}"
    message = {
        'task_id': task_id,
        'step': step,
        'status': status,
        'timestamp': datetime.utcnow().isoformat(),
        'data': data or {}
    }
    redis_client.publish(channel, json.dumps(message))
    
    # Also store latest state for reconnection
    redis_client.setex(f"deploy:{task_id}:state", 3600, json.dumps(message))

@shared_task(bind=True, max_retries=3)
def deploy_application(
    self,
    app_name: str,
    branch: str,
    environment: str,
    triggered_by: str = "manual"
) -> dict:
    """
    Background task for application deployment.
    
    Args:
        app_name: Application name
        branch: Git branch to deploy
        environment: 'production' or 'staging'
        triggered_by: 'manual', 'webhook', 'scheduled'
    
    Returns:
        Deployment result with commit SHA and status
    """
    from actions.deploy import DeployApplicationAction
    from models.applications import get_application, update_last_deploy
    from models.deployments import create_deployment, update_deployment
    
    task_id = self.request.id
    
    # Get app config
    app = get_application(app_name)
    if not app:
        emit_progress(task_id, 'init', 'failed', {'error': 'Application not found'})
        return {'success': False, 'error': 'Application not found'}
    
    servers = app.get('servers', ['100.92.26.38', '100.89.130.19'])
    deployment_results = []
    
    # Create deployment record
    deployment_id = create_deployment(
        app_id=app['id'],
        environment=environment,
        branch=branch,
        trigger_type=triggered_by,
        status='running'
    )
    
    emit_progress(task_id, 'init', 'running', {
        'app': app_name,
        'environment': environment,
        'branch': branch
    })
    
    try:
        # Deploy to each server (primary first)
        for i, server_ip in enumerate(servers):
            server_name = 'primary' if i == 0 else 'secondary'
            
            emit_progress(task_id, f'deploy_{server_name}', 'running', {
                'server': server_ip,
                'step': 'starting'
            })
            
            # Execute deploy action
            action = DeployApplicationAction(
                app_name=app_name,
                server_ip=server_ip,
                branch=branch,
                environment=environment
            )
            
            result = action.execute()
            
            if not result.success:
                # Mark deployment failed
                update_deployment(deployment_id, {
                    'status': 'failed',
                    'error_message': result.message,
                    'error_output': result.error
                })
                
                # If primary fails, don't deploy to secondary
                if i == 0:
                    emit_progress(task_id, 'failed', 'error', {
                        'error': result.message,
                        'rollback': 'not_available' if action.kwargs.get('is_first_deploy') else 'available'
                    })
                    return {
                        'success': False,
                        'error': result.message,
                        'can_rollback': not action.kwargs.get('is_first_deploy', False)
                    }
            
            deployment_results.append({
                'server': server_ip,
                'success': result.success,
                'commit': result.data.get('commit') if result.data else None
            })
            
            emit_progress(task_id, f'deploy_{server_name}', 'success', {
                'server': server_ip,
                'commit': result.data.get('commit') if result.data else None
            })
        
        # Update deployment record
        update_deployment(deployment_id, {
            'status': 'success',
            'commit_sha': deployment_results[0].get('commit')
        })
        
        # Update app last deploy status
        update_last_deploy(app_name, {
            'status': 'success',
            'commit': deployment_results[0].get('commit'),
            'branch': branch,
            'environment': environment,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        emit_progress(task_id, 'complete', 'success', {
            'commit': deployment_results[0].get('commit'),
            'servers': deployment_results
        })
        
        return {
            'success': True,
            'commit': deployment_results[0].get('commit'),
            'servers': deployment_results
        }
        
    except Exception as e:
        update_deployment(deployment_id, {
            'status': 'failed',
            'error_message': str(e)
        })
        
        emit_progress(task_id, 'failed', 'error', {'error': str(e)})
        return {'success': False, 'error': str(e)}


@shared_task
def rollback_deployment(
    app_name: str,
    environment: str,
    target_commit: str
) -> dict:
    """Rollback to a specific commit."""
    from actions.deploy import RollbackAction
    from models.applications import get_application
    
    app = get_application(app_name)
    servers = app.get('servers', ['100.92.26.38', '100.89.130.19'])
    
    results = []
    for server_ip in servers:
        action = RollbackAction(
            app_name=app_name,
            server_ip=server_ip,
            target_commit=target_commit,
            environment=environment
        )
        result = action.execute()
        results.append({
            'server': server_ip,
            'success': result.success,
            'message': result.message
        })
    
    all_success = all(r['success'] for r in results)
    return {
        'success': all_success,
        'results': results
    }


def get_deploy_status(task_id: str) -> dict:
    """Get current deployment status from Redis."""
    state = redis_client.get(f"deploy:{task_id}:state")
    if state:
        return json.loads(state)
    
    # Check Celery result
    result = AsyncResult(task_id)
    return {
        'task_id': task_id,
        'status': result.status,
        'result': result.result if result.ready() else None
    }
```

### Backup Task

```python
# tasks/backup.py
from celery import shared_task
from datetime import datetime
import subprocess

@shared_task
def backup_database(db_name: str, db_host: str = '100.102.220.16', db_port: int = 5000) -> dict:
    """Backup a single database."""
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backup_path = f"/backup/postgresql/{db_name}_{timestamp}.sql.gz"
    
    # pg_dump with compression
    cmd = f"pg_dump -h {db_host} -p {db_port} -U patroni_superuser {db_name} | gzip > {backup_path}"
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode == 0:
        # Upload to S3
        s3_path = f"s3://quantyra-backups/postgresql/{db_name}/{timestamp}.sql.gz"
        subprocess.run(f"aws s3 cp {backup_path} {s3_path}", shell=True)
        
        return {'success': True, 'backup_path': backup_path, 's3_path': s3_path}
    else:
        return {'success': False, 'error': result.stderr}


@shared_task
def backup_all_databases() -> dict:
    """Backup all databases (scheduled hourly)."""
    from models.databases import get_all_databases
    
    databases = get_all_databases()
    results = []
    
    for db in databases:
        result = backup_database.delay(db['name'])
        results.append({'database': db['name'], 'task_id': result.id})
    
    return {'success': True, 'backups_started': len(results)}
```

## WebSocket Integration

### Flask-SocketIO Setup

```python
# websocket/__init__.py
from flask_socketio import SocketIO
from flask import Flask

socketio = SocketIO(
    async_mode='eventlet',
    message_queue='redis://:CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk@100.126.103.51:6379/3',
    cors_allowed_origins=[
        'http://100.102.220.16:8080',
        'http://localhost:8080'
    ]
)

def init_socketio(app: Flask):
    """Initialize Socket.IO with Flask app."""
    socketio.init_app(app)
    return socketio
```

### Event Handlers

```python
# websocket/handlers.py
from flask_socketio import emit, join_room, leave_room
from flask import request
import redis
import json

redis_client = redis.Redis(
    host='100.126.103.51',
    port=6379,
    password='CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk',
    db=3
)

def socketio_handlers(socketio):
    
    @socketio.on('connect')
    def handle_connect():
        """Client connected."""
        emit('connected', {'status': 'ok'})
    
    @socketio.on('disconnect')
    def handle_disconnect():
        """Client disconnected."""
        pass
    
    @socketio.on('subscribe_deploy')
    def handle_subscribe_deploy(data):
        """Subscribe to deployment progress updates."""
        task_id = data.get('task_id')
        if task_id:
            join_room(f"deploy:{task_id}")
            
            # Send current state if available
            state = redis_client.get(f"deploy:{task_id}:state")
            if state:
                emit('deploy_state', json.loads(state))
    
    @socketio.on('unsubscribe_deploy')
    def handle_unsubscribe_deploy(data):
        """Unsubscribe from deployment updates."""
        task_id = data.get('task_id')
        if task_id:
            leave_room(f"deploy:{task_id}")
    
    @socketio.on('subscribe_app')
    def handle_subscribe_app(data):
        """Subscribe to application updates."""
        app_name = data.get('app_name')
        if app_name:
            join_room(f"app:{app_name}")
    
    @socketio.on('subscribe_server')
    def handle_subscribe_server(data):
        """Subscribe to server metrics."""
        server_name = data.get('server_name')
        if server_name:
            join_room(f"server:{server_name}")


# Background thread to listen for Redis messages
def redis_listener():
    """Listen for Redis pub/sub messages and emit to Socket.IO."""
    pubsub = redis_client.pubsub()
    pubsub.psubscribe('deploy:*', 'app:*', 'server:*')
    
    for message in pubsub.listen():
        if message['type'] == 'pmessage':
            channel = message['channel'].decode()
            data = json.loads(message['data'])
            
            # Emit to appropriate room
            socketio.emit('update', data, room=channel)
```

### Progress Emitter

```python
# services/progress.py
import redis
import json
from datetime import datetime
from flask_socketio import SocketIO

class ProgressEmitter:
    """Emit deployment progress to WebSocket clients."""
    
    def __init__(self, task_id: str, socketio: SocketIO = None):
        self.task_id = task_id
        self.redis = redis.Redis(
            host='100.126.103.51',
            port=6379,
            password='CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk',
            db=3
        )
        self.socketio = socketio
        self.room = f"deploy:{task_id}"
    
    def emit(self, step: str, status: str, data: dict = None):
        """Emit progress update."""
        message = {
            'task_id': self.task_id,
            'step': step,
            'status': status,
            'timestamp': datetime.utcnow().isoformat(),
            'data': data or {}
        }
        
        # Publish to Redis (for Celery workers without Socket.IO)
        self.redis.publish(self.room, json.dumps(message))
        
        # Store state for reconnection
        self.redis.setex(f"{self.room}:state", 3600, json.dumps(message))
        
        # Emit directly if Socket.IO available
        if self.socketio:
            self.socketio.emit('deploy_progress', message, room=self.room)
```

## API Design Patterns

### RESTful API

```python
# api/applications.py
from flask import Blueprint, request, jsonify
from functools import wraps

api_applications = Blueprint('api_applications', __name__, url_prefix='/api/applications')

def api_response(data=None, error=None, status=200):
    """Standard API response format."""
    return jsonify({
        'success': error is None,
        'data': data,
        'error': error
    }), status

@api_applications.route('', methods=['GET'])
def list_applications():
    """List all applications."""
    from models.applications import get_all_applications
    apps = get_all_applications()
    return api_response(data=apps)

@api_applications.route('/<app_name>', methods=['GET'])
def get_application(app_name):
    """Get application details."""
    from models.applications import get_application
    app = get_application(app_name)
    if not app:
        return api_response(error='Application not found', status=404)
    return api_response(data=app)

@api_applications.route('/<app_name>/deploy', methods=['POST'])
def deploy_application(app_name):
    """Trigger application deployment."""
    from tasks.deploy import deploy_application as deploy_task
    
    data = request.get_json() or {}
    branch = data.get('branch', 'main')
    environment = data.get('environment', 'production')
    
    # Queue deployment task
    result = deploy_task.delay(
        app_name=app_name,
        branch=branch,
        environment=environment,
        triggered_by='manual'
    )
    
    return api_response(data={
        'task_id': result.id,
        'status': 'queued',
        'message': 'Deployment started'
    }, status=202)

@api_applications.route('/<app_name>/rollback', methods=['POST'])
def rollback_application(app_name):
    """Rollback to previous deployment."""
    from tasks.deploy import rollback_deployment
    
    data = request.get_json() or {}
    target_commit = data.get('commit')
    environment = data.get('environment', 'production')
    
    if not target_commit:
        return api_response(error='Target commit required', status=400)
    
    result = rollback_deployment.delay(
        app_name=app_name,
        environment=environment,
        target_commit=target_commit
    )
    
    return api_response(data={
        'task_id': result.id,
        'status': 'queued'
    }, status=202)

@api_applications.route('/<app_name>/deploy/<task_id>/status', methods=['GET'])
def get_deploy_status(app_name, task_id):
    """Get deployment status."""
    from tasks.deploy import get_deploy_status as get_status
    status = get_status(task_id)
    return api_response(data=status)
```

### Error Handling

```python
# api/errors.py
from flask import jsonify
from werkzeug.exceptions import HTTPException

class APIError(Exception):
    """Custom API error."""
    def __init__(self, message: str, status_code: int = 400, payload: dict = None):
        super().__init__()
        self.message = message
        self.status_code = status_code
        self.payload = payload or {}
    
    def to_dict(self):
        result = dict(self.payload)
        result['success'] = False
        result['error'] = self.message
        return result

def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(error):
        return jsonify(error.to_dict()), error.status_code
    
    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        return jsonify({
            'success': False,
            'error': error.description,
            'status_code': error.code
        }), error.code
    
    @app.errorhandler(Exception)
    def handle_generic_error(error):
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(error) if app.debug else None
        }), 500
```

## Running Celery

### Start Workers

```bash
# Start Celery worker
celery -A tasks worker --loglevel=info --queue=deploy,backup,ssl

# Start Celery beat (scheduler)
celery -A tasks beat --loglevel=info

# Or run both
celery -A tasks worker --beat --loglevel=info
```

### Systemd Service

```ini
# /etc/systemd/system/celery-worker.service
[Unit]
Description=Celery Worker
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/dashboard
Environment="CELERY_BROKER_URL=redis://100.126.103.51:6379/1"
ExecStart=/usr/local/bin/celery -A tasks worker --loglevel=info --queues=deploy,backup,ssl
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Next Steps

1. **Phase 1**: Implement Action classes for existing deploy operations
2. **Phase 2**: Set up Celery with Redis broker
3. **Phase 3**: Add WebSocket support with flask-socketio
4. **Phase 4**: Migrate YAML config to PostgreSQL
5. **Phase 5**: Build API endpoints for dashboard

See [paas_roadmap.md](paas_roadmap.md) for implementation timeline.