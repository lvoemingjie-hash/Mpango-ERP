#!/bin/bash

# PostgreSQL Daily Backup Script for Mpango ERP
# Usage: ./backup_postgres.sh [backup_dir]

set -e

# Configuration
BACKUP_DIR="${1:-/opt/mpango/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/mpango_backup_${TIMESTAMP}.sql"
LOG_FILE="${BACKUP_DIR}/backup.log"

# Database connection (from environment; no versioned credential defaults)
DB_HOST="${DB_HOST:-postgres}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-mpango_erp}"
DB_USER="${DB_USER:-mpango}"
# DB_PASSWORD has no default: it must be supplied explicitly for every run.
DB_PASSWORD="${DB_PASSWORD:-}"

# Fail fast when the explicit credential is missing, empty, or blank:
# refuse BEFORE creating directories, writing logs, or invoking
# docker/pg_dump/copy/retention. The value itself is never printed.
if [ -z "$DB_PASSWORD" ] || [ -z "$(printf '%s' "$DB_PASSWORD" | tr -d '[:space:]')" ]; then
    echo "BACKUP_DB_PASSWORD_REQUIRED: DB_PASSWORD must be set to a non-blank PostgreSQL password (environment); refusing to start any backup step" >&2
    exit 2
fi

# Ensure backup directory exists
mkdir -p "$BACKUP_DIR"

# Log function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Starting PostgreSQL backup: $BACKUP_FILE"

# Create backup using pg_dump via docker exec.
# The explicit credential travels ONLY through the environment of this
# docker exec (name-only -e PGPASSWORD pass-through); it never appears in
# argv, command text, logs, or files. --no-password keeps pg_dump from
# prompting; it is not a credential supply mechanism.
PGPASSWORD="$DB_PASSWORD" docker exec \
    -e PGPASSWORD \
    mpango_postgres pg_dump \
    --host="$DB_HOST" \
    --port="$DB_PORT" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --no-password \
    --format=custom \
    --compress=9 \
    --file="/tmp/backup.dump" \
    "$DB_NAME"

# Copy backup from container to host
docker cp "mpango_postgres:/tmp/backup.dump" "$BACKUP_FILE"

# Clean up temporary file in container
docker exec mpango_postgres rm -f /tmp/backup.dump

# Verify backup file exists and has size > 0
if [ -s "$BACKUP_FILE" ]; then
    BACKUP_SIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat -c%s "$BACKUP_FILE" 2>/dev/null || echo "unknown")
    log "Backup completed successfully. Size: ${BACKUP_SIZE} bytes"

    # Keep only last 7 days of backups
    find "$BACKUP_DIR" -name "mpango_backup_*.sql" -type f -mtime +7 -delete
    log "Cleaned up old backups (keeping last 7 days)"
else
    log "ERROR: Backup file is empty or missing!"
    exit 1
fi

log "Backup process completed"
