# Infrastructure Dashboard

Web-based management interface for Quantyra infrastructure.

## Access

```
URL: http://100.102.220.16:8080
Username: admin
Password: DbAdmin2026!
```

> **Note**: Only accessible from Tailscale network (100.64.0.0/10)

## Features

### Dashboard Home
- PostgreSQL cluster status (primary/replica)
- Redis status and memory usage
- Active alerts from Prometheus
- **Disk space monitoring** for all servers (via Prometheus/node_exporter)
- Server overview with quick links

### Application Creation Wizard
Navigate to **Applications → Create Application** to:

1. **Select Framework**: Laravel, Next.js, Svelte, or Go
2. **Configure App Details**: Name, description, Git repository
3. **Database Options**: Create PostgreSQL database with optional staging environment
4. **Generate GitHub Actions**: Auto-generated workflow deploying to **both app servers** for redundancy

#### Supported Frameworks
- **Laravel**: composer install, npm build, artisan optimize/migrate
- **Next.js**: npm ci, npm run build
- **Svelte**: npm ci, npm run build  
- **Go**: go build

### Application Management
- View application status on all app servers
- **Restart/Reload/Stop** applications via API buttons
- Deploy/redeploy applications
- Manage GitHub secrets per app
- **Domain Management** with SSL provisioning
- **Delete App** or **Delete Staging** environments

### Application Status Page
Navigate to **Applications → [App Name]** to view and manage:

1. **Service Status**: Real-time nginx and PHP-FPM status on both app servers
2. **Control Buttons**:
   - **Restart App**: Restart the application service
   - **Reload Nginx**: Reload nginx configuration without downtime
   - **Reload PHP-FPM**: Reload PHP-FPM pool configuration
   - **Clear Cache**: Run framework-specific cache clear (Laravel: `artisan cache:clear`, etc.)
3. **Passwords**: Database credentials displayed for easy copy
4. **Domains**: List of provisioned domains with staging indicators
5. **GitHub Actions**: View deployment workflow status

### Domain Management with SSL
Navigate to **Applications → [App Name] → Domains** to:

1. **Multi-Domain Provisioning**: Select multiple Cloudflare zones with search and tags
2. **Per-Domain Configuration**:
   - **Production**: Root domain (`domain.tld`) with automatic `www` redirect
   - **Staging**: Subdomain (`staging.domain.tld`) with password protection
   - **Additional CNAMEs**: API, dashboard, etc.
3. **Live Preview**: See exactly what DNS records will be created
4. **Automatic SSL**: Certbot provisions Let's Encrypt certificates on both routers
5. **Security Rules**: 5 Cloudflare WAF rules applied automatically
6. **WWW Redirect**: Production domains automatically create `www.domain.tld` → `domain.tld` redirect

#### Production vs Staging

| Type | Pattern | Access | Security |
|------|---------|--------|----------|
| Production | `domain.tld` | Public | WAF rules |
| WWW | `www.domain.tld` | Redirect to root | WAF rules |
| Staging | `staging.domain.tld` | Password protected | WAF rules + Basic Auth |

#### Domain Provisioning UI Features

- **Zone Search**: Filter Cloudflare zones by name
- **Multi-Select**: Select multiple domains at once with chips display
- **Configuration Cards**: Per-domain toggle for production root vs subdomain
- **Staging Toggle**: Enable/disable staging environment per domain
- **CNAME Input**: Add additional subdomains (api, dashboard, etc.)
- **Preview Panel**: Shows all DNS records to be created before submission

#### Cloudflare Security Rules

5 security rules are automatically created per domain:

| # | Rule Name | Action | Purpose |
|---|-----------|--------|---------|
| 1 | Block Bad Bots | Block | Block known bot user agents |
| 2 | Challenge Suspicious | Managed Challenge | Challenge suspicious requests |
| 3 | Challenge Known Attackers | Managed Challenge | Challenge IPs from threat feeds |
| 4 | Rate Limit API | Managed Challenge | Rate limit API endpoints |
| 5 | Block SQL Injection | Block | Block SQL injection attempts |

#### Client IP Forwarding

Real client IPs are passed through to applications via:
```
Cloudflare → HAProxy → Nginx → App
     ↓           ↓         ↓
CF-Connecting-IP → X-Forwarded-For → X-Real-IP
```

#### Manual DNS Setup

Create two A records in Cloudflare:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | subdomain | 172.93.54.112 (router-01) | Proxied |
| A | subdomain | 23.29.118.6 (router-02) | Proxied |

### Delete Application
Navigate to **Applications → [App Name] → Delete** to remove an application:

**Delete Staging Environment**:
- Removes staging nginx config from both app servers
- Removes staging PHP-FPM pool from both app servers
- Removes staging SSL certificate from both routers
- Keeps DNS records intact
- Keeps Cloudflare WAF rules intact
- Keeps production environment intact

**Delete Entire Application**:
- Removes all server configurations (app servers + routers)
- Removes all SSL certificates
- Keeps all DNS records intact
- Keeps all Cloudflare WAF rules intact
- Removes databases (after confirmation)
- Removes GitHub secrets
- Removes application from applications.yml

**Note**: DNS and WAF rules are NOT deleted to allow easy redeployment or manual cleanup.

### Cloudflare Integration

Configure Cloudflare API credentials in **Settings**:
1. Get API token from https://dash.cloudflare.com/profile/api-tokens
2. Required permissions: Zone.DNS.Edit, Zone.Zone.Read, Zone.Firewall.Edit
3. Token and zones are auto-detected via API

Once configured, domains are automatically provisioned with:
- DNS records for both routers
- SSL certificates via Let's Encrypt
- 5 WAF security rules
- Staging password protection
- WWW redirect for production

