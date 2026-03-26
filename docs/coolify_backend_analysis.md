# Coolify Backend Architecture Analysis

**Date:** 2026-03-26  
**Purpose:** Study Coolify's backend patterns for application to Quantyra infrastructure dashboard

## Executive Summary

Coolify is a self-hostable PaaS alternative to Heroku/Vercel built with **Laravel 11/12 (PHP 8.4)**, **PostgreSQL 15**, and **Redis 7**. Key patterns applicable to the Quantyra infrastructure dashboard include: action-based architecture, SSH multiplexing, real-time updates via WebSockets, and Docker-based database provisioning.

---

## 1. Technology Stack

### Core Stack

| Layer | Coolify | Quantyra (Current) | Recommendation |
|-------|---------|-------------------|----------------|
| Backend Framework | Laravel 11/12 (PHP 8.4) | Flask 3.x (Python) | Keep Flask - simpler for scope |
| Database | PostgreSQL 15 | PostgreSQL 18 via Patroni | Already aligned |
| Caching | Redis 7 | Redis 7 with Sentinel | Already aligned |
| Real-time | Soketi (WebSocket) + Pusher | None | Add WebSocket support |
| Queue | Laravel Horizon (Redis-based) | None | Add Celery or RQ |
| Frontend | Livewire + Alpine.js + Blade | Jinja2 templates | Consider Vue/React SPA |

### Key Dependencies

```json
{
  "phpseclib/phpseclib": "^3.0",      // SSH library (pure PHP)
  "laravel/sanctum": "^4.3",           // API token authentication
  "laravel/horizon": "^5.43",          // Queue management dashboard
  "pusher/pusher-php-server": "^7.2",  // Real-time broadcasting
  "spatie/laravel-activitylog": "^4.11", // Audit logging
  "guzzlehttp/guzzle": "^7.10"         // HTTP client
}
```

---

## 2. Server Management Architecture

### SSH Connection Pattern

Coolify uses **phpseclib** (pure PHP SSH implementation) with **SSH multiplexing** for efficient remote command execution:

```php
// From config/constants.php
'ssh' => [
    'mux_enabled' => true,              // SSH multiplexing
    'mux_persist_time' => 3600,         // 1 hour persistence
    'mux_health_check_enabled' => true,
    'mux_health_check_timeout' => 5,
    'mux_max_age' => 1800,              // 30 minutes max age
    'connection_timeout' => 10,
    'server_interval' => 20,
    'command_timeout' => 3600,
    'max_retries' => 3,
    'retry_base_delay' => 2,            // Exponential backoff
    'retry_max_delay' => 30,
    'retry_multiplier' => 2,
],
```

**Key Pattern: SSH Multiplexing**

```
┌─────────────────┐     SSH ControlMaster     ┌─────────────────┐
│   Coolify       │ ──────────────────────── │   Remote Server │
│   (Dashboard)   │     Single TCP Connection │   (Target)      │
└─────────────────┘     Reused for all cmds   └─────────────────┘
```

**For Quantyra (Python equivalent):**

```python
import paramiko
from socket import socket, AF_UNIX, SOCK_STREAM

class SSMMultiplexedConnection:
    """SSH connection with ControlMaster-like multiplexing."""
    
    def __init__(self, host: str, user: str, key_path: str):
        self.host = host
        self.user = user
        self.key_path = key_path
        self._client = None
        self._last_used = None
        self._max_age = 1800  # 30 minutes
    
    def get_client(self) -> paramiko.SSHClient:
        """Get or create SSH connection with reuse."""
        now = time.time()
        
        if self._client and (now - self._last_used) < self._max_age:
            try:
                # Health check
                self._client.exec_command('echo alive', timeout=5)
                self._last_used = now
                return self._client
            except:
                pass  # Connection dead, recreate
        
        # Create new connection
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self.host,
            username=self.user,
            key_filename=self.key_path,
            timeout=10,
            banner_timeout=20
        )
        self._last_used = now
        return self._client
    
    def execute(self, command: str, timeout: int = 3600) -> dict:
        """Execute command with retry logic."""
        for attempt in range(3):
            try:
                client = self.get_client()
                stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
                return {
                    'success': stdout.channel.recv_exit_status() == 0,
                    'stdout': stdout.read().decode(),
                    'stderr': stderr.read().decode(),
                    'exit_code': stdout.channel.recv_exit_status()
                }
            except Exception as e:
                delay = min(2 ** attempt, 30)
                time.sleep(delay)
        return {'success': False, 'error': str(e)}
```

