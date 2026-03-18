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

1. **Select Framework**: Laravel, Next.js, Svelte, Python, or Go
2. **Configure App Details**: Name, description, Git repository
3. **Build Settings**: Auto-detect or customize install/build/migrate/start commands
4. **Database Options**: Create PostgreSQL database with separate user/admin accounts for production and staging
5. **Domain Configuration**: Select domains from Cloudflare with multi-select, configure production/staging/CNAMEs
6. **Review**: Summary of all settings with generated GitHub Actions workflow

#### Supported Frameworks
- **Laravel**: composer install, npm build, artisan optimize/migrate, DB_CONNECTION=pgsql auto-configured
- **Next.js**: npm ci, npm run build
- **Svelte**: npm ci, npm run build
- **Python**: pip install -r requirements.txt, gunicorn
- **Go**: go mod download, go build

Toolchain baseline (updated 2026-03-17 13:10 EDT):
- App servers now run Composer 2.9.5 (`/usr/local/bin/composer`) for PHP 8.5 compatibility during deploy steps.
- Deprecated Composer `E_STRICT` notice flood is resolved; deploy failures now surface app/runtime errors directly.

Runtime and permission baseline (updated 2026-03-17 13:52 EDT):
- Application tooling and non-Laravel service runtimes on app servers are standardized to non-root user `webapps`.
- Dashboard orchestration auto-creates `webapps` if missing and runs clone/build/setup steps under that user.
- Laravel writable directories (`storage`, `bootstrap/cache`) are permissioned for `www-data` group access without changing app ownership from `webapps`.

#### Permission Model (Updated 2026-03-17 23:55 EDT)

| Path | Owner | Group | Mode | Purpose |
|------|-------|-------|------|---------|
| `/opt/apps/{app}` | webapps | webapps | 755/644 | Code world-readable for www-data execution |
| `storage/` | webapps | www-data | 2775 (setgid) | New files inherit www-data group for write access |
| `bootstrap/cache/` | webapps | www-data | 2775 (setgid) | Same |
| `.env` | webapps | www-data | 640 | www-data reads, not world-readable (security) |

**Why this works:**
- `www-data` (PHP-FPM) can **read** all PHP files (world-readable 644)
- `www-data` can **write** to storage/ and bootstrap/cache (group www-data + setgid)
- `www-data` **cannot modify** application code (security best practice)
- `webapps` user can `git pull`, `composer install`, etc.

#### Laravel Deployment Setup (Updated 2026-03-17 23:55 EDT)

On first deployment, the dashboard automatically:
1. Detects framework as Laravel (presence of `composer.json` + `artisan`)
2. Checks if PHP-FPM pool exists (`/etc/php/8.5/fpm/pool.d/{app}.conf`)
3. If not, creates nginx + PHP-FPM configuration via `setup_laravel_app()`
4. Ensures `.env` has correct permissions (`webapps:www-data 640`)
5. Runs migrations after backing up database

#### Configurable Branch Selection (Updated 2026-03-17 22:54 EDT)

During app creation, users can configure:
- **Production Branch**: Branch that triggers production deployments (default: `main`)
- **Staging Branch**: Branch that triggers staging deployments (default: `staging`)

Backward compatibility: Existing apps without branch config use defaults (`main`/`staging`).

#### Domain Wizard (Step 5)
When Cloudflare is configured in Settings:

- **Search and Select**: Filter domains from all Cloudflare zones
- **Multi-Domain Support**: Select multiple domains at once
- **Per-Domain Configuration**:
  - Production: Root domain or subdomain
  - Staging: Enable/disable with custom prefix
  - Additional CNAMEs: api, dashboard, admin, etc.
  - Staging password: Auto-generated or custom
- **Live Preview**: See exactly what DNS records and domains will be created

#### Staging Password Protection (Updated 2026-03-18)

All staging environments are password-protected via HAProxy HTTP Basic Auth:

- **Username**: `admin`
- **Password**: Auto-generated (16 chars) or custom during domain provisioning
- **Storage**: Password stored in app config (`domains[].password`)
- **Visibility**: Displayed in Domains tab for dashboard users (Tailscale-only access)
- **htpasswd**: `/etc/haproxy/htpasswd/{app_name}-staging.htpasswd`

Access staging via:
```bash
curl -u admin:<password> https://staging.domain.tld
```

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

#### Deployment Phases

Implemented 2026-03-17 10:56 EDT. Deployment UX now shows two distinct phases:

1. **Deploy Phase**: pull/build/start/health checks on app servers
2. **Domain Provisioning Phase**: DNS + SSL + router provisioning for pending domains

