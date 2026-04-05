# Getting Started with Quantyra Infrastructure

> Quick start guide for deploying applications on Quantyra infrastructure using Dokploy.
>
> **Last Updated**: 2026-04-04

## Overview

Quantyra provides a modern, high-availability infrastructure platform for deploying applications with:

- **Dokploy**: Git-integrated deployment platform
- **Docker Swarm**: Container orchestration across 2 app servers
- **Traefik**: Automatic SSL and load balancing
- **Patroni**: PostgreSQL high availability with automatic failover
- **Redis**: High-performance caching with master-replica setup
- **Cloudflare**: DNS, WAF, and DDoS protection

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                    TRAFFIC FLOW                              │
│                                                              │
│  Apps: Cloudflare → Traefik → Docker Containers             │
│  DBs:  HAProxy → Patroni/Redis                               │
│                                                              │
│  ┌─────────────┐                                            │
│  │ Cloudflare  │  DNS + WAF + DDoS                          │
│  └──────┬──────┘                                            │
│         │                                                    │
│    ┌────┴────┐                                              │
│    │ Traefik │  SSL + Load Balancing                         │
│    └────┬────┘                                              │
│         │                                                    │
│    ┌────┴────┐                                              │
│  ┌─┴─────────┴─┐                                            │
│  │  App Server │  Docker Swarm (2 nodes)                     │
│  │   re-db     │  - re-db (Manager)                          │
│  │  re-node-02 │  - re-node-02 (Worker)                      │
│  └──────┬──────┘                                            │
│         │                                                    │
│    ┌────┴────┐                                              │
│    │ HAProxy │  Database Load Balancer                       │
│    └────┬────┘                                              │
│         │                                                    │
│    ┌────┴────┐                                              │
│    │ Database│  Patroni (3 nodes) + Redis (2 nodes)          │
│    │ Cluster │                                              │
│    └─────────┘                                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Access Dokploy Dashboard

**URL**: https://deploy.quantyralabs.cc

- Deploy, manage, and monitor applications
- Configure domains and SSL certificates
- View logs and metrics
- Manage environment variables

### 2. Deploy Your First Application

**Time Required**: ~5-10 minutes

1. **Create Application**:
   - Click **Applications** → **Create Application**
   - Connect GitHub repository
   - Set build type (Dockerfile or Nixpacks)
   - Configure replicas: 2

2. **Add Environment Variables**:
   ```
   APP_NAME=MyApp
   APP_ENV=production
   APP_KEY=base64:...
   DB_HOST=100.102.220.16
   DB_PORT=5000
   DB_DATABASE=myapp_production
   DB_USERNAME=patroni_superuser
   DB_PASSWORD=2e7vBpaaVK4vTJzrKebC
   ```

3. **Add Domain**:
   - Domain: myapp.example.com
   - HTTPS: Enabled
   - SSL: Auto-provisioned

4. **Deploy**:
   - Click **Deploy** button
   - Monitor build progress
   - Verify application is accessible

### 3. Verify Deployment

```bash
# Check DNS resolution
dig myapp.example.com +short

# Expected: Both app server IPs
# 208.87.128.115
# 23.227.173.245

# Test accessibility
curl -I https://myapp.example.com

# Expected: HTTP/2 200
```

## Infrastructure Components

### App Servers (Dokploy Cluster)

| Server | Role | Public IP | Tailscale IP |
|--------|------|-----------|--------------|
| re-db | Manager | 208.87.128.115 | 100.92.26.38 |
| re-node-02 | Worker | 23.227.173.245 | 100.89.130.19 |

**Services**:
- Dokploy Dashboard (re-db only)
- Traefik (both nodes, HA)
- Docker Swarm routing mesh

### Database Servers (Patroni + Redis)

| Server | Role | Tailscale IP |
|--------|------|--------------|
| re-node-01 | PostgreSQL, Redis Master | 100.126.103.51 |
| re-node-03 | PostgreSQL Leader, Redis Replica | 100.114.117.46 |
| re-node-04 | PostgreSQL Replica, etcd | 100.115.75.119 |