### Server Model Architecture

Coolify's Server model includes:

```php
// Key attributes
protected $casts = [
    'proxy' => SchemalessAttributes::class,  // JSON config for proxy
    'traefik_outdated_info' => 'array',       // Version tracking
    'server_metadata' => 'array',              // OS, CPU, memory info
    'logdrain_axiom_api_key' => 'encrypted',   // Encrypted secrets
];

// Key relationships
public function privateKey()      // SSH key for connection
public function settings()        // Server-specific settings
public function applications()    // Apps on this server
public function databases()       // DBs on this server
public function sslCertificates() // SSL certs
```

**For Quantyra:**

```python
# dashboard/models/server.py
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
import json

@dataclass
class Server:
    id: int
    uuid: str
    name: str
    ip: str
    port: int = 22
    user: str = 'root'
    team_id: int = 1
    
    # Connection state
    is_reachable: bool = False
    is_usable: bool = False
    sentinel_updated_at: Optional[datetime] = None
    
    # Server metadata (collected via SSH)
    metadata: Dict = field(default_factory=dict)
    # {
    #   'os': 'Ubuntu 24.04 LTS',
    #   'arch': 'x86_64',
    #   'kernel': '6.8.0-48-generic',
    #   'cpus': 8,
    #   'memory_bytes': 34359738368,
    #   'uptime_since': '2024-01-15 10:00:00'
    # }
    
    # Proxy configuration
    proxy_type: str = 'traefik'  # traefik, caddy, nginx, none
    proxy_config: Dict = field(default_factory=dict)
    
    def is_functional(self) -> bool:
        """Check if server is ready for operations."""
        return self.is_reachable and self.is_usable
    
    def workdir(self) -> str:
        """Configuration directory on server."""
        return f"/data/coolify/servers/{self.uuid}"
```

---

## 3. Application Lifecycle Management

### Action-Based Architecture

Coolify uses the **laravel-actions** pattern for encapsulating business logic:

```php
// app/Actions/Server/InstallDocker.php
class InstallDocker
{
    use AsAction;  // Makes class invokable as action
    
    public function handle(Server $server)
    {
        $supported_os = $server->validateOS();
        
        // OS-specific install commands
        if ($supported_os->contains('debian')) {
            $command = $this->getDebianDockerInstallCommand();
        } elseif ($supported_os->contains('rhel')) {
            $command = $this->getRhelDockerInstallCommand();
        }
        
        return remote_process($command, $server);
    }
}

// Usage
InstallDocker::run($server);
// or dispatch async
InstallDocker::dispatch($server);
```

**For Quantyra (Python equivalent):**

```python
# dashboard/actions/base.py
from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from dataclasses import dataclass

T = TypeVar('T')

@dataclass
class ActionResult(Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

class Action(ABC, Generic[T]):
    """Base class for all actions."""
    
    @abstractmethod
    def handle(self, *args, **kwargs) -> ActionResult[T]:
        """Execute the action logic."""
        pass
    
    def run(self, *args, **kwargs) -> ActionResult[T]:
        """Entry point with error handling."""
        try:
            return self.handle(*args, **kwargs)
        except Exception as e:
            return ActionResult(success=False, error=str(e))

# dashboard/actions/server/install_docker.py
class InstallDocker(Action[bool]):
    """Install Docker Engine on a server."""
    
    def handle(self, server: Server) -> ActionResult[bool]:
        os_type = self._validate_os(server)
        
        if os_type == 'debian':
            commands = self._debian_commands()
        elif os_type == 'rhel':
            commands = self._rhel_commands()
        else:
            return ActionResult(success=False, error=f"Unsupported OS: {os_type}")
        
        result = ssh_execute(server, commands)
        return ActionResult(success=result['success'], data=True)
    
    def _validate_os(self, server: Server) -> str:
        result = ssh_execute(server, ['cat /etc/os-release'])
        # Parse OS type...
        return 'debian'

# Usage
result = InstallDocker().run(server)
if result.success:
    print("Docker installed successfully")
```

