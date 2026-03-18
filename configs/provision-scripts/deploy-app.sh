#!/bin/bash
set -e

APP_NAME="$1"
BRANCH="${2:-main}"
APP_DIR="/opt/apps/$APP_NAME"
ENVIRONMENT="${3:-production}"
APP_RUNTIME_USER="${APP_RUNTIME_USER:-webapps}"

if [ -z "$APP_NAME" ]; then
    echo "Usage: $0 <app_name> [branch] [environment]"
    exit 1
fi

if [ ! -d "$APP_DIR" ]; then
    echo "Error: App directory $APP_DIR not found"
    exit 1
fi

run_as_app_user() {
    local cmd="$1"
    if [ "$(id -u)" -eq 0 ]; then
        sudo -u "$APP_RUNTIME_USER" -H bash -lc "$cmd"
    else
        bash -lc "$cmd"
    fi
}

ensure_runtime_user() {
    if [ "$(id -u)" -ne 0 ]; then
        return 0
    fi

    if ! id -u "$APP_RUNTIME_USER" >/dev/null 2>&1; then
        useradd --system --create-home --home-dir "/home/$APP_RUNTIME_USER" --shell /usr/sbin/nologin "$APP_RUNTIME_USER"
    fi
}

ensure_app_permissions() {
    if [ "$(id -u)" -ne 0 ]; then
        return 0
    fi

    chown -R "$APP_RUNTIME_USER:$APP_RUNTIME_USER" "$APP_DIR"

    if [ -d "$APP_DIR/storage" ] || [ -d "$APP_DIR/bootstrap/cache" ]; then
        mkdir -p "$APP_DIR/storage" "$APP_DIR/bootstrap/cache"
        chgrp -R www-data "$APP_DIR/storage" "$APP_DIR/bootstrap/cache"
        chmod -R ug+rwX "$APP_DIR/storage" "$APP_DIR/bootstrap/cache"
        find "$APP_DIR/storage" "$APP_DIR/bootstrap/cache" -type d -exec chmod 2775 {} \;
    fi

    if [ -f "$APP_DIR/.env" ]; then
        chgrp www-data "$APP_DIR/.env"
        chmod 640 "$APP_DIR/.env"
    fi
}

ensure_runtime_user
ensure_app_permissions

cd "$APP_DIR"

BACKUP_FILE=""
BEFORE_COMMIT=""
TARGET_COMMIT=""

echo "Current branch target: $BRANCH"

BEFORE_COMMIT=$(run_as_app_user "cd '$APP_DIR' && git rev-parse HEAD" 2>/dev/null || echo "unknown")
echo "Before commit: $BEFORE_COMMIT"

echo "Fetching latest code from origin/$BRANCH..."
run_as_app_user "cd '$APP_DIR' && git fetch origin '$BRANCH' --prune"
TARGET_COMMIT=$(run_as_app_user "cd '$APP_DIR' && git rev-parse 'origin/$BRANCH'" 2>/dev/null || echo "")

if [ -z "$TARGET_COMMIT" ]; then
    echo "Error: Unable to resolve origin/$BRANCH"
    exit 1
fi

echo "Target commit: $TARGET_COMMIT"
run_as_app_user "cd '$APP_DIR' && git checkout -B '$BRANCH' 'origin/$BRANCH'"
run_as_app_user "cd '$APP_DIR' && git reset --hard '$TARGET_COMMIT'"
ensure_app_permissions

backup_database() {
    DB_NAME=$(grep '^DB_DATABASE=' .env 2>/dev/null | cut -d'=' -f2)
    DB_USER=$(grep '^DB_USERNAME=' .env 2>/dev/null | cut -d'=' -f2)
    DB_PASS=$(grep '^DB_PASSWORD=' .env 2>/dev/null | cut -d'=' -f2)
    DB_HOST=$(grep '^DB_HOST=' .env 2>/dev/null | cut -d'=' -f2 || echo "100.102.220.16")
    DB_PORT=$(grep '^DB_PORT=' .env 2>/dev/null | cut -d'=' -f2 || echo "5000")
    
    if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ]; then
        echo "No database configured, skipping backup"
        return 0
    fi
    
    BACKUP_FILE="/tmp/${APP_NAME}_backup_$(date +%Y%m%d_%H%M%S).sql"
    echo "Creating database backup: $BACKUP_FILE"
    
    if PGPASSWORD="$DB_PASS" pg_dump -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -F p -f "$BACKUP_FILE" 2>&1; then
        echo "Database backup created successfully"
        return 0
    else
        echo "Warning: Database backup failed"
        return 1
    fi
}

