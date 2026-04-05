# Agent Instructions

This file contains instructions for AI agents working on this infrastructure repository.

## Project Overview

Infrastructure-as-code repository for managing Quantyra VPS infrastructure with:
- **Dokploy deployment platform** with Docker Swarm (2 nodes)
- **Traefik load balancer** with automatic SSL via Let's Encrypt
- PostgreSQL/Patroni cluster (3 nodes)
- Redis cluster with Sentinel (2 nodes)
- HAProxy routers for database traffic (2 nodes)
- Monitoring stack (Prometheus, Grafana, Alertmanager)

## Tech Stack

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
| Alertmanager | Alertmanager | 0.26.x | Alert routing and notification |
| Logging | Loki + Promtail | - | Centralized log aggregation |
| Secrets | SOPS | - | Encrypted secrets management |

## Prerequisites

- Ansible 2.12+ installed (`pip install ansible`)
- SSH access to all servers with `id_vps` key
- Tailscale connected (all servers use Tailscale IPs)
- Docker and Docker Compose (for local dashboard deployment)

## Project Structure

```
infrastructure/
├── ansible/
│   ├── inventory/hosts.yml      # Server inventory with specs
│   ├── playbooks/               # Provisioning, deploy, monitoring
│   └── roles/                   # Ansible roles
├── dashboard/
│   ├── app.py                   # Flask application (main logic)
│   ├── database.py              # SQLite database module for PaaS state
│   ├── templates/               # Jinja2 HTML templates
│   ├── config/                  # Runtime config (YAML fallback for SQLite)
│   └── requirements.txt         # Python dependencies
├── docker/
│   ├── docker-compose.yml       # Monitoring + dashboard stack
│   └── scripts/deploy.sh        # Docker Compose wrapper
├── scripts/
│   ├── provision-domain.sh      # Domain provisioning with SSL
│   ├── deploy-app.sh            # Application deployment
│   └── sync-configs.sh          # Config synchronization
├── configs/
│   ├── haproxy/                 # HAProxy configurations
│   ├── prometheus/              # Prometheus rules and alerts
│   └── grafana/                 # Grafana provisioning
├── docs/
│   ├── architecture.md          # Infrastructure architecture
│   ├── plan.md                  # Current tasks and priorities
│   └── *.md                     # Various documentation
└── AGENTS.md                    # This file
```

## Key Information

### Server Access
- **Dokploy Dashboard**: https://deploy.quantyralabs.cc (primary deployment interface)
- **App Servers**: re-db (100.92.26.38), re-node-02 (100.89.130.19, public: 23.227.173.245)
- **Routers**: router-01 (100.102.220.16), router-02 (100.116.175.9)
- **Monitoring**: Prometheus (100.102.220.16:9090), Grafana (100.102.220.16:3000)

### Critical Credentials
- **PostgreSQL Leader**: re-node-03 (100.114.117.46)
- **Redis Master**: re-node-01 (100.126.103.51:6379)
- **HAProxy Stats**: Port 8404, auth: admin:jFNeZ2bhfrTjTK7aKApD
- **Redis Password**: CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
- **Patroni Superuser**: patroni_superuser / 2e7vBpaaVK4vTJzrKebC
- **Cloudflare API Token**: zf5ncwuOaaXz2IJ1BVBu8myf0HQt5IxkPje_Rm1V
- **Cloudflare Zone ID** (xotec.io): 26470f68ef4dbbf7bf5a770630aa2a97
- **Cloudflare Zone ID** (rentalfixer.app): d565e98b12effe08e530da729b82c0b9

### Database Storage (SQLite)

**PaaS Internal State**: `/data/paas.db` (SQLite)
- Stores applications, domains, secrets, servers, deployments
- Secrets encrypted with AES-256-GCM
- Encryption key: `/data/vault.key`

**Application Databases**: External PostgreSQL cluster (managed by PaaS)
- Write endpoint: `router-01:5000`, `router-02:5000`
- Read endpoint: `router-01:5001`, `router-02:5001`

**Configuration Sync**:
- Export/import to JSON via Settings page
- GitHub Gist backup with auto-sync
- YAML files still supported as fallback

### Domain Configuration
- **Production**: Root domain (domain.tld) with www redirect
- **Staging**: staging.domain.tld (password protected)
- **Security Rules**: 5 rules with managed_challenge for rules 2, 3, 4

