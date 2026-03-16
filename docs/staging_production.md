# Staging & Production Deployment

This document explains how deployments work with separate staging and production environments.

## Overview

Each application can have:
- **Production environment**: Deployed from `main` branch
- **Staging environment**: Deployed from `staging` branch

## Branch Structure

```
main        → Production (https://domain.tld)
staging     → Staging (https://staging.domain.tld)
```

## Deployment Flow

### Production Deployment

When you push to `main`:

```
Push to main
     ↓
GitHub Actions triggered
     ↓
Build & Test
     ↓
Deploy to both app servers
     ↓
/opt/apps/{app_name}
Port: 8100 (or assigned)
Environment: production
APP_ENV: production
APP_DEBUG: false
```

### Staging Deployment

When you push to `staging`:

```
Push to staging
     ↓
GitHub Actions triggered
     ↓
Build & Test
     ↓
Deploy to both app servers
     ↓
/opt/apps/{app_name}-staging
Port: 8101 (or assigned +1)
Environment: staging
APP_ENV: staging
APP_DEBUG: true
```

## GitHub Actions Workflow

The auto-generated workflow handles both environments:

```yaml
name: Deploy myapp

on:
  push:
    branches:
      - main
      - staging

jobs:
  build:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: composer install --no-dev --optimize-autoloader
      - name: Build Assets
        run: npm ci && npm run build
      # ... deploy to production

  staging:
    runs-on: ubuntu-latest
    environment: staging
    if: github.ref == 'refs/heads/staging'
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: composer install --no-dev --optimize-autoloader
      - name: Build Assets
        run: npm ci && npm run build
      # ... deploy to staging
```

## Environment Configuration

### Laravel

| Setting | Production | Staging |
|---------|------------|---------|
| `APP_ENV` | `production` | `staging` |
| `APP_DEBUG` | `false` | `true` |
| `APP_URL` | `https://domain.tld` | `https://staging.domain.tld` |
| Database | `{app}_db` | `{app}_db_staging` |

### Next.js / Node.js

| Setting | Production | Staging |
|---------|------------|---------|
| `NODE_ENV` | `production` | `development` |
| `NEXT_PUBLIC_URL` | `https://domain.tld` | `https://staging.domain.tld` |

### Python

| Setting | Production | Staging |
|---------|------------|---------|
| `APP_ENV` | `production` | `staging` |
| `FLASK_ENV` | `production` | `development` |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` | `config.settings.staging` |

## Server Configuration

### Production

- **Directory**: `/opt/apps/{app_name}`
- **Port**: 8100+ (assigned dynamically)
- **nginx config**: `/etc/nginx/sites-available/{app_name}`
- **PHP-FPM pool**: `/etc/php/8.5/fpm/pool.d/{app_name}.conf`
- **Socket**: `/run/php/php8.5-fpm-{app_name}.sock`

### Staging

- **Directory**: `/opt/apps/{app_name}-staging`
- **Port**: 8101+ (production port + 1)
- **nginx config**: `/etc/nginx/sites-available/{app_name}-staging`
- **PHP-FPM pool**: `/etc/php/8.5/fpm/pool.d/{app_name}-staging.conf`
- **Socket**: `/run/php/php8.5-fpm-{app_name}-staging.sock`

## HAProxy Routing

Production and staging use separate HAProxy frontends:

```
# Production
frontend domain.tld_https
    bind :443 ssl crt /etc/haproxy/certs/domain.tld.pem
    use_backend {app}_backend

# Staging  
frontend staging.domain.tld_https
    bind :443 ssl crt /etc/haproxy/certs/staging.domain.tld.pem
    use_backend {app}_staging_backend
```

## Database Separation

Each environment has its own database:

| Environment | Database Name | Owner |
|-------------|--------------|-------|
| Production | `{app_name}` | `{app_name}_admin` |
| Staging | `{app_name}_staging` | `{app_name}_admin` |

Both databases are owned by the same user, allowing migrations to run independently.

## Manual Deployment

### Deploy to Production

```bash
# On both app servers
cd /opt/apps/{app_name}
git pull origin main
composer install --no-dev --optimize-autoloader
npm ci && npm run build
php artisan migrate --force
php artisan config:cache
sudo systemctl reload php8.5-fpm
```

### Deploy to Staging

```bash
# On both app servers
cd /opt/apps/{app_name}-staging
git pull origin staging
composer install --no-dev --optimize-autoloader
npm ci && npm run build
php artisan migrate --force
php artisan config:cache
sudo systemctl reload php8.5-fpm
```

## Testing Deployment

### Verify Production

```bash
curl -s -o /dev/null -w '%{http_code}' https://domain.tld
# Expected: 200
```

### Verify Staging

```bash
curl -s -o /dev/null -w '%{http_code}' https://staging.domain.tld
# Expected: 200
```

### Check Environment

```bash
# SSH to app server
cd /opt/apps/{app_name}
php artisan about | grep Environment
# Production: Environment ..... production

cd /opt/apps/{app_name}-staging
php artisan about | grep Environment
# Staging: Environment ..... staging
```

## Staging Password Protection

Staging environments are protected by HTTP Basic Auth:

- **Username**: Generated during provisioning
- **Password**: Generated during provisioning
- **Location**: Stored in `applications.yml` under `domains[].password`

To find the staging password:

```bash
# On router
cat /opt/dashboard/config/applications.yml | grep -A20 staging
```

## Troubleshooting

### 503 Service Unavailable

1. Check HAProxy backend status:
   ```bash
   ssh root@router-01 "echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep app_name"
   ```

2. Check app server:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://100.92.26.38:8100
   curl -s -o /dev/null -w '%{http_code}' http://100.101.39.22:8100
   ```

3. Check PHP-FPM:
   ```bash
   ssh root@app-server "systemctl status php8.5-fpm"
   ```

### Assets Not Loading

1. Check APP_URL in .env:
   ```bash
   ssh root@app-server "grep APP_URL /opt/apps/{app_name}/.env"
   ```

2. Verify manifest exists:
   ```bash
   ssh root@app-server "ls -la /opt/apps/{app_name}/public/build/manifest.json"
   ```

3. Rebuild assets:
   ```bash
   ssh root@app-server "cd /opt/apps/{app_name} && npm run build"
   ```

### Database Connection Failed

1. Verify database exists:
   ```bash
   psql -h 100.102.220.16 -p 5000 -U patroni_superuser -l | grep {app_name}
   ```

2. Check .env credentials:
   ```bash
   ssh root@app-server "grep DB_ /opt/apps/{app_name}/.env"
   ```

3. Test connection:
   ```bash
   psql -h 100.102.220.16 -p 5000 -U {app_name}_admin -d {app_name}_staging
   ```