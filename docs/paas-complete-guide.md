# Quantyra Platform-as-a-Service (PaaS) Complete Guide

> Comprehensive documentation for the Quantyra PaaS infrastructure management platform.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [PaaS Dashboard](#paas-dashboard)
4. [Server Management](#server-management)
5. [Application Deployment](#application-deployment)
6. [Domain Provisioning](#domain-provisioning)
7. [Database Management](#database-management)
8. [Secrets Management](#secrets-management)
9. [Backup & Restore](#backup--restore)
10. [Docker Deployment](#docker-deployment)
11. [Monitoring & Observability](#monitoring--observability)
12. [API Reference](#api-reference)
13. [Troubleshooting](#troubleshooting)
14. [Security](#security)

---

## Quick Start

### Dashboard Access

```
URL: http://100.102.220.16:8080
Username: admin
Password: DbAdmin2026!
```

> **Note**: Dashboard is only accessible from the Tailscale network (100.64.0.0/10).

### Docker Deployment (Zero-Config)

The PaaS can be deployed on any machine connected to the Tailscale network with zero configuration:

```bash
# Clone the repository
git clone https://github.com/quantyra/infrastructure.git
cd infrastructure

# Start the dashboard (auto-detects Tailscale IP and SSH key)
docker-compose -f docker/docker-compose.yml up -d dashboard

# View connection info
docker logs infrastructure-dashboard
```

The container automatically:
- Detects Tailscale IP address
- Finds SSH key at `~/.ssh/id_vps`
- Connects to PostgreSQL, Redis, and Prometheus via Tailscale IPs

### Local Development

```bash
cd dashboard

# Install dependencies
pip3 install -r requirements.txt

# Set environment variables
export PG_HOST=100.102.220.16
export PG_PORT=5000
export PG_USER=patroni_superuser
export PG_PASSWORD=2e7vBpaaVK4vTJzrKebC
export REDIS_HOST=100.126.103.51
export REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
export PROMETHEUS_URL=http://100.102.220.16:9090

# Run locally
python3 app.py
```

---

## Architecture Overview

### Server Inventory

| Server | Tailscale IP | Public IP | Role | Specs |
|--------|--------------|-----------|------|-------|
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master | 8 vCPU, 32GB RAM |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica | 8 vCPU, 32GB RAM |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd | 8 vCPU, 32GB RAM |
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy, Monitoring, Dashboard | 2 vCPU, 8GB RAM |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy (Secondary) | 2 vCPU, 8GB RAM |
| re-db | 100.92.26.38 | 208.87.128.115 | App Server (Primary) | 12 vCPU, 48GB RAM |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) | 12 vCPU, 48GB RAM |

### Network Topology

```
                                     USER
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CLOUDFLARE (Anycast Edge)                             │
│  • Global CDN with 300+ PoPs                                                    │
│  • DDoS Protection & WAF                                                        │
│  • DNS Round-robin between router IPs                                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                        │                              │
                        │ 50%                          │ 50%
                        ▼                              ▼
               172.93.54.112                  23.29.118.6
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ROUTER LAYER (HAProxy)                             │
│   router-01                              router-02                              │
│   • SSL Termination                      • SSL Termination                      │
│   • Traffic Routing                      • Traffic Routing                      │
│   • Monitoring Stack                     • Backup Router                        │
│   • PaaS Dashboard                                                              │
└─────────────────────────────────────────────────────────────────────────────────┘
                        │                                  │
                        └──────────────┬───────────────────┘
                                       │
                         ┌─────────────┴─────────────┐
                         ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            APP SERVER LAYER                                      │
│   re-db (100.92.26.38)           re-node-02 (100.89.130.19)                     │
│   • nginx + PHP-FPM 8.5          • nginx + PHP-FPM 8.5                          │
│   • Node.js 20                   • Node.js 20                                   │
│   • /opt/apps/{appname}          • /opt/apps/{appname}                          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            DATABASE LAYER                                        │
│   PostgreSQL / Patroni Cluster (3 nodes)                                         │
│   Access: router-01:5000 (RW), router-01:5001 (RO)                              │
│                                                                                  │
│   Redis Cluster with Sentinel                                                    │
│   Master: re-node-01:6379, Replica: re-node-03:6379                            │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Infrastructure | Ansible | 2.12+ | Server provisioning and configuration management |
| Containerization | Docker Compose | 3.8 | Dashboard and monitoring stack deployment |
| Dashboard | Flask | 3.x | Infrastructure management web UI |
| Database | PostgreSQL | 18.x | Primary data store via Patroni cluster |
| HA Layer | Patroni | 3.x | PostgreSQL high availability with etcd DCS |
| Caching | Redis | 7.x | Session/cache with Sentinel failover |
| Load Balancing | HAProxy | 2.8 | SSL termination, traffic routing |
| DNS/CDN | Cloudflare | - | DNS management, WAF, DDoS protection |
| Monitoring | Prometheus | 2.48.x | Metrics collection and alerting |
| Visualization | Grafana | 10.2.x | Dashboards and alert management |

### Port Allocation

| Port Range | Purpose | Notes |
|------------|---------|-------|
| 5000-5001 | PostgreSQL (HAProxy) | 5000=RW, 5001=RO |
| 6379 | Redis | Master/replica |
| 8080 | Dashboard | Infrastructure management UI |
| 8100-8199 | Production Apps | Laravel/nginx backends |
| 8404 | HAProxy Stats | Admin interface |
| 9090 | Prometheus | Metrics collection |
| 9093 | Alertmanager | Alert routing |
| 9200-9299 | Staging Apps | Laravel/nginx backends |
| 3000 | Grafana | Dashboards |

---

## PaaS Dashboard

### Core Features

The PaaS dashboard provides a comprehensive web interface for managing the entire infrastructure:

#### SQLite Database Storage (`/data/paas.db`)

All PaaS configuration is stored in a portable SQLite database:
- **Applications**: Framework, repository, branches, ports
- **Domains**: DNS configuration, SSL status, passwords
- **Secrets**: AES-256-GCM encrypted environment variables
- **Servers**: Inventory with specs and status
- **Deployments**: History with step-by-step tracking

**Benefits**:
- Single-file backup and restore
- Portable across any Docker host
- No external database dependency
- Encrypted secrets at rest

### Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Application Deployment | ✅ Working | Laravel via GitHub webhook |
| Domain Provisioning | ✅ Working | DNS + SSL via Cloudflare |
| Database Management | ✅ Working | PostgreSQL with permissions |
| Secrets Management | ✅ Working | AES-256-GCM encryption |
| Staging Environments | ✅ Working | Password protected |
| Health Checks | ✅ Working | Deploy validation |
| Monitoring | ✅ Working | Prometheus + Grafana |
| Docker Deployment | ✅ Working | Zero-config on Tailscale |
| Configuration Sync | ✅ Working | Export/Import, Gist sync |
| Real-time Progress | ✅ Working | WebSocket support |
| Background Jobs | ✅ Working | SocketIO async deploys |
| Multi-framework | ✅ Working | Laravel, Next.js, Svelte, Python, Go |

### Navigation Structure

```
Dashboard (Home)
├── Overview
├── Applications
│   ├── List
│   ├── Create (+)
│   └── [App Detail]
│       ├── Overview (default)
│       ├── Deployments
│       ├── Domains
│       ├── Secrets
│       ├── Databases
│       └── Settings
├── Servers
├── Databases
├── Monitoring
└── Settings
```

### Dashboard Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | http://100.102.220.16:8080 | PaaS management UI |
| HAProxy Stats | http://100.102.220.16:8404/stats | Load balancer status |
| Prometheus | http://100.102.220.16:9090 | Metrics |
| Grafana | http://100.102.220.16:3000 | Dashboards |
| Alertmanager | http://100.102.220.16:9093 | Alert management |

---

## Server Management

### Adding Servers

1. Navigate to **Servers** in the dashboard
2. Click **Add Server**
3. Fill in:
   - **Name**: Server hostname (e.g., `re-db`)
   - **Tailscale IP**: 100.x.x.x address
   - **Public IP**: Optional external IP
   - **Role**: app, database, router, or monitoring

Servers are auto-seeded from the default inventory on first run.

### Package Update Monitoring

The dashboard monitors available package updates on all servers:

```bash
# API endpoint
GET /api/servers/updates

# Returns for each server:
{
  "server_name": {
    "updates_available": 23,
    "security_updates": 5,
    "last_check": "2026-03-30T12:00:00Z"
  }
}
```

### SSH Connectivity

All servers use SSH key authentication with the `id_vps` key:

```bash
# Connect to a server
ssh -i ~/.ssh/id_vps root@100.102.220.16

# Test connectivity from dashboard
curl -u admin:DbAdmin2026! http://localhost:8080/api/servers
```

### Server Status Checks

The dashboard performs real-time status checks:

```bash
# Check single server
GET /api/servers/{server_name}/status

# Response
{
  "online": true,
  "uptime": "45 days",
  "load": [0.5, 0.3, 0.2],
  "memory_percent": 35,
  "disk_percent": 18
}
```

---

## Application Deployment

### Supported Frameworks

| Framework | Status | Runtime | Notes |
|-----------|--------|---------|-------|
| Laravel | ✅ Production Ready | nginx + PHP-FPM 8.5 | Full pipeline tested |
| Next.js | ✅ Working | systemd + Node.js | SSR/SSG supported |
| SvelteKit | ✅ Working | systemd + Node.js | Adapter-node required |
| Python | ✅ Working | systemd + Gunicorn | Flask/Django supported |
| Go | ✅ Working | systemd | Binary deployment |

### Creating an Application

1. Navigate to **Applications → Create Application**
2. Select **Framework** (Laravel, Next.js, Svelte, Python, Go)
3. Configure **App Details**:
   - Name (alphanumeric, dashes)
   - Display name
   - Description
   - Git repository URL
4. Set **Build Settings** (auto-detected or custom):
   - Install command
   - Build command
   - Migrate command
5. Configure **Database Options**:
   - Create PostgreSQL database
   - Separate users for production/staging
6. Set up **Domains**:
   - Select from Cloudflare zones
   - Configure production/staging
   - Add CNAME records
7. Review and create

### Deployment Workflow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ DEPLOYMENT WORKFLOW                                                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  GitHub Push ──────► Webhook ──────► Dashboard ──────► Deploy Task              │
│                                                                                  │
│  Deploy Steps:                                                                   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐│
│  │ 1. git_fetch        - Fetch latest from remote                              ││
│  │ 2. git_pull         - Pull changes to local                                 ││
│  │ 3. install_deps     - composer install / npm ci                             ││
│  │ 4. build_assets     - npm run build / artisan optimize                      ││
│  │ 5. run_migrations   - Database migrations (with backup)                     ││
│  │ 6. clear_cache      - Framework cache clear                                 ││
│  │ 7. restart_services - Reload nginx/PHP-FPM                                  ││
│  │ 8. health_check     - Verify application responds                           ││
│  └─────────────────────────────────────────────────────────────────────────────┘│
│                                                                                  │
│  Deployed to BOTH app servers: re-db + re-node-02                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Branch Policy

| Branch | Environment | Port Range |
|--------|-------------|------------|
| `main` | Production | 8100-8199 |
| `staging` | Staging | 9200-9299 |
| Other | Ignored | - |

### GitHub Webhook Setup

1. Go to GitHub → Repo → Settings → Webhooks → Add webhook
2. **Payload URL**: `https://hooks.quantyralabs.cc/{app_name}`
3. **Content type**: `application/json`
4. **Secret**: Copy from App Status page
5. **Events**: `push` and `ping`
6. **Active**: Enabled

**Response**: Returns `202 Accepted` immediately. Check Applications page for status.

### Deployment Progress (WebSocket)

Deployments show real-time progress via WebSocket:

```javascript
// Connect to deployment room
const socket = io('http://localhost:8080');
socket.emit('join', {room: 'deployment:abc123'});

// Listen for progress updates
socket.on('step_progress', (data) => {
  console.log(`${data.server}: ${data.step} - ${data.status}`);
});

socket.on('deployment_complete', (data) => {
  console.log(`Deployment completed in ${data.duration}s`);
});
```

### Deployment Hooks

Add custom scripts to run before/after deployment:

```bash
# Pre-deploy hook: /opt/apps/{app}/hooks/pre-deploy.sh
# Post-deploy hook: /opt/apps/{app}/hooks/post-deploy.sh
```

---

## Domain Provisioning

### Production vs Staging

| Type | Pattern | Access | Security |
|------|---------|--------|----------|
| Production | `domain.tld` | Public | WAF rules |
| WWW | `www.domain.tld` | Redirect to root | WAF rules |
| Staging | `staging.domain.tld` | Password protected | WAF rules + Basic Auth |

### Domain Configuration

When configuring domains:

1. **Production**: Root domain (`domain.tld`) with automatic `www` redirect
2. **Staging**: Subdomain (`staging.domain.tld`) with password protection
3. **Additional CNAMEs**: API, dashboard, admin, etc.

### DNS Record Management

| Record Type | If Exists | Action |
|-------------|-----------|--------|
| `@` (root A) | Any | Override with app IP |
| `www` | Any | Override with app IP |
| `staging` | Any | Override with app IP |
| Other CNAMEs | Exists | Block - require manual deletion |

### SSL Certificate Provisioning

SSL certificates are provisioned via Let's Encrypt using DNS-01 challenge:

```bash
# Manual certificate provisioning
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /root/.cloudflare.ini \
  -d domain.tld -d www.domain.tld
```

**Auto-renewal**: Certificates auto-renew via systemd timer.

### Cloudflare WAF Rules

5 security rules are automatically created per domain:

| # | Rule Name | Action | Purpose |
|---|-----------|--------|---------|
| 1 | Allow legitimate bots | Allow | Allow known good bots |
| 2 | Challenge suspicious | Managed Challenge | Challenge suspicious requests |
| 3 | Challenge known attackers | Managed Challenge | Challenge IPs from threat feeds |
| 4 | Rate limit API | Managed Challenge | Rate limit API endpoints |
| 5 | Block SQL injection | Block | Block SQL injection attempts |

### Client IP Forwarding

Real client IPs are passed through the entire stack:

```
Client IP: 1.2.3.4

Cloudflare receives request
    ↓ Adds CF-Connecting-IP: 1.2.3.4
    
HAProxy receives request
    ↓ Sets X-Forwarded-For: 1.2.3.4
    ↓ Sets X-Real-IP: 1.2.3.4
    
Nginx receives request
    ↓ REMOTE_ADDR = 1.2.3.4
    
Application receives real client IP
```

### Staging Password Protection

All staging environments are password-protected:

```bash
# Access staging
curl -u admin:<password> https://staging.domain.tld

# Password stored in
/etc/haproxy/htpasswd/{app_name}-staging.htpasswd
```

---

## Database Management

### Connection Endpoints

| Purpose | Endpoint | Notes |
|---------|----------|-------|
| Read/Write | `router-01:5000`, `router-02:5000` | Routes to leader |
| Read-Only | `router-01:5001`, `router-02:5001` | Load balanced replicas |

### Database User Structure

When creating a database for an application:

**Production Database:**
- `{app_name}_user` - Standard read/write user
- `{app_name}_admin` - Administrative user with CREATEDB privilege

**Staging Database (if enabled):**
- `{app_name}_staging_user` - Standard read/write user for staging
- `{app_name}_staging_admin` - Administrative user for staging

All passwords are auto-generated and stored as encrypted secrets.

### Creating a Database

1. Navigate to **Databases → Create Database**
2. Configure:
   - **Name**: Database name (e.g., `myapp_production`)
   - **Owner**: Primary user
   - **Pool Size**: PgBouncer pool size (default: 20)
3. Database and users are created automatically

### Database Metrics

```bash
GET /api/databases/{db_name}/metrics

# Response
{
  "size": 1073741824,
  "connections": 15,
  "max_connections": 200,
  "table_count": 42,
  "cache_hit_ratio": 0.99
}
```

### Backup Management

```bash
# Create backup
POST /api/databases/{db_name}/backups

# List backups
GET /api/databases/{db_name}/backups

# Restore backup
POST /api/databases/{db_name}/backups/{backup_id}/restore
```

---

## Secrets Management

### Secret Scopes

Secrets are organized by scope:

| Scope | Description | Used For |
|-------|-------------|----------|
| `shared` | All environments | APP_KEY, third-party keys |
| `production` | Production only | Production-specific config |
| `staging` | Staging only | Staging-specific config |

### Merge Precedence

When generating runtime `.env`:

```
global defaults → shared secrets → environment secrets → computed infra vars
```

### Automatic Secrets

When a database is created, these secrets are auto-generated:
- `DB_USERNAME`, `DB_PASSWORD` - Production database user
- `DB_ADMIN_USERNAME`, `DB_ADMIN_PASSWORD` - Production admin user
- `STAGING_DB_USERNAME`, `STAGING_DB_PASSWORD` - Staging user (if enabled)
- `STAGING_DB_ADMIN_USERNAME`, `STAGING_DB_ADMIN_PASSWORD` - Staging admin (if enabled)

### Encryption

All secrets are encrypted with AES-256-GCM:
- Encryption key: `/data/vault.key`
- Database field: `value_encrypted`
- Key is auto-generated on first run

### Importing Secrets

1. Navigate to **Applications → [App Name] → Secrets**
2. Click **Import .env File**
3. Select a file with format:
   ```
   STRIPE_SECRET_KEY=sk_test_xxxxx
   SENDGRID_API_KEY=SG.xxxxx
   AWS_ACCESS_KEY_ID=AKIAxxxxx
   ```
4. Secrets are encrypted and stored automatically

---

## Backup & Restore

### SQLite Database Backup

The PaaS stores all configuration in a single SQLite file:

```bash
# Backup location
/data/paas.db

# Encryption key (keep safe!)
/data/vault.key
```

### Export Configuration

Export all PaaS configuration to JSON:

```bash
# Via API
curl -u admin:DbAdmin2026! http://localhost:8080/api/config/export -o config.json

# Via Dashboard
Settings → Configuration Management → Export to File
```

Export format:
```json
{
  "version": "1.0",
  "exported_at": "2026-03-30T12:00:00Z",
  "checksum": "sha256:abc123...",
  "applications": [...],
  "domains": [...],
  "secrets": {
    "_encrypted": true,
    "_algorithm": "AES-256-GCM",
    "data": [...]
  },
  "databases": [...],
  "servers": [...]
}
```

### Import Configuration

```bash
# Via API (merge mode)
curl -u admin:DbAdmin2026! -X POST \
  -H "Content-Type: application/json" \
  -d @config.json \
  http://localhost:8080/api/config/import?mode=merge

# Via Dashboard
Settings → Configuration Management → Choose File → Import
```

**Import Modes**:
- `merge`: Add new, update existing
- `replace`: Clear all, then import

### GitHub Gist Sync

Automatic backup to private GitHub Gist:

1. Configure GitHub token in Settings (requires `repo` and `gist` scopes)
2. Enable auto-sync
3. Configuration syncs to Gist after every change (5s debounce)

```bash
# Manual sync
Settings → Configuration Management → Sync to Gist Now

# Restore from Gist version
Settings → Configuration Management → Restore from Gist
```

### Database Restore

Upload a SQLite backup file to restore configuration:

1. Go to **Settings → Configuration Management**
2. Click **Restore Database from Backup**
3. Select `.db` file
4. Confirm restore

> **Warning**: This replaces the entire configuration database.

---

## Docker Deployment

### Container Requirements

The PaaS dashboard runs in a Docker container with:
- Python 3.11 slim image
- SSH client for server access
- Host network mode for Tailscale access

### Docker Compose Configuration

```yaml
services:
  dashboard:
    build:
      context: ..
      dockerfile: Dockerfile
    container_name: infrastructure-dashboard
    network_mode: host  # Required for Tailscale access
    environment:
      - PG_HOST=${PG_HOST:-100.102.220.16}
      - PG_PORT=${PG_PORT:-5000}
      - REDIS_HOST=${REDIS_HOST:-100.126.103.51}
      - PROMETHEUS_URL=${PROMETHEUS_URL:-http://100.102.220.16:9090}
    volumes:
      - dashboard-data:/data
      - ${HOME}/.ssh/id_vps:/root/.ssh/id_vps:ro
```

### Auto-Detection Features

The container automatically detects:

1. **Tailscale IP**: Via `ip addr show tailscale0` or hostname lookup
2. **SSH Key**: Checks common paths (`~/.ssh/id_vps`, `~/.ssh/id_ed25519`)
3. **Base Directory**: Container path `/app` or server path `/opt/dashboard`

### Volume Mounts

| Volume | Purpose |
|--------|---------|
| `dashboard-data` | SQLite database and encryption key |
| `~/.ssh/id_vps` | SSH key for server access (read-only) |
| `configs/dashboard` | Optional YAML configuration files |

### Starting the Stack

```bash
# Start dashboard only (zero-config on Tailscale)
docker-compose -f docker/docker-compose.yml up -d dashboard

# Start full monitoring stack
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker logs -f infrastructure-dashboard
```

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PG_HOST` | 100.102.220.16 | PostgreSQL HAProxy IP |
| `PG_PORT` | 5000 | PostgreSQL port |
| `PG_USER` | patroni_superuser | PostgreSQL username |
| `PG_PASSWORD` | (from secrets) | PostgreSQL password |
| `REDIS_HOST` | 100.126.103.51 | Redis master IP |
| `REDIS_PASSWORD` | (from secrets) | Redis password |
| `PROMETHEUS_URL` | http://100.102.220.16:9090 | Prometheus endpoint |
| `GITHUB_TOKEN` | - | GitHub API access |
| `DASHBOARD_USER` | admin | Dashboard login |
| `DASHBOARD_PASS` | DbAdmin2026! | Dashboard password |

---

## Monitoring & Observability

### Prometheus Metrics

Access Prometheus at http://100.102.220.16:9090

Key metrics collected:
- `haproxy_frontend_current_sessions` - Active connections
- `haproxy_backend_http_responses_total` - Response codes
- `nginx_connections_active` - Active nginx connections
- `node_cpu_seconds_total` - CPU usage
- `node_memory_MemAvailable_bytes` - Available memory

### Grafana Dashboards

Access Grafana at http://100.102.220.16:3000

Default credentials: admin / admin

Pre-configured dashboards:
- Infrastructure Overview
- PostgreSQL/Patroni Cluster
- Redis Performance
- HAProxy Traffic
- Application Metrics

### Alertmanager

Access Alertmanager at http://100.102.220.16:9093

Configure alert routing to:
- Email notifications
- Slack webhooks
- PagerDuty integration

### Centralized Logging

All servers send logs to Loki via Promtail:

```
Server Logs → Promtail → Loki → Grafana Explore
```

Log retention: 31 days

### Health Endpoints

```bash
# Dashboard health
GET /health

# API health
GET /api/health

# Response
{
  "status": "healthy",
  "postgres": "connected",
  "redis": "connected"
}
```

---

## API Reference

### Authentication

All API endpoints require Basic Auth:

```bash
curl -u admin:DbAdmin2026! http://localhost:8080/api/apps
```

### Applications

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/apps` | List applications |
| GET | `/api/apps/{name}` | Get application details |
| POST | `/api/apps` | Create application |
| PUT | `/api/apps/{name}` | Update application |
| DELETE | `/api/apps/{name}` | Delete application |

### Deployments

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/apps/{name}/deploy` | Deploy application |
| POST | `/api/apps/{name}/deploy-async` | Async deploy |
| GET | `/api/deployments/{id}` | Get deployment status |
| GET | `/api/apps/{name}/deployments` | List deployments |
| POST | `/api/deployments/{id}/rollback` | Rollback deployment |

### Domains

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/apps/{name}/domains` | List domains |
| POST | `/api/apps/{name}/domains` | Provision domain |
| DELETE | `/api/apps/{name}/domains/{domain}` | Delete domain |

### Databases

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/databases` | List databases |
| POST | `/api/databases` | Create database |
| GET | `/api/databases/{name}/metrics` | Get metrics |
| POST | `/api/databases/{name}/backups` | Create backup |
| GET | `/api/databases/{name}/backups` | List backups |
| POST | `/api/databases/{name}/backups/{id}/restore` | Restore backup |

### Secrets

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/secrets/{app}` | List secrets (no values) |
| POST | `/api/secrets/{app}` | Add secret |
| PUT | `/api/secrets/{app}/{key}` | Update secret |
| DELETE | `/api/secrets/{app}/{key}` | Delete secret |

### Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/github/{app}` | GitHub webhook |
| POST | `https://hooks.quantyralabs.cc/{app}` | Public webhook URL |

### Error Responses

```json
{
  "success": false,
  "error": "Application not found",
  "code": "APP_NOT_FOUND"
}
```

Common error codes:
- `APP_NOT_FOUND` - Application does not exist
- `DOMAIN_EXISTS` - Domain already provisioned
- `DEPLOYMENT_FAILED` - Deployment error
- `INVALID_FRAMEWORK` - Unsupported framework
- `PORT_IN_USE` - Port already allocated

---

## Troubleshooting

### Common Issues

#### Dashboard Can't Connect to Servers

```bash
# Verify Tailscale connection
tailscale status

# Test connectivity from dashboard container
docker exec infrastructure-dashboard curl -s http://100.102.220.16:5000

# Check SSH key
docker exec infrastructure-dashboard ls -la /root/.ssh/
```

#### Deployment Failed

1. Check **Deployment Logs** in dashboard
2. SSH to server:
   ```bash
   ssh -i ~/.ssh/id_vps root@100.92.26.38
   ```
3. Check service:
   ```bash
   systemctl status nginx php8.5-fpm
   journalctl -u php8.5-fpm -f
   ```

#### HAProxy Configuration Errors

```bash
# Validate config
haproxy -c -f /etc/haproxy/haproxy.cfg

# Rebuild configs
/opt/scripts/provision-domain.sh --rebuild

# Check HAProxy logs
journalctl -u haproxy -f
```

#### PostgreSQL Cluster Issues

```bash
# Check Patroni status
patronictl list

# Check etcd cluster
etcdctl member list

# Manual failover
patronictl switchover
```

#### Redis Connection Issues

```bash
# Check Redis master
redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO replication

# Check Sentinel
redis-cli -h 100.126.103.51 -p 26379 SENTINEL master mymaster
```

### Log Locations

| Service | Log Path |
|---------|----------|
| Dashboard | `journalctl -u dashboard -f` |
| HAProxy | `journalctl -u haproxy -f` |
| Patroni | `journalctl -u patroni -f` |
| PHP-FPM | `journalctl -u php8.5-fpm -f` |
| Nginx | `/var/log/nginx/error.log` |

### Health Check Commands

```bash
# Dashboard health
curl -s http://100.102.220.16:8080/health

# PostgreSQL cluster
patronictl list

# Redis status
redis-cli -h 100.126.103.51 -p 6379 -a <password> PING

# HAProxy stats
curl -s http://100.102.220.16:8404/stats
```

---

## Security

### Firewall (UFW)

Each server has:
- Tailscale network (100.64.0.0/10) fully trusted
- SSH (22) from Tailscale only, rate-limited
- Application ports from routers only
- Monitoring ports from Prometheus only

### SSH Configuration

- Key-based authentication only (`id_vps`)
- Password authentication disabled
- Root login: `prohibit-password`
- Tailscale SSH disabled (using standard SSH keys)

### SSL/TLS Settings

- TLS 1.2 minimum
- HSTS enabled
- OCSP stapling enabled
- Automatic HTTP→HTTPS redirect

### Secrets Security

- AES-256-GCM encryption at rest
- Encryption key stored separately (`/data/vault.key`)
- Secrets never returned in API responses
- Key rotation: manually re-encrypt all secrets

### Cloudflare WAF

5 security rules applied to all domains:
1. Allow legitimate bots
2. Challenge suspicious traffic
3. Challenge known attackers
4. Challenge rate-limited requests
5. Block SQL injection attempts

---

## Appendix

### Key Credentials

| Service | Username | Password |
|---------|----------|----------|
| Dashboard | admin | DbAdmin2026! |
| HAProxy Stats | admin | jFNeZ2bhfrTjTK7aKApD |
| PostgreSQL Superuser | patroni_superuser | 2e7vBpaaVK4vTJzrKebC |
| Redis | - | CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk |

### Useful Commands

```bash
# Ansible
ansible all -m ping
ansible-playbook ansible/playbooks/provision.yml

# HAProxy
haproxy -c -f /etc/haproxy/haproxy.cfg
/opt/scripts/provision-domain.sh --rebuild

# PostgreSQL/Patroni
patronictl list
patronictl switchover

# Redis
redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO replication

# Docker Compose
docker-compose -f docker/docker-compose.yml up -d
docker-compose -f docker/docker-compose.yml logs -f

# Config Sync
./scripts/sync-configs.sh
```

### Related Documentation

- [Architecture](architecture.md) - Infrastructure architecture details
- [API Reference](api.md) - Complete API documentation
- [Dashboard Guide](dashboard.md) - Dashboard features and usage
- [Disaster Recovery](disaster_recovery.md) - DR procedures
- [Monitoring](monitoring.md) - Monitoring setup and alerts
- [Getting Started](getting-started.md) - Quick start guide

---

*Document created: March 2026*
*Last updated: March 2026*