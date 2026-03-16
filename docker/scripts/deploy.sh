#!/bin/bash
set -e

# Infrastructure Dashboard Deployment Script
# Usage: ./deploy.sh [command]
#
# Commands:
#   start     - Start all services
#   stop      - Stop all services
#   restart   - Restart all services
#   rebuild   - Rebuild and restart all services
#   logs      - Show logs
#   status    - Show status
#   backup    - Backup volumes
#   restore   - Restore from backup

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/.env"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    if [ ! -f "$ENV_FILE" ]; then
        log_warn ".env file not found. Creating from example..."
        cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
        log_warn "Please edit $ENV_FILE with your credentials."
        exit 1
    fi
}

start() {
    log_info "Starting infrastructure dashboard..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
    log_info "Services started. Access dashboard at http://localhost:8080"
}

stop() {
    log_info "Stopping infrastructure dashboard..."
    docker compose -f "$COMPOSE_FILE" down
    log_info "Services stopped."
}

restart() {
    log_info "Restarting infrastructure dashboard..."
    stop
    start
}

rebuild() {
    log_info "Rebuilding infrastructure dashboard..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build --no-cache
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --force-recreate
    log_info "Services rebuilt and started."
}

logs() {
    docker compose -f "$COMPOSE_FILE" logs -f "$@"
}

status() {
    log_info "Service Status:"
    docker compose -f "$COMPOSE_FILE" ps
}

backup() {
    BACKUP_DIR="$SCRIPT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    log_info "Backing up to $BACKUP_DIR..."
    
    # Backup volumes
    for volume in dashboard-config dashboard-docs prometheus-data grafana-data alertmanager-data; do
        docker run --rm \
            -v "infrastructure-$volume:/data" \
            -v "$BACKUP_DIR:/backup" \
            alpine tar czf "/backup/$volume.tar.gz" -C /data .
    done
    
    # Backup .env
    cp "$ENV_FILE" "$BACKUP_DIR/.env"
    
    log_info "Backup complete: $BACKUP_DIR"
}

restore() {
    if [ -z "$1" ]; then
        log_error "Usage: $0 restore <backup_directory>"
        exit 1
    fi
    
    BACKUP_DIR="$1"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log_error "Backup directory not found: $BACKUP_DIR"
        exit 1
    fi
    
    log_info "Restoring from $BACKUP_DIR..."
    
    # Stop services
    stop
    
    # Restore volumes
    for volume in dashboard-config dashboard-docs prometheus-data grafana-data alertmanager-data; do
        if [ -f "$BACKUP_DIR/$volume.tar.gz" ]; then
            docker run --rm \
                -v "infrastructure-$volume:/data" \
                -v "$BACKUP_DIR:/backup" \
                alpine sh -c "rm -rf /data/* && tar xzf /backup/$volume.tar.gz -C /data"
        fi
    done
    
    # Restore .env
    if [ -f "$BACKUP_DIR/.env" ]; then
        cp "$BACKUP_DIR/.env" "$ENV_FILE"
    fi
    
    log_info "Restore complete. Starting services..."
    start
}

case "${1:-}" in
    start)
        check_prerequisites
        start
        ;;
    stop)
        stop
        ;;
    restart)
        check_prerequisites
        restart
        ;;
    rebuild)
        check_prerequisites
        rebuild
        ;;
    logs)
        logs "${@:2}"
        ;;
    status)
        status
        ;;
    backup)
        backup
        ;;
    restore)
        restore "${@:2}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|rebuild|logs|status|backup|restore}"
        echo ""
        echo "Commands:"
        echo "  start     - Start all services"
        echo "  stop      - Stop all services"
        echo "  restart   - Restart all services"
        echo "  rebuild   - Rebuild and restart all services"
        echo "  logs      - Show logs (optional: specify service name)"
        echo "  status    - Show status"
        echo "  backup    - Backup volumes to backups/"
        echo "  restore   - Restore from backup directory"
        exit 1
        ;;
esac