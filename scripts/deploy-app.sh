#!/bin/bash
set -e

APP_NAME="$1"
BRANCH="${2:-main}"
APP_DIR="/opt/apps/$APP_NAME"

if [ -z "$APP_NAME" ]; then
    echo "Usage: $0 <app_name> [branch]"
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo "Error: App directory $APP_DIR not found"
    exit 1
fi

cd "$APP_DIR"

echo "=== Deploying $APP_NAME (branch: $BRANCH) ==="
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting deployment"

# Fetch and checkout
echo "Fetching latest code..."
git fetch origin
git checkout $BRANCH
git pull origin $BRANCH

# Get current commit for rollback
BEFORE_COMMIT=$(git rev-parse HEAD)
echo "Commit: $BEFORE_COMMIT"

# Detect framework
if [ -f "composer.json" ]; then
    echo "Running composer install..."
    composer install --no-dev --optimize-autoloader 2>&1
    
    if [ -f "package.json" ]; then
        echo "Building frontend assets..."
        npm ci --quiet 2>/dev/null || npm install --quiet
        npm run build 2>/dev/null || echo "No build script"
    fi
    
    echo "Running Laravel optimizations..."
    php artisan config:cache 2>/dev/null || true
    php artisan route:cache 2>/dev/null || true
    php artisan view:cache 2>/dev/null || true
    php artisan migrate --force 2>/dev/null || true
    
    echo "Reloading PHP-FPM..."
    sudo systemctl reload php8.5-fpm
    
elif [ -f "package.json" ]; then
    echo "Installing Node dependencies..."
    npm ci --quiet 2>/dev/null || npm install --quiet
    npm run build 2>/dev/null || echo "No build script"
    
    echo "Restarting service..."
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
    
elif [ -f "requirements.txt" ]; then
    echo "Installing Python dependencies..."
    if [ -d "venv" ]; then
        venv/bin/pip install -r requirements.txt
    fi
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
    
elif [ -f "go.mod" ]; then
    echo "Building Go application..."
    go build -o bin/$APP_NAME .
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - Deployment complete"
echo "=== Done ==="