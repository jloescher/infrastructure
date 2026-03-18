# Framework Build Processes

This document outlines the standardized build and deployment process for each supported framework.

## Runtime Security Baseline

- App-server language/tooling commands run as non-root user `webapps`.
- Generated non-Laravel systemd services run as `webapps:webapps`.
- Laravel keeps app ownership as `webapps` while writable paths (`storage`, `bootstrap/cache`) are group-writable for `www-data`.
- Deployment guardrails re-apply ownership/permissions to prevent drift during updates.
- Runtime `.env` files are generated during deploy from SOPS-managed dashboard secrets (router-01 key boundary), not committed plaintext files.

## Build Tool Detection

The dashboard automatically detects build tools and frameworks by scanning config files:

### Detected Config Files

| Config File | Framework/Tool |
|-------------|----------------|
| `vite.config.js`, `vite.config.ts` | Vite |
| `next.config.js`, `next.config.mjs` | Next.js |
| `svelte.config.js` | SvelteKit |
| `nuxt.config.js`, `nuxt.config.ts` | Nuxt |
| `gatsby-config.js` | Gatsby |
| `angular.json` | Angular |
| `vue.config.js` | Vue CLI |
| `webpack.config.js` | Webpack |
| `rollup.config.js` | Rollup |
| `tsconfig.json` | TypeScript |

### Package.json Script Detection

The dashboard reads `package.json` scripts to find the appropriate build command:

1. Looks for `build` script → `npm run build`
2. Falls back to `compile`, `bundle`, `prod`, `production`
3. If no build script found, skips build step

### Package Manager Detection

Based on lock files present:

| Lock File | Install Command |
|-----------|-----------------|
| `pnpm-lock.yaml` | `pnpm install` |
| `yarn.lock` | `yarn install` |
| `package-lock.json` or none | `npm install` |

### Dependency Analysis

Checks `dependencies` and `devDependencies` to identify frameworks:
- `next` → Next.js
- `@sveltejs/kit` → SvelteKit
- `nuxt` → Nuxt
- `gatsby` → Gatsby
- `@angular/core` → Angular
- `vue` → Vue
- `vite` → Vite

---

## Laravel

### Requirements
- PHP 8.5+
- Composer
- Node.js 20+ (for frontend assets)
- PostgreSQL client

### Build Process

```bash
# 1. Install PHP dependencies
composer install --no-dev --optimize-autoloader

# 2. Ensure Node.js 20+ is installed
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# 3. Install frontend dependencies and build (auto-detected)
npm install  # or yarn install, pnpm install based on lock files
npm run build  # or detected build script

# 4. Environment setup
cp .env.example .env
php artisan key:generate

# 5. Configure database (auto-injected on deploy)
# DB_HOST, DB_PORT, DB_DATABASE, DB_USERNAME, DB_PASSWORD

# 6. Configure Redis (auto-injected if enabled)
# REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

# 7. Configure APP_URL (auto-set from provisioned domain)
# APP_URL=https://your-domain.com
# ASSET_URL=https://your-domain.com

# 8. Optimize for production
php artisan config:cache
php artisan route:cache
php artisan view:cache

# 9. Run migrations
php artisan migrate --force

# 10. Set permissions
chown -R webapps:webapps /opt/apps/{app_name}
chgrp -R www-data /opt/apps/{app_name}/storage /opt/apps/{app_name}/bootstrap/cache
chmod -R ug+rwX /opt/apps/{app_name}/storage /opt/apps/{app_name}/bootstrap/cache
find /opt/apps/{app_name}/storage /opt/apps/{app_name}/bootstrap/cache -type d -exec chmod 2775 {} \;
chgrp www-data /opt/apps/{app_name}/.env
chmod 640 /opt/apps/{app_name}/.env
php artisan storage:link
```

### Environment Variables Auto-Injected

| Variable | Source |
|----------|--------|
| `DB_HOST` | PostgreSQL host via PgBouncer |
| `DB_PORT` | PgBouncer port (5000) |
| `DB_DATABASE` | App database name |
| `DB_USERNAME` | App database user |
| `DB_PASSWORD` | Generated password |
| `REDIS_HOST` | Redis master host |
| `REDIS_PASSWORD` | Redis password |
| `REDIS_PORT` | Redis port (6379) |
| `APP_URL` | First provisioned production domain |
| `ASSET_URL` | Same as APP_URL |

---

## Next.js

### Requirements
- Node.js 20+
- npm/yarn/pnpm

### Build Process

```bash
# 1. Install dependencies (package manager auto-detected)
npm install  # or yarn install, pnpm install

# 2. Build for production
npm run build  # or detected build script
```

### Output Directory
- `.next/` for standard Next.js
- `.output/` for Nuxt

