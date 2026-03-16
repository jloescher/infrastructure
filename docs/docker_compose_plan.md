# Docker Compose Deployment Plan

## Overview

Goal: Deploy the infrastructure management dashboard as a Docker Compose package that can run on a Synology NAS or any machine connected to the Tailscale network.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE STACK                         │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │                    Traefik (Reverse Proxy)               │  │
│   │                    Port 80/443                           │  │
│   └───────────────────────────┬─────────────────────────────┘  │
│                               │                                 │
│         ┌─────────────────────┼─────────────────────┐          │
│         │                     │                     │          │
│         ▼                     ▼                     ▼          │
│   ┌───────────┐         ┌───────────┐         ┌───────────┐   │
│   │ Dashboard │         │ Prometheus│         │  Grafana  │   │
│   │  :8080    │         │  :9090    │         │  :3000    │   │
│   └─────┬─────┘         └─────┬─────┘         └─────┬─────┘   │
│         │                     │                     │          │
│         └─────────────────────┼─────────────────────┘          │
│                               │                                 │
│                        ┌──────┴──────┐                         │
│                        │   Volumes   │                         │
│                        │ (Persist)   │                         │
│                        └─────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                │ Tailscale Network
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│   Routers     │       │  App Servers  │       │   Databases   │
│ (HAProxy)     │       │ (nginx/PHP)   │       │ (Postgres/    │
│ 172.93.54.112 │       │ 100.92.26.38  │       │  Redis)       │
│ 23.29.118.6   │       │ 100.101.39.22 │       │               │
└───────────────┘       └───────────────┘       └───────────────┘
```

## Components

### 1. Dashboard Container

```yaml
dashboard:
  build: ./dashboard
  ports:
    - "8080:8080"
  environment:
    - PG_HOST=100.102.220.16
    - PG_PORT=5000
    - PG_USER=patroni_superuser
    - PG_PASSWORD=${PG_PASSWORD}
    - REDIS_HOST=100.126.103.51
    - REDIS_PASSWORD=${REDIS_PASSWORD}
    - PROMETHEUS_URL=http://prometheus:9090
    - CLOUDFLARE_API_TOKEN=${CF_API_TOKEN}
  volumes:
    - dashboard-config:/opt/dashboard/config
  networks:
    - infrastructure
  restart: unless-stopped
```

### 2. Prometheus Container

```yaml
prometheus:
  image: prom/prometheus:latest
  ports:
    - "9090:9090"
  volumes:
    - ./configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - ./configs/prometheus/alerts.yml:/etc/prometheus/rules/alerts.yml
    - prometheus-data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--web.enable-lifecycle'
  networks:
    - infrastructure
  restart: unless-stopped
```

### 3. Grafana Container

```yaml
grafana:
  image: grafana/grafana:latest
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    - GF_USERS_ALLOW_SIGN_UP=false
  volumes:
    - ./configs/grafana/provisioning:/etc/grafana/provisioning
    - grafana-data:/var/lib/grafana
  networks:
    - infrastructure
  restart: unless-stopped
```

### 4. Alertmanager Container

```yaml
alertmanager:
  image: prom/alertmanager:latest
  ports:
    - "9093:9093"
  volumes:
    - ./configs/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    - alertmanager-data:/alertmanager
  networks:
    - infrastructure
  restart: unless-stopped
```

### 5. Traefik (Optional - for SSL)

```yaml
traefik:
  image: traefik:v2.10
  ports:
    - "80:80"
    - "443:443"
    - "8081:8080"  # Dashboard
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ./traefik/traefik.yml:/etc/traefik/traefik.yml
    - traefik-certs:/letsencrypt
  networks:
    - infrastructure
  restart: unless-stopped
```

## Directory Structure

```
infrastructure/
├── docker-compose.yml
├── .env.example
├── dashboard/
│   ├── Dockerfile
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
├── configs/
│   ├── prometheus/
│   │   ├── prometheus.yml
│   │   └── alerts.yml
│   ├── grafana/
│   │   ├── grafana.ini
│   │   └── provisioning/
│   └── alertmanager.yml
├── traefik/
│   └── traefik.yml
└── scripts/
    ├── deploy-docker.sh
    └── sync-configs.sh
```

## Environment Variables

```bash
# .env (DO NOT COMMIT)
PG_PASSWORD=2e7vBpaaVK4vTJzrKebC
REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
CF_API_TOKEN=zf5ncwuOaaXz2IJ1BVBu8myf0HQt5IxkPje_Rm1V
GRAFANA_PASSWORD=your_grafana_password
DASHBOARD_USER=admin
DASHBOARD_PASS=DbAdmin2026!
```

## Network Configuration

### Option 1: Host Network (Simplest)

The container uses the host's network, so it can access Tailscale IPs directly:

```yaml
services:
  dashboard:
    build: ./dashboard
    network_mode: host
    # ...
