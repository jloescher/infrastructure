# Coolify DevOps Patterns Analysis

**Date:** 2026-03-26
**Repository:** https://github.com/coollabsio/coolify
**Version:** 4.0.0-beta.470

## Executive Summary

Coolify is a Laravel-based PaaS that manages servers, containers, databases, and load balancers. This analysis identifies key patterns and recommendations for improving Quantyra's infrastructure.

---

## 1. Server Orchestration

### Coolify's Approach

**Server Model** (`app/Models/Server.php`):
- Each server has SSH credentials stored as `PrivateKey` model
- Server settings tracked in separate `ServerSetting` model
- Identity map cache to prevent N+1 queries
- Reachability tracking with notification throttling

```php
// Key server properties
- ip, port, user
- proxy (type, status, configuration)
- server_metadata (OS, arch, kernel, CPUs, memory, uptime)
- sentinel_updated_at (heartbeat tracking)
- unreachable_count (failure counter with notification)
```

**Server Validation** (`app/Actions/Server/ValidateServer.php`):
```php
- Check Docker Engine installed and running
- Validate Docker Compose available
- Verify Docker version >= 24.0
- Create coolify network if missing
- Check prerequisites (curl, wget, git, etc.)
```

**Sentinel Agent** (`app/Actions/Server/StartSentinel.php`):
- Lightweight monitoring container deployed on each server
- Mounts Docker socket for container monitoring
- Pushes metrics to central endpoint
- Health check via HTTP endpoint
- Configurable refresh rate and retention

```bash
docker run -d \
  -e TOKEN=<token> \
  -e PUSH_ENDPOINT=<fqdn> \
  -e PUSH_INTERVAL_SECONDS=60 \
  -e COLLECTOR_ENABLED=true \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /data/coolify/sentinel:/app/db \
  --pid host \
  ghcr.io/coollabsio/sentinel:latest
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Ansible ad-hoc health checks | Sentinel agent with push model | Deploy lightweight monitoring agent on each server |
| Manual server status checks | Automated with `unreachable_count` | Implement automatic health checking with escalation |
| No server metadata tracking | `server_metadata` JSON column | Add server specs collection to dashboard |
| SSH key in flat files | `PrivateKey` model with encryption | Store SSH keys in encrypted database or Vault |

**Action Items:**
1. Create `sentinel` service that reports to dashboard
2. Add `server_metadata` collection on provision
3. Implement `unreachable_count` escalation logic
4. Store SSH keys in encrypted database column

---

## 2. Container Management

### Coolify's Approach

**Docker Network Management**:
- Single `coolify` network per server
- Attachable for easy container connection
- Automatic network creation on validation

**Container Status Aggregation** (`app/Services/ContainerStatusAggregator.php`):
```php
// Priority-based state machine
Priority 1: Degraded → degraded:unhealthy
Priority 2: Restarting → degraded:unhealthy
Priority 3: Crash Loop → degraded:unhealthy
Priority 4: Mixed (running + exited) → degraded:unhealthy
Priority 5: Mixed (running + starting) → starting:unknown
Priority 6: Running → running:healthy/unhealthy/unknown
Priority 7: Dead/Removing → degraded:unhealthy
Priority 8: Paused → paused:unknown
Priority 9: Starting/Created → starting:unknown
Priority 10: Exited → exited
```

**Docker Compose Generation**:
- Generated dynamically from model attributes
- Includes health checks, resource limits, labels
- Stored in `/data/coolify/databases/<uuid>/docker-compose.yml`

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Manual container status | Priority-based aggregation | Implement ContainerStatusAggregator service |
| Static docker-compose files | Dynamic generation | Generate docker-compose from database models |
| No container health checks | Built-in healthcheck config | Add health checks to all containers |
| Port range 8100-8199 | Dynamic port allocation | Consider database-driven port registry |

**Action Items:**
1. Implement `ContainerStatusAggregator` for unified status reporting
2. Add health checks to all Docker containers
3. Store container configurations in database
4. Add container restart policies with limits

---

## 3. Service Management (Databases)

### Coolify's Approach

**Database Models**:
- Separate model per database type (`StandalonePostgresql`, `StandaloneRedis`, etc.)
- Polymorphic relationships for destinations
- Persistent volume auto-creation on model creation
- Configuration hash for change detection

```php
// StandalonePostgresql model
protected static function booted()
{
    static::created(function ($database) {
        LocalPersistentVolume::create([
            'name' => 'postgres-data-'.$database->uuid,
            'mount_path' => '/var/lib/postgresql/data',
            'resource_id' => $database->id,
            'resource_type' => $database->getMorphClass(),
        ]);
    });
}
```

**Database Startup Pattern** (`app/Actions/Database/StartPostgresql.php`):
```php
1. Create configuration directory
2. Generate SSL certificates (if enabled)
3. Generate environment variables
4. Generate docker-compose YAML
5. Write config files (custom.conf, init scripts)
6. Pull image
7. Stop/remove existing container
8. Start new container
9. Execute post-start commands (SSL permissions)
```

**Key Docker Compose Features**:
- Health checks with retries
- Resource limits (CPU, memory)
- Custom configuration mounts
- SSL certificate injection
- Log drain configuration

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Manual Patroni management | Model-driven database management | Create `ManagedDatabase` model for Patroni clusters |
| Static PostgreSQL config | Dynamic config generation | Generate patroni.yml from database model |
| No config change detection | `config_hash` for drift detection | Implement configuration hash checking |
| Manual volume management | Auto-create persistent volumes | Automatic volume lifecycle management |

**Action Items:**
1. Create `PatroniCluster` model with configuration management
2. Implement `StartPostgresql` action pattern for Patroni
3. Add configuration hash for change detection
4. Automate persistent volume creation/deletion

---

## 4. SSL/Certificate Management

### Coolify's Approach

**Self-Signed CA + Per-Service Certificates** (`app/Helpers/SslHelper.php`):
```php
// Generate CA certificate for server
$caCert = SslHelper::generateSslCertificate(
    commonName: "Coolify CA - {$server->name}",
    isCaCertificate: true,
    serverId: $server->id
);

