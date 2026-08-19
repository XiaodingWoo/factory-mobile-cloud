@echo off
setlocal
cd /d "%~dp0"
if not exist ".env" (
  echo ERROR: .env was not found.
  echo Copy .env.example to .env and enter the Supabase settings first.
  pause
  exit /b 1
)
set "PYTHON_EXE=python"
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
"%PYTHON_EXE%" --version >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python was not found.
  echo Install Python 3.11+ or add python.exe to PATH, then run this file again.
  pause
  exit /b 1
)

set "WATCH_INTERVAL_SECONDS=5"
set "FULL_SYNC_INTERVAL_SECONDS=300"
echo Supabase live sync watcher started.
echo Lightweight change check: every %WATCH_INTERVAL_SECONDS% seconds
echo Fallback full sync: every %FULL_SYNC_INTERVAL_SECONDS% seconds
echo Keep this window open.
echo.
"%PYTHON_EXE%" sync_supabase_requests.py --watch --watch-interval %WATCH_INTERVAL_SECONDS% --full-sync-interval %FULL_SYNC_INTERVAL_SECONDS%
if errorlevel 1 (
  echo.
  echo ERROR: Live sync watcher stopped unexpectedly.
  pause
)
