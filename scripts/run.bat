@echo off
cd /d "%~dp0.."
if not exist ".venv" (
  echo Virtual environment missing - run scripts\setup.bat first.
  exit /b 1
)
call .venv\Scripts\activate.bat
uvicorn xfox.main:app --host 0.0.0.0 --port 8000
