# Docker Reference

## Contents
- Dockerfile Patterns
- Compose File Structure
- Volume Management
- Networking
- Anti-Patterns

## Dockerfile Patterns

### Multi-Stage Builds (Dashboard)

The dashboard uses a single-stage build—sufficient for Flask apps without compiled assets:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

CMD ["python", "app.py"]
```

### Health Check Implementation

All services must define health checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 10s
```

**Why:** `start_period` prevents false failures during slow startup (database connections, asset compilation).

## Compose File Structure

### Service Naming Convention

Prefix all container and volume names with `infrastructure-` to avoid collisions:

```yaml
container_name: infrastructure-dashboard
volumes:
  dashboard-data:
    name: infrastructure-dashboard-data
```

### Context Paths

The dashboard builds from the parent directory:

```yaml
dashboard:
  build:
    context: ../dashboard          # Source code location
    dockerfile: ../docker/dashboard/Dockerfile
```

## Volume Management

### Backup and Restore

The deploy script handles volume backups via temporary alpine containers:

```bash
# Backup
docker run --rm \
    -v "infrastructure-prometheus-data:/data" \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/prometheus.tar.gz" -C /data .

# Restore
docker run --rm \
    -v "infrastructure-prometheus-data:/data" \
    -v "$BACKUP_DIR:/backup" \
    alpine sh -c "rm -rf /data/* && tar xzf /backup/prometheus.tar.gz -C /data"
```

### Read-Only Mounts

Configuration files should be mounted read-only:

```yaml
volumes:
  - ../configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

## Networking

### Bridge Network with External Access

The stack uses a bridge network for inter-container communication, with external services reached via Tailscale:

```yaml
networks:
  infrastructure:
    driver: bridge
    name: infrastructure-network
```

### External Network for Monitoring

App servers connect to a pre-created external network:

```yaml
networks:
  default:
    external:
      name: monitoring-network
```

Create it first: `docker network create monitoring-network`

### Tailscale Host Mapping

Containers access external infrastructure via `extra_hosts`:

```yaml
extra_hosts:
  - "router-01:100.102.220.16"
  - "re-db:100.92.26.38"
```

## Anti-Patterns

### WARNING: Using `latest` Tag in Production

**The Problem:**

```yaml
# BAD - Non-reproducible deployments
image: prom/prometheus:latest
```

**Why This Breaks:**
1. Pulls different images over time, causing "works on my machine" bugs
2. Impossible to rollback to known-good versions
3. Security patches may introduce breaking changes

**The Fix:**

```yaml
# GOOD - Pin to specific version
image: prom/prometheus:v2.48.0
```

### WARNING: Storing Secrets in Compose Files

**The Problem:**

```yaml
# BAD - Committed secrets
environment:
  - PG_PASSWORD=actual_password_here
```

**Why This Breaks:**
1. Secrets visible in `docker inspect` output
2. Committed to version control
3. No rotation mechanism

**The Fix:**

```yaml
# GOOD - Use .env file
environment:
  - PG_PASSWORD=${PG_PASSWORD}
```

`.env` is gitignored; distribute via secure channel.

### WARNING: `depends_on` Without Health Checks

**The Problem:**

```yaml
# BAD - Grafana starts before Prometheus is ready
depends_on:
  - prometheus
```

**Why This Breaks:**
1. `depends_on` only waits for container start, not service readiness
2. Apps crash on connection refused, then restart loop
3. Wasted resources during startup

**The Fix:**
Combine `depends_on` with proper retry logic in applications, or use a startup waiter script. Docker Compose does not natively support "depends on healthy."

### WARNING: Unbounded Logs

**The Problem:**

```yaml
# BAD - Default json-file driver grows forever
logging:
  driver: "json-file"
```

**Why This Breaks:**
1. Disk fills up, causing container/runtime failures
2. Difficult to recover without manual intervention

**The Fix:**

```yaml
# GOOD - Rotate logs
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"