# Monitoring Reference

## Contents
- Prometheus Configuration
- Grafana Setup
- Alertmanager Integration
- Node Exporter
- Health Check Patterns

## Prometheus Configuration

### Volume Mounts

```yaml
prometheus:
  image: prom/prometheus:v2.48.0
  volumes:
    - ../configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    - ../configs/prometheus/alerts.yml:/etc/prometheus/rules/alerts.yml:ro
    - prometheus-data:/prometheus
  command:
    - "--config.file=/etc/prometheus/prometheus.yml"
    - "--storage.tsdb.path=/prometheus"
    - "--web.enable-lifecycle"      # Enable reload via API
    - "--web.enable-admin-api"
```

**Why:** `--web.enable-lifecycle` allows configuration reload without restart: `curl -X POST http://prometheus:9090/-/reload`.

### Retention Configuration

```yaml
command:
  - '--storage.tsdb.retention.time=30d'
  - '--storage.tsdb.retention.size=10GB'
```

## Grafana Setup

### Provisioning Mounts

```yaml
grafana:
  image: grafana/grafana:10.2.2
  volumes:
    - ../configs/grafana/provisioning:/etc/grafana/provisioning:ro
    - grafana-data:/var/lib/grafana
  environment:
    - GF_SECURITY_ADMIN_USER=${GRAFANA_USER:-admin}
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD:-admin}
    - GF_USERS_ALLOW_SIGN_UP=false
```

**Why:** Provisioning directory mounts dashboards and datasources as code. Disabling signup enforces SSO or admin-only access.

### Plugin Installation

```yaml
environment:
  - GF_INSTALL_PLUGINS=redis-datasource
```

**Why:** Installs plugins at container startup. Data persists in `grafana-data` volume.

## Alertmanager Integration

### Configuration Mount

```yaml
alertmanager:
  image: prom/alertmanager:v0.26.0
  volumes:
    - ../configs/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    - alertmanager-data:/alertmanager
  command:
    - "--config.file=/etc/alertmanager/alertmanager.yml"
    - "--storage.path=/alertmanager"
    - "--web.external-url=https://alertmanager.quantyra.com"
```

## Node Exporter

### Host System Access

```yaml
node-exporter:
  image: prom/node-exporter:v1.7.0
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
    - /:/rootfs:ro
  command:
    - '--path.procfs=/host/proc'
    - '--path.sysfs=/host/sys'
    - '--path.rootfs=/rootfs'
    - '--collector.filesystem.ignored-mount-points=^/(sys|proc|dev|host|etc)($$|/)'
```

**Why:** Read-only access to host `/proc` and `/sys` for metrics. Ignores pseudo-filesystems to reduce noise.

## Health Check Patterns

### wget vs curl

Alpine-based images use `wget`:

```yaml
healthcheck:
  test: ["CMD", "wget", "-q", "--spider", "http://localhost:9090/-/healthy"]
```

Slim/python images use `curl`:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/"]
```

### Timing Parameters

```yaml
healthcheck:
  interval: 30s    # Check frequency
  timeout: 10s     # Command timeout
  retries: 3       # Failures before unhealthy
  start_period: 40s  # Grace period for slow starts
```

## Anti-Patterns

### WARNING: Exposing Monitoring Without Auth

**The Problem:**

```yaml
# BAD - Open access
ports:
  - "9090:9090"
```

**Why This Breaks:**
1. Prometheus admin API enables data deletion
2. Grafana may have sensitive dashboards
3. Alertmanager reveals infrastructure topology

**The Fix:**
Bind to localhost only, use reverse proxy with auth:

```yaml
ports:
  - "127.0.0.1:9090:9090"
```

Or use Tailscale for internal access: `http://100.102.220.16:9090`

### WARNING: Missing Data Persistence

**The Problem:**

```yaml
# BAD - Data lost on container recreation
prometheus:
  volumes:
    - ../configs/prometheus.yml:/etc/prometheus/prometheus.yml:ro
```

**Why This Breaks:**
1. Metrics lost on restart/upgrade
2. Alert state reset
3. Grafana dashboards lost

**The Fix:**
Always mount a named volume for data directories:

```yaml
volumes:
  - prometheus-data:/prometheus