### Application Deployment Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│                     APPLICATION DEPLOYMENT FLOW                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. Validate & Prepare                                               │
│     ├── Check server is functional                                   │
│     ├── Validate git repository access                               │
│     ├── Generate deployment configuration                            │
│     └── Create deployment queue entry                                │
│                                                                      │
│  2. Build Phase (ApplicationDeploymentJob)                           │
│     ├── Clone repository                                             │
│     ├── Detect framework (Laravel, Next.js, etc.)                    │
│     ├── Build Docker image OR pull from registry                     │
│     └── Push to registry (if building)                               │
│                                                                      │
│  3. Deploy Phase                                                     │
│     ├── Generate docker-compose.yaml                                 │
│     ├── Create/update environment variables                          │
│     ├── Pull image on target servers                                 │
│     ├── Start containers with health checks                          │
│     └── Update proxy configuration (Traefik/Caddy)                   │
│                                                                      │
│  4. Post-Deploy                                                      │
│     ├── Verify container health                                      │
│     ├── Update application status                                    │
│     ├── Send notifications (webhook, discord, etc.)                  │
│     └── Cleanup old containers/images                                │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Database Integration

### Database Models

Coolify manages databases as Docker containers with:

```php
// app/Models/StandalonePostgresql.php
class StandalonePostgresql extends BaseModel
{
    protected $casts = [
        'postgres_password' => 'encrypted',  // Automatic encryption
        'init_scripts' => 'array',
    ];
    
    // Internal URL (Docker network)
    protected function internalDbUrl(): Attribute
    {
        return "postgres://{$user}:{$pass}@{$this->uuid}:5432/{$db}";
    }
    
    // External URL (if public)
    protected function externalDbUrl(): Attribute
    {
        if ($this->is_public && $this->public_port) {
            return "postgres://{$user}:{$pass}@{$serverIp}:{$port}/{$db}";
        }
        return null;
    }
    
    // Persistent storage management
    public function persistentStorages()
    {
        return $this->morphMany(LocalPersistentVolume::class, 'resource');
    }
}
```

### Database Provisioning Pattern

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DATABASE PROVISIONING                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Create Database Record                                          │
│     ├── Generate UUID for container name                            │
│     ├── Generate credentials (or use provided)                      │
│     ├── Create persistent volume record                             │
│     └── Store encrypted password                                    │
│                                                                     │
│  2. Generate Configuration                                          │
│     ├── docker-compose.yaml with:                                   │
│     │   ├── Image (postgres:16-alpine)                              │
│     │   ├── Environment variables                                   │
│     │   ├── Volume mounts                                           │
│     │   ├── Network configuration                                   │
│     │   └── Health checks                                           │
│     └── Custom postgresql.conf if provided                          │
│                                                                     │
│  3. Deploy Container                                                 │
│     ├── SSH to target server                                        │
│     ├── docker compose up -d                                        │
│     ├── Wait for health check                                       │
│     └── Run init scripts if provided                                │
│                                                                     │
│  4. Configure Backups (optional)                                    │
│     ├── Create scheduled backup job                                 │
│     ├── Configure S3/storage destination                            │
│     └── Set retention policy                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**For Quantyra (Patroni Cluster Integration):**

```python
# dashboard/actions/database/provision_database.py
class ProvisionDatabase(Action[dict]):
    """Provision a database on the Patroni cluster."""
    
    def handle(
        self,
        db_name: str,
        db_user: str,
        db_password: str,
        team_id: int,
        options: dict = None
    ) -> ActionResult[dict]:
        """
        Create database via HAProxy write port.
        
        Returns connection details:
        {
            'internal_url': 'postgres://user:pass@haproxy:5000/db',
            'read_url': 'postgres://user:pass@haproxy:5001/db',
            'host': '100.102.220.16',
            'port': 5000,
            'read_port': 5001
        }
        """
        # Connect via HAProxy (port 5000 = write, 5001 = read)
        conn = psycopg2.connect(
            host=PG_HOST,
            port=5000,
            user=PG_SUPERUSER,
            password=PG_SUPERPASSWORD,
            database='postgres'
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        try:
            # Create database
            cur.execute(f'CREATE DATABASE "{db_name}";')
            
            # Create user
            cur.execute(f'CREATE USER "{db_user}" WITH PASSWORD %s;', (db_password,))
            
            # Grant privileges
            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{db_user}";')
            
            # Connect to new DB and grant schema permissions
            cur.execute(f'\\connect {db_name}')
            cur.execute(f'GRANT ALL ON SCHEMA public TO "{db_user}";')
            
            return ActionResult(success=True, data={
                'internal_url': f'postgres://{db_user}:***@{PG_HOST}:5000/{db_name}',
                'read_url': f'postgres://{db_user}:***@{PG_HOST}:5001/{db_name}',
                'host': PG_HOST,
                'port': 5000,
                'read_port': 5001
            })
        except psycopg2.Error as e:
            return ActionResult(success=False, error=str(e))
        finally:
            cur.close()
            conn.close()
```