**Connection Endpoints**:
- PostgreSQL Write: `100.102.220.16:5000` or `100.116.175.9:5000`
- PostgreSQL Read: `100.102.220.16:5001` or `100.116.175.9:5001`
- Redis: `100.102.220.16:6379` or `100.116.175.9:6379`

### Routers (HAProxy)

| Server | Role | Tailscale IP |
|--------|------|--------------|
| router-01 | Primary | 100.102.220.16 |
| router-02 | Secondary | 100.116.175.9 |

**Purpose**: Database load balancing and failover

## Deployment Methods

### Method 1: Dokploy Dashboard

**Best for**: Manual deployments, initial setup, configuration changes

1. Access https://deploy.quantyralabs.cc
2. Navigate to Applications
3. Click **Deploy** button
4. Monitor build and deployment logs

### Method 2: Git Push (Auto-Deploy)

**Best for**: Continuous deployment

```bash
# Production deployment
git push origin main

# Staging deployment
git push origin staging
```

### Method 3: CLI

**Best for**: Advanced operations, debugging

```bash
# SSH to manager node
ssh root@100.92.26.38

# List services
docker service ls

# Update service
docker service update my_app --image my-app:v2.0.0

# View logs
docker service logs my_app --tail 100 --follow
```

## Framework-Specific Guides

### Laravel

**Dockerfile**:
```dockerfile
FROM webdevops/php-nginx:8.2

WORKDIR /app
COPY . .

RUN composer install --no-dev --optimize-autoloader

EXPOSE 80

CMD ["supervisord"]
```

**Required Environment Variables**:
```bash
APP_NAME=MyApp
APP_ENV=production
APP_KEY=base64:GENERATE_WITH_PHP_ARTISAN_KEY_GENERATE
APP_DEBUG=false
APP_URL=https://myapp.example.com

DB_CONNECTION=pgsql
DB_HOST=100.102.220.16
DB_PORT=5000
DB_DATABASE=myapp_production
DB_USERNAME=patroni_superuser
DB_PASSWORD=2e7vBpaaVK4vTJzrKebC

REDIS_HOST=100.102.220.16
REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
REDIS_PORT=6379

CACHE_DRIVER=redis
SESSION_DRIVER=redis
QUEUE_CONNECTION=redis
```

**Automatic Operations**:
- Migrations run automatically during deployment
- `.env` file generated from environment variables
- Storage permissions set automatically

### Next.js

**Dockerfile**:
```dockerfile
FROM node:20-alpine

WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
```

**Required Environment Variables**:
```bash
NODE_ENV=production
NEXT_PUBLIC_API_URL=https://api.example.com
```

### Python (Flask/Django)

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "app:app"]
```

**Required Environment Variables (Django)**:
```bash
APP_ENV=production
SECRET_KEY=your-secret-key
DEBUG=false
ALLOWED_HOSTS=myapp.example.com
DATABASE_URL=postgres://patroni_superuser:2e7vBpaaVK4vTJzrKebC@100.102.220.16:5000/myapp_production
```

### Go

**Dockerfile**:
```dockerfile
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.* ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o main .

FROM alpine:latest

RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/main .

EXPOSE 8080

CMD ["./main"]
```

## Database Configuration

### PostgreSQL

**Connection String**:
```
Host: 100.102.220.16 (HAProxy router-01)
   or: 100.116.175.9 (HAProxy router-02)
Port: 5000 (Write)
   or: 5001 (Read)
Database: myapp_production
User: patroni_superuser
Password: 2e7vBpaaVK4vTJzrKebC
```

**Key Points**:
- Always use HAProxy endpoints (router IPs), not direct database IPs
- Port 5000 for writes (routes to leader)
- Port 5001 for reads (load balanced across replicas)
- Automatic failover via HAProxy health checks

**Creating Databases**:
```bash
# SSH to router or any server
ssh root@100.102.220.16

