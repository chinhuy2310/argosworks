# ==============================================================================
# ARGOS WORKS - Production Container Image
# Multi-platform Linux container (amd64 / arm64)
# ==============================================================================
FROM python:3.12-slim

# Set environment defaults
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=8080 \
    HOST=0.0.0.0 \
    TZ=Asia/Seoul

WORKDIR /app

# Install runtime utilities (curl for container healthcheck, tzdata for timezone)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY server/ ./server/
COPY web/ ./web/

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

# Pre-create data and backup directories and set permissions
RUN mkdir -p /app/data /app/data/backups /app/data/attachments /app/data/templates && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Declare volume for persistent data
VOLUME ["/app/data"]

EXPOSE 8080

# Built-in Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start ARGOS WORKS server
CMD ["python", "server/main.py"]