---

## 5. API Design

### RESTful API Structure

Coolify uses Laravel Sanctum for API authentication with ability-based scopes:

```php
// routes/api.php
Route::group([
    'middleware' => ['auth:sanctum', ApiAllowed::class, 'api.sensitive'],
    'prefix' => 'v1',
], function () {
    // Read operations
    Route::get('/servers', [ServersController::class, 'servers'])
        ->middleware(['api.ability:read']);
    
    // Write operations
    Route::post('/servers', [ServersController::class, 'create_server'])
        ->middleware(['api.ability:write']);
    
    // Deploy operations (separate scope)
    Route::post('/applications/{uuid}/start', [ApplicationsController::class, 'action_deploy'])
        ->middleware(['api.ability:deploy']);
    
    // Bulk operations
    Route::match(['get', 'post'], '/deploy', [DeployController::class, 'deploy'])
        ->middleware(['api.ability:deploy']);
});
```

### API Response Pattern

```php
// Consistent response format
return response()->json([
    'message' => 'Server created successfully',
    'data' => $server->toArray(),
], 201);

// Error responses
return response()->json([
    'message' => 'Validation failed',
    'errors' => [
        'name' => ['The name field is required.']
    ]
], 422);
```

**For Quantyra:**

```python
# dashboard/api/__init__.py
from flask import Blueprint, jsonify, request
from functools import wraps

api_v1 = Blueprint('api_v1', __name__, url_prefix='/api/v1')

def api_response(data=None, message=None, status=200):
    """Standardized API response format."""
    response = {'success': 200 <= status < 300}
    if message:
        response['message'] = message
    if data is not None:
        response['data'] = data
    return jsonify(response), status

def api_error(message, status=400, errors=None):
    """Standardized error response."""
    response = {'success': False, 'message': message}
    if errors:
        response['errors'] = errors
    return jsonify(response), status

def require_scope(scope: str):
    """Decorator for API scope checking."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            if not validate_token_scope(token, scope):
                return api_error('Insufficient permissions', 403)
            return f(*args, **kwargs)
        return decorated
    return decorator

# dashboard/api/servers.py
@api_v1.route('/servers', methods=['GET'])
@requires_auth
@require_scope('read')
def list_servers():
    servers = Server.owned_by_current_team()
    return api_response(data=[s.to_dict() for s in servers])

@api_v1.route('/servers', methods=['POST'])
@requires_auth
@require_scope('write')
def create_server():
    data = request.get_json()
    
    # Validate
    errors = validate_server_data(data)
    if errors:
        return api_error('Validation failed', 422, errors)
    
    # Create
    server = Server.create(**data)
    return api_response(
        data=server.to_dict(),
        message='Server created successfully',
        status=201
    )

@api_v1.route('/servers/<uuid>/validate', methods=['POST'])
@requires_auth
@require_scope('write')
def validate_server(uuid):
    """Trigger server validation (async)."""
    server = Server.find_by_uuid(uuid)
    if not server:
        return api_error('Server not found', 404)
    
    # Dispatch async job
    ValidateAndInstallServerJob.delay(server.id)
    
    return api_response(message='Validation started', status=202)
```

### Webhook Handling

