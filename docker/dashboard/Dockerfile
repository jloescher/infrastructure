FROM python:3.12-slim

LABEL maintainer="Quantyra Infrastructure"
LABEL description="Infrastructure Management Dashboard"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Create config and docs directories
RUN mkdir -p /opt/dashboard/config /opt/dashboard/docs

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Environment variables (defaults, override with .env)
ENV PG_HOST=100.102.220.16
ENV PG_PORT=5000
ENV PG_USER=patroni_superuser
ENV REDIS_HOST=100.126.103.51
ENV REDIS_PORT=6379
ENV PROMETHEUS_URL=http://prometheus:9090
ENV GRAFANA_URL=http://grafana:3000

# Run
CMD ["python", "app.py"]