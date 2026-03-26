# PaaS Backend Patterns

> Backend implementation patterns for the Quantyra PaaS, adapted from Coolify analysis.

## Overview

This document covers Python backend patterns, API design, SSH management, job queue implementation, and configuration sync for the portable PaaS dashboard.

## SQLite Database Connection

### Connection Pool for SQLite

```python
# services/database.py
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional
import os

class SQLiteConnectionPool:
    """
    Thread-safe SQLite connection pool.
    
    SQLite handles connections differently than PostgreSQL:
    - Single file-based database
    - WAL mode for concurrent read/write
    - Connection per thread
    """
    
    _instance = None
    _lock = threading.Lock()
    _local = threading.local()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.db_path = os.environ.get('SQLITE_DB_PATH', '/data/paas.db')
        self._ensure_database()
    
    def _ensure_database(self):
        """Ensure database exists with proper settings."""
        if not os.path.exists(self.db_path):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB
            conn.close()
    
    @contextmanager
    def get_connection(self):
        """Get thread-local connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            self._local.connection.execute("PRAGMA foreign_keys=ON")
            self._local.connection.row_factory = sqlite3.Row
        
        try:
            yield self._local.connection
        except Exception:
            # Rollback on error
            self._local.connection.rollback()
            raise
    
    def execute(self, query: str, params: tuple = None) -> sqlite3.Cursor:
        """Execute query and return cursor."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
            return cursor
    
    def fetchone(self, query: str, params: tuple = None) -> Optional[dict]:
        """Execute query and return single row as dict."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def fetchall(self, query: str, params: tuple = None) -> list:
        """Execute query and return all rows as dicts."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]


# Singleton instance
db = SQLiteConnectionPool()
```

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

## Configuration Export/Import

### Export Service

