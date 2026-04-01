#!/bin/bash
# Backup pgAdmin and Ivory Docker volumes
# Run daily via cron

set -e

BACKUP_DIR="/backup/db-ui"
DATE=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=7

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "=== DB-UI Backup Started: $(date) ==="

# Backup pgAdmin
echo "Backing up pgAdmin..."
docker run --rm \
    -v db-ui_pgadmin-data:/data \
    -v "$BACKUP_DIR:/backup" \
    alpine:latest \
    tar czf "/backup/pgadmin-$DATE.tar.gz" -C /data .

echo "pgAdmin backup: $BACKUP_DIR/pgadmin-$DATE.tar.gz"

# Backup Ivory
echo "Backing up Ivory..."
docker run --rm \
    -v db-ui_ivory-data:/data \
    -v "$BACKUP_DIR:/backup" \
    alpine:latest \
    tar czf "/backup/ivory-$DATE.tar.gz" -C /data .

echo "Ivory backup: $BACKUP_DIR/ivory-$DATE.tar.gz"

# Cleanup old backups
echo "Cleaning up backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.tar.gz" -type f -mtime +$RETENTION_DAYS -delete

# Show backup summary
echo ""
echo "=== Backup Summary ==="
ls -lh "$BACKUP_DIR"/*.tar.gz 2>/dev/null | tail -10

echo ""
echo "=== DB-UI Backup Completed: $(date) ==="