rollback_deployment() {
    echo "=== ROLLING BACK ==="
    
    if [ -n "$BEFORE_COMMIT" ] && [ "$BEFORE_COMMIT" != "unknown" ]; then
        echo "Reverting code to commit: $BEFORE_COMMIT"
        run_as_app_user "cd '$APP_DIR' && git reset --hard '$BEFORE_COMMIT'"
    fi
    
    if [ -f "$BACKUP_FILE" ]; then
        echo "Restoring database from: $BACKUP_FILE"
        DB_NAME=$(grep '^DB_DATABASE=' .env 2>/dev/null | cut -d'=' -f2)
        DB_USER=$(grep '^DB_USERNAME=' .env 2>/dev/null | cut -d'=' -f2)
        DB_PASS=$(grep '^DB_PASSWORD=' .env 2>/dev/null | cut -d'=' -f2)
        DB_HOST=$(grep '^DB_HOST=' .env 2>/dev/null | cut -d'=' -f2 || echo "100.102.220.16")
        DB_PORT=$(grep '^DB_PORT=' .env 2>/dev/null | cut -d'=' -f2 || echo "5000")
        
        if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ]; then
            PGPASSWORD="$DB_PASS" psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -f $BACKUP_FILE 2>&1 || echo "Database restore failed"
            echo "Database restored"
        fi
    fi
    
    if [ -f "composer.json" ]; then
        run_as_app_user "cd '$APP_DIR' && composer install --no-dev --optimize-autoloader" 2>&1 || true
        run_as_app_user "cd '$APP_DIR' && php artisan config:cache" 2>/dev/null || true
        run_as_app_user "cd '$APP_DIR' && php artisan route:cache" 2>/dev/null || true
        run_as_app_user "cd '$APP_DIR' && php artisan view:cache" 2>/dev/null || true
        sudo systemctl reload php8.5-fpm
    fi

    ensure_app_permissions
    
    echo "Rollback complete"
}

check_pending_migrations() {
    if [ ! -f "artisan" ]; then
        return 0
    fi
    
    echo "Checking for pending migrations..."
    PENDING=$(run_as_app_user "cd '$APP_DIR' && php artisan migrate:status" 2>&1 | grep -c "not run" || echo "0")
    
    if [ "$PENDING" -gt 0 ]; then
        echo "Found $PENDING pending migration(s)"
        return 1
    else
        echo "No pending migrations"
        return 0
    fi
}