See [Cloudflare Documentation](cloudflare.md) for details.

### Database Management
- List all configured databases with **passwords visible**
- Create new databases with users
- View connection strings with actual passwords
- Automatic PgBouncer configuration

### Server Management
- View all servers status
- Disk space usage with color-coded warnings
- Quick SSH access information
- Connection string reference

### Documentation
- View all docs from `/docs` folder
- Markdown rendering with tables and code blocks

## Architecture

### Server Classification

| Type | Servers | Purpose |
|------|---------|---------|
| Database Servers | re-node-01, re-node-03, re-node-04 | PostgreSQL + Redis (node-01,03) |
| App Servers | re-db, re-node-02 | Application deployment (both for redundancy) |
| Routers | router-01, router-02 | HAProxy, PgBouncer, Monitoring, SSL Termination |

### Application Deployment Architecture

```
Cloudflare (Proxied)
    ↓ CF-Connecting-IP
HAProxy (routers) - SSL Termination
    ↓ X-Forwarded-For, X-Real-IP
Nginx (app servers)
    ↓
PHP-FPM / Node.js / Go App
```

### Disk Space Monitoring

Uses Prometheus with node_exporter on all servers:

```bash
# API endpoint
GET /api/disk-space

# Returns for each server:
{
  "server_name": {
    "total": "629.9GB",
    "used": "115.2GB", 
    "available": "514.6GB",
    "percent": "18%"
  }
}
```

Color coding:
- **Yellow**: > 60% used
- **Red**: > 80% used

## API Endpoints

### Health Check
```
GET /api/health
```

Returns PostgreSQL and Redis status.

### Disk Space
```
GET /api/disk-space
```

Returns disk usage for all servers via Prometheus.

### Alerts
```
GET /api/alerts
```

Returns current firing alerts from Prometheus.

### Databases
```
GET /api/databases
```

Returns configured and live PostgreSQL databases.

### Servers
```
GET /api/servers
```

Returns server status information.

### Application Control
```
POST /api/restart-app/<app_name>
POST /api/reload-nginx/<app_name>
POST /api/reload-phpfpm/<app_name>
POST /api/clear-cache/<app_name>
```

Control applications on app servers. Returns JSON with status.

### Domain Provisioning
```
POST /api/provision-domain
```

Provision domains with DNS, SSL, and security rules. Request body:
```json
{
  "app_name": "myapp",
  "domains": [
    {
      "zone_id": "abc123",
      "zone_name": "xotec.io",
      "production_root": true,
      "production_subdomain": null,
      "staging": true,
      "cnames": ["api"]
    }
  ]
}
```

### Delete Operations
```
POST /api/delete-app/<app_name>
POST /api/delete-staging/<app_name>
```

Delete applications or staging environments.

## Local Development

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

Then open http://localhost:8080

## Deployment

```bash
# Sync all files
scp dashboard/app.py root@router-01:/opt/dashboard/
scp dashboard/templates/*.html root@router-01:/opt/dashboard/templates/
scp dashboard/static/style.css root@router-01:/opt/dashboard/static/

# Restart service
ssh root@router-01 "systemctl restart dashboard"
```

## Directory Structure

```
dashboard/
├── app.py                    # Flask application
├── requirements.txt          # Python dependencies
├── templates/
│   ├── base.html            # Base template with navigation
│   ├── index.html           # Dashboard home
│   ├── databases.html       # Database list (shows passwords)
│   ├── add_database.html    # Create database form
│   ├── connection.html      # Connection strings (shows passwords)
│   ├── servers.html         # Server list
│   ├── apps.html            # App servers
│   ├── create_app.html      # Application wizard
│   ├── create_app_result.html
│   ├── app_status.html      # App details with passwords & workflow
│   ├── app_domains.html     # Domain management
│   ├── docs_index.html      # Documentation index
│   └── docs_view.html       # Document viewer
└── static/
    └── style.css            # Stylesheet

On Server (router-01):
/opt/dashboard/
├── app.py
├── templates/
├── static/
├── config/
│   ├── databases.yml        # Database configuration
│   └── applications.yml     # Application configuration
└── docs/                    # Documentation files

On Routers:
/etc/haproxy/
├── haproxy.cfg              # Main HAProxy config
├── domains/                 # Domain-specific configs
└── certs/                   # SSL certificates

/opt/scripts/
└── provision-domain.sh      # Domain + SSL provisioning script
```

## GitHub Actions Integration

The application wizard generates a complete GitHub Actions workflow that:

1. **Builds** the application
2. **Deploys to BOTH app servers** (re-db and re-node-02) in parallel
3. Optionally creates a **staging environment** on the `develop` branch

### Required GitHub Secrets

| Secret | Value |
|--------|-------|
| DEPLOY_HOST | 100.92.26.38 |
| DEPLOY_USER | admin |
| DEPLOY_PASSWORD | DbAdmin2026! |
| DATABASE_URL | postgres://user:pass@100.102.220.16:6432/dbname |

## Monitoring Integration

The dashboard integrates with:

- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000
- **HAProxy Stats**: http://100.102.220.16:8404 (admin / jFNeZ2bhfrTjTK7aKApD)

All accessible from the navigation bar.

## Important Credentials

| Service | Username | Password |
|---------|----------|----------|
| Dashboard | admin | DbAdmin2026! |
| HAProxy Stats | admin | jFNeZ2bhfrTjTK7aKApD |
| PostgreSQL Superuser | patroni_superuser | 2e7vBpaaVK4vTJzrKebC |
| Redis | - | CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk |