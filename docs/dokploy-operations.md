# Dokploy Operations Guide

> Operational procedures for managing applications on the Dokploy deployment platform.
>
> **Last Updated**: 2026-04-04

## Overview

Dokploy is the primary deployment platform for Quantyra infrastructure, replacing the legacy Flask dashboard and CapRover. It provides:

- **Docker Swarm Orchestration**: 2-node cluster (1 Manager + 1 Worker)
- **Traefik Load Balancing**: Automatic SSL with Let's Encrypt
- **Git Integration**: Deploy from GitHub with auto-deploy on push
- **Multi-Replica Support**: High availability across both app servers
- **Database Integration**: Connect to external Patroni cluster via HAProxy

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    DOKPLOY CLUSTER                           │
│                                                              │
│  re-db (Manager)              re-node-02 (Worker)           │
│  100.92.26.38                 100.89.130.19                 │
│  Public: 208.87.128.115       Public: 23.227.173.245        │
│                                                              │
│  • Dokploy Dashboard :3000    • App containers              │
│  • dokploy-postgres           • Traefik replica             │
│  • dokploy-redis              • Docker routing mesh          │
│  • Traefik replica                                          │
│                                                              │
│  Swarm Services:                                             │
│  - dokploy: 1/1 replicas (manager only)                     │
│  - dokploy-traefik: 2/2 replicas (HA)                       │
│  - dokploy-postgres: 1/1 replicas                           │
│  - dokploy-redis: 1/1 replicas                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Access

### Dokploy Dashboard

- **URL**: https://deploy.quantyralabs.cc
- **Location**: re-db only (not HA)
- **Purpose**: Application and domain management
- **Access**: Tailscale network or public URL

### SSH Access to App Servers

```bash
# Manager node
ssh root@100.92.26.38

# Worker node
ssh root@100.89.130.19
```

## Deploying Applications

### Method 1: Dokploy Dashboard (Recommended)

1. **Access Dashboard**: https://deploy.quantyralabs.cc

2. **Create Application**:
   - Click **Applications** → **Create Application**
   - Fill in application details:
     - **Name**: my-app
     - **Description**: Application description
     - **Provider**: GitHub
     - **Repository**: https://github.com/user/my-app
     - **Branch**: main

3. **Configure Build Settings**:
   - **Build Type**: Dockerfile or Nixpacks
   - **Port**: 0 (auto-detect from Dockerfile EXPOSE)
   - **Dockerfile Path**: ./Dockerfile (default)

4. **Set Replicas**:
   - **Replicas**: 2 (recommended for HA)
   - Distributed across both app servers automatically

5. **Add Domains**:
   - Production: myapp.example.com
   - Staging: staging.myapp.example.com (optional)

6. **Configure Environment Variables**:
   - Add secrets and configuration
   - See Environment Variables section below

7. **Deploy**:
   - Click **Deploy** button
   - Monitor build and deployment logs
   - Verify health checks pass

### Method 2: Git Webhook (Auto-Deploy)

Dokploy automatically deploys when you push to configured branches:

1. **Configure Webhook**:
   - Dokploy creates webhook automatically
   - URL: `https://deploy.quantyralabs.cc/api/deploy/{token}`

2. **Add Webhook to GitHub**:
   - Go to repository Settings → Webhooks
   - Add webhook with Dokploy URL
   - Content type: application/json
   - Events: Just the push event

3. **Push to Deploy**:
   ```bash
   git push origin main  # Triggers production deployment
   git push origin staging  # Triggers staging deployment
   ```

### Method 3: CLI Deployment

For advanced use cases or automation:

```bash
# SSH to manager node
ssh root@100.92.26.38

# Find the service name
docker service ls | grep my-app

# Update service
docker service update my_app --image my-app:new-tag

# Scale replicas
docker service scale my_app=3
```

## Environment Variables

### Adding Environment Variables

1. **Via Dashboard**:
   - Go to Applications → [App Name] → Environment
   - Click **Add Variable**
   - Enter key-value pairs
   - Click **Save**

2. **Bulk Import**:
   ```
   APP_ENV=production
   APP_KEY=base64:...
   DB_HOST=100.102.220.16
   DB_PORT=5000
   DB_DATABASE=myapp_production
   DB_USERNAME=patroni_superuser
   DB_PASSWORD=2e7vBpaaVK4vTJzrKebC
   ```

