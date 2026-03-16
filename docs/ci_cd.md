# CI/CD Pipeline

## Overview

Deploy applications to app servers via:
1. **Dashboard Wizard** (recommended for new apps)
2. **GitHub Actions** (automated deployments)
3. **Manual deployment** (via SSH)

## Application Creation Wizard

The easiest way to set up a new application:

1. Navigate to http://100.102.220.16:8080/apps/create
2. **Select Framework**: Laravel, Next.js, Svelte, or Go
3. **Enter Details**: Name, description, Git repository URL
4. **Configure Database** (optional):
   - Create PostgreSQL database
   - Allocate Redis database
   - Optional staging environment
5. **Get GitHub Actions Workflow**: Auto-generated with deployment to **both app servers**

### What Gets Created

1. **PostgreSQL Database** (if selected)
   - New database with admin user
   - Optional staging database
   - PgBouncer pool configuration

2. **GitHub Actions Workflow**
   - Build job
   - Deploy jobs for both app servers (re-db and re-node-02)
   - Optional staging environment

3. **Connection Strings**
   - Production and staging database URLs
   - Redis connection

## GitHub Actions Setup

### Required Secrets

Add these to your GitHub repository settings:

| Secret | Value |
|--------|-------|
| `DEPLOY_HOST` | `100.102.220.16` |
| `DEPLOY_USER` | `admin` |
| `DEPLOY_PASSWORD` | `DbAdmin2026!` |
| `DATABASE_URL` | (provided by wizard) |

### Example Workflow (Laravel)

```yaml
name: Deploy myapp

on:
  push:
    branches:
      - main

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Dependencies
        run: composer install --no-dev --optimize-autoloader
      - name: Build Assets
        run: |
          npm ci
          npm run build
      - name: Optimize
        run: |
          php artisan config:cache
          php artisan route:cache
          php artisan view:cache

  deploy-re-db:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to re-db
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          password: ${{ secrets.DEPLOY_PASSWORD }}
          script: |
            cd /opt/apps/myapp
            git pull origin ${{ github.ref_name }}
            composer install --no-dev --optimize-autoloader
            php artisan migrate --force
            php artisan config:cache
            php artisan route:cache
            php artisan view:cache
            sudo systemctl restart myapp

  deploy-re-node-02:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to re-node-02
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          password: ${{ secrets.DEPLOY_PASSWORD }}
          script: |
            cd /opt/apps/myapp
            git pull origin ${{ github.ref_name }}
            composer install --no-dev --optimize-autoloader
            php artisan migrate --force
            php artisan config:cache
            php artisan route:cache
            php artisan view:cache
            sudo systemctl restart myapp
```

### Staging Environment

For staging on `develop` branch:

```yaml
  staging:
    runs-on: ubuntu-latest
    environment: staging
    if: github.ref == 'refs/heads/develop'
    steps:
      - uses: actions/checkout@v4
      # ... build steps ...
      - name: Deploy to Staging
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.DEPLOY_HOST }}
          username: ${{ secrets.DEPLOY_USER }}
          password: ${{ secrets.DEPLOY_PASSWORD }}
          script: |
            cd /opt/apps/staging-myapp
            git pull origin ${{ github.ref_name }}
            sudo systemctl restart staging-myapp
```

## App Server Setup

Each app server needs:

1. Application directory: `/opt/apps/APP_NAME/`
2. Git repository cloned
3. Systemd service

### Initial Setup

```bash
# On app server (re-db or re-node-02)
mkdir -p /opt/apps/myapp
cd /opt/apps/myapp
git clone https://github.com/your-org/myapp.git .

# Create systemd service
cat > /etc/systemd/system/myapp.service << 'EOF'
[Unit]
Description=My Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/apps/myapp
ExecStart=/opt/apps/myapp/start.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable myapp
```

## Manual Deployment

### Via Dashboard

1. Go to http://100.102.220.16:8080/apps
2. Click "Deploy Application"
3. Select target server and branch
4. Click Deploy

### Via SSH

```bash
# Deploy to both app servers
ssh root@100.92.26.38 "cd /opt/apps/myapp && git pull && systemctl restart myapp"
ssh root@100.101.39.22 "cd /opt/apps/myapp && git pull && systemctl restart myapp"
```

## Framework-Specific Notes

### Laravel

- Runs migrations automatically on deploy
- Optimizes config, routes, and views
- Requires `APP_KEY` in environment

### Next.js

- Builds with `npm run build`
- Starts with `npm start`
- Requires `NEXTAUTH_SECRET`, `DATABASE_URL`

### Svelte

- Builds with `npm run build`
- Static output or SSR

### Go

- Builds binary with `go build`
- Runs as systemd service
- No runtime dependencies

## Rollback

If deployment fails:

```bash
# Via SSH - rollback to previous commit
ssh root@100.92.26.38 "cd /opt/apps/myapp && git reset --hard HEAD~1 && systemctl restart myapp"
ssh root@100.101.39.22 "cd /opt/apps/myapp && git reset --hard HEAD~1 && systemctl restart myapp"
```

## Monitoring Deployments

- **Grafana**: http://100.102.220.16:3000
- **Prometheus**: http://100.102.220.16:9090
- **Slack**: Notifications via Alertmanager