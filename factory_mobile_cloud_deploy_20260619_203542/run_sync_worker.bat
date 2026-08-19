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

for /f "tokens=1,* delims==" %%A in ('findstr /b "SYNC_INTERVAL_SECONDS=" .env') do set "SYNC_INTERVAL_SECONDS=%%B"
if not defined SYNC_INTERVAL_SECONDS set "SYNC_INTERVAL_SECONDS=300"
echo Supabase request worker started.
echo Sync interval: %SYNC_INTERVAL_SECONDS% seconds
echo Keep this window open.
echo.
:loop
"%PYTHON_EXE%" sync_supabase_requests.py
echo.
echo Next sync in %SYNC_INTERVAL_SECONDS% seconds...
timeout /t %SYNC_INTERVAL_SECONDS% /nobreak >nul
goto loop
