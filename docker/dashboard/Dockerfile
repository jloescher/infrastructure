FROM python:3.11-slim

LABEL maintainer="Quantyra Infrastructure"
LABEL description="Infrastructure Management Dashboard"

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV BASE_DIR=/app
ENV SSH_KEY_PATH=/root/.ssh/id_vps

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    openssh-client \
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

# Create directories
RUN mkdir -p /data /app/config /app/docs

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Environment defaults
ENV PG_HOST=100.102.220.16
ENV PG_PORT=5000
ENV PG_USER=patroni_superuser
ENV REDIS_HOST=100.126.103.51
ENV REDIS_PORT=6379
ENV PAAS_DATABASE_PATH=/data/paas.db
ENV PAAS_KEY_PATH=/data/vault.key

# Run
CMD ["python", "app.py"]