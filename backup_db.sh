#!/bin/bash

# Database Backup Script for IT Helpdesk Project
# This script runs pg_dump using the DATABASE_URL environment variable,
# compresses the output, logs the results, and deletes dumps older than 30 days.

# Exit immediately if a command exits with a non-zero status
set -e

# Configuration
PROJECT_DIR="/var/www/helpdesk"
BACKUP_DIR="/var/backups/helpdesk"
LOG_FILE="/var/log/helpdesk/backup.log"
RETENTION_DAYS=30

# Create backup directory and log file if they don't exist
mkdir -p "$BACKUP_DIR"
touch "$LOG_FILE"

# Log start of backup
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting database backup..." >> "$LOG_FILE"

# Load environment variables from .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    # Filter out comments and export variables
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: .env file not found at $PROJECT_DIR/.env" >> "$LOG_FILE"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: DATABASE_URL is not set in .env" >> "$LOG_FILE"
    exit 1
fi

# Define backup filename
TIMESTAMP=$(date '+%Y-%m-%d_%H%M%S')
BACKUP_FILE="$BACKUP_DIR/helpdesk_db_$TIMESTAMP.dump"

# Run pg_dump using connection string (pg_dump handles postgres:// connections directly)
# -Fc uses PostgreSQL's custom archive format (compressed, flexible restore)
if pg_dump "$DATABASE_URL" -Fc -f "$BACKUP_FILE"; then
    # Secure backup file (read/write only by owner)
    chmod 600 "$BACKUP_FILE"
    
    # Calculate size
    FILE_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS: Backup created at $BACKUP_FILE (Size: $FILE_SIZE)" >> "$LOG_FILE"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: pg_dump failed" >> "$LOG_FILE"
    exit 1
fi

# Retention Policy: Delete backups older than $RETENTION_DAYS days
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Running retention policy..." >> "$LOG_FILE"
find "$BACKUP_DIR" -name "helpdesk_db_*.dump" -type f -mtime +$RETENTION_DAYS -print -delete >> "$LOG_FILE" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Backup process complete." >> "$LOG_FILE"
echo "--------------------------------------------------" >> "$LOG_FILE"
