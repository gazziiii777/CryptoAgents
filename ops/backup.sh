#!/bin/bash
# Периодический логический бэкап торговой и research БД (mariadb-dump → gzip) с ротацией.
# Запускается сервисом `backup` из docker-compose. Дампы пишутся в /backups (хост: ./backups).
set -euo pipefail

OUT=/backups
INTERVAL="${DB_BACKUP_INTERVAL_S:-86400}"
RETENTION_DAYS="${DB_BACKUP_RETENTION_DAYS:-7}"
export MYSQL_PWD="$DB_PASSWORD"

mkdir -p "$OUT"
echo "backup: started (interval=${INTERVAL}s retention=${RETENTION_DAYS}d)"

while true; do
  ts="$(date -u +%Y%m%dT%H%M%SZ)"
  for db in "$DB_NAME" "$DB_RESEARCH_NAME"; do
    dest="$OUT/${db}_${ts}.sql.gz"
    if mariadb-dump -h "$DB_HOST" -P "${DB_PORT:-3306}" -u "$DB_USER" \
         --single-transaction --quick --no-tablespaces "$db" | gzip >"$dest"; then
      echo "backup: wrote ${dest} ($(wc -c <"$dest") bytes)"
    else
      echo "backup: FAILED for ${db}" >&2
      rm -f "$dest"
    fi
  done
  find "$OUT" -maxdepth 1 -name '*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete || true
  sleep "$INTERVAL"
done