### Server Inventory

| Server | Tailscale IP | Public IP | Role | Specs |
|--------|--------------|-----------|------|-------|
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master | 8 vCPU, 32GB RAM |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica | 8 vCPU, 32GB RAM |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd | 8 vCPU, 32GB RAM |
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy, Monitoring | 2 vCPU, 8GB RAM |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy (Secondary) | 2 vCPU, 8GB RAM |
| re-db | 100.92.26.38 | 208.87.128.115 | App Server (Primary) | 12 vCPU, 48GB RAM |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) | 12 vCPU, 48GB RAM |

## Architecture Notes

### Current Architecture (Dokploy-Based)

**UPDATED (2026-04-03)**: The infrastructure now uses Option B architecture with Dokploy.

**Traffic Flow**:
- **App Traffic**: Cloudflare → Traefik (on app servers) → Docker containers
- **Database Traffic**: Applications → HAProxy (routers) → Patroni/Redis

**Key Changes**:
- HAProxy handles ONLY database traffic (PostgreSQL, Redis)
- Application traffic bypasses HAProxy entirely
- Traefik handles all app routing and SSL termination
- Dokploy manages deployments via Docker Swarm

### Dokploy Configuration (CRITICAL)

**Dokploy is the primary deployment platform**, replacing the legacy Flask dashboard and CapRover.

**Dashboard**: https://deploy.quantyralabs.cc

**Architecture**:
```
Docker Swarm Cluster:
- re-db (Manager): Dokploy dashboard, PostgreSQL, Redis, Traefik replica
- re-node-02 (Worker): Traefik replica, app containers

Services:
- dokploy: 1/1 replicas (manager only)
- dokploy-traefik: 2/2 replicas (HA on both nodes)
- dokploy-postgres: 1/1 replicas (Dokploy internal DB)
- dokploy-redis: 1/1 replicas (Dokploy internal cache)
```

**Deployment Workflow**:
1. Create application in Dokploy dashboard
2. Connect GitHub repository
3. Configure environment variables
4. Add domains
5. Deploy with 2+ replicas for HA

**Never manually create Docker Swarm services**. Always use Dokploy dashboard or API.

### HAProxy Configuration (Database Only)

**UPDATED (2026-04-03)**: HAProxy now handles DATABASE TRAFFIC ONLY.

**Scope**:
- PostgreSQL: Port 5000 (write), Port 5001 (read)
- Redis: Port 6379
- Stats: Port 8404

**Application traffic NO LONGER routes through HAProxy**. Apps route directly via Cloudflare → Traefik.

### Key Architectural Decisions

- **Dokploy for Deployment**: All application deployments via Dokploy dashboard, not Ansible or manual scripts
- **Traefik for App Routing**: Traefik handles app traffic, SSL, and load balancing
- **HAProxy for Databases**: HAProxy provides database connection pooling and failover
- **DNS Round-Robin**: Cloudflare returns both app server IPs; clients retry on failure
- **Tailscale VPN**: All server-to-server communication uses encrypted Tailscale network (100.64.0.0/10)

### Port Allocation Scheme

| Port Range | Purpose | Notes |
|------------|---------|-------|
| 5000-5001 | PostgreSQL (HAProxy) | 5000=RW, 5001=RO |
| 6379 | Redis | Master/replica |
| 8080 | Dashboard | Infrastructure management UI |
| 8100-8199 | Production Apps | Laravel/nginx backends |
| 8404 | HAProxy Stats | Admin interface |
| 9090 | Prometheus | Metrics collection |
| 9093 | Alertmanager | Alert routing |
| 9113 | Prometheus Exporters | nginx exporter listen port (Tailscale IP) |
| 9114 | nginx stub_status | Scraped by prometheus exporter (localhost) |
| 9200-9299 | Staging Apps | Laravel/nginx backends |
| 3000 | Grafana | Dashboards |

**Important:** The nginx stub_status must listen on port **9114** (not 9113) to avoid conflict with the prometheus-nginx-exporter which listens on port 9113 (Tailscale IP).