// Generate service certificate signed by CA
$sslCert = SslHelper::generateSslCertificate(
    commonName: $database->uuid,
    resourceType: $database->getMorphClass(),
    resourceId: $database->id,
    serverId: $server->id,
    caCert: $caCert->ssl_certificate,
    caKey: $caCert->ssl_private_key
);
```

**Certificate Storage**:
```php
// SslCertificate model
'ssl_certificate' => 'encrypted',
'ssl_private_key' => 'encrypted',
'valid_until' => 'datetime',
'subject_alternative_names' => 'array'
```

**Let's Encrypt (via Traefik)**:
- Automatic ACME via Traefik's built-in cert resolver
- DNS-01 challenge supported
- Certificates stored in Traefik's data directory

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Manual certbot | Traefik ACME + self-signed CA | Migrate to Caddy or Traefik with auto-ACME |
| DNS-01 challenge | Built-in DNS challenge | Use Traefik DNS challenge with Cloudflare |
| No internal TLS | Self-signed CA for inter-service | Generate internal CA for database connections |
| Manual renewal | Automatic renewal | Implement automatic renewal job |

**Action Items:**
1. Consider Traefik or Caddy for automatic ACME
2. Generate internal CA for PostgreSQL/Redis TLS
3. Implement automatic certificate renewal monitoring
4. Store certificates encrypted in database

---

## 5. Backup and Recovery

### Coolify's Approach

**Scheduled Database Backup** (`app/Jobs/DatabaseBackupJob.php`):
```php
// Backup flow
1. Validate database is running
2. Create backup directory
3. Execute pg_dump/mongodump/mysqldump
4. Upload to S3 (optional)
5. Delete local backup (optional)
6. Remove old backups based on retention
7. Send notification

// PostgreSQL backup
docker exec $container pg_dump --format=custom --no-acl --no-owner \
    --username $user $database > $backup_location

// S3 upload using mc (MinIO client)
docker run --rm -v $backup_location:$backup_location:ro \
    ghcr.io/coollabsio/coolify-helper \
    mc alias set temporary $endpoint $key $secret && \
    mc cp $backup_location temporary/$bucket$backup_dir/
