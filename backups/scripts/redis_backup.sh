#!/bin/bash
set -euo pipefail

BACKUP_DATE=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=30
REDIS_BACKUP_DIR="/backup/redis"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="redis"
REDIS_HOST="${REDIS_HOST:-$(tailscale ip --1 2>/dev/null || echo '127.0.0.1')}"
REDIS_PORT="${REDIS_PORT:-6379}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error_exit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
    exit 1
}

check_redis() {
    if ! command -v redis-cli &> /dev/null; then
        error_exit "redis-cli not installed"
    fi
    
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        error_exit "Cannot connect to Redis at $REDIS_HOST:$REDIS_PORT"
    fi
}

create_backup_dirs() {
    mkdir -p "$REDIS_BACKUP_DIR"
}

trigger_rdb_backup() {
    log "Triggering Redis RDB backup..."
    
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BGSAVE
    
    log "Waiting for RDB backup to complete..."
    local timeout=300
    local elapsed=0
    
    while [ $elapsed -lt $timeout ]; do
        local last_save=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE)
        sleep 1
        local current_save=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" LASTSAVE)
        
        if [ "$last_save" != "$current_save" ]; then
            log "RDB backup completed"
            return 0
        fi
        
        elapsed=$((elapsed + 1))
        if [ $((elapsed % 10)) -eq 0 ]; then
            log "Still waiting... ($elapsed seconds)"
        fi
    done
    
    error_exit "RDB backup timed out after $timeout seconds"
}

copy_rdb_file() {
    log "Copying RDB file to backup directory..."
    
    local rdb_file="/var/lib/redis/dump.rdb"
    
    if [ ! -f "$rdb_file" ]; then
        local rdb_file=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dir | tail -1)/dump.rdb
    fi
    
    if [ ! -f "$rdb_file" ]; then
        error_exit "Cannot find Redis RDB file"
    fi
    
    cp "$rdb_file" "$REDIS_BACKUP_DIR/redis_backup_${BACKUP_DATE}.rdb"
    gzip "$REDIS_BACKUP_DIR/redis_backup_${BACKUP_DATE}.rdb"
    
    log "RDB file copied and compressed"
}

create_aof_backup() {
    local aof_enabled=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET appendonly | tail -1)
    
    if [ "$aof_enabled" = "yes" ]; then
        log "AOF enabled, copying AOF file..."
        
        local aof_file=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET appendfilename | tail -1)
        local aof_dir=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET dir | tail -1)
        local aof_path="${aof_dir}/${aof_file}"
        
        if [ -f "$aof_path" ]; then
            cp "$aof_path" "$REDIS_BACKUP_DIR/redis_aof_${BACKUP_DATE}.aof"
            gzip "$REDIS_BACKUP_DIR/redis_aof_${BACKUP_DATE}.aof"
            log "AOF file copied and compressed"
        fi
    else
        log "AOF not enabled, skipping AOF backup"
    fi
}

create_info_snapshot() {
    log "Creating Redis info snapshot..."
    
    {
        echo "=== Redis Backup Info ==="
        echo "Date: $BACKUP_DATE"
        echo "Host: $(hostname)"
        echo "Redis Host: $REDIS_HOST"
        echo "Redis Port: $REDIS_PORT"
        echo ""
        echo "=== Redis INFO ==="
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" INFO
        echo ""
        echo "=== Redis CONFIG ==="
        redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" CONFIG GET "*"
    } > "$REDIS_BACKUP_DIR/redis_info_${BACKUP_DATE}.txt"
    
    log "Info snapshot created"
}

rotate_local_backups() {
    log "Rotating local backups older than $RETENTION_DAYS days..."
    
    find "$REDIS_BACKUP_DIR" -type f -name "*.rdb.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$REDIS_BACKUP_DIR" -type f -name "*.aof.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    find "$REDIS_BACKUP_DIR" -type f -name "*.txt" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true
    
    log "Local backup rotation completed"
}

sync_to_s3() {
    if [ -z "$S3_BUCKET" ]; then
        log "S3 bucket not configured, skipping S3 sync"
        return 0
    fi
    
    log "Syncing Redis backups to S3 ($S3_BUCKET/$S3_PREFIX)..."
    
    if command -v aws &> /dev/null; then
        aws s3 sync "$REDIS_BACKUP_DIR" "s3://$S3_BUCKET/$S3_PREFIX/" \
            --storage-class STANDARD_IA \
            --exclude "*.tmp"
        log "S3 sync completed"
    elif command -v rclone &> /dev/null; then
        rclone sync "$REDIS_BACKUP_DIR" "s3:$S3_BUCKET/$S3_PREFIX" \
            --storage-class STANDARD_IA
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
            --data "{\"text\":\"Redis Backup: $status - $message\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}

main() {
    log "=== Redis Backup Started ==="
    log "Redis Host: $REDIS_HOST:$REDIS_PORT"
    log "Host: $(hostname)"
    
    check_redis
    create_backup_dirs
    
    if trigger_rdb_backup && copy_rdb_file && create_aof_backup && create_info_snapshot; then
        rotate_local_backups
        sync_to_s3
        send_notification "SUCCESS" "Backup completed on $(hostname)"
        log "=== Redis Backup Completed Successfully ==="
        exit 0
    else
        send_notification "FAILED" "Backup failed on $(hostname)"
        error_exit "Backup process failed"
    fi
}

main "$@"