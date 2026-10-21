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
pause
