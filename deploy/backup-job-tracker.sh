#!/usr/bin/env bash
# Nightly Postgres backup for job_tracker.
#
# Dumps ONLY the database (not the whole droplet — that's DigitalOcean's droplet
# backups) to a dated file, keeping the last 7 days. Uses pg_dump's custom format
# (-Fc): compressed and restorable selectively with pg_restore.
#
# Runs as root via /etc/cron.d/job-tracker-backup; pg_dump runs as the postgres
# system user (peer auth), so no DB password lives in this script.
#
# Restore example:  sudo -u postgres pg_restore -d job_tracker --clean <file>
#
# TODO (off-box backup, step 3): these dumps currently live ON the droplet, so
# they die with it. Copy them off nightly — to the Raspberry Pi (rsync/scp) or
# DO Spaces — so a backup survives losing the droplet. NOT done yet.

set -euo pipefail

BACKUP_DIR=/var/backups/job-tracker
mkdir -p "$BACKUP_DIR"

STAMP=$(date +%F) # YYYY-MM-DD
FILE="$BACKUP_DIR/job_tracker_${STAMP}.dump"

sudo -u postgres pg_dump -Fc job_tracker > "$FILE"

# Keep only the last 7 daily dumps.
find "$BACKUP_DIR" -name 'job_tracker_*.dump' -mtime +7 -delete

echo "$(date -Is) backup ok: $FILE ($(du -h "$FILE" | cut -f1))"