```

**Pros:** No network configuration needed, direct access to Tailscale
**Cons:** Less isolation, port conflicts possible

### Option 2: Bridge Network + Tailscale Sidecar

Use a Tailscale sidecar container to provide network access:

```yaml
services:
  tailscale:
    image: tailscale/tailscale:latest
    hostname: infrastructure-dashboard
    environment:
      - TS_AUTHKEY=${TS_AUTHKEY}
    volumes:
      - tailscale-data:/var/lib/tailscale
    cap_add:
      - NET_ADMIN
      - SYS_MODULE
    networks:
      - infrastructure

  dashboard:
    build: ./dashboard
    network_mode: "service:tailscale"
    # ...
```

**Pros:** Full Tailscale integration, works from anywhere
**Cons:** More complex, requires Tailscale auth key

### Option 3: Bridge Network (Current Infrastructure)

Dashboard connects to existing infrastructure via Tailscale IPs:

```yaml
services:
  dashboard:
    build: ./dashboard
    networks:
      - infrastructure
    extra_hosts:
      - "router-01:100.102.220.16"
      - "router-02:100.116.175.9"
      - "re-db:100.92.26.38"
      - "re-node-02:100.101.39.22"
      - "re-node-01:100.126.103.51"
      - "re-node-03:100.114.117.46"
      - "re-node-04:100.115.75.119"
```

**Pros:** Simple, no Tailscale in container
**Cons:** Requires host to be on Tailscale network

## Deployment Options

### Synology NAS

1. **Install Docker** from Package Center
2. **Install Container Manager** (newer Synology DSM)
3. **Enable Tailscale** on NAS
4. **Deploy via SSH:**

```bash
# SSH into NAS
ssh admin@nas.local

# Clone repo
git clone https://github.com/user/infrastructure.git
cd infrastructure

# Create .env file
cp .env.example .env
nano .env

# Deploy
docker compose up -d
```

### Any Machine with Docker

```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Clone and deploy
git clone https://github.com/user/infrastructure.git
cd infrastructure
cp .env.example .env
# Edit .env with your credentials
docker compose up -d
```

## Dashboard Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create config directory
RUN mkdir -p /opt/dashboard/config

# Expose port
EXPOSE 8080

# Run
CMD ["python", "app.py"]
```

## Security Considerations

### Secrets Management

1. **Environment Variables** - Use `.env` file (not committed)
2. **Docker Secrets** - For Swarm mode
3. **External Secret Store** - HashiCorp Vault, etc.

### Network Security

1. **Tailscale Only** - Dashboard only accessible via Tailscale
2. **Traefik with Auth** - Add basic auth middleware
3. **Internal Only** - Don't expose to public internet

### Firewall Rules

```bash
# Only allow access from Tailscale network
iptables -A INPUT -p tcp --dport 8080 -s 100.64.0.0/10 -j ACCEPT
iptables -A INPUT -p tcp --dport 8080 -j DROP
```

## Implementation Steps

### Phase 1: Basic Dashboard (Week 1)

1. Create Dockerfile for dashboard
2. Create docker-compose.yml
3. Test locally with Docker
4. Document deployment process

### Phase 2: Full Stack (Week 2)

1. Add Prometheus container
2. Add Grafana container
3. Configure data sources
4. Import dashboards

### Phase 3: Production Ready (Week 3)

1. Add Traefik for SSL
2. Configure alerts
3. Add health checks
4. Create backup/restore scripts

### Phase 4: NAS Deployment (Week 4)

1. Deploy to Synology NAS
2. Configure auto-start
3. Set up monitoring
4. Document maintenance

## Files to Create

```
docker/
├── docker-compose.yml          # Main compose file
├── docker-compose.dev.yml      # Development overrides
├── docker-compose.prod.yml     # Production overrides
├── .env.example                # Environment template
├── dashboard/
│   └── Dockerfile              # Dashboard container
├── prometheus/
│   └── Dockerfile              # Custom Prometheus (if needed)
├── grafana/
│   └── Dockerfile              # Custom Grafana (if needed)
└── scripts/
    ├── deploy.sh               # Deploy script
    ├── backup.sh               # Backup volumes
    └── restore.sh              # Restore volumes
```

## Testing Plan

1. **Local Testing:**
   ```bash
   docker compose up -d
   curl http://localhost:8080
   ```

2. **Tailscale Access:**
   ```bash
   curl http://<tailscale-ip>:8080
   ```

3. **NAS Deployment:**
   - Deploy to NAS
   - Test from another machine on Tailscale

## Monitoring the Dashboard

The dashboard itself monitors the infrastructure. For monitoring the dashboard:

```yaml
# Add to prometheus.yml
- job_name: 'dashboard'
  static_configs:
    - targets: ['dashboard:8080']
  metrics_path: '/metrics'
```

## Backup Strategy

```bash
# Backup volumes
docker run --rm -v infrastructure_dashboard-config:/data -v $(pwd):/backup alpine tar czf /backup/dashboard-config.tar.gz /data

# Backup .env
cp .env .env.backup
```

## Future Enhancements

1. **Multi-architecture Support:**
   - Build for amd64 and arm64
   - Support for Raspberry Pi, ARM NAS

2. **Auto-update:**
   - Watchtower container for auto-updates
   - Blue-green deployment

3. **High Availability:**
   - Run on multiple machines
   - Load balance via Tailscale

4. **GitOps:**
   - Auto-deploy on git push
   - ArgoCD or Flux integration