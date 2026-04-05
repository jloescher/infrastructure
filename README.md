# Quantyra Infrastructure

Infrastructure-as-code repository for managing Quantyra VPS infrastructure with Dokploy deployment platform.

## Architecture

**UPDATED (2026-04-03)**: Architecture changed to Option B with Dokploy.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         CLOUDFLARE (Anycast Edge)                              │
│  • DNS: Round-robin between APP SERVER IPs                                     │
│  • WAF + DDoS Protection                                                       │
│  • SSL: Cloudflare Edge Certificate                                            │
└───────────────────────────┬─────────────────────────────────────────────────────┘
                            │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
    ┌────▼────┐         ┌────▼────┐
    │  re-db  │         │re-node-02│
    │Traefik  │◄───────►│ Traefik  │
    │ Dokploy │         │  Worker  │
    │ Manager │         │          │
    └────┬────┘         └────┬────┘
         │                   │
         │    App Traffic    │
         │   (HTTP/HTTPS)    │
         │                   │
    ┌────▼───────────────────▼────┐
    │   Docker Swarm Containers    │
    │   • Laravel apps             │
    │   • Node.js apps             │
    │   • 2+ replicas (HA)         │
    └──────────────┬───────────────┘
                   │
         ┌─────────┴─────────┐
         │   DB Traffic      │
         │  (HAProxy only)   │
         ▼                   ▼
    ┌────────┐          ┌────────┐
    │router-01│          │router-02│
    │ HAProxy │◄────────►│ HAProxy │
    │Prometheus│         │         │
    │ Grafana │          │         │
    └────┬────┘          └────┬────┘
         │                    │
         │    HAProxy PG      │
         │   Write: 5000      │
         │   Read: 5001       │
         │                    │
    ┌────▼───────────────────▼────┐
    │    Patroni PostgreSQL       │
    │  ┌────────┐  ┌────────┐  ┌────────┐
    │  │re-node-│  │re-node-│  │re-node-│
    │  │   01   │  │   03   │  │   04   │
    │  │Redis   │  │Redis   │  │        │
    │  │Master  │  │Replica │  │        │
    │  └────────┘  └────────┘  └────────┘
    └─────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
                      Tailscale VPN                │
└──────────────────────────────────────────────────┘
```

**Key Changes (2026-04-03)**:
- **App Traffic**: Routes directly via Cloudflare → Traefik (bypasses HAProxy)
- **Database Traffic**: HAProxy handles PostgreSQL and Redis only
- **Deployment**: Dokploy with Docker Swarm (2 nodes)
- **SSL**: Automatic Let's Encrypt via Traefik with DNS-01 challenge

## Server Inventory

| Server | Tailscale IP | Public IP | Role | Specs |
|--------|--------------|-----------|------|-------|
| re-db | 100.92.26.38 | 208.87.128.115 | Dokploy Manager, App Server | 12 vCPU, 48GB RAM |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | Dokploy Worker, App Server | 12 vCPU, 48GB RAM |
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy (DB), Monitoring | 2 vCPU, 8GB RAM |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy (DB) | 2 vCPU, 8GB RAM |
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master | 8 vCPU, 32GB RAM |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica | 8 vCPU, 32GB RAM |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd | 8 vCPU, 32GB RAM |

## Directory Structure

```
infrastructure/
├── ansible/                    # Ansible configuration
│   ├── inventory/              # Host inventory and variables
│   ├── playbooks/              # Ansible playbooks
│   └── roles/                  # Ansible roles
├── backups/                    # Backup scripts and configs
│   ├── scripts/                # Backup scripts
│   └── configs/                # Backup configurations
├── configs/                    # Service configurations (synced from servers)
│   ├── dokploy/                # Dokploy configurations
│   ├── docker/                 # Docker daemon configs
│   ├── haproxy/                # HAProxy configs
│   ├── patroni/                # Patroni configs
│   ├── postgresql/             # PostgreSQL configs
│   ├── redis/                  # Redis configs
│   ├── prometheus/             # Prometheus rules and alerts
│   └── grafana/                # Grafana dashboards
├── scripts/                    # Utility scripts
│   └── sync-configs.sh         # Config synchronization
├── docs/                       # Documentation
│   ├── plan.md                 # Current tasks and priorities
│   ├── architecture.md         # Infrastructure architecture
│   ├── dokploy-operations.md   # Dokploy operational guide
│   ├── deployment.md           # Deployment guide
│   ├── getting-started.md      # Quick start guide
│   ├── monitoring.md           # Monitoring setup
│   └── disaster_recovery.md    # DR procedures
├── reports/                    # Server reports
└── .github/                    # GitHub Actions
    └── workflows/              # CI/CD workflows
```

## Quick Start

### Deploy Your First Application

1. **Access Dokploy Dashboard**: https://deploy.quantyralabs.cc

2. **Create Application**:
   - Click **Applications** → **Create Application**
   - Connect GitHub repository
   - Configure build settings (Dockerfile or Nixpacks)
   - Set replicas: 2

3. **Configure Environment**:
   ```bash
   DB_HOST=100.102.220.16
   DB_PORT=5000
   DB_DATABASE=myapp_production
   DB_USERNAME=patroni_superuser
   DB_PASSWORD=2e7vBpaaVK4vTJzrKebC
   ```

4. **Add Domain**: myapp.example.com

5. **Deploy**: Click **Deploy** button

Total time: ~5-10 minutes

See [Getting Started Guide](docs/getting-started.md) for detailed instructions.

### Prerequisites

- Dokploy dashboard access: https://deploy.quantyralabs.cc
- SSH access via Tailscale (for troubleshooting)
- GitHub repository with Dockerfile

### Git-Based Deployment

```bash
# Production deployment
git push origin main