### Runtime
- **systemd** service: `{app_name}.service`
- ExecStart: `npm start`
- Port: 3000 (configurable via PORT env var)
- User/Group: `webapps:webapps`

---

## Python

### Requirements
- Python 3.11+
- pip
- virtualenv

### Build Process

```bash
# 1. Create virtual environment
python3 -m venv /opt/apps/{app_name}/venv

# 2. Install dependencies
source /opt/apps/{app_name}/venv/bin/activate
pip install -r requirements.txt
pip install gunicorn  # Production WSGI server

# 3. Collect static (Django)
python manage.py collectstatic --noinput

# 4. Run migrations (if applicable)
python manage.py migrate
```

### Runtime
- **systemd** service: `{app_name}.service`
- ExecStart: `/opt/apps/{app_name}/venv/bin/gunicorn --bind 0.0.0.0:8000 app:app`
- User/Group: `webapps:webapps`

---

## Vue / Vite / Svelte / Nuxt

### Requirements
- Node.js 20+
- npm/yarn/pnpm

### Build Process

```bash
# 1. Install dependencies (package manager auto-detected)
npm install  # or yarn install, pnpm install

# 2. Build for production (build script auto-detected)
npm run build
```

### Output Directories

| Framework | Output Directory |
|-----------|------------------|
| Vite | `dist/` |
| Vue CLI | `dist/` |
| SvelteKit | `.svelte-kit/` |
| Nuxt | `.output/` |
| Gatsby | `public/` |
| Angular | `dist/` |

---

## Go

### Requirements
- Go 1.21+

### Build Process

```bash
# 1. Download dependencies
go mod download

# 2. Build binary
go build -o bin/{app_name} .

# 3. Optimize (optional)
go build -ldflags="-s -w" -o bin/{app_name} .
```

### Runtime
- **systemd** service: `{app_name}.service`
- ExecStart: `/opt/apps/{app_name}/bin/{app_name}`
- User/Group: `webapps:webapps`

---

## Deployment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      Deploy Triggered                            │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   1. Clone Repository                            │
│   - Git clone to /opt/apps/{app_name}                           │
│   - Use GitHub token for private repos                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                2. Detect Framework & Tools                       │
│   - Scan for config files (vite.config.js, etc.)               │
│   - Parse package.json for scripts and dependencies            │
│   - Detect package manager (npm/yarn/pnpm)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                  3. Run Framework Setup                          │
│                                                                 │
│   Laravel:                                                      │
│   ├── composer install                                          │
│   ├── ensure Node.js 20 installed                               │
│   ├── npm install && npm run build                              │
│   ├── Configure .env (DB, Redis, APP_URL)                       │
│   └── php artisan storage:link                                  │
│                                                                 │
│   Next.js/Vue/Svelte/etc:                                       │
│   ├── ensure Node.js 20 installed                               │
│   ├── npm install (or yarn/pnpm)                                │
│   └── npm run build (detected script)                           │
│                                                                 │
│   Python:                                                       │
│   ├── Create venv                                               │
│   └── pip install -r requirements.txt                           │
│                                                                 │
│   Go:                                                           │
│   └── go build                                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                4. Configure Server Services                      │
│   Laravel: nginx + PHP-FPM                                      │
│   Others: systemd service                                       │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      5. Complete                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deployment Checklist

### Pre-Deployment
1. Verify all environment variables are set
2. Check database connectivity
3. Verify Redis connectivity (if used)
4. Ensure SSL certificates are valid

### Automatic Configuration (On Deploy)
The dashboard automatically configures:

**For Laravel apps:**
- Database credentials in `.env` (DB_HOST, DB_PORT, DB_DATABASE, DB_USERNAME, DB_PASSWORD)
- Redis credentials in `.env` (REDIS_HOST, REDIS_PASSWORD, REDIS_PORT) if Redis is enabled
- APP_URL and ASSET_URL set from first provisioned production domain
- Node.js 20 installation verified
- Frontend assets built (`npm install && npm run build` or detected script)
- Storage link created
- Config cache cleared

**For other frameworks:**
- Environment variables in systemd service
- DATABASE_URL and REDIS_URL if configured
- Build command auto-detected from package.json

### Post-Deployment
1. Check service status: `systemctl status {app_name}`
2. Check logs: `journalctl -u {app_name} -f`
3. Test health endpoint: `curl http://localhost:{port}/health`
4. Verify domain resolves correctly

### Rollback
1. `cd /opt/apps/{app_name}`
2. `git checkout {previous_commit}`
3. Re-run build process
4. `systemctl restart {app_name}`

---

## GitHub Actions Workflow

Each framework has an auto-generated workflow that:
1. Runs on push to `main` (and `develop` for staging)
2. Builds the application
3. Deploys to both app servers in parallel
4. Restarts the service

See the dashboard's "Create Application" wizard for the generated workflow.
