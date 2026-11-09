#!/usr/bin/env bash
# Daily database backup, keeps the last 14 days.
# Add to cron (crontab -e):   30 2 * * *  /opt/customers-platform/deploy/backup.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p backups
file="backups/customers_$(date +%F_%H%M).sql.gz"
docker compose exec -T db pg_dump -U customers -d customers | gzip > "$file"
find backups -name 'customers_*.sql.gz' -mtime +14 -delete
echo "Backup written: $file"