# Connect via HAProxy
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser

# Create database
CREATE DATABASE myapp_production;
CREATE DATABASE myapp_staging;
```

### Redis

**Connection String**:
```
Host: 100.102.220.16 (HAProxy router-01)
   or: 100.116.175.9 (HAProxy router-02)
Port: 6379
Password: CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
```

**Key Points**:
- Use HAProxy endpoints for high availability
- Master-replica setup with automatic failover
- Max memory: 4GB per node
- Persistence: RDB + AOF enabled

## Domain and SSL Configuration

### Adding Domains

1. **Via Dokploy Dashboard**:
   - Applications → [App Name] → Domains
   - Click **Add Domain**
   - Enter: myapp.example.com
   - Enable HTTPS

2. **SSL Certificate**:
   - Auto-provisioned by Let's Encrypt
   - Uses DNS-01 challenge via Cloudflare
   - Works with Cloudflare proxy enabled
   - Auto-renewal at 30 days before expiry

### DNS Configuration

**Automatic** (Recommended):
- Dokploy configures DNS automatically via Cloudflare API
- No manual intervention required

**Manual** (If needed):
```
Type: A
Name: myapp.example.com
Value: 208.87.128.115 (re-db)
Proxy: ON

Type: A
Name: myapp.example.com
Value: 23.227.173.245 (re-node-02)
Proxy: ON
```

### Wildcard Domains

For multi-tenant applications:

1. Add domain: `*.myapp.example.com`
2. SSL: Wildcard certificate issued automatically
3. DNS: Single A record for `*.myapp.example.com`

## Monitoring and Observability

### Prometheus

**URL**: http://100.102.220.16:9090

- Metrics collection and alerting
- Scrape targets: all servers, databases, Traefik, Docker
- Retention: 30 days

### Grafana

**URL**: http://100.102.220.16:3000
**Credentials**: admin / nyb4faf3hye6zwn_UQT

**Pre-configured Dashboards**:
- Traefik Dashboard
- Docker Swarm Dashboard
- PostgreSQL Dashboard
- Redis Dashboard
- Node Exporter Dashboard

### HAProxy Stats

**URL**: http://100.102.220.16:8404/stats
**Credentials**: admin / jFNeZ2bhfrTjTK7aKApD

- Real-time connection statistics
- Backend health status
- Request rates and response times

### Alerting

Alerts are configured in Prometheus and routed via Alertmanager:

- **Critical**: Slack #critical-alerts
- **Warning**: Slack #infrastructure-alerts

## SSH Access

### Prerequisites

- Tailscale installed and connected
- SSH key added to Tailscale account
- SSH key authorized on servers

### Connecting

```bash
# Connect via Tailscale IP
ssh root@100.92.26.38      # re-db (app server)
ssh root@100.89.130.19     # re-node-02 (app server)
ssh root@100.102.220.16    # router-01 (HAProxy, monitoring)
ssh root@100.116.175.9     # router-02 (HAProxy)
ssh root@100.126.103.51    # re-node-01 (PostgreSQL, Redis)
ssh root@100.114.117.46    # re-node-03 (PostgreSQL, Redis)
ssh root@100.115.75.119    # re-node-04 (PostgreSQL, etcd)
```

### SSH Config (Optional)

Add to `~/.ssh/config`:

```
Host re-db
    HostName 100.92.26.38
    User root

Host re-node-02
    HostName 100.89.130.19
    User root

Host router-01
    HostName 100.102.220.16
    User root

Host router-02
    HostName 100.116.175.9
    User root
```

## Common Operations

### Deploy Application

```bash
# Via Git (auto-deploy)
git push origin main

# Via Dokploy Dashboard
# 1. Navigate to Applications → [App Name]
# 2. Click "Deploy"
# 3. Monitor build logs
```

### View Logs

```bash
# Via Dokploy Dashboard
# Applications → [App Name] → Logs

# Via CLI
ssh root@100.92.26.38
docker service logs my_app --tail 100 --follow
```

### Scale Application

```bash
# Via Dokploy Dashboard
# Applications → [App Name] → Settings → Replicas: 2

