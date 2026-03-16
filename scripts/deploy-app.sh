#!/bin/bash
set -e

APP_NAME="$1"
BRANCH="${2:-main}"
APP_DIR="/opt/apps/$APP_NAME"
ENVIRONMENT="${3:-production}"

if [ -z "$APP_NAME" ]; then
    echo "Usage: $0 <app_name> [branch] [environment]"
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo "Error: App directory $APP_DIR not found"
    exit 1
fi

cd "$APP_DIR"

echo "=== Deploying $APP_NAME (branch: $BRANCH, env: $ENVIRONMENT) ==="
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting deployment"

BEFORE_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
echo "Current commit: $BEFORE_COMMIT"

echo "Fetching latest code..."
git fetch origin
git checkout $BRANCH 2>/dev/null || git checkout -b $BRANCH origin/$BRANCH
git pull origin $BRANCH

AFTER_COMMIT=$(git rev-parse HEAD)
echo "New commit: $AFTER_COMMIT"

if [ "$BEFORE_COMMIT" = "$AFTER_COMMIT" ] && [ "$ENVIRONMENT" != "force" ]; then
    echo "No changes to deploy. Use 'force' as 3rd arg to force rebuild."
    exit 0
fi

# Detect framework
if [ -f "composer.json" ]; then
    echo "Detected: Laravel/PHP"
    
    echo "Running composer install..."
    composer install --no-dev --optimize-autoloader 2>&1
    
    if [ -f "package.json" ]; then
        echo "Building frontend assets..."
        npm ci --quiet 2>/dev/null || npm install --quiet
        npm run build 2>/dev/null || npm run prod 2>/dev/null || echo "No build script"
    fi
    
    echo "Running Laravel optimizations..."
    php artisan config:clear 2>/dev/null || true
    php artisan cache:clear 2>/dev/null || true
    php artisan route:clear 2>/dev/null || true
    php artisan view:clear 2>/dev/null || true
    
    echo "Running migrations..."
    php artisan migrate --force 2>&1 || echo "Migration skipped or failed"
    
    echo "Caching config..."
    php artisan config:cache 2>/dev/null || true
    php artisan route:cache 2>/dev/null || true
    php artisan view:cache 2>/dev/null || true
    
    echo "Reloading PHP-FPM..."
    sudo systemctl reload php8.5-fpm
    
    echo "Testing application..."
    sleep 2
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$(grep -oP 'listen\s*=\s*\K\d+' /etc/php/8.5/fpm/pool.d/$APP_NAME.conf 2>/dev/null || echo "80") 2>/dev/null || echo "000")
    if [ "$RESPONSE" = "200" ] || [ "$RESPONSE" = "302" ]; then
        echo "Health check passed (HTTP $RESPONSE)"
    else
        echo "Warning: Health check returned HTTP $RESPONSE"
    fi
    
elif [ -f "package.json" ]; then
    echo "Detected: Node.js"
    
    echo "Installing dependencies..."
    npm ci --quiet 2>/dev/null || npm install --quiet
    
    echo "Building application..."
    npm run build 2>/dev/null || echo "No build script"
    
    echo "Restarting service..."
    if sudo systemctl is-active $APP_NAME >/dev/null 2>&1; then
        sudo systemctl restart $APP_NAME
    else
        sudo systemctl start $APP_NAME
    fi
    
    echo "Waiting for service to start..."
    sleep 3
    
    if sudo systemctl is-active $APP_NAME >/dev/null 2>&1; then
        echo "Service started successfully"
    else
        echo "Error: Service failed to start"
        sudo journalctl -u $APP_NAME --no-pager -n 20
        exit 1
    fi
    
elif [ -f "requirements.txt" ]; then
    echo "Detected: Python"
    
    if [ -d "venv" ]; then
        echo "Installing dependencies..."
        venv/bin/pip install -r requirements.txt -q
    fi
    
    echo "Restarting service..."
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
    
elif [ -f "go.mod" ]; then
    echo "Detected: Go"
    
    echo "Building application..."
    go build -o bin/$APP_NAME .
    
    echo "Restarting service..."
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Deployment complete"
echo "=== Done ==="