### Traffic Flow
1. **Cloudflare** terminates SSL at edge, routes to APP SERVERS via DNS round-robin
2. **Traefik** (on app servers) routes by Host header to Docker containers
3. **Docker containers** run applications (Laravel, Node.js, etc.)
4. **Database layer** accessed via HAProxy ports 5000 (write) / 5001 (read)

**Application Deployment**:
- Via Dokploy dashboard: https://deploy.quantyralabs.cc
- Git push to main/staging branches triggers auto-deploy
- Deploy with 2+ replicas for high availability
- Traefik automatically configures routing and SSL

### Client IP Forwarding
```
Cloudflare → HAProxy → Nginx → App
     ↓           ↓         ↓
CF-Connecting-IP → X-Forwarded-For → X-Real-IP
```

### Application Deployment
- Laravel apps: nginx + PHP-FPM (NOT systemd service)
- Each app gets unique port (8100+)
- PHP-FPM pool per application
- Deploy to BOTH app servers for redundancy

### Security Rules
- Rules 2, 3, 4 use "managed_challenge" (shows CAPTCHA)
- Rules 1, 5 use allow/block (immediate action)

## Available Commands

### Ansible

| Command | Description |
|---------|-------------|
| `ansible all -m ping` | Test connectivity to all servers |
| `ansible-playbook ansible/playbooks/provision.yml` | Provision all servers |
| `ansible-playbook ansible/playbooks/deploy.yml` | Deploy applications |
| `ansible-playbook ansible/playbooks/monitoring.yml` | Deploy monitoring stack |

### Docker Compose

| Command | Description |
|---------|-------------|
| `./scripts/deploy.sh start` | Start all services |
| `./scripts/deploy.sh stop` | Stop all services |
| `./scripts/deploy.sh logs` | View logs |

### Dashboard Local Development

```bash
cd dashboard
pip3 install -r requirements.txt
export PG_HOST=100.102.220.16
export PG_PORT=5000
export PG_USER=patroni_superuser
export PG_PASSWORD=2e7vBpaaVK4vTJzrKebC
export REDIS_HOST=100.126.103.51
export REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
export PROMETHEUS_URL=http://100.102.220.16:9090
python3 app.py
```

### Provisioning Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync-configs.sh` | Sync configs from servers to repo (includes Dokploy, Docker, Swarm) |

**Note**: Domain provisioning and app deployment are now handled via Dokploy dashboard, not scripts.

## Environment Variables

### Dashboard (.env or runtime)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `PG_HOST` | Yes | PostgreSQL HAProxy IP | `100.102.220.16` |
| `PG_PORT` | Yes | PostgreSQL port | `5000` (RW) / `5001` (RO) |
| `PG_USER` | Yes | PostgreSQL username | `patroni_superuser` |
| `PG_PASSWORD` | Yes | PostgreSQL password | (from secrets) |
| `REDIS_HOST` | Yes | Redis host IP | `100.126.103.51` |
| `REDIS_PASSWORD` | Yes | Redis password | (from secrets) |
| `PROMETHEUS_URL` | No | Prometheus endpoint | `http://100.102.220.16:9090` |
| `DASHBOARD_USER` | No | Dashboard login | `admin` |
| `DASHBOARD_PASS` | No | Dashboard password | `DbAdmin2026!` |
| `GITHUB_TOKEN` | No | GitHub API access | (from secrets) |
| `CLOUDFLARE_API_TOKEN` | No | Cloudflare API | (from secrets) |

## Database Operations

### PostgreSQL Cluster

**Connection endpoints:**
- Write: `router-01:5000`, `router-02:5000` (via HAProxy to leader)
- Read: `router-01:5001`, `router-02:5001` (load balanced replicas)

**Check cluster status:**
```bash
ssh root@100.102.220.16 'patronictl list'
```

**Manual failover:**
```bash
ssh root@100.102.220.16 'patronictl switchover'
```

### Redis Cluster

**Master:** re-node-01 (100.126.103.51:6379)
**Replica:** re-node-03 (100.114.117.46:6379)

**Check status:**
```bash
redis-cli -h 100.126.103.51 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO replication
```

## Monitoring & Alerts

### Service Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| HAProxy Stats | http://100.102.220.16:8404/stats | Load balancer dashboard |
| Prometheus | http://100.102.220.16:9090 | Metrics collection |
| Grafana | http://100.102.220.16:3000 | Dashboards |
| Alertmanager | http://100.102.220.16:9093 | Alert management |
| Loki | http://100.102.220.16:3100 | Log aggregation |

