#!/usr/bin/env bash
# ==============================================================================
# ARGOS WORKS - Automated 1-Click Deployment Script
# ==============================================================================
set -e

echo "=========================================================="
echo " ARGOS WORKS - Deployment Script"
echo "=========================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker is not installed on this system."
    echo "Please install Docker and Docker Compose before running this script."
    exit 1
fi

# Ensure data directory exists on host
mkdir -p data/backups data/attachments data/templates

# Ensure config.json exists
if [ ! -f server/config.json ]; then
    echo "⚠️ Warning: server/config.json not found. Initializing with default config..."
    mkdir -p server
    echo '{"server":{"host":"0.0.0.0","port":8080}}' > server/config.json
fi

echo "🚀 Building and starting ARGOS WORKS container via Docker Compose..."
if docker compose version &> /dev/null; then
    docker compose up -d --build
else
    docker-compose up -d --build
fi

echo ""
echo "=========================================================="
echo " ✅ ARGOS WORKS is successfully deployed with HTTPS!"
echo " 🌐 HTTPS URL: https://${DOMAIN:-localhost} (Port 443 - SSL/TLS Secured)"
echo " 🌐 HTTP  URL: http://${DOMAIN:-localhost}  (Port 80  - Auto redirects to HTTPS)"
echo " To view logs: docker compose logs -f"
echo " To stop     : docker compose down"
echo "=========================================================="