3. **Environment-Specific Variables**:
   - Use different variable sets for production/staging
   - Prefix with environment name if needed

### Required Variables for Laravel

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

### Database Connection Best Practices

**PostgreSQL**:
- **Write endpoint**: `100.102.220.16:5000` or `100.116.175.9:5000`
- **Read endpoint**: `100.102.220.16:5001` or `100.116.175.9:5001`
- Use HAProxy endpoints for automatic failover
- Connection pooling handled by PgBouncer

**Redis**:
- **Master**: `100.102.220.16:6379` or `100.116.175.9:6379`
- Use HAProxy endpoints for high availability
- Password required

## Configuring Domains

### Adding Domains

1. **Via Dashboard**:
   - Applications → [App Name] → Domains
   - Click **Add Domain**
   - Enter domain: myapp.example.com
   - **Port**: Leave empty (auto-detected)
   - **HTTPS**: Enable

2. **SSL Certificate**:
   - Automatically provisioned by Let's Encrypt
   - Uses DNS-01 challenge via Cloudflare API
   - Works with Cloudflare proxy enabled

3. **DNS Configuration**:
   - Point A records to BOTH app server IPs:
     ```
     myapp.example.com → 208.87.128.115 (re-db)
     myapp.example.com → 23.227.173.245 (re-node-02)
     ```
   - Enable Cloudflare proxy (orange cloud)

### Wildcard Domains

For multi-tenant applications:

1. **Add wildcard domain**: *.myapp.example.com
2. **SSL**: Wildcard certificate issued automatically
3. **DNS**: Single A record for `*.myapp.example.com`

### Domain Verification

```bash
# Check DNS resolution
dig myapp.example.com +short

# Expected: Both app server IPs
# 208.87.128.115
# 23.227.173.245

# Check SSL certificate
echo | openssl s_client -servername myapp.example.com -connect myapp.example.com:443 2>/dev/null | openssl x509 -noout -dates

# Test accessibility
curl -I https://myapp.example.com
```

## SSL Certificates

### Automatic SSL Provisioning

Dokploy uses Traefik with Let's Encrypt:

- **DNS-01 Challenge**: Via Cloudflare API
- **Wildcard Support**: *.example.com certificates
- **Auto-Renewal**: 30 days before expiry
- **Storage**: Docker volume `dokploy-letsencrypt`

### Certificate Requirements

1. **Cloudflare API Token**: Configured in Dokploy settings
2. **DNS Zone**: Domain must use Cloudflare DNS
3. **Proxy**: Can be enabled (orange cloud)

### Manual Certificate Check

```bash
# SSH to manager node
ssh root@100.92.26.38

# Check Traefik certificate storage
docker run --rm -v dokploy-letsencrypt:/data alpine ls -la /data

# Check certificate details
docker exec $(docker ps -q -f name=dokploy-traefik) cat /etc/traefik/acme/acme.json | jq '.letsencrypt.Certificates'
```

### Certificate Renewal

Automatic renewal is handled by Traefik. No manual intervention required.

## Viewing Logs

### Application Logs

1. **Via Dashboard**:
   - Applications → [App Name] → Logs
   - Real-time log streaming
   - Filter by time range

2. **Via CLI**:
   ```bash
   # SSH to manager node
   ssh root@100.92.26.38

   # View service logs
   docker service logs my_app --tail 100 --follow

   # View logs from specific replica
   docker service logs my_app.1.my_app_id --tail 100
   ```

### Traefik Logs

```bash
# Access logs
docker service logs dokploy-traefik --tail 100

# Error logs only
docker service logs dokploy-traefik 2>&1 | grep -i error
```

### Build Logs

1. **Via Dashboard**:
   - Applications → [App Name] → Deployments
   - Click on deployment ID
   - View build logs

2. **Via CLI**:
   ```bash
   # Find Dokploy container
   docker ps | grep dokploy

   # View Dokploy logs
   docker logs dokploy_dokploy --tail 200
   ```

## Scaling Applications

### Manual Scaling

1. **Via Dashboard**:
   - Applications → [App Name] → Settings
   - Change **Replicas** value
   - Click **Save & Redeploy**

2. **Via CLI**:
   ```bash
   # SSH to manager node
   ssh root@100.92.26.38

   # Scale to 3 replicas
   docker service scale my_app=3

   # Verify distribution
   docker service ps my_app
   ```

### Replica Distribution

With 2 replicas:
- 1 replica on re-db
- 1 replica on re-node-02

