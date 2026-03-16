# Deployment Fixes

## Issues Fixed

### 1. Environment Variables Not Configured
**Problem**: Laravel apps were using `.env.example` defaults instead of actual database and Redis credentials.

**Solution**: Updated `run_framework_setup()` to:
- Accept `db_config` and `redis_config` parameters
- Automatically inject credentials into `.env` file using `sed` commands
- Configure DB_HOST, DB_PORT, DB_DATABASE, DB_USERNAME, DB_PASSWORD
- Configure REDIS_HOST, REDIS_PASSWORD, REDIS_PORT

### 2. Frontend Assets Not Built
**Problem**: Vite manifest missing because npm build wasn't run or failed silently.

**Solution**:
- Added `ensure_nodejs_20()` function to verify/install Node.js 20
- Changed from `npm ci` to `npm install` with clean install
- Better error reporting for build failures
- Build failures now stop deployment with clear error message

### 3. Redis Config Not Stored
**Problem**: Redis configuration wasn't saved to applications.yml.

**Solution**: Added `redis_enabled` field to application config when Redis is selected.

### 4. Redeploys Reset Environment
**Problem**: Redeploying would reset `.env` file, losing credentials.

**Solution**: Both `create_app` and `deploy_app` routes now pass database and Redis configs to `run_framework_setup()`.

## Files Modified

### `/dashboard/app.py`
- Added `ensure_nodejs_20()` function
- Updated `run_framework_setup()` signature to accept `db_config` and `redis_config`
- Added `.env` configuration injection for Laravel
- Updated `create_app()` to pass configs to setup
- Updated `deploy_app()` to pass configs to setup
- Added `redis_enabled` to application config

### `/docs/framework_builds.md`
- Updated Laravel build process
- Added automatic configuration documentation
- Added Node.js 20 installation step

## Deployment Flow

```
1. Clone repository
   ↓
2. run_framework_setup()
   ├── Laravel:
   │   ├── composer install
   │   ├── ensure_nodejs_20()
   │   ├── npm install && npm run build
   │   ├── cp .env.example .env
   │   ├── php artisan key:generate
   │   └── Inject DB + Redis credentials
   ├── Next.js/Svelte:
   │   ├── npm ci
   │   └── npm run build
   ├── Python:
   │   ├── Create venv
   │   └── pip install -r requirements.txt
   └── Go:
       └── go build
   ↓
3. Configure server (nginx/PHP-FPM or systemd)
   ↓
4. Push GitHub secrets
   ↓
5. Save application config
```

## Testing

To test the deployment flow:

1. Create a new Laravel app with database and Redis
2. Deploy to app servers
3. Verify `.env` contains correct credentials:
   ```bash
   ssh root@100.92.26.38 "grep -E 'DB_|REDIS_' /opt/apps/{app_name}/.env"
   ```
4. Verify frontend assets built:
   ```bash
   ssh root@100.92.26.38 "ls -la /opt/apps/{app_name}/public/build/"
   ```
5. Verify app responds with 200:
   ```bash
   curl -s -o /dev/null -w '%{http_code}' http://100.92.26.38:{port}
   ```