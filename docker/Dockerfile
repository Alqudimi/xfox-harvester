# syntax=docker/dockerfile:1
# =====================================================================
# XFox Harvester — production image
#   stage 1 (web):    build the React console
#   stage 2 (server): Python + X-CrawlFox + Camoufox browser + built UI
# =====================================================================

# ---------------- stage 1: web console ----------------
FROM node:20-slim AS web
WORKDIR /build
COPY web/package.json web/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------- stage 2: application ----------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System libraries required by the Camoufox (Firefox) runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        libgtk-3-0 \
        libdbus-glib-1-2 \
        libxt6 \
        libx11-xcb1 \
        libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the Python package first (layer caching friendly).
COPY pyproject.toml README.md alembic.ini ./
COPY xfox ./xfox
COPY migrations ./migrations
RUN pip install --no-deps . && pip install .

# Browser payload (~200 MB) — downloaded once at build time.
RUN camoufox fetch

# Built console from stage 1.
COPY --from=web /build/dist ./web/dist

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/app/data"]
EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "xfox.main:app", "--host", "0.0.0.0", "--port", "8000"]