With 3+ replicas:
- Docker Swarm distributes across available nodes
- Load balanced via Traefik

### Resource Limits

Set resource constraints per replica:

1. **Via Dashboard**:
   - Applications → [App Name] → Settings
   - **Memory Limit**: 512MB (example)
   - **CPU Limit**: 0.5 (50% of 1 CPU)

2. **Via CLI**:
   ```bash
   docker service update my_app --limit-memory 512M --limit-cpu 0.5
   ```

## Health Checks

### Container Health Checks

Add to Dockerfile:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:80/health || exit 1
```

### Traefik Health Checks

Traefik automatically checks container health via Docker health checks.

### Application-Level Health Checks

For Laravel applications:

```php
// routes/web.php
Route::get('/health', function () {
    return response()->json(['status' => 'ok']);
});
```

### Monitoring Health Status

```bash
# Check service health
docker service inspect my_app --format '{{json .Spec.TaskTemplate.ContainerSpec.Healthcheck}}'

# Check individual container health
docker inspect $(docker ps -q -f name=my_app | head -1) --format '{{.State.Health.Status}}'
```

## Troubleshooting

### Common Issues

#### 1. Application Won't Start

**Symptoms**: Container exits immediately, restart loop

**Diagnosis**:
```bash
# Check service status
docker service ps my_app --no-trunc

# Check logs
docker service logs my_app --tail 100

# Check container exit code
docker inspect $(docker ps -aq -f name=my_app | head -1) --format '{{.State.ExitCode}}'
```

**Common Causes**:
- Missing environment variables
- Database connection failure
- Port misconfiguration
- Permission issues

**Solutions**:
- Verify all required environment variables are set
- Test database connectivity manually
- Check Dockerfile EXPOSE directive
- Review container logs for specific errors

#### 2. Redis Connection Issues

**Symptoms**: Application logs show Redis connection refused

**Root Cause**: Redis container missing password authentication in entrypoint

**Solution**:
```bash
# SSH to manager node
ssh root@100.92.26.38

# Check Redis container logs
docker service logs dokploy-redis

# Verify Redis requires password
docker exec $(docker ps -q -f name=dokploy-redis) redis-cli -a <password> PING
```

**Fix Applied**: Redis entrypoint script updated to include password in startup command

#### 3. Port Conflicts

**Symptoms**: nginx container fails to start, port 80/443 already in use

**Root Cause**: nginx listening on port 9000 instead of 80

**Diagnosis**:
```bash
# Check what's using port 80
ss -tlnp | grep :80

# Check nginx container config
docker exec $(docker ps -q -f name=my_app | head -1) cat /etc/nginx/nginx.conf
```

**Solution**:
- Verify Dockerfile EXPOSE 80
- Check nginx configuration inside container
- Ensure Traefik routes to correct port

#### 4. SSL Certificate Not Generated

**Symptoms**: HTTPS returns invalid certificate, Let's Encrypt errors

**Diagnosis**:
```bash
# Check Traefik logs
docker service logs dokploy-traefik 2>&1 | grep -i acme

# Check certificate storage
docker exec $(docker ps -q -f name=dokploy-traefik) ls -la /etc/traefik/acme/
```

**Common Causes**:
- Cloudflare API token not configured
- DNS not pointing to correct IPs
- Domain not added to Cloudflare

**Solutions**:
- Verify Cloudflare API token in Dokploy settings
- Check DNS A records point to app server IPs
- Confirm domain exists in Cloudflare zone

#### 5. Service Distribution Issues

**Symptoms**: All replicas on one node, none on other

**Diagnosis**:
```bash
# Check node availability
docker node ls

# Check service distribution
docker service ps my_app

# Check node resources
docker node inspect re-db --format '{{.Description.Resources}}'
docker node inspect re-node-02 --format '{{.Description.Resources}}'
```

**Solutions**:
- Ensure both nodes are in "Ready" state
- Check resource constraints aren't too high
- Verify placement constraints aren't limiting distribution

### Debugging Commands

```bash
# List all services
docker service ls

# Inspect service configuration
docker service inspect my_app --pretty

# View service environment variables
docker service inspect my_app --format '{{json .Spec.TaskTemplate.ContainerSpec.Env}}'

# Check service networks
docker service inspect my_app --format '{{json .Spec.TaskTemplate.Networks}}'

# View service logs with timestamps
docker service logs my_app --timestamps --tail 100

