# Deployment Guide

> Complete guide for deploying applications and managing infrastructure on Quantyra.
>
> **Last Updated**: 2026-05-12

## Overview

Quantyra uses **Coolify v4** as the primary deployment platform, providing:

- **Git-Integrated Deployment**: Automatic builds and deployments from GitHub
- **Docker Compose Orchestration**: Container management across 2 app servers
- **Traefik Load Balancing**: Automatic SSL with Let's Encrypt DNS-01 challenges
- **Multi-Server Deploy**: Distribute app containers across both servers for HA
- **External Database Integration**: Connect to Patroni cluster via HAProxy

### Architecture

```
┌─────────────┐
│ Cloudflare  │  DNS + WAF + DDoS Protection
└──────┬──────┘
       │ Round-robin DNS (app server IPs)
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
         │ Docker      │                   │
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
         │   etcd      │
         └─────────────┘
```

**Key Points**:
- App traffic: Cloudflare → HAProxy (TCP passthrough) → Traefik → Docker containers
- Database traffic: HAProxy → Patroni (unchanged from previous architecture)
- SSL: Coolify's Traefik manages Let's Encrypt certificates automatically via DNS-01
- HA: Deploy to both app servers with rolling updates

## Prerequisites

### Required Access

- **Coolify Dashboard**: http://100.92.26.38:8000 (Tailscale only)
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

1. **Access Coolify Dashboard**: http://100.92.26.38:8000 (Tailscale only)

2. **Create Application**:
   - Click **Project** → **Create Application**
   - Connect your GitHub repository
   - Set build pack: Dockerfile
   - Configure Docker Build Stage Target if using multi-stage Dockerfile