```python
# dashboard/api/webhooks.py
@api_v1.route('/webhooks/github', methods=['POST'])
def github_webhook():
    """Handle GitHub push webhooks for auto-deploy."""
    signature = request.headers.get('X-Hub-Signature-256')
    payload = request.data
    
    # Verify signature
    if not verify_github_signature(payload, signature):
        return api_error('Invalid signature', 401)
    
    event = request.headers.get('X-GitHub-Event')
    data = request.get_json()
    
    if event == 'push':
        # Find applications with this repo
        apps = Application.find_by_repo(
            repo=data['repository']['full_name'],
            branch=data['ref'].replace('refs/heads/', '')
        )
        
        for app in apps:
            # Trigger deployment
            ApplicationDeploymentJob.delay(
                app.id,
                commit_sha=data['after']
            )
        
        return api_response(message=f'Deployment triggered for {len(apps)} applications')
    
    return api_response(message='Event ignored')
```

---

## 6. Real-Time Updates

### WebSocket Architecture

Coolify uses **Soketi** (Pusher-compatible WebSocket server) for real-time updates:

```php
// Broadcasting events
class ApplicationStatusChanged implements ShouldBroadcast
{
    public function broadcastOn()
    {
        return new PrivateChannel("application.{$this->application->uuid}");
    }
    
    public function broadcastWith()
    {
        return [
            'status' => $this->application->status,
            'updated_at' => now()->toIso8601String(),
        ];
    }
}

// Frontend (JavaScript)
const channel = Echo.private(`application.${uuid}`);
channel.listen('ApplicationStatusChanged', (e) => {
    updateStatusUI(e.status);
});
```

**For Quantyra (using Flask-SocketIO):**

```python
# dashboard/app.py
from flask_socketio import SocketIO, emit, join_room, leave_room

socketio = SocketIO(app, cors_allowed_origins="*", message_queue='redis://')

# Server-side events
def broadcast_deployment_status(app_uuid: str, status: str, logs: str = None):
    """Broadcast deployment status to connected clients."""
    socketio.emit('deployment_status', {
        'uuid': app_uuid,
        'status': status,
        'logs': logs,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f'app:{app_uuid}')

def broadcast_server_status(server_uuid: str, status: dict):
    """Broadcast server status update."""
    socketio.emit('server_status', {
        'uuid': server_uuid,
        **status,
        'timestamp': datetime.utcnow().isoformat()
    }, room=f'server:{server_uuid}')

# WebSocket handlers
@socketio.on('subscribe')
def handle_subscribe(data):
    """Subscribe to resource updates."""
    resource_type = data.get('type')  # 'app', 'server', 'database'
    resource_uuid = data.get('uuid')
    
    if resource_type and resource_uuid:
        join_room(f'{resource_type}:{resource_uuid}')
        emit('subscribed', {'room': f'{resource_type}:{resource_uuid}'})

@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    """Unsubscribe from resource updates."""
    leave_room(f"{data['type']}:{data['uuid']}")

# In deployment job
class ApplicationDeploymentJob:
    def execute(self):
        broadcast_deployment_status(self.app.uuid, 'building')
        
        # Build steps...
        self.run_build_commands(log_callback=lambda l: 
            broadcast_deployment_status(self.app.uuid, 'building', logs=l)
        )
        
        broadcast_deployment_status(self.app.uuid, 'deploying')
        # Deploy steps...
        
        broadcast_deployment_status(self.app.uuid, 'running')
```

---

## 7. Secrets Management

### Encryption Pattern

Coolify uses Laravel's built-in encryption for sensitive fields:

```php
// Model casts
protected $casts = [
    'postgres_password' => 'encrypted',
    'logdrain_axiom_api_key' => 'encrypted',
];

// Automatic encryption/decryption
$password = $database->postgres_password;  // Automatically decrypted
$database->postgres_password = $newPassword;  // Automatically encrypted
```

**For Quantyra (SOPS integration):**

```python
# dashboard/utils/secrets.py
import subprocess
import json
from functools import lru_cache

class SecretManager:
    """Manage secrets with SOPS encryption."""
    
    def __init__(self, secrets_file: str = 'secrets/encrypted.yaml'):
        self.secrets_file = secrets_file
        self._cache = {}
    
    def decrypt(self) -> dict:
        """Decrypt secrets file using SOPS."""
        result = subprocess.run(
            ['sops', '--decrypt', '--output-type', 'json', self.secrets_file],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"SOPS decryption failed: {result.stderr}")
        return json.loads(result.stdout)
    
    @lru_cache(maxsize=1)
    def get(self, key: str, default=None) -> str:
        """Get a secret value (cached)."""
        if key not in self._cache:
            secrets = self.decrypt()
            self._cache.update(secrets)
        return self._cache.get(key, default)
    
    def get_database_password(self, db_name: str) -> str:
        """Get database-specific password."""
        return self.get(f'databases.{db_name}.password')
    
    def rotate(self, key: str, new_value: str):
        """Rotate a secret (requires re-encryption)."""
        # This would integrate with your SOPS workflow
        pass

# Usage in models
from dashboard.utils.secrets import SecretManager

secrets = SecretManager()

class Database:
    @property
    def password(self) -> str:
        """Get decrypted password."""
        return secrets.get_database_password(self.name)
```