## Development Workflow

### Dokploy Dashboard Changes

The Dokploy dashboard is the primary interface for deployment and application management.

**Access**: https://deploy.quantyralabs.cc

**Common Operations**:
1. **Deploy Application**: Applications → [App Name] → Deploy
2. **Add Environment Variables**: Applications → [App Name] → Environment
3. **Add Domain**: Applications → [App Name] → Domains → Add Domain
4. **View Logs**: Applications → [App Name] → Logs
5. **Scale Replicas**: Applications → [App Name] → Settings → Replicas

**No code deployment needed**. All changes are made via the web UI.

### Docker Compose Deployment

Deploy the dashboard on any machine connected to Tailscale:

```bash
cd docker
cp .env.example .env
./scripts/deploy.sh start
```

**Services:**
- Dashboard: http://localhost:8080
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Alertmanager: http://localhost:9093

### Testing

No automated tests configured. Test manually:
1. Dashboard functionality via browser
2. API endpoints via curl
3. Domain provisioning end-to-end
4. Delete staging/production environments

## Troubleshooting

### Common Issues

**Dashboard can't connect to servers:**
```bash
# Verify Tailscale connection
tailscale status

# Test connectivity from dashboard container
docker exec infrastructure-dashboard curl -s http://100.102.220.16:5000
```

**HAProxy config errors:**
```bash
# Validate config
haproxy -c -f /etc/haproxy/haproxy.cfg

# Rebuild configs
/opt/scripts/provision-domain.sh --rebuild
```

**PostgreSQL cluster issues:**
```bash
# Check Patroni status
patronictl list

# Check etcd cluster
etcdctl member list
```

### Logs

```bash
# Dashboard
journalctl -u dashboard -f

# HAProxy
journalctl -u haproxy -f

# Patroni/PostgreSQL
journalctl -u patroni -f

# PHP-FPM
journalctl -u php8.5-fpm -f
```

## Code Style

### Python/Flask
- Functions: `snake_case` (`def provision_domain()`)
- Variables: `snake_case` (`app_name`, `environment`)
- Constants: `SCREAMING_SNAKE_CASE` (`APP_PORT_RANGE`)
- Files: lowercase with underscores (`app.py`)

### Ansible/YAML
- Variables: `snake_case` (`postgres_max_connections`)
- Files: `kebab-case` (`web_backends.cfg`, `ufw_rules.yml`)

### Shell Scripts
- Functions: `snake_case` (`ssh_command()`, `configure_laravel_nginx()`)
- Variables: UPPERCASE for globals (`APP_SERVER_1`, `REGISTRY_FILE`)

### Import Order (Python)
1. Standard library (`os`, `subprocess`, `datetime`)
2. External packages (`flask`, `psycopg2`, `redis`, `requests`)
3. Internal imports (none in dashboard - single file)

### Commit Conventions

Follow Conventional Commits:
- `feat:` - New feature (domain provisioning, dashboard feature)
- `fix:` - Bug fix
- `docs:` - Documentation updates
- `infra:` - Infrastructure changes (Ansible, configs)
- `config:` - Configuration changes

## Common Tasks

### Deploy New Application

1. Access Dokploy dashboard: https://deploy.quantyralabs.cc
2. Click **Applications** → **Create Application**
3. Connect GitHub repository
4. Configure build settings (Dockerfile or Nixpacks)
5. Set replicas: 2 (recommended for HA)
6. Add environment variables (database credentials, app secrets)
7. Add domains (production and/or staging)
8. Click **Deploy**
9. Monitor build and deployment logs
10. Verify application is accessible

### Add New Domain to Existing Application

1. Dokploy → Applications → [App Name] → Domains
2. Click **Add Domain**
3. Enter domain name (e.g., myapp.example.com)
4. Enable HTTPS
5. Click **Save**
6. SSL certificate auto-provisioned by Let's Encrypt
7. DNS auto-configured via Cloudflare API

### Delete Application

1. Dokploy → Applications → [App Name] → Settings
2. Scroll to bottom
3. Click **Delete Application**
4. Confirm deletion
5. Note: DNS records remain in Cloudflare (manual cleanup if needed)