**Important:** Domain provisioning only runs during **production** deploys. Staging deploys show "N/A" because:
- Staging domains are provisioned during production deploy or app creation
- Staging deploy only updates code, not DNS/SSL infrastructure

Behavior:
- If deploy phase fails, domain provisioning is explicitly marked **skipped**.
- App status page shows a clear failed deploy indicator.
- Users can opt into a manual fallback action: **Force Provision Pending Domains**.
- For first-time deploy failures with no known-good commit, rollback is not attempted; UI reports rollback unavailable.

#### Delete Consistency (Updated 2026-03-17 11:38 EDT)

- App delete, staging delete, and database delete flows are treated as infra lifecycle operations.
- Cleanup must remove both runtime artifacts (DB/users) and corresponding config entries (including staging records) to avoid stale state in dashboard views.

### Domain Management with SSL
Navigate to **Applications → [App Name] → Domains** to:

1. **Add Additional Domains**: Select Cloudflare zones and add production/staging/CNAME domains after initial deployment
2. **Per-Domain Configuration**:
   - **Production**: Root domain (`domain.tld`) with automatic `www` redirect
   - **Staging**: Subdomain (`staging.domain.tld`) with password protection
   - **Additional CNAMEs**: API, dashboard, etc.
3. **Live Preview**: See exactly what DNS records will be created
4. **Automatic SSL**: Certbot provisions Let's Encrypt certificates on both routers
5. **Security Rules**: 5 Cloudflare WAF rules applied automatically
6. **WWW Redirect**: Production root domains automatically create `www.domain.tld` → `domain.tld` redirect

Initial domains selected in the create wizard are stored in the same `domains` list and are provisioned during deployment.
Cloudflare zones already assigned to an app are excluded from selection in other apps.

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
- Drops staging database users (`{app}_staging_user`, `{app}_staging_admin`)
- Drops staging database
- Keeps DNS records intact
- Keeps Cloudflare WAF rules intact
- Keeps production environment intact

**Delete Entire Application**:
- Removes all server configurations (app servers + routers)
- Removes all SSL certificates from both routers
- Removes HAProxy registry entries and rebuilds config
- Stops PM2 processes (for Node.js apps)
- Drops all database users (`{app}_user`, `{app}_admin`, `{app}_staging_user`, `{app}_staging_admin`)
- Drops databases (after confirmation)
- Removes secrets file (`/opt/dashboard/secrets/{app}.yaml`)
- Removes application from applications.yml
- Keeps all DNS records intact
- Keeps all Cloudflare WAF rules intact

**Note**: DNS and WAF rules are NOT deleted to allow easy redeployment or manual cleanup.

### GitHub Repository Validation

When creating an application, the GitHub repository is validated before any resources are created:

1. **URL Format Check**: Validates `https://github.com/owner/repo` format
2. **Repository Access**: Verifies the repository exists and is accessible
3. **Error Handling**: Shows clear error message if repo not found

**Supported Formats:**
- `https://github.com/owner/repo`
- `git@github.com:owner/repo.git`
- `owner/repo` (short form)

**Behavior:**
- If validation fails, app creation is blocked with an error message
- Both public and private repos are supported (private requires GitHub token)

### DNS Record Management

#### Read-Only DNS View

When configuring domains, existing DNS records are displayed in read-only mode:

- **Record Table**: Shows all existing DNS records for selected zones
- **Conflict Indicators**: Highlights records that will be updated
- **Lock Icons**: Indicates records that cannot be modified through the dashboard

#### Conflict Rules

| Record Type | If Exists | Action |
|-------------|-----------|--------|
| `@` (root A) | Any | Override with app IP |
| `www` | Any | Override with app IP |
| `staging` | Any | Override with app IP |
| Other CNAMEs | Exists | Block - show error, require manual deletion in Cloudflare |

#### DNS Refresh

Click the refresh button to reload DNS records from Cloudflare:
- On the **Domains** page for existing apps
- In the **Domain Configuration** step (step 5) of the app creation wizard

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

#### Database User Structure

When creating a database for an application, the following users are automatically created:

**Production Database:**
- `{app_name}_user` - Standard read/write user
- `{app_name}_admin` - Administrative user with CREATEDB privilege

**Staging Database (if enabled):**
- `{app_name}_staging_user` - Standard read/write user for staging
- `{app_name}_staging_admin` - Administrative user for staging

All passwords are auto-generated and stored as encrypted secrets.

Runtime deployment model (updated 2026-03-17 14:58 EDT):
- SOPS-encrypted secrets remain source-of-truth on dashboard host (`/opt/dashboard/secrets/*.yaml`).
- Deploy flow generates runtime `.env` from SOPS secrets and writes it to each app server just before deploy execution.
- AGE private key remains only on router-01; app servers do not hold SOPS key material.
- Branch policy is strict: `main` deploys production only, `staging` deploys staging only, all other branches are ignored.
- Production and staging deploy to separate app directories (`/opt/apps/{app_name}` and `/opt/apps/{app_name}-staging`).

