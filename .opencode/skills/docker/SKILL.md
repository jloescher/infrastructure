---
name: docker
description: Manages Docker Compose configurations and container deployments for the Quantyra infrastructure stack. Handles local dashboard development, monitoring services (Prometheus, Grafana, Alertmanager), and application server deployments. Use when modifying docker-compose files, building container images, managing service lifecycles, debugging container issues, or adding new services to the infrastructure stack.
---

# Docker Skill

This project uses Docker Compose to run the Flask dashboard and monitoring stack locally. Services connect to external infrastructure (PostgreSQL Patroni cluster, Redis) via Tailscale IPs, not containers. The setup emphasizes host-network bridging for external service access and persistent named volumes for data retention.

## Quick Start

### Start the Local Stack

```bash
cd docker
cp .env.example .env
# Edit .env with credentials
./scripts/deploy.sh start
```

### Rebuild After Dashboard Changes

```bash
./scripts/deploy.sh rebuild
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Named volumes | Explicit naming for persistence | `infrastructure-prometheus-data` |
| External network | Monitoring on `monitoring-network` | `external: name: monitoring-network` |
| Tailscale hosts | extra_hosts for DB/Cache access | `router-01:100.102.220.16` |
| Health checks | All services define probes | `test: ["CMD", "curl", "-f", ...]` |
| Resource limits | Production workloads only | `limits: cpus: '2', memory: 2G` |

## Common Patterns

### Adding a New Monitoring Service

**When:** Extending the observability stack

```yaml
services:
  loki:
    image: grafana/loki:2.9.0
    container_name: infrastructure-loki
    ports:
      - "3100:3100"
    volumes:
      - ../configs/loki/loki.yml:/etc/loki/local-config.yaml:ro
      - loki-data:/loki
    networks:
      - infrastructure
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "wget", "-q", "--spider", "http://localhost:3100/ready"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  loki-data:
    name: infrastructure-loki-data
```

### Dashboard Environment with Defaults

**When:** Services need fallback values for local dev

```yaml
environment:
  - PG_HOST=${PG_HOST:-100.102.220.16}
  - PG_PORT=${PG_PORT:-5000}
  - PG_PASSWORD=${PG_PASSWORD}  # Required, no default
```

## See Also

- [docker](references/docker.md) - Dockerfile and compose patterns
- [ci-cd](references/ci-cd.md) - GitHub Actions container builds
- [deployment](references/deployment.md) - Production deployment workflows
- [monitoring](references/monitoring.md) - Prometheus/Grafana stack configuration

## Related Skills

- **python** - Flask dashboard application code
- **flask** - Dashboard web framework patterns
- **postgresql** - Database connection configuration
- **redis** - Cache layer integration
- **prometheus** - Metrics collection setup
- **grafana** - Dashboard visualization
- **haproxy** - Load balancer for container egress