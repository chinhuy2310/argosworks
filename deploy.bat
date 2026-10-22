@echo off
REM ==============================================================================
REM ARGOS WORKS - Automated 1-Click Windows Deployment Script
REM ==============================================================================

echo ==========================================================
echo  ARGOS WORKS - Windows Deployment Script
echo ==========================================================

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not installed or not in PATH.
    echo Please install Docker Desktop for Windows or run directly using python server\main.py
    pause
    exit /b 1
)

if not exist "data" mkdir "data"
if not exist "data\backups" mkdir "data\backups"
if not exist "data\attachments" mkdir "data\attachments"
if not exist "data\templates" mkdir "data\templates"

REM ------------------------------------------------------------------------------
REM First-run bootstrap (.env secrets, server\config.json as a file, data dirs).
REM Without this, Docker mounts a directory over the missing config.json and the
REM app can no longer persist settings, and Compose aborts on missing secrets.
REM ------------------------------------------------------------------------------
set BOOTSTRAP_OK=0
where python >nul 2>nul
if not errorlevel 1 python "%~dp0scripts\init_deploy.py"
if not errorlevel 1 set BOOTSTRAP_OK=1
if "%BOOTSTRAP_OK%"=="1" goto bootstrap_done

echo [INFO] Python not available - using PowerShell bootstrap...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\init_deploy.ps1"
if errorlevel 1 goto bootstrap_failed

:bootstrap_done

echo [INFO] Starting ARGOS WORKS with Docker Compose...
docker compose up -d --build
if %ERRORLEVEL% NEQ 0 (
    docker-compose up -d --build
)

echo.
echo ==========================================================
echo  [SUCCESS] ARGOS WORKS is running with HTTPS!
echo  HTTPS URL: https://localhost (Port 443 - SSL/TLS Secured)
echo  HTTP  URL: http://localhost  (Port 80  - Auto redirects to HTTPS)
echo  Logs     : docker compose logs -f
echo ==========================================================
exit /b 0

:bootstrap_failed
echo.
echo [ERROR] Deployment bootstrap failed. Review the messages above and re-run deploy.bat
pause
exit /b 1

