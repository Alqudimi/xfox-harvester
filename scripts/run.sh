#!/usr/bin/env bash
# Start XFox Harvester (assumes scripts/setup.sh completed successfully).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d ".venv" ]; then
  echo "Virtual environment missing — run ./scripts/setup.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn xfox.main:app --host "${XFOX_HOST:-0.0.0.0}" --port "${XFOX_PORT:-8000}"