# Staging deployment
git push origin staging
```

## Key Services

### Dokploy (Deployment Platform)

- **Dashboard**: https://deploy.quantyralabs.cc
- **Manager**: re-db (100.92.26.38)
- **Worker**: re-node-02 (100.89.130.19)
- **Services**:
  - dokploy: 1/1 replicas (manager only)
  - dokploy-traefik: 2/2 replicas (HA)
  - dokploy-postgres: 1/1 replicas
  - dokploy-redis: 1/1 replicas

### PostgreSQL/Patroni

- **Cluster**: `quantyra_pg`
- **Nodes**: re-node-01, re-node-03, re-node-04
- **Write Endpoint**: router-01:5000, router-02:5000
- **Read Endpoint**: router-01:5001, router-02:5001

```bash
# Check cluster status
patronictl list

# Manual failover
patronictl switchover
```

### Redis

- **Master**: re-node-01:6379
- **Replica**: re-node-03:6379
- **Access**: Tailscale network only

```bash
# Check status
redis-cli -h 100.126.103.51 INFO replication
```

### HAProxy (Database Only)

**UPDATED (2026-04-03)**: HAProxy now handles ONLY database traffic.

- **PostgreSQL Write**: Port 5000 (routes to leader)
- **PostgreSQL Read**: Port 5001 (load balanced replicas)
- **Redis**: Port 6379 (routes to master)
- **Stats**: http://router-01:8404/stats

### Traefik (App Load Balancer)

**NEW (2026-04-03)**: Traefik handles all application traffic.

- **Ports**: 80, 443
- **SSL**: Let's Encrypt with DNS-01 challenge
- **Replicas**: 2 (one per app server)
- **Automatic routing**: Based on Host header

### Monitoring

- **Prometheus**: http://router-01:9090
- **Grafana**: http://router-01:3000
- **Alertmanager**: http://router-01:9093
- **Traefik Metrics**: http://re-db:8080/metrics
- **Docker Metrics**: http://re-db:9323/metrics

## Backup & Recovery

### Backup Schedule

- PostgreSQL: Daily at 2 AM (full on Sunday, diff other days)
- Redis: Daily at 3 AM
- S3 Sync: Daily at 4 AM

### Manual Backup

```bash
# PostgreSQL
PGPASSWORD=2e7vBpaaVK4vTJzrKebC pg_dump -h 100.102.220.16 -p 5000 -U patroni_superuser myapp_production > backup.sql

# Redis
redis-cli -h 100.126.103.51 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk BGSAVE
```

### Recovery

See [Disaster Recovery Guide](docs/disaster_recovery.md)

## Monitoring & Alerts

### Dashboards

- **Traefik**: Grafana → Quantyra - Traefik
- **Docker Swarm**: Grafana → Quantyra - Docker Swarm
- **PostgreSQL & HAProxy**: Grafana → Quantyra - PostgreSQL & HAProxy
- **Redis**: Grafana → Quantyra - Redis
- **Infrastructure**: Grafana → Quantyra - Node Exporter

### Alerts

- Critical: Slack #critical-alerts
- Warning: Slack #infrastructure-alerts

## Security

### Firewall

- UFW configured on all servers
- Tailscale network (100.64.0.0/10) allowed
- SSH rate-limited
- Application ports from Cloudflare IPs

### SSH

- Key-based authentication only
- Password authentication disabled
- Root login: prohibit-password
- Tailscale SSH disabled (using standard SSH keys)

### Cloudflare WAF

5 security rules applied:
1. Allow legitimate bots
2. Challenge suspicious traffic (managed_challenge)
3. Challenge known attackers (managed_challenge)
4. Challenge rate-limited requests (managed_challenge)
5. Block SQL injection attempts

## Documentation

- [Plan](docs/plan.md) - Current tasks, priorities, and milestones
- [Architecture](docs/architecture.md) - Complete infrastructure architecture
- [Dokploy Operations](docs/dokploy-operations.md) - Operational guide for Dokploy
- [Deployment Guide](docs/deployment.md) - Application deployment procedures
- [Getting Started](docs/getting-started.md) - Quick start guide
- [Monitoring](docs/monitoring.md) - Monitoring and alerting setup
- [Disaster Recovery](docs/disaster_recovery.md) - DR procedures

## Common Operations

### Deploy Application

```bash
# Via Git (auto-deploy)
git push origin main

# Via Dokploy Dashboard
# https://deploy.quantyralabs.cc
```

### Check Service Status

```bash
# Dokploy services
ssh root@100.92.26.38 "docker service ls"

# PostgreSQL cluster
ssh root@100.102.220.16 "patronictl list"

# Redis
ssh root@100.126.103.51 "redis-cli INFO replication"
```

### View Logs

```bash
# Application logs (via Dokploy Dashboard)
# Applications → [App] → Logs

# Or via CLI
ssh root@100.92.26.38
docker service logs my_app --tail 100 --follow
```

## Support

- **Dokploy Dashboard**: https://deploy.quantyralabs.cc
- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000
- **HAProxy Stats**: http://100.102.220.16:8404/stats