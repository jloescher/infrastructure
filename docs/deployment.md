# Deployment Guide

> Complete guide for deploying applications and managing infrastructure on Quantyra.
>
> **Last Updated**: 2026-04-04

## Overview

Quantyra uses **Dokploy** as the primary deployment platform, providing:

- **Git-Integrated Deployment**: Automatic builds and deployments from GitHub
- **Docker Swarm Orchestration**: High availability across 2 app servers
- **Traefik Load Balancing**: Automatic SSL with Let's Encrypt DNS-01 challenges
- **Multi-Replica Support**: Distribute app replicas across both servers
- **External Database Integration**: Connect to Patroni cluster via HAProxy

### Architecture

```
┌─────────────┐
│ Cloudflare  │  DNS + WAF + DDoS Protection
└──────┬──────┘
       │ Round-robin DNS
       ├─────────────────┬─────────────────┐
       ▼                 ▼                 │
   ┌───────┐         ┌───────┐             │
   │ re-db │         │re-node│             │
   │Traefik│         │Traefik│             │
   └───┬───┘         └───┬───┘             │
       │                 │                 │
       └────────┬────────┘                 │
                │                          │
         ┌──────▼──────┐                   │
         │ Docker Swarm│                   │
         │  Containers │                   │
         └──────┬──────┘                   │
                │                          │
         ┌──────▼──────┐                   │
         │   HAProxy   │◄──────────────────┘
         │  (Database) │     Database traffic only
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Patroni +  │
         │   Redis     │
         └─────────────┘
```

**Key Points**:
- App traffic: Cloudflare → Traefik → Docker containers (bypasses HAProxy)
- Database traffic: HAProxy → Patroni/Redis (unchanged from previous architecture)
- SSL: Traefik manages Let's Encrypt certificates automatically
- HA: Deploy with 2+ replicas for high availability

## Prerequisites

### Required Access

- **Dokploy Dashboard**: https://deploy.quantyralabs.cc
- **GitHub Repository**: Write access to application repos
- **Cloudflare**: DNS management access
- **SSH Access**: Tailscale-connected to app servers (optional, for troubleshooting)

### Required Tools

- Git
- Docker (for local testing)
- SSH client (for troubleshooting)

### Network Access

All servers are accessible via Tailscale VPN (100.64.0.0/10 network).

## Quick Start

### Deploy Your First Application

1. **Access Dokploy Dashboard**: https://deploy.quantyralabs.cc

2. **Create Application**:
   - Click **Applications** → **Create Application**
   - Connect your GitHub repository
   - Set build type: Dockerfile or Nixpacks
   - Configure replicas: 2 (recommended)