```python
# services/config_export.py
import json
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from services.database import db
from services.secrets.vault import SecretVault

class ConfigExporter:
    """Export all PaaS configuration to portable format."""
    
    def __init__(self, include_secrets: bool = True):
        self.include_secrets = include_secrets
        self.vault = SecretVault() if include_secrets else None
    
    def export_all(self) -> Dict[str, Any]:
        """Export all configuration to dictionary."""
        export = {
            'version': '1.0',
            'exported_at': datetime.utcnow().isoformat() + 'Z',
            'checksum': None,  # Calculated at end
            'data': {
                'applications': self._export_applications(),
                'domains': self._export_domains(),
                'servers': self._export_servers(),
                'databases': self._export_databases(),
                'deployment_history': self._export_deployment_history(),
                'secrets': self._export_secrets() if self.include_secrets else {}
            }
        }
        
        # Calculate checksum
        export['checksum'] = self._calculate_checksum(export['data'])
        
        return export
    
    def _export_applications(self) -> list:
        """Export all applications."""
        apps = db.fetchall("""
            SELECT * FROM applications ORDER BY created_at
        """)
        
        for app in apps:
            # Get environments
            app['environments'] = db.fetchall("""
                SELECT * FROM environments WHERE app_id = ?
            """, (app['id'],))
            
            # Get environment variables (encrypted)
            env_vars = db.fetchall("""
                SELECT key_name, scope, is_sensitive, source, created_at
                FROM environment_variables WHERE app_id = ?
            """, (app['id'],))
            
            if self.include_secrets:
                # Include encrypted values
                env_vars_full = db.fetchall("""
                    SELECT * FROM environment_variables WHERE app_id = ?
                """, (app['id'],))
                app['environment_variables'] = env_vars_full
            else:
                app['environment_variables'] = env_vars
        
        return apps
    
    def _export_domains(self) -> list:
        """Export all domains."""
        return db.fetchall("""
            SELECT d.*, a.name as app_name
            FROM domains d
            JOIN applications a ON d.app_id = a.id
            ORDER BY d.created_at
        """)
    
    def _export_servers(self) -> list:
        """Export all servers."""
        return db.fetchall("""
            SELECT * FROM servers ORDER BY name
        """)
    
    def _export_databases(self) -> list:
        """Export all database resources."""
        return db.fetchall("""
            SELECT r.*, rd.*, a.name as app_name
            FROM resources r
            JOIN resource_databases rd ON r.id = rd.resource_id
            JOIN applications a ON r.app_id = a.id
            WHERE r.type = 'database'
            ORDER BY r.created_at
        """)
    
    def _export_deployment_history(self, limit: int = 100) -> list:
        """Export recent deployment history."""
        return db.fetchall("""
            SELECT d.*, a.name as app_name, s.name as server_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            JOIN servers s ON d.server_id = s.id
            ORDER BY d.created_at DESC
            LIMIT ?
        """, (limit,))
    
    def _export_secrets(self) -> Dict[str, Any]:
        """Export encrypted secrets."""
        if not self.vault:
            return {}
        
        secrets = {}
        apps = db.fetchall("SELECT name FROM applications")
        
        for app in apps:
            app_secrets = self.vault.get_app_secrets(app['name'])
            if app_secrets:
                secrets[app['name']] = app_secrets
        
        return secrets
    
    def _calculate_checksum(self, data: Any) -> str:
        """Calculate SHA-256 checksum of data."""
        content = json.dumps(data, sort_keys=True, default=str)
        return 'sha256:' + hashlib.sha256(content.encode()).hexdigest()
    
    def export_to_file(self, filepath: str) -> Dict[str, Any]:
        """Export configuration to file."""
        export = self.export_all()
        
        with open(filepath, 'w') as f:
            json.dump(export, f, indent=2, default=str)
        
        # Record export in database
        export_id = str(uuid.uuid4())
        db.execute("""
            INSERT INTO config_exports (id, export_type, file_path, checksum, 
                                        size_bytes, includes_secrets, apps_count, 
                                        domains_count, secrets_count)
            VALUES (?, 'manual', ?, ?, ?, ?, 
                   (SELECT COUNT(*) FROM applications),
                   (SELECT COUNT(*) FROM domains),
                   (SELECT COUNT(*) FROM environment_variables))
        """, (
            export_id,
            filepath,
            export['checksum'],
            len(json.dumps(export)),
            1 if self.include_secrets else 0
        ))
        
        return {
            'export_id': export_id,
            'filepath': filepath,
            'checksum': export['checksum'],
            'apps_count': len(export['data']['applications']),
            'domains_count': len(export['data']['domains'])
        }
```

### Import Service