# Via CLI
ssh root@100.92.26.38
docker service scale my_app=3
```

### Check Database Status

```bash
# PostgreSQL cluster status
ssh root@100.102.220.16
patronictl list

# Redis master/replica status
ssh root@100.126.103.51
redis-cli -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO replication
```

### Backup Database

```bash
# PostgreSQL backup
PGPASSWORD=2e7vBpaaVK4vTJzrKebC pg_dump -h 100.102.220.16 -p 5000 -U patroni_superuser myapp_production > backup.sql

# Redis backup
ssh root@100.126.103.51
redis-cli -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk BGSAVE
```

## Troubleshooting

### Application Not Accessible

1. **Check DNS**:
   ```bash
   dig myapp.example.com +short
   # Should return both app server IPs
   ```

2. **Check SSL**:
   ```bash
   curl -I https://myapp.example.com
   # Should return HTTP/2 200
   ```

3. **Check Application Logs**:
   - Dokploy Dashboard → Applications → [App] → Logs
   - Or via CLI: `docker service logs my_app --tail 100`

4. **Check Container Status**:
   ```bash
   ssh root@100.92.26.38
   docker service ps my_app
   ```

### Database Connection Failed

1. **Verify HAProxy Endpoint**:
   ```bash
   psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d myapp_production -c "SELECT 1;"
   ```

2. **Check Database Exists**:
   ```bash
   PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c "\l"
   ```

3. **Verify Credentials**:
   - Check environment variables in Dokploy
   - Ensure using correct host (router IP, not database IP)

### Deployment Failed

1. **Check Build Logs**:
   - Dokploy Dashboard → Applications → [App] → Deployments
   - Click failed deployment to view logs

2. **Common Issues**:
   - Missing environment variables
   - Database connection failure during build
   - Dockerfile syntax errors
   - Out of memory during build

3. **Solution**:
   - Fix identified issue
   - Push new commit or click "Redeploy"

## Security Best Practices

### Application Security

- ✅ Enable Cloudflare proxy (orange cloud) on all domains
- ✅ Use HTTPS for all traffic
- ✅ Set `APP_DEBUG=false` in production
- ✅ Use separate databases for production/staging
- ❌ Never commit secrets to Git
- ❌ Never use default passwords

### Database Security

- ✅ Use HAProxy endpoints (not direct IPs)
- ✅ Use strong, unique passwords
- ✅ Limit database user permissions
- ❌ Never expose databases to public internet
- ❌ Never use root user in applications

### Access Security

- ✅ Use Tailscale for SSH access
- ✅ Use key-based authentication
- ✅ Keep software updated
- ❌ Never disable firewall
- ❌ Never share credentials

## Next Steps

- **Deploy Your First App**: Follow the quick start guide above
- **Explore Documentation**: [Deployment Guide](deployment.md), [Architecture](architecture.md)
- **Set Up Monitoring**: Access Grafana and Prometheus dashboards
- **Configure Alerts**: Review [Monitoring Guide](monitoring.md)
- **Plan for DR**: Read [Disaster Recovery Guide](disaster_recovery.md)

## Additional Resources

### Documentation

- [Dokploy Operations Guide](dokploy-operations.md) - Detailed operational procedures
- [Deployment Guide](deployment.md) - Complete deployment documentation
- [Architecture Overview](architecture.md) - System architecture details
- [Monitoring Guide](monitoring.md) - Monitoring and alerting setup
- [Disaster Recovery](disaster_recovery.md) - Backup and recovery procedures

### External Resources

- [Dokploy Documentation](https://docs.dokploy.com)
- [Docker Swarm Guide](https://docs.docker.com/engine/swarm/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Patroni Documentation](https://patroni.readthedocs.io/)

### Support

- **Dokploy Dashboard**: https://deploy.quantyralabs.cc
- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000
- **HAProxy Stats**: http://100.102.220.16:8404/stats