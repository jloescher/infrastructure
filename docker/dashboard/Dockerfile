FROM python:3.11-slim

LABEL maintainer="Quantyra Infrastructure"
LABEL description="Infrastructure Management Dashboard"

WORKDIR /app

# Set environment variables with auto-detection defaults
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (includes openssh-client for SSH, iproute2 for auto-detection)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    openssh-client \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py database.py gist_sync.py .
COPY templates/ templates/
COPY static/ static/
COPY websocket/ websocket/
COPY tasks/ tasks/
COPY services/ services/
COPY actions/ actions/
COPY api/ api/
COPY docker-entrypoint.sh .

# Create directories
RUN mkdir -p /data /app/config /app/docs

# Make entrypoint executable
RUN chmod +x /app/docker-entrypoint.sh

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Environment defaults (all optional on Tailscale network)
# These are here for documentation; actual defaults are in app.py
ENV PG_HOST=100.102.220.16
ENV PG_PORT=5000
ENV PG_USER=patroni_superuser
ENV REDIS_HOST=100.126.103.51
ENV REDIS_PORT=6379
ENV PROMETHEUS_URL=http://100.102.220.16:9090
ENV GRAFANA_URL=http://100.102.220.16:3000
ENV PAAS_DATABASE_PATH=/data/paas.db
ENV PAAS_KEY_PATH=/data/vault.key

# Run with entrypoint (shows connection instructions on startup)
ENTRYPOINT ["/app/docker-entrypoint.sh"]