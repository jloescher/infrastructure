# Agent Instructions

This file contains instructions for AI agents working on this infrastructure repository.

## Project Overview

Infrastructure-as-code repository for managing Quantyra VPS infrastructure with:
- PostgreSQL/Patroni cluster (3 nodes)
- Redis cluster with Sentinel (2 nodes)
- HAProxy routers (2 nodes)
- App servers (2 nodes)
- Monitoring stack (Prometheus, Grafana, Alertmanager)
- Web-based management dashboard

## Key Information

### Server Access
- **Dashboard**: http://100.102.220.16:8080 (admin / DbAdmin2026!)
- **App Servers**: re-db (100.92.26.38), re-node-02 (100.101.39.22)
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

### Testing

No automated tests configured. Test manually:
1. Dashboard functionality via browser
2. API endpoints via curl
3. Domain provisioning end-to-end
4. Delete staging/production environments

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

### Application Deployment
- Laravel apps: nginx + PHP-FPM (NOT systemd service)
- Each app gets unique port (8100+)
- PHP-FPM pool per application
- Deploy to BOTH app servers for redundancy

### Client IP Forwarding
```
Cloudflare → HAProxy → Nginx → App
     ↓           ↓         ↓
CF-Connecting-IP → X-Forwarded-For → X-Real-IP
```

### Security Rules
- Rules 2, 3, 4 use "managed_challenge" (shows CAPTCHA)
- Rules 1, 5 use allow/block (immediate action)

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
ssh root@100.101.39.22 "systemctl status nginx php8.5-fpm"
```

### Docker Compose Deployment

Deploy the dashboard on any machine connected to Tailscale:

```bash
cd docker
cp .env.example .env
# Edit .env with credentials
./scripts/deploy.sh start
```

**Services:**
- Dashboard: http://localhost:8080
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
- Alertmanager: http://localhost:9093

**Commands:**
- `./scripts/deploy.sh start` - Start services
- `./scripts/deploy.sh stop` - Stop services
- `./scripts/deploy.sh logs` - View logs
- `./scripts/deploy.sh backup` - Backup data

**Requirements:**
- Docker and Docker Compose installed
- Connected to Tailscale network
- Valid credentials in `.env`

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
- `/docs/session_2026-03-15.md` - Session summary with all changes
- `/docker/README.md` - Docker Compose quick start guide

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

## Build Tool Detection

The dashboard automatically detects build tools from:
- `vite.config.js` → Vite
- `next.config.js` → Next.js
- `svelte.config.js` → SvelteKit
- `nuxt.config.js` → Nuxt
- `angular.json` → Angular
- `package.json` scripts → Build command detected

## Environment Configuration

Apps automatically configured on deploy:

**Laravel:**
- `APP_ENV` based on environment
- `APP_DEBUG=true` for staging, `false` for production
- `APP_URL` from provisioned domain
- `DB_*` from database config
- `REDIS_*` if Redis enabled

**Node.js:**
- `NODE_ENV` based on environment
- `NEXT_PUBLIC_URL` if Next.js