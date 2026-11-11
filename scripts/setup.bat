@echo off
REM ===============================================================
REM XFox Harvester - one-command setup (Windows)
REM ===============================================================
cd /d "%~dp0.."

where python >nul 2>nul || (echo Python 3.11+ is required & exit /b 1)

if not exist ".venv" (
  python -m venv .venv
  echo [ok] Virtual environment created
)
call .venv\Scripts\activate.bat

python -m pip install --upgrade pip -q
pip install -e . -q
echo [ok] Python dependencies installed (incl. x-crawlfox)

echo Downloading the Camoufox browser payload (~200 MB, one time)...
camoufox fetch
echo [ok] Camoufox browser ready

if not exist ".env" (
  python -c "import secrets; print('XFOX_SECRET_KEY=' + secrets.token_urlsafe(48))" > .secret.tmp
  set /p SECRET_LINE=<.secret.tmp
  del .secret.tmp
  (for /f "delims=" %%L in (.env.example) do (
    echo %%L | findstr /b "XFOX_SECRET_KEY=" >nul && (echo %SECRET_LINE%) || (echo %%L)
  )) > .env
  echo [ok] .env created with a generated secret
) else (
  echo [skip] .env already exists
)

where node >nul 2>nul && (
  pushd web
  call npm install --no-audit --no-fund
  call npm run build
  popd
  echo [ok] Web console built
) || (echo [warn] Node.js not found - the web console was not rebuilt)

echo Applying database migrations (requires a reachable PostgreSQL)...
alembic upgrade head && (echo [ok] Database ready) || (echo [warn] Migration skipped - check XFOX_DATABASE_URL)

echo.
echo Setup complete. Start the server with:  scripts\run.bat
