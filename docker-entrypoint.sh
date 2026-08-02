#!/bin/sh
set -e

# Ensure /data and debug directories exist
mkdir -p /data /data/debug

# If running as root, fix volume permissions for /data and drop privileges to appuser (UID 1000)
if [ "$(id -u)" = "0" ]; then
    chown -R appuser:appuser /data /app 2>/dev/null || true
    exec setpriv --reuid=1000 --regid=1000 --clear-groups "$@"
else
    exec "$@"
fi