### Check Service Status
```bash
# Dashboard
ssh root@100.102.220.16 "systemctl status dashboard"

# App servers
ssh root@100.92.26.38 "systemctl status nginx php8.5-fpm"
ssh root@100.89.130.19 "systemctl status nginx php8.5-fpm"
```

## Important Notes

1. **Deploy via Dokploy** - Always use Dokploy dashboard for application deployments
2. **Use 2+ replicas** - For high availability across both app servers
3. **Database via HAProxy** - Always use HAProxy endpoints (router IPs) for database connections
4. **Traefik handles SSL** - Let's Encrypt certificates are automatic via DNS-01 challenge
5. **Cloudflare proxy enabled** - All domains use Cloudflare proxy (orange cloud)
6. **DNS round-robin** - Cloudflare returns both app server IPs automatically
7. **Tailscale for SSH** - All SSH access via Tailscale network (100.64.0.0/10)
8. **Sync configs after changes** - Run `scripts/sync-configs.sh` after any server changes
9. **HAProxy is database-only** - Application traffic bypasses HAProxy entirely
10. **Monitoring is comprehensive** - Traefik, Docker, PostgreSQL, Redis, and more all monitored

## Config Sync Workflow

**CRITICAL:** Every time a configuration change is made on any server, it MUST be synced to the local repository.

### When to Sync

Sync configs to local repo after:
- Any HAProxy configuration changes
- Any nginx configuration changes
- Any PHP-FPM pool changes
- Any PostgreSQL/Patroni configuration changes
- Any Redis configuration changes
- Any Prometheus/Grafana/Alertmanager changes
- Any systemd service changes
- Any changes to `/etc/` on any server

### How to Sync

```bash
# From infrastructure/ root directory
./scripts/sync-configs.sh
```

This script pulls all configuration files from all servers into the `configs/` directory.

### After Syncing

1. Review changes: `git status`
2. Review diffs: `git diff`
3. Commit changes: `git add -A && git commit -m "sync: description of changes"`
4. Document significant changes in `docs/plan.md`

### Why This Matters

- **Disaster Recovery:** Local repo serves as backup of all server configurations
- **Audit Trail:** Git history shows what changed and when
- **Consistency:** Easier to detect configuration drift between servers
- **Documentation:** Configs in repo serve as documentation of current state

## Documentation Update Workflow

**CRITICAL:** After completing any task, the relevant documentation MUST be updated:

### Required Updates

1. **`docs/plan.md`**: Mark completed tasks with:
   - Status: Change `⏳ In Progress` to `✅ Complete`
   - Timestamp: Add completion date/time (e.g., `2026-03-19 02:24 UTC`)
   - Checkboxes: Change `[ ]` to `[x]` for completed items

2. **Related Documentation**: Update any relevant docs:
   - `docs/architecture.md` - If architectural changes
   - `docs/dashboard.md` - If dashboard features changed
   - `docs/monitoring.md` - If monitoring/alerting changed
   - `docs/security_audit.md` - If security-related changes

### Documentation Format

```markdown
**Tracking:**
- Started: YYYY-MM-DD (description)
- Completed: YYYY-MM-DD HH:MM UTC
- Status: ✅ Complete
```

### Why This Matters

- **Audit Trail:** Clear history of what was done and when
- **Continuity:** Future sessions can understand previous work
- **Accountability:** Timestamps show progress over time

## Framework Support

| Framework | Runtime | Environment Variable |
|-----------|---------|---------------------|
| Laravel | nginx + PHP-FPM | `APP_ENV` (production/staging) |
| Next.js | systemd + npm | `NODE_ENV` (production/development) |
| Svelte | systemd + npm | `NODE_ENV` (production/development) |
| Python | systemd + gunicorn | `APP_ENV` (production/staging) |
| Go | systemd | `APP_ENV` (production/staging) |

## Deployment Branches