# Detect framework
if [ -f "composer.json" ]; then
    echo "Detected: Laravel/PHP"

    if [ ! -f ".env" ]; then
        echo "Error: Missing $APP_DIR/.env"
        echo "Generate .env from SOPS-managed dashboard secrets on router-01 before deploy."
        exit 1
    fi
    
    # Load custom commands from .env.deploy if exists
    if [ -f ".env.deploy" ]; then
        source .env.deploy
    fi
    
    INSTALL_CMD="${DEPLOY_INSTALL_CMD:-composer install --no-dev --optimize-autoloader}"
    BUILD_CMD="${DEPLOY_BUILD_CMD:-npm ci && npm run build}"
    MIGRATE_CMD="${DEPLOY_MIGRATE_CMD:-php artisan migrate --force}"
    
    echo "Running install: $INSTALL_CMD"
    run_as_app_user "cd '$APP_DIR' && $INSTALL_CMD" 2>&1
    
    if [ -f "package.json" ]; then
        echo "Building frontend assets..."
        echo "Running build: $BUILD_CMD"
        run_as_app_user "cd '$APP_DIR' && $BUILD_CMD" 2>/dev/null || run_as_app_user "cd '$APP_DIR' && npm run prod" 2>/dev/null || echo "No build script"
    fi
    
    echo "Running Laravel optimizations..."
    run_as_app_user "cd '$APP_DIR' && php artisan config:clear" 2>/dev/null || true
    run_as_app_user "cd '$APP_DIR' && php artisan cache:clear" 2>/dev/null || true
    run_as_app_user "cd '$APP_DIR' && php artisan route:clear" 2>/dev/null || true
    run_as_app_user "cd '$APP_DIR' && php artisan view:clear" 2>/dev/null || true
    
    # Pre-migration backup
    DB_NAME=$(grep '^DB_DATABASE=' .env 2>/dev/null | cut -d'=' -f2)
    if [ -n "$DB_NAME" ]; then
        backup_database
        
        # Check migration status
        if ! check_pending_migrations; then
            echo "Running migrations: $MIGRATE_CMD"
            if ! run_as_app_user "cd '$APP_DIR' && $MIGRATE_CMD" 2>&1; then
                echo "ERROR: Migration failed!"
                rollback_deployment
                exit 1
            fi
        fi
    fi
    
    echo "Caching config..."
    run_as_app_user "cd '$APP_DIR' && php artisan config:cache" 2>/dev/null || true
    run_as_app_user "cd '$APP_DIR' && php artisan route:cache" 2>/dev/null || true
    run_as_app_user "cd '$APP_DIR' && php artisan view:cache" 2>/dev/null || true
    ensure_app_permissions
    
    echo "Reloading PHP-FPM..."
    sudo systemctl reload php8.5-fpm
    
    echo "Testing application..."
    sleep 2
    PORT=$(grep -oP 'listen\s+\K\d+' /etc/nginx/sites-enabled/$APP_NAME 2>/dev/null | head -1 || echo "80")
    RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT 2>/dev/null || echo "000")
    if [ "$RESPONSE" = "200" ] || [ "$RESPONSE" = "302" ]; then
        echo "Health check passed (HTTP $RESPONSE)"
    else
        echo "Error: Health check returned HTTP $RESPONSE"
        echo "Check logs: journalctl -u php8.5-fpm -n 50"
        rollback_deployment
        exit 1
    fi
    
elif [ -f "package.json" ]; then
    echo "Detected: Node.js"
    
    INSTALL_CMD="${DEPLOY_INSTALL_CMD:-npm ci}"
    BUILD_CMD="${DEPLOY_BUILD_CMD:-npm run build}"
    START_CMD="${DEPLOY_START_CMD:-npm start}"
    
    echo "Running install: $INSTALL_CMD"
    run_as_app_user "cd '$APP_DIR' && $INSTALL_CMD" 2>/dev/null || run_as_app_user "cd '$APP_DIR' && npm install --quiet"
    
    echo "Running build: $BUILD_CMD"
    run_as_app_user "cd '$APP_DIR' && $BUILD_CMD" 2>/dev/null || echo "No build script"
    
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
    
    INSTALL_CMD="${DEPLOY_INSTALL_CMD:-pip install -r requirements.txt}"
    MIGRATE_CMD="${DEPLOY_MIGRATE_CMD:-}"
    
    echo "Running install: $INSTALL_CMD"
    if [ -d "venv" ]; then
        run_as_app_user "cd '$APP_DIR' && venv/bin/pip install -r requirements.txt -q"
    fi
    
    # Run migrations if Django/Flask-Migrate
    if [ -f "manage.py" ] && [ -n "$MIGRATE_CMD" ]; then
        echo "Running migrations: $MIGRATE_CMD"
        run_as_app_user "cd '$APP_DIR' && $MIGRATE_CMD" 2>&1 || echo "Migration skipped"
    fi
    
    echo "Restarting service..."
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
    
elif [ -f "go.mod" ]; then
    echo "Detected: Go"
    
    INSTALL_CMD="${DEPLOY_INSTALL_CMD:-go mod download}"
    BUILD_CMD="${DEPLOY_BUILD_CMD:-go build -o bin/$APP_NAME .}"
    
    echo "Running install: $INSTALL_CMD"
    run_as_app_user "cd '$APP_DIR' && $INSTALL_CMD"
    
    echo "Running build: $BUILD_CMD"
    run_as_app_user "cd '$APP_DIR' && $BUILD_CMD"
    
    echo "Restarting service..."
    sudo systemctl restart $APP_NAME 2>/dev/null || echo "No systemd service"
fi

# Cleanup old backups (keep last 5)
find /tmp/${APP_NAME}_backup_*.sql 2>/dev/null | sort -r | tail -n +6 | xargs rm -f 2>/dev/null || true

echo "$(date '+%Y-%m-%d %H:%M:%S') - Deployment complete"
echo "=== Done ==="
