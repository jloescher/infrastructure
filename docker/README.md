# Docker Compose Deployment

Deploy the infrastructure management dashboard using Docker Compose on any machine connected to your Tailscale network.

## Quick Start

```bash
# 1. Navigate to docker directory
cd docker

# 2. Create environment file
cp .env.example .env
nano .env  # Fill in your credentials

# 3. Deploy
./scripts/deploy.sh start
```

## Access

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | http://localhost:8080 | Infrastructure management |
| Prometheus | http://localhost:9090 | Metrics and alerting |
| Grafana | http://localhost:3000 | Dashboards and visualization |
| Alertmanager | http://localhost:9093 | Alert management |

## Requirements

- Docker and Docker Compose installed
- Connected to Tailscale network (for accessing infrastructure servers)
- Valid credentials in `.env` file

## Commands

```bash
./scripts/deploy.sh start     # Start all services
./scripts/deploy.sh stop      # Stop all services
./scripts/deploy.sh restart   # Restart all services
./scripts/deploy.sh rebuild   # Rebuild containers
./scripts/deploy.sh logs      # View logs
./scripts/deploy.sh status    # Show status
./scripts/deploy.sh backup    # Backup data
./scripts/deploy.sh restore   # Restore from backup
```

## Synology NAS Deployment

1. **Install Docker** from Package Center
2. **Enable SSH** in Control Panel → Terminal & SNMP
3. **Install Tailscale** from Package Center or via SSH:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
4. **Deploy:**
   ```bash
   ssh admin@your-nas
   git clone https://github.com/user/infrastructure.git
   cd infrastructure/docker
   cp .env.example .env
   nano .env
   ./scripts/deploy.sh start
   ```

## Architecture

```
┌─────────────────────────────────────┐
│         Docker Compose Stack        │
│                                     │
│  Dashboard ── Prometheus ── Grafana │
│     │            │           │      │
│     └────────────┴───────────┘      │
│                  │                  │
│           Docker Network            │
└─────────────────────────────────────┘
                   │
           Tailscale Network
                   │
    ┌──────────────┼──────────────┐
    │              │              │
  Routers     App Servers    Databases
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| PG_HOST | PostgreSQL HAProxy IP | Yes |
| PG_PORT | PostgreSQL port (5000=RW, 5001=RO) | Yes |
| PG_USER | PostgreSQL username | Yes |
| PG_PASSWORD | PostgreSQL password | Yes |
| REDIS_HOST | Redis host IP | Yes |
| REDIS_PASSWORD | Redis password | Yes |
| DASHBOARD_USER | Dashboard login username | Yes |
| DASHBOARD_PASS | Dashboard login password | Yes |
| GRAFANA_PASSWORD | Grafana admin password | Yes |

### Volumes

| Volume | Purpose |
|--------|---------|
| dashboard-config | Application configurations |
| dashboard-docs | Documentation files |
| prometheus-data | Metrics storage (15d retention) |
| grafana-data | Dashboards and settings |
| alertmanager-data | Alert state |

## Troubleshooting

### Dashboard can't connect to servers

1. Verify you're on Tailscale network:
   ```bash
   tailscale status
   ```

2. Test connectivity:
   ```bash
   docker exec infrastructure-dashboard curl -s http://100.102.220.16:5000
   ```

3. Check .env credentials are correct

### Services not starting

```bash
# Check logs
./scripts/deploy.sh logs dashboard
./scripts/deploy.sh logs prometheus

# Rebuild
./scripts/deploy.sh rebuild
```

### Reset everything

```bash
# Stop and remove all containers and volumes
docker compose down -v

# Start fresh
./scripts/deploy.sh start
```

## Security Notes

1. **Never commit .env file** - Contains all credentials
2. **Use strong passwords** - For dashboard, Grafana, and database access
3. **Tailscale only** - Dashboard not exposed to public internet
4. **Regular backups** - Use `./scripts/deploy.sh backup`