3. **Add Environment Variables**:
   - Add database credentials
   - Add application secrets
   - See [Environment Variables](#environment-variables) section

4. **Add Domain**:
   - Add production domain: myapp.example.com
   - SSL certificate auto-provisioned via Let's Encrypt DNS-01
   - DNS auto-configured in Cloudflare

5. **Deploy**:
   - Click **Deploy** button
   - Monitor build and deployment progress
   - Verify application is accessible

Total time: ~5-10 minutes for first deployment.

## Deployment Methods

### Method 1: Coolify Dashboard (Recommended)

**Best for**: Initial deployment, configuration changes, manual deployments

1. **Navigate to Project**:
   - Access http://100.92.26.38:8000
   - Click your project

2. **Create New Application**:
   ```
   Name: my-app
   Provider: GitHub
   Repository: user/my-app
   Branch: main
   Build Pack: dockerfile
   Dockerfile Location: /Dockerfile.optimized
   Docker Build Stage Target: production (if multi-stage)
   ```

3. **Configure**:
   - **Environment Variables**: Add required secrets
   - **Domains**: Add production and staging domains
   - **Build Settings**: Configure Dockerfile path and build target

4. **Deploy**:
   - Click **Deploy** button
   - Watch build logs in real-time
   - Verify health checks pass

### Method 2: Git Push (Auto-Deploy)

**Best for**: Continuous deployment, frequent updates

1. **Configure Webhook**:
   - Coolify automatically creates webhook when you connect GitHub
   - Auto-deploy can be enabled per application

2. **Push to Deploy**:
   ```bash
   # Production deployment
   git push origin main
   ```

3. **Monitor Deployment**:
   - View progress in Coolify dashboard
   - Check deployment logs
   - Receive notifications on completion

**Note**: Branch-based deployment maps `main` → production by default.

### Method 3: CLI (Advanced)

**Best for**: Debugging, advanced operations, automation scripts

```bash
# SSH to manager node
ssh root@100.92.26.38

# List all containers
docker ps

# View logs for a container
docker logs <container_name> --tail 100 --follow

# Check container health
docker inspect <container_name> --format '{{.State.Health.Status}}'
```

## Application Configuration

### Dockerfile Requirements

**Laravel Example (Multi-Stage)**:
```dockerfile
# Builder stage
FROM ghcr.io/jloescher/php-base:8.5-alpine AS builder
WORKDIR /app
COPY . .
RUN composer install --no-dev --optimize-autoloader
RUN npm ci && npm run build

# Production stage (with HEALTHCHECK)
FROM ghcr.io/jloescher/php-base:8.5-alpine AS production
WORKDIR /app
COPY --from=builder /app .
HEALTHCHECK --interval=5s --timeout=3s --start-period=60s --retries=3 \
  CMD curl -f http://127.0.0.1/ || exit 1
EXPOSE 80
CMD ["/usr/local/bin/start-container.sh"]
```

**Important**: If using a multi-stage Dockerfile, set **Docker Build Stage Target** to the production stage name in Coolify.

### Port Configuration

| App Type | Internal Port | Coolify `ports_exposes` |
|----------|---------------|-------------------------|
| Laravel (nginx+php-fpm) | 80 | `80` |
| Next.js / Node.js | 3000 | `3000` |
| Python (Flask/Gunicorn) | 8080 | `8080` |

**Note**: The `ports_exposes` field must match the port the app listens on inside the container. Coolify uses this to configure Traefik's `loadbalancer.server.port`.

### Build-Time vs Runtime Environment Variables

Coolify injects env vars either as `--build-arg` (build-time) or at container runtime. Only mark vars as build-time if they are needed during `docker build` (e.g., `APP_ENV`, `VITE_*`). All other vars (DB credentials, API keys, secrets) should be runtime-only to avoid baking them into the image.

| Category | Build-Time | Runtime |
|----------|------------|---------|
| App config (APP_ENV, APP_KEY, APP_URL) | ✅ | - |
| Frontend build vars (VITE_*) | ✅ | - |
| Database credentials | - | ✅ |
| API keys / secrets | - | ✅ |
| Mail / OAuth config | - | ✅ |

## Environment Variables

### Adding Variables

1. **Via Coolify Dashboard**:
   - Project → [App Name] → Environment
   - Click **Add Variable**
   - Enter key-value pairs
   - Toggle "Build Time" only if needed during `docker build`

2. **Bulk Import**:
   ```
   APP_ENV=production
   APP_KEY=base64:...
   DB_HOST=100.102.220.16
   DB_PORT=5000
   ```

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

**Key Points**:
- Always use HAProxy endpoints (router IPs) for database connections
- HAProxy provides automatic failover
- Both routers (100.102.220.16 and 100.116.175.9) are valid endpoints
- Use port 5000 for writes, port 5001 for reads

## Domain Configuration

### Adding Domains

1. **Navigate to Domains**:
   - Project → [App Name] → Domains

2. **Add Production Domain**:
   ```
   Domain: https://myapp.example.com
   ```

3. **SSL**: Auto-provisioned by Coolify's Traefik via Let's Encrypt DNS-01 challenge

### DNS Configuration

Coolify automatically configures DNS via Cloudflare API.

**Manual Verification**:
```bash
# Check DNS resolution
dig myapp.example.com +short
# Expected: Both app server public IPs
```

### SSL Certificates

**Automatic Provisioning**:
- Let's Encrypt certificates via Coolify's Traefik
- DNS-01 challenge via Cloudflare API (works behind Cloudflare proxy)
- Auto-renewal by Traefik

## Monitoring and Observability

### Application Logs

**Via Coolify Dashboard**:
- Project → [App Name] → Logs
- Real-time streaming

**Via CLI**:
```bash
ssh root@100.92.26.38
docker logs <container_name> --tail 100 --follow
```

### Health Checks

**Container Health**:
```bash
docker inspect <container_name> --format '{{.State.Health.Status}}'
```

**Application Health**:
```bash
curl -sI https://myapp.example.com
```

## Troubleshooting

### Build Fails with "context canceled"

See [docs/coolify_deployment_tuning.md](coolify_deployment_tuning.md) for detailed diagnosis.

1. Check `/etc/docker/daemon.json` has `max-concurrent-uploads: 1`
2. Prune build cache: `docker builder prune -f`
3. Check disk/memory: `df -h / && free -h`

### Health Check Fails

1. Verify `dockerfile_target_build` is set to the stage with `HEALTHCHECK`
2. Test inside container: `docker exec <container> curl -sI http://127.0.0.1:<port>`

### 502 Bad Gateway

1. Verify `ports_exposes` matches the container's listen port
2. Check Traefik labels: `docker inspect <container> --format '{{json .Config.Labels}}'`

### Database Connection Issues

1. Verify using HAProxy endpoint (100.102.220.16 or 100.116.175.9)
2. Check port is 5000/5001, not 5432
3. Test connectivity: `PGPASSWORD=xxx psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c "SELECT 1;"`

## Additional Resources

### Documentation

- [Coolify Deployment Tuning](coolify_deployment_tuning.md) - Build reliability fixes and Docker tuning
- [Architecture Overview](architecture.md) - System architecture details
- [Disaster Recovery](disaster_recovery.md) - Backup and recovery procedures
- [Getting Started](getting-started.md) - Quick start guide
- [Monitoring](monitoring.md) - Monitoring and alerting setup

### External Resources

- [Coolify Documentation](https://coolify.io/docs)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

### Support

- **Coolify Dashboard**: http://100.92.26.38:8000 (Tailscale only)
- **HAProxy Stats**: http://100.102.220.16:8404/stats
- **Prometheus**: http://100.102.220.16:9090
- **Grafana**: http://100.102.220.16:3000