#!/bin/bash
# PostgreSQL Backup Script
# Backs up all databases to R2 with 30-day retention

set -e

# Configuration
BACKUP_DIR="/var/lib/postgresql/backups"
DATE=$(date +%Y%m%d_%H%M%S)
R2_BUCKET="quantyra-backup"
R2_PATH="postgresql"
RETENTION_DAYS=30

# PostgreSQL connection (via localhost)
export PGHOST="127.0.0.1"
export PGPORT="5432"
export PGUSER="patroni_superuser"
export PGPASSWORD="2e7vBpaaVK4vTJzrKebC"
export PGDATABASE="postgres"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Cleanup old local backups
cleanup_local() {
    find "$BACKUP_DIR" -name "*.sql.gz" -mtime +3 -delete 2>/dev/null || true
}

# Main backup function
backup() {
    log "Starting PostgreSQL backup..."
    
    # Get list of databases
    DATABASES=$(psql -At -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname != 'postgres';")
    
    # Backup each database
    for DB in $DATABASES; do
        log "Backing up database: $DB"
        BACKUP_FILE="${BACKUP_DIR}/${DB}_${DATE}.sql.gz"
        
        if pg_dump "$DB" | gzip > "$BACKUP_FILE"; then
            log "Local backup created: $BACKUP_FILE"
            
            # Upload to R2
            if rclone copy "$BACKUP_FILE" "r2:${R2_BUCKET}/${R2_PATH}/${DB}/" --config /etc/rclone/rclone.conf; then
                log "Uploaded to R2: ${R2_PATH}/${DB}/${DB}_${DATE}.sql.gz"
            else
                log "ERROR: Failed to upload $DB to R2"
                return 1
            fi
        else
            log "ERROR: Failed to backup $DB"
            return 1
        fi
    done
    
    # Backup globals (users, roles, etc.)
    GLOBALS_FILE="${BACKUP_DIR}/globals_${DATE}.sql.gz"
    if pg_dumpall --globals-only | gzip > "$GLOBALS_FILE"; then
        log "Globals backup created: $GLOBALS_FILE"
        rclone copy "$GLOBALS_FILE" "r2:${R2_BUCKET}/${R2_PATH}/globals/" --config /etc/rclone/rclone.conf
    fi
    
    log "PostgreSQL backup completed successfully"
}

# Cleanup old R2 backups
cleanup_r2() {
    log "Cleaning up R2 backups older than ${RETENTION_DAYS} days..."
    
    # Get all database directories
    for DB_DIR in $(rclone lsf "r2:${R2_BUCKET}/${R2_PATH}/" --config /etc/rclone/rclone.conf 2>/dev/null); do
        # List files older than retention
        rclone ls "r2:${R2_BUCKET}/${R2_PATH}/${DB_DIR}" --config /etc/rclone/rclone.conf 2>/dev/null | \
        while read SIZE FILE; do
            # Check file age (simplified - rclone doesn't have built-in date filtering)
            # We'll use rclone deletefile with --min-age but that's not straightforward
            # Instead, we'll purge old files based on date in filename
            FILE_DATE=$(echo "$FILE" | grep -oE '[0-9]{8}_[0-9]{6}' | head -1)
            if [ -n "$FILE_DATE" ]; then
                FILE_TS=$(date -d "${FILE_DATE:0:8} ${FILE_DATE:9:2}:${FILE_DATE:11:2}:${FILE_DATE:13:2}" +%s 2>/dev/null || echo "0")
                CUTOFF_TS=$(date -d "-${RETENTION_DAYS} days" +%s)
                if [ "$FILE_TS" -lt "$CUTOFF_TS" ] && [ "$FILE_TS" -gt "0" ]; then
                    log "Deleting old backup: $FILE"
                    rclone deletefile "r2:${R2_BUCKET}/${R2_PATH}/${DB_DIR}${FILE}" --config /etc/rclone/rclone.conf 2>/dev/null || true
                fi
            fi
        done
    done
}

# Send notification on failure
notify_failure() {
    local message="$1"
    # Could integrate with Slack webhook or email
    log "FAILURE: $message"
}

# Main execution
main() {
    if backup; then
        cleanup_local
        cleanup_r2
        exit 0
    else
        notify_failure "PostgreSQL backup failed"
        exit 1
    fi
}

main "$@"