---

## 8. Queue & Background Jobs

### Job Queue Architecture

Coolify uses Laravel Horizon for Redis-based job queues:

```php
// app/Jobs/ApplicationDeploymentJob.php
class ApplicationDeploymentJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;
    
    public $tries = 3;           // Retry attempts
    public $timeout = 3600;      // 1 hour timeout
    public $backoff = [10, 30, 60]; // Exponential backoff
    
    public function handle()
    {
        // Deployment logic
    }
    
    public function failed(Throwable $exception)
    {
        // Cleanup on failure
        $this->application->update(['status' => 'failed']);
    }
}

// Dispatch
ApplicationDeploymentJob::dispatch($application);
```

**For Quantyra (using Celery with Redis):**

```python
# dashboard/tasks/__init__.py
from celery import Celery
from celery.utils.log import get_task_logger

celery = Celery('dashboard',
    broker='redis://:password@100.126.103.51:6379/0',
    backend='redis://:password@100.126.103.51:6379/1'
)

celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit
    task_acks_late=True,  # Acknowledge after completion
    task_reject_on_worker_lost=True,
)

logger = get_task_logger(__name__)

# dashboard/tasks/deployment.py
@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def deploy_application(self, app_id: int, commit_sha: str = None):
    """Deploy an application."""
    from dashboard.models import Application
    
    app = Application.find(app_id)
    
    try:
        # Update status
        app.update_status('deploying')
        broadcast_status(app.uuid, 'deploying')
        
        # Clone/Pull repository
        repo_path = clone_repository(app, commit_sha)
        
        # Build
        build_docker_image(app, repo_path)
        
        # Deploy
        deploy_containers(app)
        
        # Success
        app.update_status('running')
        broadcast_status(app.uuid, 'running')
        
    except Exception as e:
        logger.error(f"Deployment failed for {app.uuid}: {e}")
        app.update_status('failed')
        broadcast_status(app.uuid, 'failed', error=str(e))
        
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

# dashboard/tasks/server.py
@celery.task
def validate_server(server_id: int):
    """Validate and install prerequisites on server."""
    server = Server.find(server_id)
    
    # Check SSH connectivity
    result = ssh_execute(server, ['ls /'])
    if not result['success']:
        server.update(is_reachable=False)
        return {'success': False, 'error': 'SSH connection failed'}
    
    server.update(is_reachable=True)
    
    # Check Docker
    result = ssh_execute(server, ['docker version'])
    if not result['success']:
        install_docker(server)
    
    server.update(is_usable=True)
    return {'success': True}

# Periodic tasks
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Server health checks every minute
    sender.add_periodic_task(60.0, check_all_servers.s(), name='server-health-check')
    
    # Backup cleanup every hour
    sender.add_periodic_task(3600.0, cleanup_old_backups.s(), name='backup-cleanup')
    
    # SSL certificate renewal check daily
    sender.add_periodic_task(86400.0, check_ssl_renewals.s(), name='ssl-renewal')

@celery.task
def check_all_servers():
    """Health check all servers."""
    servers = Server.all()
    for server in servers:
        validate_server.delay(server.id)
```

---

## 9. Recommendations for Quantyra

### High Priority

1. **Add WebSocket Support**
   - Install `flask-socketio` with Redis message queue
   - Implement real-time status updates for deployments
   - Add terminal/SSH-in-browser capability

2. **Implement Job Queue**
   - Add Celery with Redis backend
   - Move long-running operations (deployments, backups) to background
   - Add progress tracking via WebSocket

3. **Create Action Classes**
   - Refactor business logic into reusable action classes
   - Standardize error handling and response format
   - Enable both sync and async execution

