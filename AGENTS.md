# Agent Instructions

This file contains instructions for AI agents working on this infrastructure repository.

## Project Overview

Infrastructure-as-code repository for managing Quantyra VPS infrastructure with:
- PostgreSQL/Patroni cluster (3 nodes)
- Redis cluster with Sentinel (2 nodes)
- HAProxy routers (2 nodes)
- App servers (2 nodes)
- Monitoring stack (Prometheus, Grafana, Alertmanager)
- Web-based management dashboard (Flask)

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
│   ├── templates/               # Jinja2 HTML templates
│   ├── config/                  # Runtime config (databases.yml, applications.yml)
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
- **Dashboard**: http://100.102.220.16:8080 (admin / DbAdmin2026!)
- **App Servers**: re-db (100.92.26.38), re-node-02 (100.89.130.19, public: 23.227.173.245)
- **Routers**: router-01 (100.102.220.16), router-02 (100.116.175.9)

### Critical Credentials
- **PostgreSQL Leader**: re-node-03 (100.114.117.46)
- **Redis Master**: re-node-01 (100.126.103.51:6379)
- **HAProxy Stats**: Port 8404, auth: admin:jFNeZ2bhfrTjTK7aKApD
- **Redis Password**: CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
- **Patroni Superuser**: patroni_superuser / 2e7vBpaaVK4vTJzrKebC
- **Cloudflare API Token**: zf5ncwuOaaXz2IJ1BVBu8myf0HQt5IxkPje_Rm1V
- **Cloudflare Zone ID** (xotec.io): 26470f68ef4dbbf7bf5a770630aa2a97
- **Cloudflare Zone ID** (rentalfixer.app): d565e98b12effe08e530da729b82c0b9

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

### HAProxy Configuration (CRITICAL)
**Consolidated Frontend Architecture**: All domains share a SINGLE HAProxy frontend, not separate frontends per domain.

```
/etc/haproxy/domains/
├── web_http.cfg       # Single HTTP frontend (redirects)
├── web_https.cfg      # Single HTTPS frontend (ALL certificates)
├── web_backends.cfg   # All application backends
└── registry.conf      # Domain → App → Port mapping
```

**Why consolidated?**
- Multiple frontends on port 443 cause SNI routing issues
- Single frontend with multiple certificates works reliably
- HAProxy routes by Host header after SSL termination

**Never create per-domain frontend configs.** Always use the registry and rebuild:
```bash
/opt/scripts/provision-domain.sh --rebuild
```

### Key Architectural Decisions

- **Consolidated HAProxy Frontend**: All domains share a SINGLE frontend on port 443 with multiple certificates. Routing uses Host header ACLs after SSL termination.
- **DNS Round-Robin + HTTP Retry**: Cloudflare DNS returns both router IPs; clients retry the other on failure.
- **Tailscale VPN**: All server-to-server communication uses encrypted Tailscale network (100.64.0.0/10).
- **Separate Production/Staging Ports**: Production (8100-8199), Staging (9200-9299) to avoid conflicts with system services.

### Traffic Flow
1. **Cloudflare** terminates SSL at edge, routes to routers via DNS round-robin
2. **HAProxy routers** (consolidated frontend) route by Host header to app backends
3. **App servers** run nginx + PHP-FPM (Laravel) or systemd + Node.js
4. **Database layer** accessed via HAProxy ports 5000 (write) / 5001 (read)

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
| `scripts/provision-domain.sh` | Provision domain with SSL, HAProxy config |
| `scripts/deploy-app.sh` | Deploy Laravel/Node.js app to servers |
| `scripts/sync-configs.sh` | Sync configs from repo to servers |

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

### Dashboard Changes

1. **Local Development**:
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

2. **Deploy**:
   ```bash
   scp dashboard/app.py root@100.102.220.16:/opt/dashboard/app.py
   scp dashboard/templates/*.html root@100.102.220.16:/opt/dashboard/templates/
   ssh root@100.102.220.16 "systemctl restart dashboard"
   ```

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

### Provision New Domain
1. Dashboard → Applications → [App] → Domains
2. Select Cloudflare zones
3. Configure production root + staging
4. Provision

### Delete Application
1. Dashboard → Applications → [App] → Delete
2. Choose: Delete Staging or Delete Entire App
3. Confirm database deletion if prompted
4. Note: DNS and WAF rules are NOT deleted (manual cleanup in Cloudflare if needed)

### Check Service Status
```bash
# Dashboard
ssh root@100.102.220.16 "systemctl status dashboard"

# App servers
ssh root@100.92.26.38 "systemctl status nginx php8.5-fpm"
ssh root@100.89.130.19 "systemctl status nginx php8.5-fpm"
```

## Important Notes

1. **Always deploy to both app servers** for redundancy
2. **WWW redirect is automatic** for production root domains
3. **Staging is always password protected**
4. **Delete staging** keeps production intact
5. **PHP 8.5** is installed on app servers
6. **Node.js 20** is installed on app servers
7. **No linting/tests** configured - manual testing required
8. **HAProxy uses consolidated frontends** - never create per-domain frontend configs
9. **Use registry.conf** to manage domains, then rebuild configs
10. **SSL uses DNS-01 challenge** - works with Cloudflare proxy enabled
11. **Always sync configs after server changes** - see Config Sync Workflow below

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
- `/docs/docker_compose_plan.md` - Docker deployment for NAS and Tailscale
- `/docs/dashboard.md` - Dashboard features and API
- `/docs/domain_provisioning.md` - Domain provisioning system
- `/docs/haproxy_ha_dns.md` - HAProxy configuration and load balancing
- `/docs/cloudflare.md` - Cloudflare integration
- `/docs/monitoring.md` - Monitoring setup
- `/docs/framework_builds.md` - Build process for each framework
- `/docs/staging_production.md` - Staging and production deployment
- `/docs/disaster_recovery.md` - DR procedures

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