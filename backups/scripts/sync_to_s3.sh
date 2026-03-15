#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:-/backup}"
S3_BUCKET="${S3_BUCKET:-}"
S3_PREFIX="${S3_PREFIX:-infrastructure}"
SYNC_MODE="${SYNC_MODE:-sync}"
STORAGE_CLASS="${STORAGE_CLASS:-STANDARD_IA}"
DRY_RUN="${DRY_RUN:-false}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error_exit() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" >&2
    exit 1
}

validate_config() {
    if [ -z "$S3_BUCKET" ]; then
        error_exit "S3_BUCKET environment variable not set"
    fi
    
    if [ ! -d "$BACKUP_DIR" ]; then
        error_exit "Backup directory does not exist: $BACKUP_DIR"
    fi
}

check_tools() {
    if command -v aws &> /dev/null; then
        TOOL="aws"
        log "Using AWS CLI"
    elif command -v rclone &> /dev/null; then
        TOOL="rclone"
        log "Using rclone"
    else
        error_exit "Neither aws-cli nor rclone found. Please install one of them."
    fi
}

sync_with_aws_cli() {
    local dry_run_flag=""
    [ "$DRY_RUN" = "true" ] && dry_run_flag="--dryrun"
    
    local s3_uri="s3://$S3_BUCKET/$S3_PREFIX/"
    
    case "$SYNC_MODE" in
        sync)
            log "Syncing $BACKUP_DIR to $s3_uri"
            aws s3 sync "$BACKUP_DIR" "$s3_uri" \
                --storage-class "$STORAGE_CLASS" \
                --delete \
                --exclude "*.tmp" \
                --exclude "*.lock" \
                $dry_run_flag
            ;;
        upload)
            log "Uploading $BACKUP_DIR to $s3_uri"
            aws s3 cp "$BACKUP_DIR" "$s3_uri" \
                --recursive \
                --storage-class "$STORAGE_CLASS" \
                --exclude "*.tmp" \
                --exclude "*.lock" \
                $dry_run_flag
            ;;
        download)
            log "Downloading from $s3_uri to $BACKUP_DIR"
            aws s3 cp "$s3_uri" "$BACKUP_DIR" \
                --recursive \
                $dry_run_flag
            ;;
        *)
            error_exit "Invalid SYNC_MODE: $SYNC_MODE. Use: sync, upload, or download"
            ;;
    esac
}

sync_with_rclone() {
    local dry_run_flag=""
    [ "$DRY_RUN" = "true" ] && dry_run_flag="--dry-run"
    
    local s3_remote="s3:$S3_BUCKET/$S3_PREFIX"
    
    case "$SYNC_MODE" in
        sync)
            log "Syncing $BACKUP_DIR to $s3_remote"
            rclone sync "$BACKUP_DIR" "$s3_remote" \
                --storage-class "$STORAGE_CLASS" \
                --exclude "*.tmp" \
                --exclude "*.lock" \
                $dry_run_flag \
                -v
            ;;
        copy|upload)
            log "Copying $BACKUP_DIR to $s3_remote"
            rclone copy "$BACKUP_DIR" "$s3_remote" \
                --storage-class "$STORAGE_CLASS" \
                --exclude "*.tmp" \
                --exclude "*.lock" \
                $dry_run_flag \
                -v
            ;;
        download)
            log "Downloading from $s3_remote to $BACKUP_DIR"
            rclone copy "$s3_remote" "$BACKUP_DIR" \
                $dry_run_flag \
                -v
            ;;
        *)
            error_exit "Invalid SYNC_MODE: $SYNC_MODE. Use: sync, copy, or download"
            ;;
    esac
}

list_s3_backups() {
    log "Listing backups in S3..."
    
    if [ "$TOOL" = "aws" ]; then
        aws s3 ls "s3://$S3_BUCKET/$S3_PREFIX/" --recursive --human-readable
    else
        rclone ls "s3:$S3_BUCKET/$S3_PREFIX"
    fi
}

calculate_cost_estimate() {
    log "Calculating backup size..."
    
    local total_size=$(du -sh "$BACKUP_DIR" | cut -f1)
    log "Total backup size: $total_size"
    
    case "$STORAGE_CLASS" in
        STANDARD_IA)
            log "Storage class: STANDARD_IA (Infrequent Access)"
            log "Estimated cost: ~\$0.0125/GB/month"
            ;;
        GLACIER)
            log "Storage class: GLACIER"
            log "Estimated cost: ~\$0.004/GB/month"
            ;;
        DEEP_ARCHIVE)
            log "Storage class: DEEP_ARCHIVE"
            log "Estimated cost: ~\$0.00099/GB/month"
            ;;
        *)
            log "Storage class: $STORAGE_CLASS"
            ;;
    esac
}

send_notification() {
    local status=$1
    local message=$2
    
    if [ -n "${SLACK_WEBHOOK:-}" ]; then
        curl -s -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"S3 Backup Sync: $status - $message\"}" \
            "$SLACK_WEBHOOK" > /dev/null 2>&1 || true
    fi
}

main() {
    log "=== S3 Backup Sync Started ==="
    log "Backup Directory: $BACKUP_DIR"
    log "S3 Bucket: $S3_BUCKET"
    log "S3 Prefix: $S3_PREFIX"
    log "Sync Mode: $SYNC_MODE"
    log "Dry Run: $DRY_RUN"
    
    validate_config
    check_tools
    calculate_cost_estimate
    
    if [ "$TOOL" = "aws" ]; then
        if sync_with_aws_cli; then
            send_notification "SUCCESS" "Sync completed for $BACKUP_DIR"
            log "=== S3 Backup Sync Completed Successfully ==="
        else
            send_notification "FAILED" "Sync failed for $BACKUP_DIR"
            error_exit "S3 sync failed"
        fi
    else
        if sync_with_rclone; then
            send_notification "SUCCESS" "Sync completed for $BACKUP_DIR"
            log "=== S3 Backup Sync Completed Successfully ==="
        else
            send_notification "FAILED" "Sync failed for $BACKUP_DIR"
            error_exit "S3 sync failed"
        fi
    fi
    
    if [ "${LIST_AFTER_SYNC:-false}" = "true" ]; then
        list_s3_backups
    fi
}

main "$@"