```python
# services/config_import.py
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from services.database import db
from services.secrets.vault import SecretVault

class ConfigImporter:
    """Import configuration from export file."""
    
    def __init__(self):
        self.vault = SecretVault()
        self.errors = []
        self.warnings = []
    
    def validate(self, export: Dict[str, Any]) -> Dict[str, Any]:
        """Validate export data without importing."""
        errors = []
        warnings = []
        
        # Check version
        if export.get('version') != '1.0':
            errors.append(f"Unsupported export version: {export.get('version')}")
        
        # Validate applications
        for app in export.get('data', {}).get('applications', []):
            if not app.get('name'):
                errors.append("Application missing name")
            if not app.get('git_repo'):
                errors.append(f"Application {app.get('name', 'unknown')} missing git_repo")
        
        # Validate domains
        for domain in export.get('data', {}).get('domains', []):
            if not domain.get('domain_name'):
                errors.append("Domain missing domain_name")
        
        # Check for conflicts
        existing_apps = set(row['name'] for row in db.fetchall("SELECT name FROM applications"))
        for app in export.get('data', {}).get('applications', []):
            if app.get('name') in existing_apps:
                warnings.append(f"Application '{app['name']}' already exists and will be updated")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'stats': {
                'apps_count': len(export.get('data', {}).get('applications', [])),
                'domains_count': len(export.get('data', {}).get('domains', [])),
                'servers_count': len(export.get('data', {}).get('servers', [])),
                'secrets_count': sum(len(s) for s in export.get('data', {}).get('secrets', {}).values())
            }
        }
    
    def import_config(self, export: Dict[str, Any], mode: str = 'merge') -> Dict[str, Any]:
        """
        Import configuration.
        
        Args:
            export: Export data dictionary
            mode: 'merge' (add new, update existing), 'replace' (clear all, then import)
        
        Returns:
            Import results
        """
        import_id = str(uuid.uuid4())
        started_at = datetime.utcnow().isoformat()
        
        # Record import start
        db.execute("""
            INSERT INTO config_imports (id, source, import_mode, validation_passed, import_status, started_at)
            VALUES (?, 'file', ?, 1, 'running', ?)
        """, (import_id, mode, started_at))
        
        results = {
            'import_id': import_id,
            'apps_imported': 0,
            'apps_updated': 0,
            'apps_skipped': 0,
            'domains_imported': 0,
            'secrets_imported': 0,
            'errors': [],
            'warnings': []
        }
        
        try:
            if mode == 'replace':
                self._clear_all()
            
            data = export.get('data', {})
            
            # Import servers first
            self._import_servers(data.get('servers', []))
            
            # Import applications
            app_results = self._import_applications(data.get('applications', []), mode)
            results['apps_imported'] = app_results['imported']
            results['apps_updated'] = app_results['updated']
            results['apps_skipped'] = app_results['skipped']
            
            # Import domains
            results['domains_imported'] = self._import_domains(data.get('domains', []))
            
            # Import secrets
            results['secrets_imported'] = self._import_secrets(data.get('secrets', {}))
            
            # Update import record
            db.execute("""
                UPDATE config_imports 
                SET import_status = 'success',
                    apps_imported = ?,
                    apps_updated = ?,
                    apps_skipped = ?,
                    domains_imported = ?,
                    secrets_imported = ?,
                    completed_at = ?
                WHERE id = ?
            """, (
                results['apps_imported'],
                results['apps_updated'],
                results['apps_skipped'],
                results['domains_imported'],
                results['secrets_imported'],
                datetime.utcnow().isoformat(),
                import_id
            ))
            
        except Exception as e:
            db.execute("""
                UPDATE config_imports 
                SET import_status = 'failed', error_message = ?, completed_at = ?
                WHERE id = ?
            """, (str(e), datetime.utcnow().isoformat(), import_id))
            results['errors'].append(str(e))
        
        return results
    
    def _clear_all(self):
        """Clear all configuration (for replace mode)."""
        db.execute("DELETE FROM environment_variables")
        db.execute("DELETE FROM domains")
        db.execute("DELETE FROM deployments")
        db.execute("DELETE FROM environments")
        db.execute("DELETE FROM resource_databases")
        db.execute("DELETE FROM resources")
        db.execute("DELETE FROM applications")
        # Keep servers - they're infrastructure
    
    def _import_servers(self, servers: list) -> int:
        """Import servers."""
        count = 0
        for server in servers:
            existing = db.fetchone(
                "SELECT id FROM servers WHERE name = ?", 
                (server['name'],)
            )
            if existing:
                continue  # Don't update existing servers
            
            db.execute("""
                INSERT INTO servers (id, name, hostname, tailscale_ip, public_ip,
                                    server_type, location, cpu_cores, memory_gb, disk_gb, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """, (
                str(uuid.uuid4()),
                server['name'],
                server.get('hostname'),
                server['tailscale_ip'],
                server.get('public_ip'),
                server['server_type'],
                server.get('location'),
                server.get('cpu_cores'),
                server.get('memory_gb'),
                server.get('disk_gb')
            ))
            count += 1
        return count
    
    def _import_applications(self, apps: list, mode: str) -> dict:
        """Import applications."""
        results = {'imported': 0, 'updated': 0, 'skipped': 0}
        
        for app in apps:
            existing = db.fetchone(
                "SELECT id FROM applications WHERE name = ?",
                (app['name'],)
            )
            
            if existing and mode == 'merge':
                # Update existing
                db.execute("""
                    UPDATE applications SET
                        display_name = ?, description = ?, git_repo = ?,
                        framework = ?, git_branch_production = ?,
                        git_branch_staging = ?, port_production = ?,
                        port_staging = ?, staging_enabled = ?,
                        updated_at = ?
                    WHERE id = ?
                """, (
                    app.get('display_name'),
                    app.get('description'),
                    app['git_repo'],
                    app.get('framework', 'laravel'),
                    app.get('git_branch_production', 'main'),
                    app.get('git_branch_staging', 'staging'),
                    app.get('port_production'),
                    app.get('port_staging'),
                    app.get('staging_enabled', 1),
                    datetime.utcnow().isoformat(),
                    existing['id']
                ))
                results['updated'] += 1
            elif not existing:
                # Create new
                app_id = str(uuid.uuid4())
                db.execute("""
                    INSERT INTO applications (id, name, display_name, description,
                                             git_repo, framework, git_branch_production,
                                             git_branch_staging, port_production, port_staging,
                                             staging_enabled, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'created')
                """, (
                    app_id,
                    app['name'],
                    app.get('display_name'),
                    app.get('description'),
                    app['git_repo'],
                    app.get('framework', 'laravel'),
                    app.get('git_branch_production', 'main'),
                    app.get('git_branch_staging', 'staging'),
                    app.get('port_production'),
                    app.get('port_staging'),
                    app.get('staging_enabled', 1)
                ))
                results['imported'] += 1
            else:
                results['skipped'] += 1
        
        return results
    
    def _import_domains(self, domains: list) -> int:
        """Import domains."""
        count = 0
        for domain in domains:
            existing = db.fetchone(
                "SELECT id FROM domains WHERE domain_name = ?",
                (domain['domain_name'],)
            )
            
            if existing:
                continue
            
            # Get app_id
            app = db.fetchone(
                "SELECT id FROM applications WHERE name = ?",
                (domain.get('app_name'),)
            )
            if not app:
                continue
            
            db.execute("""
                INSERT INTO domains (id, app_id, domain_name, domain_type,
                                    ssl_status, auth_enabled, auth_password_encrypted, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
            """, (
                str(uuid.uuid4()),
                app['id'],
                domain['domain_name'],
                domain.get('domain_type', 'production'),
                domain.get('ssl_status', 'pending'),
                domain.get('auth_enabled', 0),
                domain.get('auth_password_encrypted')
            ))
            count += 1
        
        return count
    
    def _import_secrets(self, secrets: Dict[str, Any]) -> int:
        """Import secrets."""
        count = 0
        for app_name, app_secrets in secrets.items():
            for scope, scoped_secrets in app_secrets.items():
                self.vault.store_app_secrets(app_name, scoped_secrets, scope)
                count += len(scoped_secrets)
        return count
```