### Medium Priority

4. **Enhance SSH Management**
   - Implement connection pooling/multiplexing
   - Add retry logic with exponential backoff
   - Cache connection state in Redis

5. **API Versioning**
   - Add `/api/v1` prefix
   - Implement token-based auth with scopes
   - Document with OpenAPI/Swagger

6. **Audit Logging**
   - Log all state changes to applications/databases/servers
   - Store in PostgreSQL with retention policy
   - Add UI for viewing audit history

### Low Priority

7. **Backup Integration**
   - Schedule automated backups for Patroni databases
   - Integrate with S3-compatible storage
   - Add backup restoration workflow

8. **Metrics Collection**
   - Collect container metrics via cAdvisor
   - Store in Prometheus
   - Create Grafana dashboards

---

## 10. Code Examples for Implementation

### SSH Manager with Connection Pooling

```python
# dashboard/utils/ssh_manager.py
import paramiko
import redis
import json
import time
from threading import Lock
from dataclasses import dataclass
from typing import Optional, Dict, List

@dataclass
class SSHResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int

class SSHConnectionPool:
    """Thread-safe SSH connection pool with health checking."""
    
    def __init__(self, redis_client: redis.Redis, max_age: int = 1800):
        self.redis = redis_client
        self.max_age = max_age
        self._connections: Dict[str, paramiko.SSHClient] = {}
        self._last_used: Dict[str, float] = {}
        self._lock = Lock()
    
    def get_connection(self, server_ip: str, user: str, key_path: str) -> paramiko.SSHClient:
        """Get or create connection for server."""
        key = f"{user}@{server_ip}"
        
        with self._lock:
            now = time.time()
            
            # Check if connection exists and is fresh
            if key in self._connections:
                if now - self._last_used.get(key, 0) < self.max_age:
                    # Health check
                    try:
                        self._connections[key].exec_command('echo ok', timeout=5)
                        self._last_used[key] = now
                        return self._connections[key]
                    except:
                        # Connection dead, remove it
                        self._close_connection(key)
            
            # Create new connection
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=server_ip,
                username=user,
                key_filename=key_path,
                timeout=10,
                banner_timeout=20,
                compress=True
            )
            
            self._connections[key] = client
            self._last_used[key] = now
            return client
    
    def execute(
        self,
        server_ip: str,
        commands: List[str],
        user: str = 'root',
        key_path: str = '/root/.ssh/id_vps',
        timeout: int = 3600,
        sudo: bool = False
    ) -> SSHResult:
        """Execute commands on server."""
        start = time.time()
        
        # Prepare commands
        if sudo and user != 'root':
            commands = [f'sudo {cmd}' for cmd in commands]
        
        full_command = ' && '.join(commands)
        
        try:
            client = self.get_connection(server_ip, user, key_path)
            stdin, stdout, stderr = client.exec_command(full_command, timeout=timeout)
            
            exit_code = stdout.channel.recv_exit_status()
            
            return SSHResult(
                success=exit_code == 0,
                stdout=stdout.read().decode('utf-8', errors='replace'),
                stderr=stderr.read().decode('utf-8', errors='replace'),
                exit_code=exit_code,
                duration_ms=int((time.time() - start) * 1000)
            )
        except Exception as e:
            return SSHResult(
                success=False,
                stdout='',
                stderr=str(e),
                exit_code=-1,
                duration_ms=int((time.time() - start) * 1000)
            )
    
    def _close_connection(self, key: str):
        """Close and remove connection."""
        if key in self._connections:
            try:
                self._connections[key].close()
            except:
                pass
            del self._connections[key]
            self._last_used.pop(key, None)

# Global instance
ssh_pool = SSHConnectionPool(redis.Redis())

# Convenience function
def instant_remote_process(
    commands: List[str],
    server,
    timeout: int = 3600,
    sudo: bool = False
) -> SSHResult:
    """Execute commands on server (Coolify-style)."""
    return ssh_pool.execute(
        server_ip=server.ip,
        commands=commands,
        user=server.user,
        timeout=timeout,
        sudo=sudo
    )
```

### Database Provisioning with Patroni

