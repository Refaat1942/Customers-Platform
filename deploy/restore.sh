#!/usr/bin/env bash
# Restore a backup:  deploy/restore.sh backups/customers_2026-11-09_0230.sql.gz
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "usage: $0 backups/<file>.sql.gz"; exit 1; }
read -r -p "This REPLACES the current database with $1. Type YES to continue: " ok
[ "$ok" = "YES" ] || exit 1
docker compose stop app
docker compose exec -T db psql -U customers -d postgres -c "DROP DATABASE IF EXISTS customers;" -c "CREATE DATABASE customers;"
gunzip -c "$1" | docker compose exec -T db psql -U customers -d customers
docker compose start app
echo "Restored."