### API Endpoints

```python
# api/config.py
from flask import Blueprint, request, jsonify, send_file
from services.config_export import ConfigExporter
from services.config_import import ConfigImporter
import tempfile
import os

api_config = Blueprint('api_config', __name__, url_prefix='/api/config')

@api_config.route('/export', methods=['POST'])
def export_config():
    """Export all configuration to JSON."""
    data = request.get_json() or {}
    include_secrets = data.get('include_secrets', True)
    
    exporter = ConfigExporter(include_secrets=include_secrets)
    
    # Export to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        filepath = f.name
    
    result = exporter.export_to_file(filepath)
    
    return jsonify({
        'success': True,
        'download_url': f'/api/config/download/{os.path.basename(filepath)}',
        'checksum': result['checksum'],
        'stats': {
            'apps': result['apps_count'],
            'domains': result['domains_count']
        }
    })

@api_config.route('/download/<filename>', methods=['GET'])
def download_export(filename):
    """Download exported configuration file."""
    filepath = os.path.join(tempfile.gettempdir(), filename)
    return send_file(filepath, as_attachment=True, download_name='paas_config.json')

@api_config.route('/import', methods=['POST'])
def import_config():
    """Import configuration from JSON file."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    mode = request.form.get('mode', 'merge')  # 'merge' or 'replace'
    
    # Parse JSON
    try:
        export = json.load(file)
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid JSON: {e}'}), 400
    
    importer = ConfigImporter()
    
    # Validate first
    validation = importer.validate(export)
    if not validation['valid']:
        return jsonify({
            'success': False,
            'errors': validation['errors'],
            'warnings': validation['warnings']
        }), 400
    
    # Import
    results = importer.import_config(export, mode)
    
    return jsonify({
        'success': True,
        'results': results,
        'warnings': validation['warnings']
    })

@api_config.route('/validate', methods=['POST'])
def validate_import():
    """Validate import file without importing."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    try:
        export = json.load(file)
    except json.JSONDecodeError as e:
        return jsonify({'success': False, 'error': f'Invalid JSON: {e}'}), 400
    
    importer = ConfigImporter()
    validation = importer.validate(export)
    
    return jsonify({
        'success': validation['valid'],
        'validation': validation
    })
```

