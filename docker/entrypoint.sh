#!/bin/sh
# ---------------------------------------------------------------
# XFox Harvester container entrypoint
# Applies database migrations, then starts the API server.
# ---------------------------------------------------------------
set -e

echo "[entrypoint] applying database migrations…"
alembic upgrade head

echo "[entrypoint] starting XFox Harvester…"
exec "$@"