- **main** → Production (https://domain.tld)
- **staging** → Staging (https://staging.domain.tld)

## SSH Key Infrastructure

### SSH Key Distribution

All servers have the following SSH keys authorized:
- `id_vps` (ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDWDnyAL96iqiqsxJLPkD+ShpHra55FWH7hULEsOc4Ih) - Primary access key
- `root@re-db` - For server-to-server communication from re-db
- `root@router-01` - For server-to-server communication from router-01 (dashboard orchestrator)
- `root@router-02` - For server-to-server communication from router-02 (secondary router)

### Tailscale SSH

Tailscale SSH (`RunSSH`) is **disabled** on all servers. SSH access uses standard SSH keys.

### SSH Rollback Procedure

If SSH connectivity issues arise after disabling Tailscale SSH:

1. **Re-enable Tailscale SSH via SSDNodes console**:
   ```bash
   tailscale set --ssh=true
   ```

2. **Or via Tailscale admin console ACL**:
   - Go to https://login.tailscale.com/admin/acls
   - Add SSH rule to allow access
   - Connect via Tailscale SSH and re-add keys

3. **Verify access and re-disable Tailscale SSH**:
   ```bash
   tailscale set --ssh=false --accept-risk=lose-ssh
   ```

## Security

### Firewall (UFW)
- Tailscale network (100.64.0.0/10) fully trusted
- SSH (22) from Tailscale only, rate-limited
- Application ports from routers only
- Monitoring ports from Prometheus only

### SSH
- Key-based authentication only (`id_vps`)
- Password authentication disabled
- Root login: prohibit-password
- Tailscale SSH disabled (using standard SSH keys)

### fail2ban
- SSH protection enabled on all servers
- HAProxy, PostgreSQL, Redis protection enabled

### Cloudflare WAF
5 security rules applied:
1. Allow legitimate bots
2. Challenge suspicious traffic (managed_challenge)
3. Challenge known attackers (managed_challenge)
4. Challenge rate-limited requests (managed_challenge)
5. Block SQL injection attempts

## Documentation

- `/docs/plan.md` - Current tasks, priorities, and future improvements
- `/docs/architecture.md` - Complete infrastructure architecture and traffic flow
- `/docs/dokploy-operations.md` - Operational guide for Dokploy platform
- `/docs/deployment.md` - Application deployment procedures
- `/docs/getting-started.md` - Quick start guide for new users
- `/docs/monitoring.md` - Monitoring setup (includes Traefik and Docker Swarm)
- `/docs/disaster_recovery.md` - DR procedures including Dokploy recovery
- `/docs/dokploy_migration_plan.md` - Migration plan from CapRover to Dokploy (complete)

## Skill Usage Guide

When working on tasks involving these technologies, invoke the corresponding skill:

| Skill | Invoke When |
|-------|-------------|
| ansible | Configuring Ansible playbooks, roles, and infrastructure automation |
| docker | Managing Docker Compose configurations and container deployments |
| postgresql | Handling PostgreSQL database operations and Patroni cluster management |
| python | Managing Python code patterns, dependencies, and Flask application development |
| redis | Managing Redis caching, replication, and Sentinel failover |
| haproxy | Configuring HAProxy load balancing, SSL termination, and traffic routing |
| prometheus | Managing Prometheus metrics collection, alerting rules, and monitoring |
| grafana | Handling Grafana dashboard visualization and alert management |
| patroni | Managing Patroni PostgreSQL high availability and etcd DCS |
| flask | Handling Flask web application routes, templates, and API endpoints |
| tailscale | Handling Tailscale VPN networking and secure server communication |
| cloudflare | Configuring Cloudflare DNS, WAF rules, and DDoS protection |
| nginx | Configuring nginx web server and PHP-FPM for application backends |

## Agent Usage Guide

When to use specific agents:

| Agent | Use When |
|-------|----------|
| devops-engineer | Provisioning servers, configuring HAProxy, deploying apps, Docker Compose services |
| backend-engineer | Building dashboard API endpoints, database queries, infrastructure automation scripts |
| debugger | Services are down, deployments fail, database replication lag, HAProxy misrouting |
| security-engineer | Auditing security configurations, reviewing firewall rules, hardening SSH |
| code-reviewer | Reviewing PRs, checking code before commits, validating Ansible playbooks |
| performance-engineer | Troubleshooting slow queries, high latency, resource exhaustion |
| documentation-writer | Creating or updating documentation in docs/, writing README files |
| data-engineer | Managing Patroni clusters, troubleshooting replication, database migrations |
| product-strategist | Improving dashboard UX, onboarding flows, feature discovery |