## GitHub Gist Sync

### Gist Sync Service

```python
# services/gist_sync.py
import requests
import json
import hashlib
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
import os

class GistSyncService:
    """
    Sync PaaS configuration to GitHub Gist for backup and version control.
    
    Features:
    - Automatic sync on configuration changes
    - Manual sync/restore via API
    - Version history in Gist revisions
    - Encrypted secrets in Gist
    """
    
    GITHUB_API = "https://api.github.com"
    
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN')
        self.gist_id = os.environ.get('GIST_ID')
        self.enabled = bool(self.token)
    
    def sync_to_gist(self, export: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sync configuration to GitHub Gist.
        
        Returns:
            Sync result with gist_id and version
        """
        if not self.enabled:
            return {'success': False, 'error': 'Gist sync not configured'}
        
        event_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        # Prepare gist content
        content = json.dumps(export, indent=2, default=str)
        filename = f"paas-config-{datetime.utcnow().strftime('%Y%m%d')}.json"
        
        # Build gist data
        gist_data = {
            'description': f'PaaS Configuration - {datetime.utcnow().isoformat()}',
            'public': False,
            'files': {
                filename: {
                    'content': content
                },
                'README.md': {
                    'content': self._generate_readme(export)
                }
            }
        }
        
        try:
            if self.gist_id:
                # Update existing gist
                response = requests.patch(
                    f"{self.GITHUB_API}/gists/{self.gist_id}",
                    headers=self._headers(),
                    json=gist_data,
                    timeout=30
                )
            else:
                # Create new gist
                response = requests.post(
                    f"{self.GITHUB_API}/gists",
                    headers=self._headers(),
                    json=gist_data,
                    timeout=30
                )
                if response.status_code == 201:
                    self.gist_id = response.json()['id']
                    # Save gist_id for future use
                    self._save_gist_id(self.gist_id)
            
            if response.status_code in (200, 201):
                gist = response.json()
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Record sync event
                self._record_sync_event(
                    event_id=event_id,
                    sync_type='export',
                    status='success',
                    gist_version=gist.get('history', [{}])[0].get('version'),
                    duration_ms=duration_ms
                )
                
                # Update sync state
                self._update_sync_state(
                    gist_id=self.gist_id,
                    gist_url=gist['html_url'],
                    gist_version=gist.get('history', [{}])[0].get('version'),
                    status='success'
                )
                
                return {
                    'success': True,
                    'gist_id': self.gist_id,
                    'gist_url': gist['html_url'],
                    'version': gist.get('history', [{}])[0].get('version')
                }
            else:
                error = response.json().get('message', 'Unknown error')
                self._record_sync_event(
                    event_id=event_id,
                    sync_type='export',
                    status='failed',
                    error_message=error
                )
                return {'success': False, 'error': error}
                
        except requests.RequestException as e:
            self._record_sync_event(
                event_id=event_id,
                sync_type='export',
                status='failed',
                error_message=str(e)
            )
            return {'success': False, 'error': str(e)}
    
    def restore_from_gist(self) -> Dict[str, Any]:
        """
        Restore configuration from GitHub Gist.
        
        Returns:
            Export data from gist
        """
        if not self.enabled or not self.gist_id:
            return {'success': False, 'error': 'Gist sync not configured'}
        
        event_id = str(uuid.uuid4())
        start_time = datetime.utcnow()
        
        try:
            response = requests.get(
                f"{self.GITHUB_API}/gists/{self.gist_id}",
                headers=self._headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                gist = response.json()
                
                # Find the config file
                config_file = None
                for filename, file_data in gist['files'].items():
                    if filename.startswith('paas-config-') and filename.endswith('.json'):
                        config_file = file_data
                        break
                
                if not config_file:
                    return {'success': False, 'error': 'No config file found in gist'}
                
                export = json.loads(config_file['content'])
                duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Record sync event
                self._record_sync_event(
                    event_id=event_id,
                    sync_type='import',
                    status='success',
                    gist_version=gist.get('history', [{}])[0].get('version'),
                    duration_ms=duration_ms
                )
                
                return {
                    'success': True,
                    'export': export,
                    'gist_url': gist['html_url'],
                    'updated_at': gist['updated_at']
                }
            else:
                error = response.json().get('message', 'Unknown error')
                self._record_sync_event(
                    event_id=event_id,
                    sync_type='import',
                    status='failed',
                    error_message=error
                )
                return {'success': False, 'error': error}
                
        except requests.RequestException as e:
            self._record_sync_event(
                event_id=event_id,
                sync_type='import',
                status='failed',
                error_message=str(e)
            )
            return {'success': False, 'error': str(e)}
    
    def get_gist_history(self, limit: int = 10) -> list:
        """Get gist version history."""
        if not self.enabled or not self.gist_id:
            return []
        
        try:
            response = requests.get(
                f"{self.GITHUB_API}/gists/{self.gist_id}/commits",
                headers=self._headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()[:limit]
            return []
        except requests.RequestException:
            return []
    
    def _headers(self) -> dict:
        """Get API headers with authentication."""
        return {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        }
    
    def _generate_readme(self, export: Dict[str, Any]) -> str:
        """Generate README content for gist."""
        data = export.get('data', {})
        return f"""# PaaS Configuration Backup

**Exported:** {export.get('exported_at')}  
**Checksum:** {export.get('checksum')}

## Contents

| Resource | Count |
|----------|-------|
| Applications | {len(data.get('applications', []))} |
| Domains | {len(data.get('domains', []))} |
| Servers | {len(data.get('servers', []))} |
| Secrets | {sum(len(s) for s in data.get('secrets', {}).values())} |

## Applications

{chr(10).join(f"- {app['name']} ({app.get('framework', 'unknown')})" for app in data.get('applications', []))}

---
*This backup was automatically generated by the Quantyra PaaS Dashboard.*
"""
    
    def _save_gist_id(self, gist_id: str):
        """Save gist_id to database and environment."""
        from services.database import db
        
        db.execute("""
            UPDATE gist_sync_state SET gist_id = ?, gist_url = ?, updated_at = ?
            WHERE id = 1
        """, (gist_id, f"https://gist.github.com/{gist_id}", datetime.utcnow().isoformat()))
        
        self.gist_id = gist_id
    
    def _update_sync_state(self, gist_id: str, gist_url: str, gist_version: str, status: str):
        """Update sync state in database."""
        from services.database import db
        
        db.execute("""
            UPDATE gist_sync_state SET
                gist_id = ?,
                gist_url = ?,
                gist_version = ?,
                last_sync_at = ?,
                last_sync_status = ?,
                total_syncs = total_syncs + 1,
                updated_at = ?
            WHERE id = 1
        """, (
            gist_id,
            gist_url,
            gist_version,
            datetime.utcnow().isoformat(),
            status,
            datetime.utcnow().isoformat()
        ))
    
    def _record_sync_event(self, event_id: str, sync_type: str, status: str,
                           gist_version: str = None, duration_ms: int = None,
                           error_message: str = None):
        """Record sync event for audit log."""
        from services.database import db
        
        db.execute("""
            INSERT INTO gist_sync_events (id, sync_type, direction, status,
                                         gist_version_after, duration_ms, error_message)
            VALUES (?, ?, 'push', ?, ?, ?, ?)
        """, (
            event_id,
            sync_type,
            status,
            gist_version,
            duration_ms,
            error_message
        ))


# Singleton instance
gist_sync = GistSyncService()
```

