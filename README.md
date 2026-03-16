# Quantyra Infrastructure

Infrastructure-as-code repository for managing Quantyra VPS infrastructure.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Cloudflare DNS                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐         ┌────▼────┐
   │router-01│         │router-02│
   │ HAProxy │◄───────►│ HAProxy │
   │  etcd   │         │         │
   │Prometheus│        │  Web    │
   │ Grafana │         │  :80/443│
   └────┬────┘         └────┬────┘
        │                   │
        │    HAProxy PG     │
        │   Write: 5000     │
        │   Read: 5001      │
        │                   │
   ┌────▼───────────────────▼────┐
   │    Patroni PostgreSQL       │
   │  ┌────────┐  ┌────────┐  ┌────────┐
   │  │re-node-│  │re-node-│  │re-node-│
   │  │   01   │  │   03   │  │   04   │
   │  │Redis   │  │Redis   │  │        │
   │  │Master  │  │Replica │  │        │
   │  └────────┘  └────────┘  └────────┘
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │     re-db (XOTEC Data Layer)        │
   │  ┌──────────────────────────────┐   │
   │  │ Caddy (Reverse Proxy)        │   │
   │  │ :80, :443                    │   │
   │  │ quantyra.io, lzrcdn.com         │   │
   │  └──────────────┬───────────────┘   │
   │                 │                    │
   │  ┌──────────────┴───────────────┐   │
   │  │ App Blue :8001  App Green :8002 │
   │  └──────────────┬───────────────┘   │
   │                 │                    │
   │  ┌──────────────┴───────────────┐   │
   │  │ Workers (Ingest/Media/Maint) │   │
   │  │ Scheduler | Asynqmon :9090   │   │
   │  └──────────────────────────────┘   │
   └─────────────────────────────────────┘

   ┌─────────────────────────────────────┐
   │        re-node-02 (Idle)            │
   │        Ready for deployment         │
   └─────────────────────────────────────┘

└──────────────────────────────────────────────────┘
                     Tailscale VPN
```

## Server Inventory

| Server | IP (Tailscale) | Role | Specs |
|--------|----------------|------|-------|
| re-node-01 | 100.126.103.51 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| re-node-03 | 100.114.117.46 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| re-node-04 | 100.115.75.119 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| router-01 | 100.102.220.16 | Router/Monitoring | 2 vCPU, 8GB RAM, 160GB SSD |
| router-02 | 100.116.175.9 | Router | 2 vCPU, 8GB RAM, 160GB SSD |
| re-db | 100.92.26.38 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |
| re-node-02 | 100.101.39.22 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |

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
├── configs/                    # Service configurations
│   ├── caddy/                  # Caddy reverse proxy
│   ├── haproxy/                # HAProxy configs
│   ├── patroni/                # Patroni configs
│   ├── postgresql/             # PostgreSQL configs
│   ├── redis/                  # Redis configs
│   └── quantyra/                  # XOTEC application configs
├── docker/                     # Docker Compose files
│   ├── app-servers/            # App server compose files
│   └── monitoring/             # Monitoring stack compose
├── monitoring/                 # Monitoring configs
│   ├── prometheus/             # Prometheus config
│   ├── grafana/                # Grafana dashboards
│   └── alertmanager/           # Alertmanager config
├── reports/                    # Server reports
├── scripts/                    # Utility scripts
├── security/                   # Security configs
│   ├── firewall/               # UFW rules
│   └── ssh/                    # SSH hardening
├── docs/                       # Documentation
│   ├── runbook.md              # Operational runbook
│   ├── deployment.md           # Deployment guide
│   ├── disaster_recovery.md    # DR procedures
│   ├── action_items.md         # Prioritized tasks
│   └── quantyra_application.md    # XOTEC app docs
└── .github/                    # GitHub Actions
    └── workflows/              # CI/CD workflows
```

## Quick Start

### Prerequisites

- Ansible 2.12+
- SSH access to all servers
- Tailscale connected

### Initial Setup

```bash
# Install dependencies
pip install ansible

# Test connectivity
ansible all -m ping

# Collect current configuration
bash scripts/collect_quantyra_infra_report.sh
```

### Provisioning

```bash
# Provision all servers
ansible-playbook ansible/playbooks/provision.yml

# Provision specific group
ansible-playbook ansible/playbooks/provision.yml --limit db_servers
```

