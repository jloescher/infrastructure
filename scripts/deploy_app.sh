#!/bin/bash
set -euo pipefail

APP_NAME="${1:-}"
ENVIRONMENT="${2:-production}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/apps}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error_exit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
    exit 1
}

usage() {
    echo "Usage: $0 <app_name> [environment]"
    echo ""
    echo "Examples:"
    echo "  $0 web-app production"
    echo "  $0 api staging"
    exit 1
}

check_prerequisites() {
    if [ -z "$APP_NAME" ]; then
        usage
    fi
    
    if ! command -v docker &> /dev/null; then
        error_exit "Docker not installed"
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error_exit "Docker Compose not installed"
    fi
}

pull_latest_image() {
    log "Pulling latest image for $APP_NAME..."
    
    cd "$DEPLOY_DIR/$APP_NAME"
    docker-compose pull "$APP_NAME"
}

backup_current_deployment() {
    log "Backing up current deployment..."
    
    local backup_dir="/backup/apps/${APP_NAME}_${TIMESTAMP}"
    mkdir -p "$backup_dir"
    
    if [ -d "$DEPLOY_DIR/$APP_NAME" ]; then
        cp -r "$DEPLOY_DIR/$APP_NAME"/* "$backup_dir/" 2>/dev/null || true
        log "Backup created at $backup_dir"
    fi
}

stop_services() {
    log "Stopping $APP_NAME services..."
    
    cd "$DEPLOY_DIR/$APP_NAME"
    docker-compose stop
}

start_services() {
    log "Starting $APP_NAME services..."
    
    cd "$DEPLOY_DIR/$APP_NAME"
    docker-compose up -d --remove-orphans
}

health_check() {
    log "Performing health check..."
    
    local max_retries=30
    local retry_interval=10
    local health_url="${HEALTH_URL:-http://localhost:3000/health}"
    
    for i in $(seq 1 $max_retries); do
        if curl -sf "$health_url" > /dev/null 2>&1; then
            log "Health check passed!"
            return 0
        fi
        
        log "Health check attempt $i/$max_retries failed, retrying in ${retry_interval}s..."
        sleep $retry_interval
    done
    
    error_exit "Health check failed after $max_retries attempts"
}

rollback() {
    log "Rolling back to previous deployment..."
    
    local backup_dir="/backup/apps/${APP_NAME}_previous"
    
    if [ -d "$backup_dir" ]; then
        stop_services
        cp -r "$backup_dir/"* "$DEPLOY_DIR/$APP_NAME/"
        start_services
        log "Rollback completed"
    else
        error_exit "No backup found for rollback"
    fi
}

cleanup_old_backups() {
    log "Cleaning up old backups..."
    
    find /backup/apps -type d -name "${APP_NAME}_*" -mtime +30 -exec rm -rf {} + 2>/dev/null || true
}

send_notification() {
    local status=$1
    local message=$2
    
    if [ -n "${SLACK_WEBHOOK:-}" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"Deployment: $status - $message\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}

main() {
    log "=== Deployment Started for $APP_NAME ==="
    log "Environment: $ENVIRONMENT"
    log "Host: $(hostname)"
    
    check_prerequisites
    
    trap 'send_notification "FAILED" "Deployment failed for $APP_NAME on $(hostname)"; error_exit "Deployment failed"' ERR
    
    backup_current_deployment
    pull_latest_image
    stop_services
    start_services
    health_check
    cleanup_old_backups
    
    send_notification "SUCCESS" "Deployed $APP_NAME to $ENVIRONMENT on $(hostname)"
    log "=== Deployment Completed Successfully ==="
}

main "$@"