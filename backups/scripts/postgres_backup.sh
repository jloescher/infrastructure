#!/bin/bash
set -euo pipefail

BACKUP_DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_TYPE="${1:-full}"
RETENTION_DAYS=30
PG_BACKUP_DIR="/backup/pgbackrest"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="postgresql"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error_exit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
    exit 1
}

check_pgbackrest() {
    if ! command -v pgbackrest &> /dev/null; then
        error_exit "pgBackRest not installed"
    fi
}

create_backup_dirs() {
    mkdir -p "$PG_BACKUP_DIR"
    mkdir -p "$(dirname "$PG_BACKUP_DIR")/logs"
}

perform_backup() {
    log "Starting PostgreSQL $BACKUP_TYPE backup..."
    
    case "$BACKUP_TYPE" in
        full)
            pgbackrest --type=full --stanza=main backup
            ;;
        differential|diff)
            pgbackrest --type=diff --stanza=main backup
            ;;
        incremental|incr)
            pgbackrest --type=incr --stanza=main backup
            ;;
        *)
            error_exit "Invalid backup type: $BACKUP_TYPE. Use: full, diff, or incr"
            ;;
    esac
    
    log "PostgreSQL backup completed successfully"
}

verify_backup() {
    log "Verifying backup integrity..."
    pgbackrest --stanza=main verify
    
    if [ $? -eq 0 ]; then
        log "Backup verification passed"
    else
        error_exit "Backup verification failed"
    fi
}

rotate_local_backups() {
    log "Rotating local backups older than $RETENTION_DAYS days..."
    
    find "$PG_BACKUP_DIR" -type f -name "*.backup" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$PG_BACKUP_DIR" -type f -name "*.manifest" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    
    log "Local backup rotation completed"
}

sync_to_s3() {
    if [ -z "$S3_BUCKET" ]; then
        log "S3 bucket not configured, skipping S3 sync"
        return 0
    fi
    
    log "Syncing backups to S3 ($S3_BUCKET/$S3_PREFIX)..."
    
    if command -v aws &> /dev/null; then
        aws s3 sync "$PG_BACKUP_DIR" "s3://$S3_BUCKET/$S3_PREFIX/" \
            --storage-class STANDARD_IA \
            --delete \
            --exclude "*.tmp"
        log "S3 sync completed"
    elif command -v rclone &> /dev/null; then
        rclone sync "$PG_BACKUP_DIR" "s3:$S3_BUCKET/$S3_PREFIX" \
            --storage-class STANDARD_IA \
            --exclude "*.tmp"
        log "Rclone S3 sync completed"
    else
        log "WARNING: Neither aws-cli nor rclone found, skipping S3 sync"
    fi
}

send_notification() {
    local status=$1
    local message=$2
    
    if [ -n "${SLACK_WEBHOOK:-}" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"PostgreSQL Backup ($BACKUP_TYPE): $status - $message\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}

main() {
    log "=== PostgreSQL Backup Started ==="
    log "Backup Type: $BACKUP_TYPE"
    log "Host: $(hostname)"
    
    check_pgbackrest
    create_backup_dirs
    
    if perform_backup && verify_backup; then
        rotate_local_backups
        sync_to_s3
        send_notification "SUCCESS" "Backup completed on $(hostname)"
        log "=== PostgreSQL Backup Completed Successfully ==="
        exit 0
    else
        send_notification "FAILED" "Backup failed on $(hostname)"
        error_exit "Backup process failed"
    fi
}

main "$@"