3. **Add Environment Variables**:
   - Add database credentials
   - Add application secrets
   - See [Environment Variables](#environment-variables) section

4. **Add Domain**:
   - Add production domain: myapp.example.com
   - SSL certificate auto-provisioned
   - DNS auto-configured in Cloudflare

5. **Deploy**:
   - Click **Deploy** button
   - Monitor build and deployment progress
   - Verify application is accessible

Total time: ~5-10 minutes for first deployment.

## Deployment Methods

### Method 1: Dokploy Dashboard (Recommended)

**Best for**: Initial deployment, configuration changes, manual deployments

1. **Navigate to Applications**:
   - Access https://deploy.quantyralabs.cc
   - Click **Applications** in sidebar

2. **Create New Application**:
   ```
   Name: my-app
   Provider: GitHub
   Repository: user/my-app
   Branch: main
   Build Type: Dockerfile
   Port: 0 (auto-detect)
   Replicas: 2
   ```

3. **Configure**:
   - **Environment Variables**: Add required secrets
   - **Domains**: Add production and staging domains
   - **Build Settings**: Configure Dockerfile path if non-standard

4. **Deploy**:
   - Click **Deploy** button
   - Watch build logs in real-time
   - Verify health checks pass

### Method 2: Git Push (Auto-Deploy)

**Best for**: Continuous deployment, frequent updates

1. **Configure Webhook**:
   - Dokploy automatically creates webhook when you connect GitHub
   - Webhook URL: `https://deploy.quantyralabs.cc/api/deploy/{token}`

2. **Push to Deploy**:
   ```bash
   # Production deployment
   git push origin main

   # Staging deployment
   git push origin staging
   ```

3. **Monitor Deployment**:
   - View progress in Dokploy dashboard
   - Check deployment logs
   - Receive notifications on completion

**Note**: Branch-based deployment is configurable. Default mapping:
- `main` → production environment
- `staging` → staging environment

### Method 3: Webhook (External Triggers)

**Best for**: CI/CD pipelines, external automation

1. **Get Webhook URL**:
   - Applications → [App Name] → Settings → Webhook
   - Copy webhook URL

2. **Trigger Deployment**:
   ```bash
   curl -X POST https://deploy.quantyralabs.cc/api/deploy/{token} \
     -H "Content-Type: application/json" \
     -d '{"ref": "refs/heads/main"}'
   ```

### Method 4: CLI (Advanced)

**Best for**: Debugging, advanced operations, automation scripts

```bash
# SSH to manager node
ssh root@100.92.26.38

# List all services
docker service ls

# Update service image
docker service update my_app --image my-app:v2.0.0

# Scale replicas
docker service scale my_app=3

# View logs
docker service logs my_app --tail 100 --follow

# Rollback
docker service rollback my_app
```

## Application Configuration

### Dockerfile Requirements

**Laravel Example**:
```dockerfile
FROM webdevops/php-nginx:8.2

WORKDIR /app
COPY . .

RUN composer install --no-dev --optimize-autoloader

EXPOSE 80

CMD ["supervisord"]
```

**Next.js Example**:
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

### Port Configuration

| Setting | Value | Behavior |
|---------|-------|----------|
| `EXPOSE 80` in Dockerfile | Port: `0` (auto) | ✅ Auto-detects port 80 |
| `EXPOSE 3000` in Dockerfile | Port: `0` (auto) | ✅ Auto-detects port 3000 |
| No EXPOSE in Dockerfile | Port: `80` (manual) | ✅ Explicitly set port 80 |

**Recommendation**: Always include `EXPOSE` directive in Dockerfile for clarity.

### Replica Configuration

**Single Replica** (Not Recommended):
- ❌ No high availability
- ❌ Downtime during updates
- ✅ Lower resource usage

**Two Replicas** (Recommended):
- ✅ High availability (1 replica per node)
- ✅ Zero-downtime updates
- ✅ Fault tolerance if one node fails
- ⚠️ Requires 2x memory/CPU

**Three+ Replicas**:
- ✅ Higher availability
- ✅ Can handle node failure + load
- ⚠️ Higher resource usage
- ⚠️ May exceed database connection limits

**Database Connection Considerations**:
- Each replica opens its own database connections
- PostgreSQL max_connections: 200
- PgBouncer pooling: 20 connections per pool
- Recommended: 2 replicas maximum per app

### Resource Limits

Set resource constraints per replica:

**Memory Limits**:
- Laravel apps: 256MB - 512MB
- Next.js apps: 512MB - 1GB
- Python apps: 256MB - 512MB

**CPU Limits**:
- Light traffic: 0.25 (25% of 1 CPU)
- Medium traffic: 0.5 (50% of 1 CPU)
- Heavy traffic: 1.0 (100% of 1 CPU)

**Configuration**:
```bash
# Via Dashboard: Applications → [App] → Settings
# Memory Limit: 512MB
# CPU Limit: 0.5
```

## Environment Variables

### Adding Variables

1. **Via Dashboard**:
   - Applications → [App Name] → Environment
   - Click **Add Variable**
   - Enter key-value pairs

2. **Bulk Import**:
   ```
   APP_ENV=production
   APP_KEY=base64:...
   DB_HOST=100.102.220.16
   DB_PORT=5000
   ```

3. **Sensitive Values**:
   - Mark as "Secret" to hide from UI
   - Encrypted at rest in Dokploy database

### Database Connections

**PostgreSQL (Production)**:
```bash
DB_CONNECTION=pgsql
DB_HOST=100.102.220.16          # HAProxy endpoint (router-01)
# or: 100.116.175.9             # HAProxy endpoint (router-02)
DB_PORT=5000                    # Write endpoint
# or: 5001                      # Read endpoint
DB_DATABASE=myapp_production
DB_USERNAME=patroni_superuser
DB_PASSWORD=2e7vBpaaVK4vTJzrKebC
```

**Redis**:
```bash
REDIS_HOST=100.102.220.16       # HAProxy endpoint (router-01)
# or: 100.116.175.9             # HAProxy endpoint (router-02)
REDIS_PORT=6379
REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
```

**Key Points**:
- Always use HAProxy endpoints (router IPs) for database connections
- HAProxy provides automatic failover
- Both routers (100.102.220.16 and 100.116.175.9) are valid endpoints
- Use port 5000 for writes, port 5001 for reads

### Framework-Specific Variables

**Laravel**:
```bash
APP_NAME=MyApp
APP_ENV=production
APP_KEY=base64:GENERATE_WITH_PHP_ARTISAN_KEY_GENERATE
APP_DEBUG=false
APP_URL=https://myapp.example.com

LOG_CHANNEL=stderr
LOG_LEVEL=error
```

**Next.js**:
```bash
NODE_ENV=production
NEXT_PUBLIC_API_URL=https://api.example.com
```

**Python (Flask/Django)**:
```bash
APP_ENV=production
SECRET_KEY=your-secret-key
DEBUG=false
ALLOWED_HOSTS=myapp.example.com
```

## Domain Configuration

### Adding Domains

1. **Navigate to Domains**:
   - Applications → [App Name] → Domains

2. **Add Production Domain**:
   ```
   Domain: myapp.example.com
   Port: (leave empty for auto-detect)
   HTTPS: Enabled
   ```

3. **Add Staging Domain** (Optional):
   ```
   Domain: staging.myapp.example.com
   Port: (leave empty)
   HTTPS: Enabled
   ```

4. **Wildcard Domain** (Multi-tenant):
   ```
   Domain: *.myapp.example.com
   Port: (leave empty)
   HTTPS: Enabled
   ```

### DNS Configuration

Dokploy automatically configures DNS via Cloudflare API.

**Manual Verification**:
```bash
# Check DNS resolution
dig myapp.example.com +short

# Expected output: Both app server IPs
# 208.87.128.115
# 23.227.173.245
```

**Manual Configuration** (if needed):
1. Go to Cloudflare DNS settings
2. Add two A records:
   ```
   myapp.example.com → 208.87.128.115 (re-db)
   myapp.example.com → 23.227.173.245 (re-node-02)
   ```
3. Enable Cloudflare proxy (orange cloud)

### SSL Certificates

**Automatic Provisioning**:
- Let's Encrypt certificates via Traefik
- DNS-01 challenge via Cloudflare API
- Works with Cloudflare proxy enabled
- Auto-renewal at 30 days before expiry

**Verification**:
```bash
# Check certificate
echo | openssl s_client -servername myapp.example.com -connect myapp.example.com:443 2>/dev/null | openssl x509 -noout -dates
```

## Deployment Workflow

### Initial Deployment

```
1. Create Application in Dokploy
   ↓
2. Configure Environment Variables
   ↓
3. Add Domains
   ↓
4. Click "Deploy"
   ↓
5. Build Phase (5-10 min)
   - Clone repository
   - Build Docker image
   - Push to local registry
   ↓
6. Deploy Phase (1-2 min)
   - Create Swarm service
   - Start containers on both nodes
   - Configure Traefik routing
   ↓
7. Health Check Phase (1 min)
   - Verify containers are healthy
   - Verify Traefik routing works
   - Verify SSL certificate issued
   ↓
8. Complete ✅
```

### Update Deployment

```
1. Push changes to Git
   ↓
2. Dokploy detects webhook
   ↓
3. Build new image
   ↓
4. Rolling update:
   - Start new container on re-node-02
   - Wait for health check
   - Stop old container on re-node-02
   - Start new container on re-db
   - Wait for health check
   - Stop old container on re-db
   ↓
5. Complete ✅
   (Zero downtime)
```

### Rollback

**Via Dashboard**:
1. Applications → [App Name] → Deployments
2. Find previous successful deployment
3. Click **Rollback**

**Via CLI**:
```bash
# SSH to manager node
ssh root@100.92.26.38

# Rollback to previous version
docker service rollback my_app
```

## Monitoring and Observability

### Application Logs

**Via Dashboard**:
- Applications → [App Name] → Logs
- Real-time streaming
- Filter by time range

**Via CLI**:
```bash
# SSH to manager node
ssh root@100.92.26.38

# View logs
docker service logs my_app --tail 100 --follow

# View logs from specific replica
docker service logs my_app.1.my_app_id --tail 50
```

### Metrics

**Prometheus Endpoints**:
- Traefik: `http://re-db:8080/metrics`
- Docker: `http://re-db:9323/metrics`

**Grafana Dashboards**:
- Access: http://100.102.220.16:3000
- Credentials: admin / nyb4faf3hye6zwn_UQT
- Pre-configured dashboards:
  - Traefik Dashboard
  - Docker Swarm Dashboard
  - Node Exporter Dashboard
  - PostgreSQL Dashboard

### Health Checks

**Container Health**:
```bash
# Check container health status
docker inspect $(docker ps -q -f name=my_app | head -1) --format '{{.State.Health.Status}}'
```

**Application Health**:
```bash
# Check application responds
curl -I https://myapp.example.com

# Check on specific server
curl -I https://myapp.example.com --resolve myapp.example.com:443:208.87.128.115
curl -I https://myapp.example.com --resolve myapp.example.com:443:23.227.173.245
```

## Troubleshooting

### Application Won't Start

**Diagnosis**:
```bash
# Check service status
docker service ps my_app --no-trunc

# Check logs
docker service logs my_app --tail 100

# Check container exit code
docker ps -a -f name=my_app --format "{{.ID}} {{.State.ExitCode}}"
```

**Common Causes**:
1. Missing environment variables
2. Database connection failure
3. Port misconfiguration
4. Permission issues
5. Out of memory

**Solutions**:
- Verify all required environment variables are set
- Test database connectivity manually
- Check Dockerfile EXPOSE directive
- Review container logs for errors
- Increase memory limit

### Database Connection Issues

**Symptoms**: Application logs show "connection refused" or timeout

**Diagnosis**:
```bash
# Test database connectivity from app server
ssh root@100.92.26.38

# Test PostgreSQL
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d myapp_production -c "SELECT 1;"

# Test Redis
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk PING
```

**Common Issues**:
1. Wrong DB_HOST (should be HAProxy endpoint, not database server)
2. Wrong DB_PORT (5000 for write, 5001 for read)
3. Missing or wrong password
4. Database not created

**Solutions**:
- Verify using HAProxy endpoint (100.102.220.16 or 100.116.175.9)
- Check port is 5000/5001, not 5432
- Verify credentials in environment variables
- Create database if needed (see Database Creation section)

### SSL Certificate Issues

**Symptoms**: Browser shows invalid certificate, HTTPS fails

**Diagnosis**:
```bash
# Check Traefik logs
ssh root@100.92.26.38
docker service logs dokploy-traefik 2>&1 | grep -i acme

# Check certificate storage
docker exec $(docker ps -q -f name=dokploy-traefik) ls -la /etc/traefik/acme/
```

**Common Causes**:
1. Cloudflare API token not configured
2. DNS not pointing to correct IPs
3. Domain not in Cloudflare

**Solutions**:
- Verify Cloudflare API token in Dokploy settings
- Check DNS A records point to app server IPs
- Confirm domain exists in Cloudflare zone

### Service Not Distributed Across Nodes

**Symptoms**: All replicas on one node

**Diagnosis**:
```bash
# Check node status
docker node ls

# Check service distribution
docker service ps my_app

# Check node resources
docker node inspect re-db --format '{{.Description.Resources}}'
docker node inspect re-node-02 --format '{{.Description.Resources}}'
```

**Causes**:
1. One node is in "Drain" or "Unavailable" state
2. Resource constraints too high
3. Placement constraints limiting distribution

**Solutions**:
- Ensure both nodes are "Ready"
- Reduce memory/CPU limits
- Remove placement constraints

## Database Operations

### Creating Databases

**Via PostgreSQL CLI**:
```bash
# SSH to any server with PostgreSQL client
ssh root@100.102.220.16

# Connect via HAProxy write endpoint
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser

# Create database
CREATE DATABASE myapp_production;
CREATE DATABASE myapp_staging;

# Create user (optional)
CREATE USER myapp_user WITH ENCRYPTED PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE myapp_production TO myapp_user;
```

### Database Migrations

**Laravel**:
```bash
# Migrations run automatically during deployment
# Or run manually:
docker exec -it $(docker ps -q -f name=my_app | head -1) php artisan migrate --force
```

**Manual Migration**:
```bash
# Connect to database
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d myapp_production -f migration.sql
```

### Backup and Restore

**PostgreSQL Backup**:
```bash
# Backup via HAProxy
PGPASSWORD=2e7vBpaaVK4vTJzrKebC pg_dump -h 100.102.220.16 -p 5000 -U patroni_superuser myapp_production > backup.sql
```

**PostgreSQL Restore**:
```bash
# Restore via HAProxy
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser myapp_production < backup.sql
```

## Security Best Practices

### Environment Variables

- ✅ Mark sensitive values as "Secret"
- ✅ Use separate databases for production/staging
- ✅ Rotate database passwords regularly
- ❌ Never commit secrets to Git
- ❌ Never use default passwords

### Network Security

- ✅ Use HAProxy endpoints (not direct database IPs)
- ✅ Cloudflare WAF enabled on all domains
- ✅ Tailscale VPN for SSH access
- ❌ Never expose databases to public internet
- ❌ Never disable firewall rules

### Access Control

- ✅ Limit Dokploy dashboard access
- ✅ Use strong passwords
- ✅ Enable 2FA where possible
- ❌ Never share credentials
- ❌ Never use root user in applications

## Maintenance Operations

### Updating Dokploy

**WARNING**: Dashboard may be briefly unavailable during update. Applications continue running.

```bash
# SSH to manager node
ssh root@100.92.26.38

# Check current version
docker service inspect dokploy --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}'

# Update to latest
docker service update dokploy --image dokploy/dokploy:latest

# Monitor update
docker service ps dokploy
```

### Scaling Infrastructure

**Add New App Server**:
1. Provision new server with Docker and Tailscale
2. Join to Docker Swarm cluster
3. Deploy Traefik replica
4. Update Cloudflare DNS to include new server IP
5. Redeploy applications for redistribution

**Add New Database Node**:
1. Provision server with PostgreSQL and Patroni
2. Join to Patroni cluster
3. HAProxy automatically detects new node
4. Update Prometheus scrape targets

### Backup Procedures

**Dokploy Configuration Backup**:
```bash
# SSH to manager node
ssh root@100.92.26.38

# Backup database
docker exec dokploy-postgres pg_dump -U dokploy dokploy > dokploy_backup_$(date +%Y%m%d).sql

# Backup volumes
docker run --rm -v dokploy-letsencrypt:/data -v $(pwd):/backup alpine tar czf /backup/letsencrypt_backup.tar.gz /data
```

**Application Data Backup**:
- PostgreSQL: Automated via pgBackRest (see disaster recovery guide)
- Redis: Automated RDB snapshots
- Files: Use S3 or external storage

## Additional Resources

### Documentation

- [Dokploy Operations Guide](dokploy-operations.md) - Detailed operational procedures
- [Architecture Overview](architecture.md) - System architecture details
- [Disaster Recovery](disaster_recovery.md) - Backup and recovery procedures
- [Getting Started](getting-started.md) - Quick start guide
- [Monitoring](monitoring.md) - Monitoring and alerting setup

### External Resources

- [Dokploy Documentation](https://docs.dokploy.com)
- [Docker Swarm Documentation](https://docs.docker.com/engine/swarm/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

### Support

- **Infrastructure Dashboard**: http://100.102.220.16:8080
- **HAProxy Stats**: http://100.102.220.16:8404/stats
- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000