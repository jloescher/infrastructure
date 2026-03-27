FROM python:3.11-slim

LABEL maintainer="Quantyra"
LABEL description="Quantyra PaaS - Portable infrastructure management"

# Set environment variables with auto-detection defaults
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PAAS_DATABASE_PATH=/data/paas.db
ENV PAAS_KEY_PATH=/data/vault.key

# Install system dependencies (including openssh-client for SSH access)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    curl \
    openssh-client \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY dashboard/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY dashboard/ .

# Create data directory
RUN mkdir -p /data

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the application (no env vars required on Tailscale network)
CMD ["python", "app.py"]