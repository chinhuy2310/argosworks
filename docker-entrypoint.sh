#!/bin/sh
set -e

# Pre-create data directories if not present
mkdir -p /app/data /app/data/backups /app/data/attachments /app/data/templates /app/logs

# Fix bind-mount ownership if running as root
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appgroup /app/data /app/logs 2>/dev/null || true
    chmod -R 775 /app/data /app/logs 2>/dev/null || true
    exec gosu appuser "$@"
else
    exec "$@"
fi