### API Endpoints for Gist Sync

```python
# api/gist_sync.py
from flask import Blueprint, jsonify, request
from services.gist_sync import gist_sync
from services.config_export import ConfigExporter
from services.config_import import ConfigImporter

api_gist = Blueprint('api_gist', __name__, url_prefix='/api/gist')

@api_gist.route('/sync', methods=['POST'])
def sync_to_gist():
    """Manually sync configuration to GitHub Gist."""
    data = request.get_json() or {}
    include_secrets = data.get('include_secrets', True)
    
    # Export configuration
    exporter = ConfigExporter(include_secrets=include_secrets)
    export = exporter.export_all()
    
    # Sync to gist
    result = gist_sync.sync_to_gist(export)
    
    return jsonify(result)

@api_gist.route('/restore', methods=['POST'])
def restore_from_gist():
    """Restore configuration from GitHub Gist."""
    data = request.get_json() or {}
    mode = data.get('mode', 'merge')  # 'merge' or 'replace'
    
    # Get from gist
    gist_result = gist_sync.restore_from_gist()
    
    if not gist_result['success']:
        return jsonify(gist_result), 400
    
    # Import configuration
    importer = ConfigImporter()
    import_result = importer.import_config(gist_result['export'], mode)
    
    return jsonify({
        'success': True,
        'import_result': import_result,
        'gist_url': gist_result['gist_url'],
        'gist_updated_at': gist_result['updated_at']
    })

@api_gist.route('/status', methods=['GET'])
def gist_status():
    """Get gist sync status."""
    from services.database import db
    
    state = db.fetchone("SELECT * FROM gist_sync_state WHERE id = 1")
    recent_events = db.fetchall("""
        SELECT * FROM gist_sync_events
        ORDER BY created_at DESC
        LIMIT 10
    """)
    
    return jsonify({
        'enabled': gist_sync.enabled,
        'gist_id': gist_sync.gist_id,
        'state': state,
        'recent_events': recent_events
    })

@api_gist.route('/history', methods=['GET'])
def gist_history():
    """Get gist version history."""
    limit = request.args.get('limit', 10, type=int)
    history = gist_sync.get_gist_history(limit)
    
    return jsonify({
        'success': True,
        'history': history
    })
```