# Check container processes
docker top $(docker ps -q -f name=my_app | head -1)

# Execute command in container
docker exec -it $(docker ps -q -f name=my_app | head -1) /bin/sh

# Check container resource usage
docker stats $(docker ps -q -f name=my_app)
```

## Maintenance Operations

### Updating Applications

1. **Zero-Downtime Update**:
   ```bash
   # Push new code to Git
   git push origin main

   # Dokploy automatically:
   # 1. Builds new image
   # 2. Starts new containers
   # 3. Stops old containers gracefully
   # 4. Updates Traefik routing
   ```

2. **Manual Update**:
   ```bash
   # Via Dashboard: Applications → [App Name] → Deploy
   # Via CLI:
   docker service update my_app --image my-app:v2.0.0
   ```

### Rolling Back

1. **Via Dashboard**:
   - Applications → [App Name] → Deployments
   - Find previous successful deployment
   - Click **Rollback**

2. **Via CLI**:
   ```bash
   # List recent deployments
   docker service inspect my_app --format '{{json .Spec.RollbackConfig}}'

   # Rollback to previous version
   docker service rollback my_app
   ```

### Updating Dokploy

**WARNING**: Updates may cause brief downtime for the dashboard. Applications continue running.

```bash
# SSH to manager node
ssh root@100.92.26.38

# Check current version
docker service inspect dokploy --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}'

# Update to latest version
docker service update dokploy --image dokploy/dokploy:latest

# Monitor update
docker service ps dokploy
```

### Backup Dokploy Configuration

1. **Database Backup**:
   ```bash
   # Backup Dokploy PostgreSQL database
   docker exec dokploy-postgres pg_dump -U dokploy dokploy > dokploy_backup_$(date +%Y%m%d).sql
   ```

2. **Volume Backup**:
   ```bash
   # Backup volumes
   docker run --rm -v dokploy-letsencrypt:/data -v $(pwd):/backup alpine tar czf /backup/letsencrypt_backup.tar.gz /data
   ```

3. **Configuration Export**:
   - Via Dashboard: Settings → Export Configuration
   - Saves JSON file with all applications, domains, and settings

## Monitoring Integration

### Prometheus Metrics

Dokploy exposes metrics via Traefik:

- **Traefik Metrics**: `http://re-db:8080/metrics`
- **Docker Metrics**: `http://re-db:9323/metrics`

Prometheus scrape configuration:

```yaml
scrape_configs:
  - job_name: 'traefik'
    static_configs:
      - targets: ['100.92.26.38:8080']
        labels: {node: 're-db', role: 'app'}
      - targets: ['100.89.130.19:8080']
        labels: {node: 're-node-02', role: 'app'}

  - job_name: 'docker'
    static_configs:
      - targets: ['100.92.26.38:9323']
        labels: {node: 're-db', role: 'app'}
      - targets: ['100.89.130.19:9323']
        labels: {node: 're-node-02', role: 'app'}
```

### Grafana Dashboards

Pre-configured dashboards:

- **Traefik Dashboard**: Request rates, response times, SSL certificates
- **Docker Swarm Dashboard**: Container states, node health, service distribution

Access: http://100.102.220.16:3000

## Security Considerations

### Access Control

- **Dashboard**: Tailscale network or public access with authentication
- **API**: Token-based authentication
- **Applications**: Cloudflare WAF + DDoS protection

### Network Isolation

- **Dokploy Network**: Isolated Docker network for services
- **Database Access**: Via HAProxy only (Tailscale network)
- **Inter-Service Communication**: Docker internal network

### Secrets Management

- **Environment Variables**: Encrypted at rest in Dokploy database
- **Cloudflare API Token**: Stored securely in Dokploy settings
- **Database Credentials**: Use Patroni superuser or create app-specific users

## Support and Resources

### Documentation

- [Dokploy Official Docs](https://docs.dokploy.com)
- [Architecture Overview](architecture.md)
- [Deployment Guide](deployment.md)
- [Disaster Recovery](disaster_recovery.md)

### Troubleshooting Support

- **Logs**: Access via Dashboard or CLI
- **Metrics**: Prometheus and Grafana dashboards
- **Community**: Dokploy Discord and GitHub Discussions

### Emergency Contacts

- **Infrastructure Dashboard**: http://100.102.220.16:8080 (if available)
- **HAProxy Stats**: http://100.102.220.16:8404/stats
- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000