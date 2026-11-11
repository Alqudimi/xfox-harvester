#!/usr/bin/env bash
# ===============================================================
# XFox Harvester — one-command setup (Linux / macOS)
#   1. creates a virtual environment and installs the package
#   2. downloads the Camoufox browser payload
#   3. prepares .env with a generated secret
#   4. builds the web console (when Node.js is available)
#   5. applies database migrations (when the database is reachable)
# ===============================================================
set -euo pipefail
cd "$(dirname "$0")/.."

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; RESET="\033[0m"
step() { echo -e "${GREEN}✔${RESET} $1"; }
warn() { echo -e "${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "${RED}✘${RESET} $1"; exit 1; }

# --- Python ---
command -v python3 >/dev/null || fail "Python 3.11+ is required (https://python.org)"
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
step "Python ${PY_VERSION} found"

# --- Virtual environment ---
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  step "Virtual environment created"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# --- Install ---
pip install --upgrade pip -q
pip install -e . -q
step "Python dependencies installed (incl. x-crawlfox)"

# --- Camoufox browser ---
echo "Downloading the Camoufox browser payload (~200 MB, one time)…"
camoufox fetch
step "Camoufox browser ready"

# --- .env ---
if [ ! -f ".env" ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  sed "s|^XFOX_SECRET_KEY=.*|XFOX_SECRET_KEY=${SECRET}|" .env.example > .env
  step ".env created with a generated secret — edit the database URL as needed"
else
  warn ".env already exists — leaving it untouched"
fi

# --- Web console ---
if command -v node >/dev/null && command -v npm >/dev/null; then
  (cd web && npm install --no-audit --no-fund && npm run build)
  step "Web console built into web/dist"
else
  warn "Node.js not found — the web console was not rebuilt (the prebuilt copy is used)"
fi

# --- Database ---
echo "Applying database migrations (requires a reachable PostgreSQL)…"
if alembic upgrade head; then
  step "Database schema is up to date"
else
  warn "Migration skipped — start PostgreSQL, set XFOX_DATABASE_URL in .env, then run: alembic upgrade head"
fi

echo ""
echo -e "${GREEN}Setup complete.${RESET} Start the server with:  ./scripts/run.sh"