### Secrets Management

Navigate to **Secrets** to manage encrypted secrets:

#### Global Secrets
- Shared across all applications
- Editable via UI
- Examples: DEPLOY_HOST, DEPLOY_USER, STRIPE_SECRET_KEY

#### Application Secrets
- Per-application secrets
- Scoped in one app file: `shared`, `production`, `staging`
- Merge precedence for generated runtime env: `global` -> `shared` -> environment scope -> computed infra vars
- **Import from .env file** - Upload a .env file to batch import secrets
- Automatic database credentials:
  - `DB_USERNAME`, `DB_PASSWORD` - Production database user
  - `DB_ADMIN_USERNAME`, `DB_ADMIN_PASSWORD` - Production admin user
  - `STAGING_DB_USERNAME`, `STAGING_DB_PASSWORD` - Staging user (if enabled)
  - `STAGING_DB_ADMIN_USERNAME`, `STAGING_DB_ADMIN_PASSWORD` - Staging admin (if enabled)

#### Importing Secrets from .env

1. Navigate to **Applications → [App Name] → Secrets**
2. Click **Import .env File**
3. Select a .env file with format:
   ```
   STRIPE_SECRET_KEY=sk_test_xxxxx
   SENDGRID_API_KEY=SG.xxxxx
   AWS_ACCESS_KEY_ID=AKIAxxxxx
   ```
4. Secrets are automatically encrypted and stored

Deploy-time behavior:
- Dashboard validates required runtime keys (Laravel) before deploy and fails fast with missing-key names.
- Laravel first deploy auto-generates `APP_KEY` when missing and persists it in encrypted app secrets.
- `.env` is written atomically with `webapps:webapps` ownership and `640` mode to:
  - `/opt/apps/{app_name}/.env` (production)
  - `/opt/apps/{app_name}-staging/..env` (staging)
- Secret add/edit/delete operations trigger `.env` regeneration + sync to app servers for affected environment(s).

#### Secrets UI (Updated 2026-03-17)

The secrets management page now uses **tab-based navigation** instead of a dropdown:

- **Tabs**: All | Shared | Production | Staging
- **Scope Badges**: Color-coded indicators for each secret's scope
  - Shared: Blue (#8ab4f8)
  - Production: Green (#81c784)
  - Staging: Orange (#ffb74d)
- **Import .env**: Batch import respects currently selected scope

#### Database Deletion (Updated 2026-03-17)

**Important:** Database deletion now respects scope boundaries:

- Deleting a **production database** only removes the production database and its users
- Deleting a **staging database** only removes the staging database and its users
- The `include_staging` parameter is now correctly scoped to the requested deletion

This prevents accidental deletion of staging environments when managing production databases.

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

### Deployment APIs
```
POST /api/apps/<app_name>/deploy
POST /api/webhooks/github/<app_name>
POST /<app_name>  (webhook host only)
```

- `/api/apps/<app_name>/deploy`: authenticated dashboard/API deploy
- `/api/webhooks/github/<app_name>`: public GitHub webhook endpoint with HMAC signature validation (`X-Hub-Signature-256`)
- `POST https://hooks.quantyralabs.cc/<app_name>`: canonical GitHub webhook URL

Webhook branch gating:
- `refs/heads/main` -> production deploy only
- `refs/heads/staging` -> staging deploy only
- other branches -> ignored (no deployment)

**Ingress policy:**
- Dashboard host and all non-webhook APIs are Tailscale-only
- Public webhooks use dedicated host: `https://hooks.quantyralabs.cc/<app_name>`
- `hooks.quantyralabs.cc` only allows webhook POST traffic; all other paths return 404

### Cloudflare DNS Records
```
GET /api/cloudflare/zones
GET /api/cloudflare/zones/<zone_id>/dns
```

List Cloudflare zones and their DNS records. DNS records are returned in read-only mode.

### GitHub Repository Validation
```
GET /api/github/validate?repo=https://github.com/owner/repo
```

Validate a GitHub repository exists and is accessible. Returns:
```json
{
  "valid": true,
  "private": false,
  "error": null
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

GitHub Actions are optional for CI checks (lint/test/build). Deployment is handled by dashboard webhooks with strict branch mapping.

Webhook deploy policy:
1. `refs/heads/main` -> production deploy
2. `refs/heads/staging` -> staging deploy
3. Any other branch -> ignored

If you use Actions, keep them CI-only or as a workflow-dispatch helper that calls dashboard deploy endpoints.

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