```

**Backup Configuration**:
```php
// ScheduledDatabaseBackup model
'frequency' => '0 0 * * *',  // Cron expression
'number_of_backups_locally' => 7,
'save_s3' => true,
's3_storage_id' => 1,
'disable_local_backup' => false,  // S3-only mode
'databases_to_backup' => 'db1,db2,db3',
'dump_all' => false
```

**Backup Execution Tracking**:
```php
// ScheduledDatabaseBackupExecution model
'status' => 'success|failed',
'size' => 1234567,
'filename' => '/backups/db/pg-dump-db-1234567890.dmp',
's3_uploaded' => true,
'local_storage_deleted' => false,
'message' => 'Backup completed successfully'
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Manual pg_dump | Scheduled backup jobs | Implement `DatabaseBackupJob` with scheduling |
| Local backups only | S3 + local or S3-only | Add S3 backup support |
| No backup tracking | Execution log model | Track all backup runs with status |
| No retention policy | Configurable retention | Implement retention-based cleanup |
| No backup notifications | Success/failure notifications | Add backup status notifications |

**Action Items:**
1. Create `ScheduledBackup` model and scheduler
2. Implement `DatabaseBackupJob` for PostgreSQL/Redis
3. Add S3 backup support via MinIO or AWS S3
4. Create backup execution logging
5. Add retention-based cleanup
6. Integrate with Discord/Slack notifications

---

## 6. Monitoring and Logging

### Coolify's Approach

**Sentinel Agent**:
```yaml
# Deployed on each server
environment:
  TOKEN: <server-specific-token>
  DEBUG: false
  PUSH_ENDPOINT: https://coolify.example.com/api/sentinel
  PUSH_INTERVAL_SECONDS: 60
  COLLECTOR_ENABLED: true
  COLLECTOR_REFRESH_RATE_SECONDS: 5
  COLLECTOR_RETENTION_PERIOD_DAYS: 7

volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /data/coolify/sentinel:/app/db
```

**Metrics Collection**:
- Container stats (CPU, memory, network)
- Disk usage
- Container status
- Health check results

**Container Status Aggregation**:
- Priority-based state machine
- Handles mixed states gracefully
- Supports restarting, degraded, healthy states

**Log Drain**:
- Fluentd integration for centralized logging
- Support for New Relic, Axiom, Highlight, custom endpoints
- Per-service log drain configuration

```php
// Log drain configuration
if ($server->isLogDrainEnabled() && $database->isLogDrainEnabled()) {
    $docker_compose['services'][$container_name]['logging'] = generate_fluentd_configuration();
}
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Prometheus + Grafana | Sentinel push model | Keep Prometheus but add agent for container stats |
| Manual container monitoring | Automatic status aggregation | Implement ContainerStatusAggregator |
| No log aggregation | Fluentd integration | Consider Loki or Fluentd for log aggregation |
| Basic alerting | Multi-channel notifications | Enhance alerting with Discord/Slack |

**Action Items:**
1. Deploy node-exporter + cAdvisor on all servers
2. Implement `ContainerStatusAggregator` for unified status
3. Consider Loki for log aggregation
4. Enhance alerting with Discord/Slack webhooks

---

## 7. Proxy/Load Balancer Management

### Coolify's Approach

**Proxy Types**: Traefik (default), Caddy, None

**Dynamic Configuration Generation** (`app/Actions/Proxy/StartProxy.php`):
```php
// Traefik docker-compose
services:
  coolify-proxy:
    image: traefik:v3.5
    command:
      - --api.dashboard=true
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.letsencrypt.acme.dnschallenge=true
      - --certificatesresolvers.letsencrypt.acme.dnschallenge.provider=cloudflare
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./dynamic:/etc/traefik/dynamic
```

**Dynamic Routing**:
```yaml
# dynamic/coolify.yaml
http:
  routers:
    myapp:
      rule: "Host(`app.example.com`)"
      service: myapp
      tls:
        certResolver: letsencrypt
  services:
    myapp:
      loadBalancer:
        servers:
          - url: http://myapp:3000
```

**Proxy Network Management**:
- Automatic network creation
- Container connection to proxy network
- Dynamic configuration hot-reload

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| HAProxy with manual config | Dynamic Traefik config | Consider Traefik for dynamic routing |
| Consolidated frontends | Per-service dynamic config | Generate HAProxy config from database |
| Manual SSL certificates | ACME with DNS challenge | Automate SSL with Let's Encrypt |
| Static backend config | Dynamic service discovery | Consider service labels for routing |

**Action Items:**
1. Evaluate Traefik vs HAProxy for dynamic configuration
2. Generate HAProxy config from database models
3. Automate SSL certificate provisioning
4. Consider service discovery pattern

---

## 8. Action Pattern (Key Insight)

### Coolify's Approach

Every operation is a dedicated **Action class**:

```
app/Actions/
├── Application/
│   ├── GenerateConfig.php
│   ├── StopApplication.php
│   └── LoadComposeFile.php
├── Database/
│   ├── StartPostgresql.php
│   ├── StartRedis.php
│   └── StopDatabase.php
├── Proxy/
│   ├── StartProxy.php
│   ├── StopProxy.php
│   └── SaveProxyConfiguration.php
└── Server/
    ├── InstallDocker.php
    ├── StartSentinel.php
    └── ValidateServer.php
```

**Benefits**:
- Single responsibility per action
- Easy to test in isolation
- Clear naming convention
- Reusable across controllers/jobs/listeners

**Example**:
```php
// Using the action
class StartDatabase
{
    public function handle($database)
    {
        switch ($database->getMorphClass()) {
            case StandalonePostgresql::class:
                return StartPostgresql::run($database);
            case StandaloneRedis::class:
                return StartRedis::run($database);
            // ...
        }
    }
}
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Shell scripts for operations | Action classes | Create `app/actions/` directory with operations |
| Inline logic in routes | Dedicated action classes | Extract operations to action classes |
| No operation tracking | Activity log via actions | Add operation logging to actions |

**Action Items:**
1. Create `actions/` directory structure
2. Implement actions for: `StartPatroni`, `StartRedis`, `ProvisionDomain`, `DeployApp`
3. Add operation logging to actions
4. Create testable, reusable operations

---

## 9. Job Queue System

### Coolify's Approach

**Laravel Horizon** for queue management:
```php
// config/horizon.php
'environments' => [
    'production' => [
        'supervisor-1' => [
            'maxProcesses' => 10,
            'balanceMaxShift' => 1,
            'balanceCooldown' => 3,
        ],
    ],
],
```

**Key Jobs**:
```
app/Jobs/
├── ApplicationDeploymentJob.php
├── DatabaseBackupJob.php
├── CheckAndStartSentinelJob.php
├── RegenerateSslCertJob.php
├── RestartProxyJob.php
└── ScheduledTaskJob.php
```

**Deployment Queue**:
```php
// ApplicationDeploymentQueue model
class ApplicationDeploymentQueue extends Model
{
    // Tracks deployment progress
    protected $casts = [
        'logs' => 'array',  // JSON log entries
        'finished_at' => 'datetime',
    ];
    
    public function addLogEntry(string $message, string $type = 'stdout')
    {
        // Real-time log streaming
    }
}
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| No queue system | Laravel Horizon | Add Celery or RQ for async tasks |
| Synchronous deployments | Async deployment jobs | Queue deployments for reliability |
| No progress tracking | Deployment log model | Track deployment progress in database |

**Action Items:**
1. Evaluate Celery/RQ for async task processing
2. Create `DeploymentQueue` model for tracking
3. Implement async deployment jobs
4. Add real-time progress streaming

---

## 10. Configuration Management

### Coolify's Approach

**Environment Variables**:
- Stored in `EnvironmentVariable` model
- Encrypted sensitive values
- Isolated per application/database

**Configuration Generation**:
```php
// Dynamic docker-compose generation
$docker_compose = [
    'services' => [
        $container_name => [
            'image' => $database->image,
            'environment' => $environment_variables->all(),
            'volumes' => $persistent_storages,
            'healthcheck' => [...],
            'labels' => defaultDatabaseLabels($database),
        ],
    ],
];
```

**Configuration Drift Detection**:
```php
public function isConfigurationChanged(bool $save = false)
{
    $newConfigHash = md5(
        $this->image .
        $this->ports_mappings .
        json_encode($this->environment_variables()->get('value')->sort())
    );
    
    return $this->config_hash !== $newConfigHash;
}
```

### Recommendations for Quantyra

| Current State | Coolify Pattern | Recommendation |
|--------------|-----------------|----------------|
| Ansible for config | Model-driven config | Store configurations in database |
| No drift detection | Config hash comparison | Implement configuration drift detection |
| Manual sync | Automatic config generation | Generate configs from models |

**Action Items:**
1. Store service configurations in database
2. Implement config hash for drift detection
3. Generate configs from database models
4. Sync configs on change detection

---

## Summary: Top 10 Recommendations

### Immediate (Week 1-2)
1. **Implement Action Pattern**: Create `actions/` directory for all operations
2. **Add Container Status Aggregation**: Unified status reporting
3. **Implement Backup Scheduler**: `ScheduledBackup` model + `DatabaseBackupJob`

### Short-term (Week 3-4)
4. **Deploy Monitoring Agent**: Lightweight sentinel-like agent for container stats
5. **Add Configuration Drift Detection**: Hash-based change detection
6. **Implement Deployment Queue**: Async deployments with progress tracking

### Medium-term (Week 5-8)
7. **Migrate to Dynamic Config Generation**: Generate docker-compose/HAProxy from models
8. **Add S3 Backup Support**: Off-site backup storage
9. **Implement SSL Automation**: ACME with DNS-01 challenge

### Long-term (Week 9+)
10. **Model-Driven Infrastructure**: All infrastructure defined in database models

---

## Architecture Comparison

| Component | Quantyra | Coolify | Recommendation |
|-----------|----------|---------|----------------|
| **Dashboard** | Flask | Laravel + Livewire | Keep Flask, add async jobs |
| **Database** | Patroni (3 nodes) | Single PostgreSQL | Keep Patroni, add management layer |
| **Cache** | Redis (2 nodes) | Single Redis | Keep Redis cluster |
| **Load Balancer** | HAProxy | Traefik/Caddy | Consider Traefik for dynamic config |
| **Monitoring** | Prometheus + Grafana | Sentinel + Push | Add container status aggregation |
| **Backups** | Manual | Scheduled + S3 | Implement backup scheduler |
| **SSL** | Manual certbot | ACME + Self-signed CA | Automate with Let's Encrypt |
| **Logging** | None | Fluentd integration | Consider Loki |
| **Queue** | None | Laravel Horizon | Add Celery/RQ |

---

## Key Code Patterns to Adopt

### 1. Action Pattern
```python
# actions/start_postgresql.py
class StartPostgresql:
    @staticmethod
    def run(database):
        commands = []
        commands.extend(ValidateServer.run(database.server))
        commands.extend(GenerateConfig.run(database))
        commands.extend(StartContainer.run(database))
        return execute_commands(commands)
```

### 2. Status Aggregation
```python
# services/container_status_aggregator.py
class ContainerStatusAggregator:
    PRIORITIES = [
        ('degraded', 'unhealthy'),
        ('restarting', 'unhealthy'),
        ('crash_loop', 'unhealthy'),
        ('running', 'healthy'),
        ('exited', None),
    ]
    
    def aggregate(self, containers):
        for status, health in self.PRIORITIES:
            if self._has_status(containers, status):
                return f"{status}:{health}" if health else status
```

### 3. Backup Scheduler
```python
# jobs/database_backup_job.py
class DatabaseBackupJob:
    def run(self, backup_config):
        try:
            self._create_backup()
            if backup_config.s3_enabled:
                self._upload_to_s3()
            if backup_config.delete_local:
                self._delete_local()
            self._notify_success()
        except Exception as e:
            self._notify_failure(e)
        finally:
            self._cleanup_old_backups()
```

### 4. Configuration Drift Detection
```python
# models/managed_database.py
class ManagedDatabase(Base):
    config_hash = Column(String)
    
    def is_config_changed(self):
        new_hash = self._compute_config_hash()
        return self.config_hash != new_hash
    
    def _compute_config_hash(self):
        config = f"{self.image}{self.port}{self.environment_hash}"
        return hashlib.md5(config.encode()).hexdigest()
```

---

## Conclusion

Coolify demonstrates several patterns that would improve Quantyra's infrastructure:

1. **Action-based operations** provide clear separation of concerns
2. **Model-driven configuration** enables dynamic infrastructure
3. **Status aggregation** provides unified view of system health
4. **Scheduled backups** with S3 support ensures data safety
5. **Configuration drift detection** prevents manual changes from going unnoticed

The most impactful immediate changes would be:
1. Implementing the backup scheduler
2. Adding container status aggregation
3. Creating action classes for core operations

These changes would bring Quantyra closer to a fully managed PaaS while maintaining the control and flexibility of the current infrastructure.