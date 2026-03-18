# Deployment Reference

## Contents
- Deploy Script Interface
- Environment Configuration
- Backup and Restore
- Production Workflows
- Anti-Patterns

## Deploy Script Interface

The `docker/scripts/deploy.sh` provides unified service management:

```bash
./deploy.sh start      # Start all services
./deploy.sh stop       # Stop all services
./deploy.sh restart    # Restart all services
./deploy.sh rebuild    # Rebuild and recreate
./deploy.sh logs       # Follow logs
./deploy.sh status     # Show running containers
./deploy.sh backup     # Backup all volumes
./deploy.sh restore <dir>  # Restore from backup
```

### Script Structure

All commands follow a pattern:

```bash
check_prerequisites() {
    # Verify docker and docker compose installed
    # Check .env exists, copy from example if not
}

start() {
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
}
```

## Environment Configuration

### Required vs Optional Variables

```bash
# Required - no default, must be set
PG_PASSWORD=${PG_PASSWORD}

# Optional - fallback default
PG_HOST=${PG_HOST:-100.102.220.16}
```

The script enforces prerequisites:

```bash
if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    echo "Please edit $ENV_FILE with your credentials."
    exit 1
fi
```

### Tailscale Requirements

Local development requires Tailscale connection for database access. The dashboard connects to external PostgreSQL and Redis clusters via Tailscale IPs.

## Backup and Restore

### Volume Backup

```bash
backup() {
    BACKUP_DIR="$SCRIPT_DIR/backups/$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    for volume in dashboard-config prometheus-data grafana-data; do
        docker run --rm \
            -v "infrastructure-$volume:/data" \
            -v "$BACKUP_DIR:/backup" \
            alpine tar czf "/backup/$volume.tar.gz" -C /data .
    done
}
```

**Why:** Alpine image is small (~5MB). Tar preserves permissions and symlinks.

### Restore Procedure

```bash
restore() {
    BACKUP_DIR="$1"
    
    # Stop services
    stop
    
    # Restore volumes
    for volume in dashboard-config prometheus-data grafana-data; do
        docker run --rm \
            -v "infrastructure-$volume:/data" \
            -v "$BACKUP_DIR:/backup" \
            alpine sh -c "rm -rf /data/* && tar xzf /backup/$volume.tar.gz -C /data"
    done
    
    start
}
```

## Production Workflows

### Resource Constraints

Production services define resource limits:

```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '0.5'
      memory: 512M
```

**Why:** Prevents noisy neighbor problems. Reservations guarantee minimum resources.

### Restart Policy

All services use `unless-stopped`:

```yaml
restart: unless-stopped
```

**Why:** Restarts on failure but respects intentional stops. Preferred over `always` for maintenance windows.

## Anti-Patterns

### WARNING: Running Without Resource Limits

**The Problem:**

```yaml
# BAD - No resource constraints
services:
  api:
    image: api:latest
```

**Why This Breaks:**
1. Container can consume all host resources
2. Causes OOM kills of other services
3. No predictable performance characteristics

**The Fix:**

```yaml
deploy:
  resources:
    limits:
      cpus: '4'
      memory: 4G
    reservations:
      cpus: '1'
      memory: 1G
```

### WARNING: Using `docker-compose up` Without `-d`

**The Problem:**

```bash
# BAD - Ties up terminal, dies on disconnect
docker-compose up
```

**Why This Breaks:**
1. SSH sessions dropping kill the deployment
2. CI/CD runners hang indefinitely
3. No proper service management

**The Fix:**

```bash
docker-compose up -d
docker-compose logs -f  # Optional: follow logs
```

### WARNING: Manual Container Management

**The Problem:**

```bash
# BAD - Bypasses compose orchestration
docker stop container_name
docker rm container_name
docker run ...
```

**Why This Breaks:**
1. Breaks compose networking and volumes
2. Environment variables not loaded
3. Health checks ignored

**The Fix:**
Always use `docker-compose` commands for compose-managed services.