### Auto-Sync on Configuration Changes

```python
# services/config_change_handler.py
from functools import wraps
from services.gist_sync import gist_sync
from services.config_export import ConfigExporter
from services.database import db

def sync_on_change(func):
    """
    Decorator to automatically sync to Gist after configuration changes.
    
    Usage:
        @sync_on_change
        def create_application(...):
            # Create application
            pass
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Execute the function
        result = func(*args, **kwargs)
        
        # Check if auto-sync is enabled
        state = db.fetchone("SELECT auto_sync_enabled, sync_enabled FROM gist_sync_state WHERE id = 1")
        
        if state and state['sync_enabled'] and state['auto_sync_enabled']:
            # Export and sync
            exporter = ConfigExporter(include_secrets=True)
            export = exporter.export_all()
            gist_sync.sync_to_gist(export)
        
        return result
    
    return wrapper


# Example usage in models/applications.py
@sync_on_change
def create_application(app_config: dict) -> dict:
    """Create new application and auto-sync to gist."""
    # ... create application logic ...
    return {'success': True, 'app_id': app_id}

@sync_on_change
def delete_application(app_name: str) -> dict:
    """Delete application and auto-sync to gist."""
    # ... delete application logic ...
    return {'success': True}
```

## Next Steps

1. **Phase 1**: Implement Action classes for existing deploy operations
2. **Phase 2**: Migrate from YAML config to SQLite
3. **Phase 3**: Add WebSocket support with flask-socketio
4. **Phase 4**: Implement configuration export/import API
5. **Phase 5**: Set up GitHub Gist sync for backup
6. **Phase 6**: Build Docker container for portable deployment

See [paas_roadmap.md](paas_roadmap.md) for implementation timeline.