### Deployment

```bash
# Deploy applications
ansible-playbook ansible/playbooks/deploy.yml

# Deploy via CI/CD
git push origin main
```

## Key Services

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

### HAProxy

- **Stats**: http://router-01:8404/stats
- **Metrics**: Port 9101

### Monitoring

- **Prometheus**: http://router-01:9090
- **Grafana**: https://grafana.quantyra.com
- **Alertmanager**: http://router-01:9093

## Backup & Recovery

### Backup Schedule

- PostgreSQL: Daily at 2 AM (full on Sunday, diff other days)
- Redis: Daily at 3 AM
- S3 Sync: Daily at 4 AM

### Manual Backup

```bash
# PostgreSQL
/usr/local/bin/postgres_backup.sh full

# Redis
/usr/local/bin/redis_backup.sh

# Sync to S3
/usr/local/bin/sync_to_s3.sh /backup
```

### Recovery

See [Disaster Recovery Guide](docs/disaster_recovery.md)

## Monitoring & Alerts

### Dashboards

- PostgreSQL & HAProxy: Grafana → Quantyra → PostgreSQL & HAProxy
- Redis: Grafana → Quantyra → Redis
- Infrastructure: Grafana → Quantyra → Node Exporter

### Alerts

- Critical: Slack #critical-alerts + PagerDuty
- Warning: Slack #infrastructure-alerts

### Health Check

```bash
# Run health check script
/usr/local/bin/health_check.sh
```

## Security

### Firewall

- UFW configured on all servers
- Tailscale network (100.64.0.0/10) allowed
- SSH rate-limited
- Application ports restricted

### SSH

- Key-based authentication only
- Password authentication disabled
- Root login: prohibit-password

### fail2ban

- SSH protection enabled
- HAProxy, PostgreSQL, Redis protection enabled

## Documentation

- [Runbook](docs/runbook.md) - Operational procedures
- [Deployment Guide](docs/deployment.md) - Deployment instructions
- [Disaster Recovery](docs/disaster_recovery.md) - DR procedures
- [Infrastructure Overview](quantyra_infrastructure_overview.md) - Architecture details

## Maintenance

### Update System Packages

```bash
ansible-playbook ansible/playbooks/update.yml
```

### Update Specific Service

```bash
# PostgreSQL
ansible-playbook ansible/playbooks/update.yml --tags postgresql

# Redis
ansible-playbook ansible/playbooks/update.yml --tags redis

# HAProxy
ansible-playbook ansible/playbooks/update.yml --tags haproxy
```

### Planned Maintenance

1. Create silence in Alertmanager
2. Perform maintenance
3. Verify services
4. Remove silence

## Troubleshooting

### Common Issues

See [Runbook](docs/runbook.md) for detailed troubleshooting procedures.

### Logs

```bash
# PostgreSQL
journalctl -u patroni -f

# Redis
journalctl -u redis -f

# HAProxy
journalctl -u haproxy -f

# Prometheus
journalctl -u prometheus -f
```

## XOTEC Application

The XOTEC Data Layer is a Go application running on `re-db` that processes MLS real estate data.

### Services

| Service | Port | Description |
|---------|------|-------------|
| `quantyra-app-blue` | 8001 | HTTP server (active) |
| `quantyra-app-green` | 8002 | HTTP server (standby) |
| `quantyra-scheduler` | - | Job scheduler |
| `quantyra-asynqmon` | 9090 | Queue monitor |
| `quantyra-worker-*` | - | Background workers |
| `caddy` | 80, 443 | Reverse proxy |

### Domains

- `quantyra.io` - Main application
- `lzrcdn.com` - CDN/Media
- `media.lzrcdn.com` - Media proxy

### Quick Commands

```bash
# Check service status
ssh root@100.92.26.38 'systemctl status quantyra-* --no-pager'

# View logs
journalctl -u quantyra-app-blue -f

# Health check
curl https://quantyra.io/health
```

See [XOTEC Application Documentation](docs/quantyra_application.md) for details.

## Contributing

1. Create feature branch
2. Make changes
3. Test on staging environment
4. Submit PR for review
5. Deploy after approval

## Support

- **Slack**: #infrastructure-alerts
- **On-call**: PagerDuty
- **Documentation**: This repository