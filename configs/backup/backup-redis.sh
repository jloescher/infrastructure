#!/bin/bash
# Redis Backup Script
# Backs up RDB snapshot to R2 with 30-day retention

set -e

# Configuration
BACKUP_DIR="/var/lib/redis/backups"
DATE=$(date +%Y%m%d_%H%M%S)
R2_BUCKET="quantyra-backup"
R2_PATH="redis"
RETENTION_DAYS=30
REDIS_HOST="100.126.103.51"
REDIS_PORT="6379"
REDIS_PASSWORD="CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk"
RDB_FILE="/var/lib/redis/dump.rdb"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Cleanup old local backups
cleanup_local() {
    find "$BACKUP_DIR" -name "*.rdb.gz" -mtime +3 -delete 2>/dev/null || true
}

# Main backup function
backup() {
    log "Starting Redis backup..."
    
    # Trigger Redis BGSAVE to ensure we have a recent snapshot
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning BGSAVE 2>/dev/null || true
    
    # Wait for BGSAVE to complete (up to 60 seconds)
    log "Waiting for BGSAVE to complete..."
    for i in {1..60}; do
        if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" --no-auth-warning LASTSAVE 2>/dev/null | grep -q "$(date +%s | cut -c1-8)"; then
            log "BGSAVE completed"
            break
        fi
        sleep 1
    done
    
    # Copy and compress RDB file
    BACKUP_FILE="${BACKUP_DIR}/redis_${DATE}.rdb.gz"
    
    if [ -f "$RDB_FILE" ]; then
        cp "$RDB_FILE" "/tmp/redis_backup.rdb"
        gzip -c "/tmp/redis_backup.rdb" > "$BACKUP_FILE"
        rm "/tmp/redis_backup.rdb"
        
        log "Local backup created: $BACKUP_FILE"
        
        # Upload to R2
        if rclone copy "$BACKUP_FILE" "r2:${R2_BUCKET}/${R2_PATH}/" --config /etc/rclone/rclone.conf; then
            log "Uploaded to R2: ${R2_PATH}/redis_${DATE}.rdb.gz"
        else
            log "ERROR: Failed to upload Redis backup to R2"
            return 1
        fi
    else
        log "ERROR: RDB file not found at $RDB_FILE"
        return 1
    fi
    
    log "Redis backup completed successfully"
}

# Cleanup old R2 backups
cleanup_r2() {
    log "Cleaning up R2 backups older than ${RETENTION_DAYS} days..."
    
    rclone ls "r2:${R2_BUCKET}/${R2_PATH}/" --config /etc/rclone/rclone.conf 2>/dev/null | \
    while read SIZE FILE; do
        FILE_DATE=$(echo "$FILE" | grep -oE '[0-9]{8}_[0-9]{6}' | head -1)
        if [ -n "$FILE_DATE" ]; then
            FILE_TS=$(date -d "${FILE_DATE:0:8} ${FILE_DATE:9:2}:${FILE_DATE:11:2}:${FILE_DATE:13:2}" +%s 2>/dev/null || echo "0")
            CUTOFF_TS=$(date -d "-${RETENTION_DAYS} days" +%s)
            if [ "$FILE_TS" -lt "$CUTOFF_TS" ] && [ "$FILE_TS" -gt "0" ]; then
                log "Deleting old backup: $FILE"
                rclone deletefile "r2:${R2_BUCKET}/${R2_PATH}/${FILE}" --config /etc/rclone/rclone.conf 2>/dev/null || true
            fi
        fi
    done
}

# Main execution
main() {
    if backup; then
        cleanup_local
        cleanup_r2
        exit 0
    else
        log "Redis backup failed"
        exit 1
    fi
}

main "$@"