```python
# dashboard/actions/database/create_database.py
from dashboard.actions.base import Action, ActionResult
from dashboard.utils.ssh_manager import instant_remote_process
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import secrets
import string

class CreateDatabase(Action[dict]):
    """Create a database on the Patroni cluster."""
    
    def handle(
        self,
        db_name: str,
        db_user: str = None,
        db_password: str = None,
        options: dict = None
    ) -> ActionResult[dict]:
        """
        Create database on Patroni cluster via HAProxy.
        
        Args:
            db_name: Database name
            db_user: Username (defaults to db_name)
            db_password: Password (auto-generated if not provided)
            options: Additional options (encoding, template, etc.)
        
        Returns:
            ActionResult with connection details
        """
        options = options or {}
        
        # Validate database name
        if not self._is_valid_identifier(db_name):
            return ActionResult(
                success=False,
                error=f"Invalid database name: {db_name}"
            )
        
        # Generate credentials
        if not db_user:
            db_user = db_name[:63]  # PostgreSQL limit
        
        if not db_password:
            db_password = self._generate_password(32)
        
        try:
            # Connect via HAProxy write port
            conn = psycopg2.connect(
                host=os.environ['PG_HOST'],  # HAProxy IP
                port=5000,  # Write port
                user=os.environ['PG_USER'],
                password=os.environ['PG_PASSWORD'],
                database='postgres'
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            
            # Check if database exists
            cur.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,)
            )
            if cur.fetchone():
                cur.close()
                conn.close()
                return ActionResult(
                    success=False,
                    error=f"Database '{db_name}' already exists"
                )
            
            # Create database
            encoding = options.get('encoding', 'UTF8')
            cur.execute(f'CREATE DATABASE "{db_name}" ENCODING %s', (encoding,))
            
            # Create user
            cur.execute(f'CREATE USER "{db_user}" WITH PASSWORD %s', (db_password,))
            
            # Grant privileges
            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{db_user}"')
            
            # Connect to new database and grant schema privileges
            conn.close()
            conn = psycopg2.connect(
                host=os.environ['PG_HOST'],
                port=5000,
                user=os.environ['PG_USER'],
                password=os.environ['PG_PASSWORD'],
                database=db_name
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f'GRANT ALL ON SCHEMA public TO "{db_user}"')
            cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO "{db_user}"')
            cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO "{db_user}"')
            
            cur.close()
            conn.close()
            
            # Return connection details
            return ActionResult(success=True, data={
                'database': db_name,
                'user': db_user,
                'password': db_password,  # Return for initial setup
                'connection': {
                    'host': os.environ['PG_HOST'],
                    'write_port': 5000,
                    'read_port': 5001,
                    'internal_url': f'postgres://{db_user}:***@{os.environ["PG_HOST"]}:5000/{db_name}',
                    'read_url': f'postgres://{db_user}:***@{os.environ["PG_HOST"]}:5001/{db_name}'
                }
            })
            
        except psycopg2.Error as e:
            return ActionResult(success=False, error=f"Database error: {e}")
        except Exception as e:
            return ActionResult(success=False, error=str(e))
    
    def _is_valid_identifier(self, name: str) -> bool:
        """Check if name is valid PostgreSQL identifier."""
        if not name or len(name) > 63:
            return False
        return name.replace('_', '').replace('-', '').isalnum()
    
    def _generate_password(self, length: int) -> str:
        """Generate secure random password."""
        chars = string.ascii_letters + string.digits
        return ''.join(secrets.choice(chars) for _ in range(length))
```

---

## Summary

Coolify provides an excellent reference architecture for a self-hosted PaaS. The key patterns to adopt are:

| Pattern | Coolify Approach | Quantyra Recommendation |
|---------|-----------------|------------------------|
| SSH Management | phpseclib + multiplexing | paramiko + connection pooling |
| Business Logic | Action classes | Python action classes |
| Real-time | Soketi/Pusher | Flask-SocketIO + Redis |
| Queues | Laravel Horizon | Celery + Redis |
| API Auth | Sanctum with scopes | Flask-JWT-Extended with scopes |
| Secrets | Laravel encryption | SOPS + environment variables |
| Database Provisioning | Docker containers | Patroni cluster integration |

The most impactful improvements for Quantyra would be:
1. **WebSocket support** for real-time deployment status
2. **Celery integration** for background job processing
3. **SSH connection pooling** for more reliable server management
4. **Action-based architecture** for maintainable business logic