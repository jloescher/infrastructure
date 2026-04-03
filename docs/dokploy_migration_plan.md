# CapRover to Dokploy Migration Plan (Option B)

## Executive Summary

Migrate from CapRover to Dokploy with Option B architecture where applications bypass HAProxy entirely, routing directly through Traefik on app servers. HAProxy is preserved only for database traffic (Patroni and Redis). This simplifies the architecture and eliminates the single point of failure in app routing.

**Migration Date:** 2026-04-03  
**Estimated Duration:** 1-1.5 hours  
**Downtime Risk:** Minimal (during low-traffic period)

**Status:** ✅ **ALL PHASES COMPLETE** (2026-04-03)

### Objectives

- Replace CapRover with Dokploy ✅
- Implement Option B: Apps route directly via Traefik (bypass HAProxy) ✅
- Maintain HA with both app servers ✅
- Preserve Patroni, Redis, HAProxy for databases ✅
- Zero impact on database backends ✅
- Configure Cloudflare DNS API for wildcard SSL ✅
- Verify complete traffic flow ✅

### Key Benefits

1. Modern web interface with active development
2. Better documentation and community support
3. Native Docker Swarm integration
4. **Simplified architecture** - apps don't route through HAProxy
5. **Automatic SSL via Let's Encrypt** - Traefik handles certificates
6. **Direct DNS routing** - Cloudflare points to app servers

---

## Architecture Overview

### Option B (NEW Architecture)

```
APP TRAFFIC:
═════════════
User Request
     ↓
Cloudflare (WAF/DDoS)
     ↓ (A records: re-db + re-node-02 public IPs)
     ├─ 208.87.128.115 (re-db)
     └─ 23.227.173.245 (re-node-02)
     ↓
Dokploy Traefik (ports 80 + 443)
     ↓ (Let's Encrypt SSL termination)
App Containers (distributed via Docker Swarm)
     ↓
PostgreSQL (via HAProxy:5000/5001)
Redis (via HAProxy:6379)

DATABASE TRAFFIC (Unchanged):
══════════════════════════════
Cloudflare
     ↓ (A records: router-01 + router-02 IPs)
HAProxy (router-01/02)
     ├─ Port 5000 → PostgreSQL Write (Patroni Leader)
     ├─ Port 5001 → PostgreSQL Read (Replicas)
     └─ Port 6379 → Redis Master
     ↓
Patroni Cluster / Redis Sentinel
```

### Current State (CapRover)

```
Cloudflare (DNS/WAF)
        ↓
HAProxy (router-01, router-02) - Port 443
        ↓
CapRover Traefik (re-db:80 only - SINGLE POINT OF FAILURE)
        ↓
App Containers (re-db only)
        ↓
PostgreSQL (via HAProxy:5000/5001)
Redis (via HAProxy:6379)
```

### Key Differences: Option B

| Component | Current (CapRover) | Option B (Dokploy) |
|-----------|-------------------|-------------------|
| **App DNS** | Points to routers | Points to app servers directly |
| **App SSL** | HAProxy manages certs | Traefik/Let's Encrypt manages certs |
| **App Routing** | HAProxy → Traefik | Cloudflare → Traefik directly |
| **HAProxy Role** | Apps + Databases | **Only databases** |
| **SSL Certificates** | Manual/DNS-01 in HAProxy | Automatic via Let's Encrypt |
| **Port 443** | HAProxy listens | Traefik listens on app servers |

### Server Inventory

| Server | Tailscale IP | Public IP | Role | Dokploy Role | Status |
|--------|--------------|-----------|------|--------------|--------|
| re-db | 100.92.26.38 | 208.87.128.115 | App Server | **Manager** | ✅ Active |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) | **Worker** | ✅ Active |
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy Primary | N/A | ✅ Database routing |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy Secondary | N/A | ✅ Database routing |
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master | N/A | ✅ Unchanged |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica | N/A | ✅ Unchanged |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd | N/A | ✅ Unchanged |

---

## Discoveries & Critical Fixes Applied (Phases 0-3)

### Critical Fix 1: Traefik File Provider Path Mismatch

**Problem:** Traefik routers were not loading, causing 404 errors on dashboard access.

**Root Cause Analysis:**
- `traefik.yml` specified file provider directory: `/etc/dokploy/traefik/dynamic`
- Docker service mount: `/etc/dokploy/traefik/dynamic` → `/etc/traefik/dynamic`
- Traefik was looking for configs in `/etc/dokploy/traefik/dynamic` but mount was at `/etc/traefik/dynamic`

**Original Configuration (WRONG):**
```yaml
# traefik.yml
providers:
  file:
    directory: /etc/dokploy/traefik/dynamic  # WRONG - doesn't match mount
    watch: true
```

**Fix Applied:**
```yaml
# traefik.yml
providers:
  file:
    directory: /etc/traefik/dynamic  # CORRECT - matches mount point
    watch: true
```

**Verification:**
```bash
# After fix
curl -I https://deploy.quantyralabs.cc
# HTTP/2 200 (routers now loading correctly)
```

**Impact:** Critical - Without this fix, all apps return 404 because Traefik cannot find dynamic router configs.

---

### Critical Fix 2: ACME Storage Path Mismatch

**Problem:** SSL certificates not generating, "unable to get ACME account" errors in Traefik logs.

**Root Cause Analysis:**
- `traefik.yml` specified ACME storage: `/etc/dokploy/traefik/dynamic/acme.json`
- Volume mount: `dokploy-letsencrypt` → `/etc/traefik/acme`
- Path mismatch: Traefik trying to write to `/etc/dokploy/traefik/dynamic/acme.json` but volume mounted at `/etc/traefik/acme`

**Original Configuration (WRONG):**
```yaml
# traefik.yml
certificatesResolvers:
  letsencrypt:
    acme:
      storage: /etc/dokploy/traefik/dynamic/acme.json  # WRONG
```

**Fix Applied:**
```yaml
# traefik.yml
certificatesResolvers:
  letsencrypt:
    acme:
      storage: /etc/traefik/acme/acme.json  # CORRECT - matches volume mount
```

**Verification:**
```bash
# After fix
ls -la /etc/traefik/acme/acme.json
# File exists with Let's Encrypt certificate data
```

**Impact:** Critical - Without this fix, SSL certificates cannot be generated, all HTTPS traffic fails.

---

### Critical Fix 3: Dokploy PostgreSQL Password Mismatch

**Problem:** Dokploy service failing with PostgreSQL authentication errors.

**Root Cause Analysis:**
- Multiple reinstall attempts created password mismatch
- Docker secret had one password, PostgreSQL database had different password
- Error: "password authentication failed for user dokploy"

**Fix Applied:**
```bash
# Reset PostgreSQL user password to match Docker secret
psql -U postgres -c "ALTER USER dokploy WITH PASSWORD '5DTiwcIUptDZ2jCygfPp776x8oSyWBu8';"

# Restart Dokploy service
docker service update dokploy --force
```

**Verification:**
```bash
# After fix
docker service ps dokploy
# 1/1 replicas running, container healthy
docker exec dokploy-postgres psql -U dokploy -d dokploy -c "SELECT 1;"
# Query successful
```

**Impact:** Critical - Dokploy dashboard and all application management fails without PostgreSQL connectivity.

---

### Additional Discoveries

1. **Swarm Advertise Address Auto-Detection Issue:**
   - Dokploy installer auto-detects Docker bridge IP (172.17.0.1) instead of Tailscale IP
   - Workers cannot join if advertise address is wrong
   - Manual override required: `docker swarm init --advertise-addr 100.92.26.38`

2. **Bind Mount Requirement for Swarm:**
   - Bind mounts in Swarm services require paths to exist on ALL nodes
   - Created `/etc/dokploy/traefik/` on re-node-02 before deploying Traefik
   - Synced configs from manager to worker nodes

3. **Traefik Standalone Container Blocking Ports:**
   - Initial Dokploy install creates standalone Traefik container
   - This blocks ports 80/443, preventing Swarm service deployment
   - Must remove standalone container before deploying as service

4. **Installer URL Correction:**
   - Correct URL: `https://dokploy.com/install.sh`
   - NOT `https://get.dokploy.com` (does not exist)

---

## Current Infrastructure State (Post-Migration)

### Dokploy Stack
- **Status:** ✅ Running
- **Dashboard:** https://deploy.quantyralabs.cc (HTTP 200)
- **Manager:** re-db (100.92.26.38) - Leader/Active
- **Worker:** re-node-02 (100.89.130.19) - Active
- **Services:**
  - dokploy: 1/1 replicas, healthy
  - dokploy-traefik: 2/2 replicas (HA on both app servers)
  - dokploy-postgres: 1/1 replicas
  - dokploy-redis: 1/1 replicas

### Traefik Configuration
- **SSL:** Let's Encrypt wildcard certificate (*.quantyralabs.cc)
- **Valid Until:** 2026-06-14
- **Challenge:** DNS-01 via Cloudflare
- **Ports:** 80/443 listening on both app servers

### HAProxy (Database Only)
- **Status:** ✅ Running
- **Scope:** PostgreSQL + Redis traffic only (app routing removed)
- **Endpoints:**
  - PostgreSQL Write: router-01:5000, router-02:5000
  - PostgreSQL Read: router-01:5001, router-02:5001
  - Redis: router-01:6379, router-02:6379

### Preserved Services (Unchanged)
- Patroni cluster: re-node-01/03/04 (3-node HA)
- Redis cluster: re-node-01 (master), re-node-03 (replica)
- Prometheus/Grafana/Alertmanager: router-01
- Infrastructure dashboard: router-01:8080

### DNS Configuration Summary

**App Domains:** Point to app servers (re-db + re-node-02 public IPs)
**Database Connections:** Use router IPs (Tailscale: 100.102.220.16, 100.116.175.9)

| Traffic Type | DNS Target | IPs Used |
|--------------|------------|----------|
| **Apps** | App servers | 208.87.128.115, 23.227.173.245 |
| **Database connections** | HAProxy routers | 100.102.220.16:5000/5001, 100.116.175.9:5000/5001 |
| **Redis connections** | HAProxy routers | 100.102.220.16:6379, 100.116.175.9:6379 |

---

## Phase 0: Clean Up Coolify Assets (5-10 min)

**Purpose:** Remove Coolify domain sync service and clean up HAProxy app routing before installing Dokploy.

**Target:** router-01 (100.102.220.16), router-02 (100.116.175.9)

### Step 0.1: Stop and Disable Coolify Sync Service

```bash
ssh root@100.102.220.16

# Stop and disable the timer
systemctl stop sync-coolify-domains.timer
systemctl disable sync-coolify-domains.timer
systemctl stop sync-coolify-domains.service

# Remove systemd unit files
rm -f /etc/systemd/system/sync-coolify-domains.service
rm -f /etc/systemd/system/sync-coolify-domains.timer
rm -f /etc/systemd/system/timers.target.wants/sync-coolify-domains.timer

# Reload systemd
systemctl daemon-reload

# Verify removed
systemctl list-units --all | grep coolify
# Expected: No output
```

### Step 0.2: Remove HAProxy App SSL Certificates

```bash
# Backup certs directory
cp -r /etc/haproxy/certs /etc/haproxy/certs.backup.$(date +%Y%m%d_%H%M%S)

# Remove app-specific SSL certs
rm -f /etc/haproxy/certs/jonathanloescher.com.pem
rm -f /etc/haproxy/certs/rentalfixer.app.pem
rm -f /etc/haproxy/certs/staging.jonathanloescher.com.pem
rm -f /etc/haproxy/certs/staging.rentalfixer.app.pem
rm -f /etc/haproxy/certs/hooks.quantyralabs.cc.pem

# Keep default.pem for HAProxy internal use
ls -la /etc/haproxy/certs/
# Expected: default.pem only (or empty directory)
```

### Step 0.3: Update HAProxy Config (Remove App Routing)

```bash
# Backup current config
cp /etc/haproxy/domains/web_https.cfg /etc/haproxy/domains/web_https.cfg.backup.$(date +%Y%m%d_%H%M%S)
cp /etc/haproxy/domains/web_backends.cfg /etc/haproxy/domains/web_backends.cfg.backup.$(date +%Y%m%d_%H%M%S)

# Remove coolify_backend, simplify HTTPS frontend
cat > /etc/haproxy/domains/web_backends.cfg << 'EOF'
# HAProxy Backends
# Note: Apps now route directly via Dokploy Traefik (Option B)
# HAProxy only handles: PostgreSQL, Redis, Stats

backend not_found_backend
    mode http
    http-request deny deny_status 404
EOF

cat > /etc/haproxy/domains/web_https.cfg << 'EOF'
# HTTPS Frontend - Minimal (apps bypass HAProxy)
# Apps route directly: Cloudflare → Traefik (re-db/re-node-02)

frontend web_https
    bind :443 ssl crt /etc/haproxy/certs/default.pem alpn h2,http/1.1
    mode http
    
    # Default to 404 (no apps routed through HAProxy)
    default_backend not_found_backend
EOF

# Validate config
haproxy -c -f /etc/haproxy/haproxy.cfg
# Expected: Configuration file is valid

# Reload HAProxy
systemctl reload haproxy
systemctl status haproxy
```

### Step 0.4: Apply to router-02

```bash
exit

ssh root@100.116.175.9

# Remove systemd services (if exist)
systemctl stop sync-coolify-domains.timer 2>/dev/null || true
systemctl disable sync-coolify-domains.timer 2>/dev/null || true
rm -f /etc/systemd/system/sync-coolify-domains.*
systemctl daemon-reload

# Copy updated HAProxy config from router-01
scp root@100.102.220.16:/etc/haproxy/domains/web_https.cfg /etc/haproxy/domains/
scp root@100.102.220.16:/etc/haproxy/domains/web_backends.cfg /etc/haproxy/domains/

# Remove app SSL certs
rm -f /etc/haproxy/certs/jonathanloescher.com.pem
rm -f /etc/haproxy/certs/rentalfixer.app.pem
rm -f /etc/haproxy/certs/staging.jonathanloescher.com.pem
rm -f /etc/haproxy/certs/staging.rentalfixer.app.pem

# Validate and reload
haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy

exit
```

### Step 0.5: Verify HAProxy Cleanup

```bash
ssh root@100.102.220.16

# Check no coolify services
systemctl list-units --all | grep coolify || echo "✓ Coolify services removed"

# Check minimal HAProxy config
cat /etc/haproxy/domains/web_backends.cfg
# Expected: Only not_found_backend

# Check certs
ls -la /etc/haproxy/certs/
# Expected: default.pem only

# Check HAProxy status
systemctl status haproxy | grep Active
# Expected: active (running)

exit
```

**Checkpoint:** ✓ Coolify sync removed, HAProxy cleaned up, app SSL certs removed, both routers updated.

---

## Phase 1: Uninstall CapRover (15-20 min)

**Target:** re-db (100.92.26.38)

### Step 1.1: Stop and Remove CapRover Services

```bash
# SSH into re-db
ssh root@100.92.26.38

# List all CapRover services
docker service ls

# Scale down all CapRover services
docker service scale captain-captain=0 captain-nginx=0 captain-certbot=0 captain-registry=0 2>/dev/null || true

# Wait for services to stop
sleep 10

# Remove all CapRover services
docker service rm captain-captain captain-nginx captain-certbot captain-registry

# Verify services are removed
docker service ls
```

### Step 1.2: Leave Docker Swarm

```bash
# Leave Swarm (force because this is the only node)
docker swarm leave --force

# Verify Swarm is inactive
docker info | grep Swarm
# Expected: Swarm: inactive
```

### Step 1.3: Clean Up Docker Resources

```bash
# Remove all containers
docker ps -aq | xargs -r docker rm -f

# Remove all volumes
docker volume prune -f

# Remove all networks (except default)
docker network prune -f

# Clean up Docker system
docker system prune -af --volumes
```

### Step 1.4: Remove CapRover Directories

```bash
# Remove /captain directory
rm -rf /captain

# Remove any CapRover config directories
rm -rf /etc/captain 2>/dev/null || true
rm -rf /var/log/captain 2>/dev/null || true

# Verify removal
ls -la /captain
# Expected: No such file or directory
```

### Step 1.5: Restart Docker

```bash
# Restart Docker to ensure clean state
systemctl restart docker

# Wait for Docker to start
sleep 5

# Verify Docker is running
systemctl status docker
docker info | head -20
```

### Step 1.6: Verify Clean State

```bash
# Check ports are free (80 and 443 for Dokploy)
ss -tulnp | grep -E ':80|:443|:3000'
# Expected: No output (ports are free)

# Check no CapRover containers
docker ps -a | grep captain
# Expected: No output

# Check Swarm is inactive
docker info | grep Swarm
# Expected: Swarm: inactive

exit
```

**Checkpoint:** ✓ CapRover completely removed, ports 80/443/3000 are free.

---

## Phase 2: Install Dokploy with Option B (20-30 min)

**CRITICAL:** Traefik needs ports 80 AND 443 for Let's Encrypt SSL certificates.

**Target:** re-db (manager), re-node-02 (worker)

### Step 2.1: Configure Firewall on re-db

```bash
# SSH into re-db
ssh root@100.92.26.38

# Allow HTTP, HTTPS, Dokploy dashboard
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw allow 3000/tcp

# Docker Swarm ports (for cluster communication)
ufw allow 2377/tcp
ufw allow 2377/udp
ufw allow 7946/tcp
ufw allow 7946/udp
ufw allow 4789/udp

# Reload UFW
ufw reload

# Verify rules
ufw status | grep -E '80|443|3000|2377|7946|4789'
```

### Step 2.2: Install Dokploy Manager

```bash
# Still on re-db

# Install Dokploy using official installer
curl -sSL https://get.dokploy.com | bash

# This will:
# 1. Initialize Docker Swarm with Tailscale IP
# 2. Create Dokploy network
# 3. Deploy Dokploy services
# 4. Deploy Traefik (initially as standalone)

# Wait for installation to complete (2-3 minutes)
echo "Waiting for Dokploy to start..."
sleep 30

# Check Dokploy services
docker service ls

# Expected services:
# dokploy
# dokploy-postgres
# dokploy-redis
# dokploy-traefik (or just traefik container)

# Check containers
docker ps | grep dokploy

# Check Traefik is listening on port 80
ss -tulnp | grep ':80'
```

### Step 2.3: Get Swarm Join Token

```bash
# Get worker join token
docker swarm join-token worker

# COPY THIS OUTPUT - you'll need it for re-node-02
# Example: docker swarm join --token SWMTKN-1-xxx 100.92.26.38:2377
```

### Step 2.4: Join re-node-02 as Worker

```bash
# Exit re-db
exit

# SSH into re-node-02
ssh root@100.89.130.19

# Configure firewall (ports 80 and 443 for Traefik)
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw allow 2377/tcp
ufw allow 2377/udp
ufw allow 7946/tcp
ufw allow 7946/udp
ufw allow 4789/udp
ufw reload

# Join the Swarm (use token from Step 2.3)
docker swarm join --token SWMTKN-1-xxx 100.92.26.38:2377

# Verify join
docker info | grep Swarm
# Expected: Swarm: active

exit
```

### Step 2.5: Verify Dokploy Cluster

```bash
# SSH back into re-db
ssh root@100.92.26.38

# Check Swarm nodes
docker node ls

# Expected output:
# ID                           HOSTNAME    STATUS  AVAILABILITY  MANAGER STATUS
# xxxxxxxxxxxxxxxxxxxxxxxx *   re-db       Ready   Active        Leader
# yyyyyyyyyyyyyyyyyyyyyyyy     re-node-02  Ready   Active

# Check all services are running
docker service ls

# Test Dokploy dashboard
curl -I http://localhost:3000
# Expected: HTTP/1.1 200 OK or 302 Found

exit
```

**Checkpoint:** ✓ Dokploy installed, both nodes in Swarm, dashboard accessible at http://100.92.26.38:3000

---

## Phase 3: Deploy Traefik with HTTPS Support (10-15 min)

**CRITICAL:** Default Dokploy Traefik may only run on manager node and may not have HTTPS enabled. We need to redeploy it as a Swarm service with ports 80 + 443 and Let's Encrypt support.

**Target:** re-db (Traefik HA setup)

### Step 3.1: Stop Standalone Traefik and Deploy as Swarm Service

```bash
# SSH into re-db
ssh root@100.92.26.38

# Check current Traefik deployment
docker service ls | grep traefik

# If Traefik is a standalone container (not a service), stop it
docker stop dokploy-traefik 2>/dev/null || true
docker rm dokploy-traefik 2>/dev/null || true

# If Traefik is already a service, remove it
docker service rm dokploy-traefik 2>/dev/null || true

# Wait for cleanup
sleep 5

# Deploy Traefik as Swarm service with 2 replicas AND HTTPS support
docker service create \
  --name dokploy-traefik \
  --replicas 2 \
  --network dokploy-network \
  --publish mode=host,published=80,target=80 \
  --publish mode=host,published=443,target=443 \
  --publish mode=host,published=443,target=443,protocol=udp \
  --mount type=bind,source=/etc/dokploy/traefik/traefik.yml,target=/etc/traefik/traefik.yml \
  --mount type=bind,source=/etc/dokploy/traefik/dynamic,target=/etc/traefik/dynamic \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock:ro \
  --mount type=volume,source=dokploy-letsencrypt,target=/etc/traefik/acme \
  traefik:v3.6.7

# Wait for replicas to start
sleep 15

# Verify Traefik replicas are distributed
docker service ps dokploy-traefik

# Expected: 2 tasks, one on re-db and one on re-node-02
```

### Step 3.2: Verify Traefik on Both Nodes

```bash
# Verify port 80 and 443 are listening on BOTH servers
ss -tulnp | grep -E ':80|:443'

# Expected: docker-proxy listening on both ports

# Check re-node-02 (from re-db)
ssh root@100.89.130.19 "ss -tulnp | grep -E ':80|:443'"

# Expected: docker-proxy listening on both ports

exit
```

### Step 3.3: Verify Traefik Configuration

```bash
# SSH into re-db
ssh root@100.92.26.38

# Check Traefik configuration file
cat /etc/dokploy/traefik/traefik.yml

# Verify Let's Encrypt is configured (look for certificatesResolver section)
# If not present, we'll configure it in the next phase via Dokploy dashboard

# Check Traefik is running
docker service ps dokploy-traefik --no-trunc

exit
```

**Checkpoint:** ✓ Traefik running on both app servers with ports 80 + 443 enabled.

---

## Phase 4 Completion Notes (Cloudflare DNS API)

**Date:** 2026-04-03  
**Status:** ✅ Complete

**Cloudflare DNS API Configuration:**
- Cloudflare API token configured in Dokploy dashboard
- DNS-01 challenge enabled for wildcard certificates
- Let's Encrypt wildcard certificate for `*.quantyralabs.cc` auto-renewed
- Works with Cloudflare proxy enabled (no need to disable)

**Verification:**
```bash
# Verify certificate
curl -I https://deploy.quantyralabs.cc
# HTTP/2 200 - SSL working

# Check certificate details
echo | openssl s_client -servername deploy.quantyralabs.cc -connect deploy.quantyralabs.cc:443 2>/dev/null | openssl x509 -noout -dates
```

---

## Key Discoveries & Best Practices

### Docker Swarm Configuration

**Discovery 1: Swarm Advertise Address**
- **Issue**: Dokploy installer auto-detects Docker bridge IP (172.17.0.1) instead of Tailscale IP
- **Solution**: Manually specify `--advertise-addr` with Tailscale IP
- **Command**: `docker swarm init --advertise-addr 100.92.26.38`
- **Impact**: Workers cannot join if advertise address is wrong

**Discovery 2: Two-Manager Quorum Issue**
- **Issue**: 2 managers in Swarm causes split-brain scenarios
- **Solution**: Use 1 manager + workers for stability
- **Architecture**: re-db (Manager), re-node-02 (Worker)
- **Rationale**: Odd number of managers required for quorum (1, 3, 5, etc.)

**Discovery 3: Docker Routing Mesh (Ingress Mode)**
- **Issue**: Traefik replicas need to receive traffic on any node
- **Solution**: Use Docker routing mesh with `--publish 80:80` (without `mode=host`)
- **Benefit**: Any node can receive traffic, Docker routes to available Traefik replica
- **Critical for**: Cross-node communication in Swarm

### Traefik Configuration

**Discovery 4: File Provider Path Mismatch**
- **Issue**: Traefik routers not loading, causing 404 errors
- **Root Cause**: `traefik.yml` specified `/etc/dokploy/traefik/dynamic` but mount was at `/etc/traefik/dynamic`
- **Fix**: Update `traefik.yml` to use `/etc/traefik/dynamic`
- **Impact**: CRITICAL - Without this, all apps return 404

**Discovery 5: ACME Storage Path Mismatch**
- **Issue**: SSL certificates not generating, "unable to get ACME account" errors
- **Root Cause**: ACME storage path didn't match volume mount location
- **Fix**: Update `traefik.yml` to use `/etc/traefik/acme/acme.json`
- **Impact**: CRITICAL - Without this, SSL certificates cannot be generated

**Discovery 6: Bind Mount Requirement for Swarm**
- **Issue**: Bind mounts in Swarm require paths on ALL nodes
- **Solution**: Create `/etc/dokploy/traefik/` on re-node-02 before deploying
- **Command**: `ssh root@100.89.130.19 "mkdir -p /etc/dokploy/traefik/dynamic"`
- **Sync**: Copy configs from manager to worker nodes

### Database Configuration

**Discovery 7: Dokploy PostgreSQL Password Mismatch**
- **Issue**: Multiple reinstall attempts created password mismatch
- **Solution**: Reset PostgreSQL password to match Docker secret
- **Command**: `psql -U postgres -c "ALTER USER dokploy WITH PASSWORD '...';"`
- **Impact**: CRITICAL - Dokploy dashboard fails without PostgreSQL connectivity

**Discovery 8: Database Endpoints Unchanged**
- **Finding**: Database connections still use HAProxy router IPs (Tailscale)
- **Endpoints**: 
  - PostgreSQL Write: `100.102.220.16:5000`, `100.116.175.9:5000`
  - PostgreSQL Read: `100.102.220.16:5001`, `100.116.175.9:5001`
  - Redis: `100.102.220.16:6379`, `100.116.175.9:6379`
- **Benefit**: No changes needed to application database configurations

### HAProxy Architecture Change

**Discovery 9: HAProxy Now Database-Only**
- **Change**: HAProxy no longer routes application traffic
- **Scope**: PostgreSQL (5000/5001), Redis (6379) only
- **App Traffic**: Routes directly via Cloudflare → Traefik
- **SSL Certificates**: Removed from HAProxy (managed by Traefik/Let's Encrypt)
- **Cleanup**: Removed coolify_backend and app-specific ACLs

**Discovery 10: App DNS Configuration**
- **Change**: DNS A records point to app server IPs, not router IPs
- **IPs**: 
  - re-db: 208.87.128.115
  - re-node-02: 23.227.173.245
- **Cloudflare**: Load balances between both app server IPs
- **Benefit**: Direct routing, no HAProxy intermediary

### Dokploy HA Architecture

**Discovery 11: Management UI Not HA**
- **Finding**: Dokploy dashboard runs on manager node only (1 replica)
- **Reason**: Management tool, not customer-facing
- **Impact**: Dashboard unavailable if manager fails, but apps continue running
- **Workaround**: Can redeploy dashboard to another node if needed

**Discovery 12: Apps Can Be HA**
- **Finding**: Deploy apps with 2+ replicas for HA
- **Distribution**: Replicas spread across both app servers
- **Failover**: If one server fails, traffic routes to other
- **Configuration**: Set `replicas: 2` in Dokploy application settings

---

## Phase 4: Configure Cloudflare DNS API in Dokploy (5-10 min)

**Purpose:** Enable DNS-01 challenges for wildcard certificates with Cloudflare proxy enabled.

**Optional but Recommended:** Without this, Dokploy uses HTTP-01 challenge which requires temporarily disabling Cloudflare proxy.

### Step 4.1: Create Cloudflare API Token

**In Cloudflare Dashboard:**

1. Go to: https://dash.cloudflare.com/profile/api-tokens
2. Click "Create Token"
3. Use "Edit zone DNS" template or create custom:
   - **Permissions:**
     - Zone → DNS → Edit
     - Zone → Zone → Read
   - **Zone Resources:**
     - Include → All zones (or specific zones)
4. Click "Continue to summary" → "Create Token"
5. **COPY THE TOKEN** (you'll need it for Dokploy)

### Step 4.2: Configure in Dokploy Dashboard

**Access Dokploy Dashboard:** http://100.92.26.38:3000

1. **Navigate to Settings → Certificates**
2. **Add Certificate Provider:**
   - Provider: `Cloudflare`
   - Email: Your email address (for Let's Encrypt registration)
   - API Token: Paste the token from Step 4.1
   
3. **Save Configuration**

### Benefits of DNS-01 Challenge

| Feature | HTTP-01 | DNS-01 |
|---------|---------|--------|
| **Wildcard certs** | ❌ No | ✅ Yes (`*.domain.com`) |
| **Cloudflare proxy** | ❌ Must disable temporarily | ✅ Works with proxy ON |
| **Port 80 required** | ✅ Yes | ❌ No |
| **Internal domains** | ❌ No | ✅ Yes |
| **Automatic renewal** | ✅ Yes | ✅ Yes |

### Without Cloudflare API (HTTP-01 Alternative)

If you choose not to configure Cloudflare API:

1. **During certificate generation:**
   - Temporarily disable Cloudflare proxy (gray cloud)
   - Let's Encrypt validates via HTTP on port 80
   - Certificate is generated
   - Re-enable Cloudflare proxy (orange cloud)

2. **Limitations:**
   - No wildcard certificates
   - Must disable proxy during cert generation
   - More manual intervention

**Recommendation:** Configure Cloudflare DNS API for seamless certificate management.

---

## Phase 5: DNS Configuration for Apps (10-15 min)

**CRITICAL:** DNS records point to APP SERVERS (not routers) for Option B.

### Step 5.1: Configure Cloudflare DNS for App Domains

**In Cloudflare Dashboard:**

For each app domain (e.g., `your-app.com`):

```
Type: A
Name: your-app.com
Value: 208.87.128.115 (re-db public IP)
TTL: 300
Proxy: ON (orange cloud)

Type: A  
Name: your-app.com
Value: 23.227.173.245 (re-node-02 public IP)
TTL: 300
Proxy: ON (orange cloud)
```

**Result:** Cloudflare load balances between both app servers. If one fails, traffic routes to the other automatically.

### Step 5.2: Server Public IPs Reference

| Server | Public IP | DNS Usage |
|--------|-----------|-----------|
| re-db | 208.87.128.115 | **App DNS A records** |
| re-node-02 | 23.227.173.245 | **App DNS A records** |
| router-01 | 172.93.54.112 | Database HAProxy (internal) |
| router-02 | 23.29.118.6 | Database HAProxy (internal) |

### Step 5.3: Verify DNS Configuration

```bash
# Check DNS resolution
dig your-app.com +short

# Expected: Both app server IPs
# 208.87.128.115
# 23.227.173.245

# Check DNS with Cloudflare
dig your-app.com @1.1.1.1 +short

# Verify Cloudflare proxy is enabled
curl -I https://your-app.com
# Look for: cf-ray header (indicates Cloudflare proxy)
```

### Step 5.4: Database Connection IPs (Reminder)

**Database connections still use HAProxy router IPs (Tailscale):**

| Service | Endpoint | Connection String |
|---------|----------|-------------------|
| PostgreSQL Write | router-01:5000 | `100.102.220.16:5000` |
| PostgreSQL Write | router-02:5000 | `100.116.175.9:5000` |
| PostgreSQL Read | router-01:5001 | `100.102.220.16:5001` |
| PostgreSQL Read | router-02:5001 | `100.116.175.9:5001` |
| Redis | router-01:6379 | `100.102.220.16:6379` |
| Redis | router-02:6379 | `100.116.175.9:6379` |

**Note:** These are Tailscale IPs (internal network), NOT public IPs.

---

## Phase 6: Laravel Deployment in Dokploy (15-30 min)

**Dashboard:** http://100.92.26.38:3000

### Step 6.1: Create Database

```bash
# SSH into router-01 or use HAProxy endpoint from any server
ssh root@100.102.220.16

# Connect via HAProxy write endpoint
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser << EOF
CREATE DATABASE your_app_production;
CREATE DATABASE your_app_staging;
EOF

# Verify databases created
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c "\l"

exit
```

### Step 6.2: Configure Application in Dokploy Dashboard

**Access:** http://100.92.26.38:3000

1. **Applications → Create Application**
2. **Connect Git Repository:**
   - Repository URL: `https://github.com/your-org/your-app.git`
   - Branch: `main` (production)
   
3. **Build Settings:**
   - Build Type: `Dockerfile` or `Nixpacks`
   - **Port: `0`** (auto-detect from Dockerfile EXPOSE)
   
4. **Deployment Settings:**
   - **Replicas: `2`** (distributed across both nodes)
   - Enable autosave for auto-deploy on push
   
5. **Add Domains:**
   - Production: `your-app.com`
   - Production: `www.your-app.com`
   - Staging: `staging.your-app.com`

### Step 6.3: Understanding Port Configuration

| Dockerfile Setting | Dokploy Port | Result |
|--------------------|--------------|--------|
| `EXPOSE 80` | `0` (auto) | ✅ Auto-detects port 80 |
| `EXPOSE 80` | `80` (manual) | ✅ Explicitly set port 80 |
| No EXPOSE | `0` (auto) | ❌ Won't work |
| No EXPOSE | `80` (manual) | ✅ Works fine |

**Recommended Dockerfile for Laravel:**

```dockerfile
FROM webdevops/php-nginx:8.2

WORKDIR /app
COPY . .

RUN php artisan config:clear && \
    php artisan route:clear && \
    php artisan view:clear

EXPOSE 80  # Dokploy auto-detects this

CMD ["supervisord"]
```

**In Dokploy:** Set Port = `0` (auto-detect) OR `80` (explicit)

### Step 6.4: Production Environment Variables

**Copy to Dokploy → Application → Environment:**

```bash
# Application
APP_NAME=YourApp
APP_ENV=production
APP_KEY=base64:GENERATE_WITH_php_artisan_key:generate
APP_DEBUG=false
APP_URL=https://your-app.com

# Database (via HAProxy to Patroni - WRITE endpoint)
DB_CONNECTION=pgsql
DB_HOST=100.102.220.16
DB_PORT=5000
DB_DATABASE=your_app_production
DB_USERNAME=patroni_superuser
DB_PASSWORD=2e7vBpaaVK4vTJzrKebC

# Redis (via HAProxy)
REDIS_HOST=100.102.220.16
REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
REDIS_PORT=6379
REDIS_CLIENT=predis

# Queue & Cache
QUEUE_CONNECTION=redis
CACHE_DRIVER=redis
SESSION_DRIVER=redis

# Logging
LOG_CHANNEL=stack
LOG_LEVEL=error
```

### Step 6.5: Staging Environment Variables

**For staging deployment:**

```bash
# Application
APP_NAME=YourApp
APP_ENV=staging
APP_KEY=base64:SAME_KEY_AS_PRODUCTION
APP_DEBUG=true
APP_URL=https://staging.your-app.com

# Database (via HAProxy to Patroni - WRITE endpoint)
DB_CONNECTION=pgsql
DB_HOST=100.102.220.16
DB_PORT=5000
DB_DATABASE=your_app_staging
DB_USERNAME=patroni_superuser
DB_PASSWORD=2e7vBpaaVK4vTJzrKebC

# Redis (via HAProxy)
REDIS_HOST=100.102.220.16
REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
REDIS_PORT=6379
REDIS_CLIENT=predis

# Queue & Cache
QUEUE_CONNECTION=redis
CACHE_DRIVER=redis
SESSION_DRIVER=redis

# Logging
LOG_CHANNEL=stack
LOG_LEVEL=debug
```

### Step 6.6: Deploy and Verify

```bash
# Via Dokploy Dashboard, click "Deploy"

# Or verify via CLI
ssh root@100.92.26.38

# Check application service
docker service ls | grep your-app

# Check replicas distribution
docker service ps your-app-name

# Expected: 2 replicas, one on re-db and one on re-node-02

# Check logs
docker service logs your-app-name --tail 50

# Verify HTTPS certificate generated
curl -I https://your-app.com
# Look for: SSL certificate details

exit
```

### Step 6.7: Verify Application Accessibility

```bash
# Test production URL
curl -I https://your-app.com

# Expected:
# HTTP/2 200
# server: cloudflare (indicates Cloudflare proxy)
# cf-ray: xxx (Cloudflare Ray ID)

# Test both app servers are responding
curl -I https://your-app.com --resolve your-app.com:443:208.87.128.115
curl -I https://your-app.com --resolve your-app.com:443:23.227.173.245

# Both should return 200 OK
```

**Checkpoint:** ✓ Application deployed with 2 replicas, HTTPS certificate generated, accessible via Cloudflare.

---

## Bill of Materials

### Components Removed

| Component | Location | Status |
|-----------|----------|--------|
| CapRover (Captain) | re-db | Removed |
| CapRover Traefik | re-db | Removed |
| CapRover Networks | re-db | Removed |
| CapRover Volumes | re-db | Removed |
| /captain directory | re-db | Removed |
| Coolify sync service | router-01/02 | Removed |
| HAProxy app SSL certs | router-01/02 | Removed |
| coolify_backend (HAProxy) | router-01/02 | Removed |

### Components Installed

| Component | Location | Purpose |
|-----------|----------|---------|
| Dokploy Manager | re-db:3000 | PaaS Dashboard |
| Dokploy Worker | re-node-02 | Cluster node |
| Traefik (Swarm service) | re-db:80/443, re-node-02:80/443 | HA Load Balancer + SSL |
| Let's Encrypt | Traefik | Automatic SSL certificates |
| Docker Swarm | re-db (Manager), re-node-02 (Worker) | Container Orchestration |

### Preserved Services (HAProxy - Database Only)

| Service | Endpoint | Purpose |
|---------|----------|---------|
| HAProxy | router-01:5000 | PostgreSQL Write (Patroni Leader) |
| HAProxy | router-01:5001 | PostgreSQL Read (Replicas) |
| HAProxy | router-01:6379 | Redis Master |
| HAProxy | router-01:8404 | Stats Dashboard |
| HAProxy | router-02:5000 | PostgreSQL Write (Patroni Leader) |
| HAProxy | router-02:5001 | PostgreSQL Read (Replicas) |
| HAProxy | router-02:6379 | Redis Master |

### Preserved Services (Unchanged)

| Service | Endpoint | Purpose |
|---------|----------|---------|
| Patroni | re-node-01/03/04:5432 | PostgreSQL HA Cluster |
| Redis | re-node-01:6379, re-node-03:6379 | Cache/Session |
| Prometheus | router-01:9090 | Metrics Collection |
| Grafana | router-01:3000 | Dashboards |
| Alertmanager | router-01:9093 | Alert Routing |
| Loki | router-01:3100 | Log Aggregation |
| Dashboard | router-01:8080 | Infrastructure Management |
| Tailscale | All servers:100.64.x.x | VPN Network |

---

## Risks & Rollback Plan

### Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Coolify cleanup incomplete | Low | Medium | Verification commands provided |
| CapRover uninstall incomplete | Low | Medium | Verification commands provided |
| Dokploy install fails | Low | High | Rollback commands provided |
| Swarm init fails | Low | Medium | Reset Docker, retry |
| Traefik HA fails | Medium | Medium | Fallback to single replica |
| DNS configuration error | Medium | High | Test DNS resolution before deployment |
| SSL certificate generation fails | Medium | Medium | Use Cloudflare DNS API for DNS-01 |
| Database connection fails | Low | High | Use correct HAProxy endpoints |

### Rollback to CapRover

**Time Estimate:** 30-45 minutes

```bash
# STEP 1: Remove Dokploy from re-db
ssh root@100.92.26.38

# Stop all services
docker service rm $(docker service ls -q) 2>/dev/null || true

# Leave Swarm
docker swarm leave --force

# Remove Dokploy directories
rm -rf /etc/dokploy

# Clean Docker
docker system prune -af --volumes

# STEP 2: Reinstall CapRover
docker run -p 80:80 -p 443:443 -p 3000:3000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /captain:/captain \
  -e ACCEPTED_TERMS=true \
  caprover/caprover

# STEP 3: Restore HAProxy config (on BOTH routers)
ssh root@100.102.220.16
cp /etc/haproxy/domains/web_backends.cfg.backup.YYYYMMDD_HHMMSS /etc/haproxy/domains/web_backends.cfg
cp /etc/haproxy/domains/web_https.cfg.backup.YYYYMMDD_HHMMSS /etc/haproxy/domains/web_https.cfg
haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy
exit

ssh root@100.116.175.9
cp /etc/haproxy/domains/web_backends.cfg.backup.YYYYMMDD_HHMMSS /etc/haproxy/domains/web_backends.cfg
cp /etc/haproxy/domains/web_https.cfg.backup.YYYYMMDD_HHMMSS /etc/haproxy/domains/web_https.cfg
haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy
exit

# STEP 4: Restore DNS to point to routers
# In Cloudflare dashboard, update A records to point to router IPs
```

---

## Verification Commands

### Verify Phase 0: Coolify Cleanup

```bash
ssh root@100.102.220.16 << 'EOF'
echo "=== Coolify Services ==="
systemctl list-units --all | grep coolify || echo "✓ Removed"

echo "=== HAProxy App Certs ==="
ls -la /etc/haproxy/certs/ | grep -E 'jonathanloescher|rentalfixer|quantyralabs' || echo "✓ Removed"

echo "=== HAProxy Config ==="
cat /etc/haproxy/domains/web_backends.cfg | grep coolify || echo "✓ No coolify backend"

echo "=== HAProxy Status ==="
systemctl status haproxy | grep Active
EOF
```

### Verify Phase 1: CapRover Removed

```bash
ssh root@100.92.26.38 << 'EOF'
echo "=== CapRover Containers ==="
docker ps -a | grep captain || echo "✓ None found"

echo "=== /captain Directory ==="
ls /captain 2>/dev/null || echo "✓ Removed"

echo "=== Swarm Status ==="
docker info | grep Swarm

echo "=== Port Availability ==="
ss -tulnp | grep -E ':80|:443|:3000' || echo "✓ Ports free"
EOF
```

### Verify Phase 2: Dokploy Installed

```bash
ssh root@100.92.26.38 << 'EOF'
echo "=== Dokploy Services ==="
docker service ls

echo "=== Swarm Nodes ==="
docker node ls

echo "=== Dokploy Dashboard ==="
curl -I http://localhost:3000

echo "=== Traefik Status ==="
ss -tulnp | grep -E ':80|:443'
EOF
```

### Verify Phase 3: Traefik HA

```bash
echo "=== re-db ==="
ssh root@100.92.26.38 "ss -tulnp | grep -E ':80|:443'"

echo "=== re-node-02 ==="
ssh root@100.89.130.19 "ss -tulnp | grep -E ':80|:443'"

echo "=== Traefik Replicas ==="
ssh root@100.92.26.38 "docker service ps dokploy-traefik"
```

### Verify Phase 5: DNS Configuration

```bash
echo "=== DNS Resolution ==="
dig your-app.com +short

echo "=== Cloudflare Proxy Check ==="
curl -I https://your-app.com | grep -E 'cf-ray|server'

echo "=== Both App Servers Reachable ==="
curl -I https://your-app.com --resolve your-app.com:443:208.87.128.115 | head -5
curl -I https://your-app.com --resolve your-app.com:443:23.227.173.245 | head -5
```

### Verify Patroni and Redis (Unchanged)

```bash
echo "=== Patroni Cluster ==="
ssh root@100.114.117.46 'patronictl list'

echo "=== Redis Master ==="
ssh root@100.126.103.51 'redis-cli -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO replication'

echo "=== PostgreSQL via HAProxy ==="
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c "SELECT version();"

echo "=== Redis via HAProxy ==="
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk PING
```

---

## Runbooks

### RB-01: Coolify Cleanup (5-10 min)

```bash
# On router-01
ssh root@100.102.220.16

# Stop and remove services
systemctl stop sync-coolify-domains.timer
systemctl disable sync-coolify-domains.timer
rm -f /etc/systemd/system/sync-coolify-domains.*
systemctl daemon-reload

# Remove app certs
rm -f /etc/haproxy/certs/jonathanloescher.com.pem
rm -f /etc/haproxy/certs/rentalfixer.app.pem
rm -f /etc/haproxy/certs/staging.*.pem

# Update HAProxy config
cat > /etc/haproxy/domains/web_backends.cfg << 'EOF'
backend not_found_backend
    mode http
    http-request deny deny_status 404
EOF

cat > /etc/haproxy/domains/web_https.cfg << 'EOF'
frontend web_https
    bind :443 ssl crt /etc/haproxy/certs/default.pem
    mode http
    default_backend not_found_backend
EOF

haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy

# Apply to router-02
ssh root@100.116.175.9
scp root@100.102.220.16:/etc/haproxy/domains/web_*.cfg /etc/haproxy/domains/
haproxy -c -f /etc/haproxy/haproxy.cfg && systemctl reload haproxy
```

### RB-02: CapRover Uninstallation (10-15 min)

```bash
ssh root@100.92.26.38

# Drain and remove services
docker service scale captain-captain=0 captain-nginx=0 2>/dev/null || true
sleep 10
docker service rm captain-captain captain-nginx

# Leave Swarm
docker swarm leave --force

# Clean up
docker ps -aq | xargs -r docker rm -f
docker volume prune -f
docker network prune -f
docker system prune -af --volumes
rm -rf /captain

# Restart Docker
systemctl restart docker

# Verify
docker ps -a | grep captain || echo "✓ CapRover removed"
ss -tulnp | grep -E ':80|:443|:3000' || echo "✓ Ports free"
```

### RB-03: Dokploy Installation (15-20 min)

```bash
# On re-db
ssh root@100.92.26.38

# Firewall
ufw allow 80,443,3000,2377/tcp
ufw allow 2377,7946,4789/udp
ufw reload

# Install
curl -sSL https://get.dokploy.com | bash

# Wait and verify
sleep 30
docker service ls
docker node ls
curl -I http://localhost:3000

# Get join token
docker swarm join-token worker

# On re-node-02
ssh root@100.89.130.19
ufw allow 80,443,2377/tcp
ufw allow 2377,7946,4789/udp
ufw reload
docker swarm join --token SWMTKN-1-xxx 100.92.26.38:2377
```

### RB-04: Traefik HA Deployment (10 min)

```bash
ssh root@100.92.26.38

# Remove standalone Traefik
docker stop dokploy-traefik && docker rm dokploy-traefik
docker service rm dokploy-traefik 2>/dev/null || true
sleep 5

# Deploy as Swarm service with HTTPS
docker service create \
  --name dokploy-traefik \
  --replicas 2 \
  --network dokploy-network \
  --publish mode=host,published=80,target=80 \
  --publish mode=host,published=443,target=443 \
  --publish mode=host,published=443,target=443,protocol=udp \
  --mount type=bind,source=/etc/dokploy/traefik/traefik.yml,target=/etc/traefik/traefik.yml \
  --mount type=bind,source=/etc/dokploy/traefik/dynamic,target=/etc/traefik/dynamic \
  --mount type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock:ro \
  --mount type=volume,source=dokploy-letsencrypt,target=/etc/traefik/acme \
  traefik:v3.6.7

# Verify
docker service ps dokploy-traefik
ss -tulnp | grep -E ':80|:443'
ssh root@100.89.130.19 "ss -tulnp | grep -E ':80|:443'"
```

### RB-05: DNS Configuration (5-10 min)

```bash
# Verify current DNS
dig your-app.com +short

# In Cloudflare dashboard:
# Update A records to point to:
# 208.87.128.115 (re-db)
# 23.227.173.245 (re-node-02)

# Verify after update
dig your-app.com +short
# Expected: Both IPs listed

# Test with Cloudflare proxy
curl -I https://your-app.com | grep cf-ray
```

### RB-06: Laravel Deployment (15-30 min)

```bash
# Create database
PGPASSWORD=2e7vBpaaVK4vTJzrKebC psql -h 100.102.220.16 -p 5000 -U patroni_superuser << EOF
CREATE DATABASE your_app_production;
CREATE DATABASE your_app_staging;
EOF

# Via Dokploy Dashboard (http://100.92.26.38:3000):
# 1. Create Application
# 2. Connect Git repository
# 3. Set Port = 0
# 4. Set Replicas = 2
# 5. Add domains
# 6. Add environment variables
# 7. Deploy

# Verify
ssh root@100.92.26.38
docker service ls | grep your-app
docker service ps your-app-name
curl -I https://your-app.com
```

---

## Completion Checklist

### Phase 0: Coolify Cleanup ✅ COMPLETE

- [x] Stop sync-coolify-domains.timer
- [x] Remove systemd service/timer files
- [x] Remove app SSL certs from HAProxy
- [x] Update HAProxy config (remove app routing)
- [x] Apply changes to both routers (router-01, router-02)
- [x] Verify HAProxy minimal config active

### Phase 1: CapRover Removal ✅ COMPLETE

- [x] Stop CapRover services
- [x] Leave Docker Swarm
- [x] Remove containers/volumes/networks
- [x] Remove /captain directory
- [x] Restart Docker
- [x] Verify ports 80/443/3000 are free

### Phase 2: Dokploy Installation ✅ COMPLETE

- [x] Configure UFW on re-db
- [x] Install Dokploy on re-db
- [x] Fix PostgreSQL password mismatch
- [x] Get Swarm join token
- [x] Configure UFW on re-node-02
- [x] Join re-node-02 to Swarm
- [x] Verify both nodes in Swarm
- [x] Verify dashboard at http://100.92.26.38:3000

### Phase 3: Traefik HA Deployment ✅ COMPLETE

- [x] Remove standalone Traefik container
- [x] Create /etc/dokploy/traefik/ on re-node-02
- [x] Sync Traefik configs to worker node
- [x] Deploy Traefik as Swarm service (replicas=2)
- [x] Fix file provider path mismatch
- [x] Fix ACME storage path mismatch
- [x] Enable ports 80 AND 443
- [x] Mount Let's Encrypt volume
- [x] Verify Traefik on both app servers
- [x] Verify ports listening on both nodes
- [x] Verify SSL certificate generated

### Phase 4: Cloudflare DNS API ✅ COMPLETE

- [x] Create Cloudflare API token
- [x] Configure in Dokploy dashboard
- [x] Test certificate generation
- [x] Verify wildcard certificate for *.quantyralabs.cc
- [x] Confirm DNS-01 challenge works with Cloudflare proxy enabled

### Phase 5: DNS Configuration ✅ COMPLETE

- [x] Update Cloudflare DNS A records
- [x] Point to re-db public IP (208.87.128.115)
- [x] Point to re-node-02 public IP (23.227.173.245)
- [x] Enable Cloudflare proxy (orange cloud)
- [x] Verify DNS resolution
- [x] Test failover between app servers

### Phase 6: Application Deployment ✅ COMPLETE

- [x] Create databases in Patroni
- [x] Create application in Dokploy
- [x] Connect Git repository
- [x] Set Port = 0 (auto-detect)
- [x] Set Replicas = 2
- [x] Add domains (production + staging)
- [x] Add environment variables
- [x] Deploy application
- [x] Verify HTTPS certificate generated
- [x] Verify 2 replicas distributed
- [x] Test application URL
- [x] Verify cross-node routing works

### Post-Migration ✅ COMPLETE

- [x] Test application functionality
- [x] Verify Cloudflare load balancing
- [x] Monitor logs for errors
- [x] Test failover (stop one replica)
- [x] Update documentation
- [x] Verify HAProxy database-only routing
- [x] Confirm database endpoints unchanged
- [x] Document key discoveries

---

## Next Steps

1. **Configure GitHub Integration**
   - Connect repositories to Dokploy
   - Enable auto-deploy on push
   - Set up branch-based deployments (main→prod, staging→staging)

2. **Set Up Monitoring Integration**
   - Add Dokploy metrics to Prometheus
   - Configure alerts for service failures
   - Monitor Traefik certificate expiry

3. **Configure Backups**
   - Database backups via Dokploy or existing scripts
   - Application backup to external storage
   - Dokploy configuration backup

4. **Team Training**
   - Document deployment workflow
   - Create team access accounts
   - Document DNS configuration process

5. **Optimize Cloudflare Settings**
   - Configure page rules for staging
   - Set up WAF rules for app domains
   - Enable performance optimizations

---

## Architecture Comparison

### Before (CapRover via HAProxy)

```
┌─────────────┐
│  Cloudflare │
└──────┬──────┘
       │
       ├──────────────┬──────────────┐
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
│  router-01  │ │ router-02 │ │  HAProxy  │
│  HAProxy    │ │  HAProxy  │ │  Stats    │
└──────┬──────┘ └─────┬─────┘ │  8404     │
       │              │       └───────────┘
       │              │
       └──────────────┼──────────────┐
                      │              │
               ┌──────▼──────┐ ┌─────▼─────┐
               │   re-db     │ │  Patroni  │
               │  CapRover   │ │  Redis    │
               │  Traefik    │ │           │
               └──────┬──────┘ └───────────┘
                      │
                      │
               ┌──────▼──────┐
               │  App Containers │
               │  (re-db only)   │
               └─────────────┘
```

**Issues:**
- Single point of failure (CapRover on re-db only)
- Apps route through HAProxy unnecessarily
- Manual SSL certificate management
- No automatic load balancing between app servers

### After (Dokploy Option B)

```
┌─────────────┐
│  Cloudflare │
└──────┬──────┘
       │
       ├──────────────┬──────────────┐
       │ (App DNS)    │ (DB Internal)│
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
│   re-db     │ │ re-node-02│ │  HAProxy  │
│  Dokploy    │ │  Dokploy  │ │  Stats    │
│  Traefik    │ │  Traefik  │ │  8404     │
│  80/443     │ │  80/443   │ └───────────┘
└──────┬──────┘ └─────┬─────┘
       │              │
       │              │
       └──────────────┼──────────────┐
                      │              │
               ┌──────▼──────┐ ┌─────▼─────┐
               │ App Containers │ │  Patroni  │
               │  (distributed) │ │  Redis    │
               │                │ │           │
               └───────────────┘ └───────────┘
                      │
                      │ (via HAProxy)
                      │
               ┌──────▼──────┐ ┌─────▼─────┐
               │  router-01  │ │ router-02 │
               │  HAProxy    │ │  HAProxy  │
               │  :5000/5001 │ │  :5000/5001│
               │  :6379      │ │  :6379    │
               └─────────────┘ └───────────┘
```

**Benefits:**
- ✅ High availability (both app servers)
- ✅ Automatic SSL via Let's Encrypt
- ✅ Simplified architecture (apps bypass HAProxy)
- ✅ Direct DNS routing to app servers
- ✅ Cloudflare load balancing between app servers
- ✅ HAProxy dedicated to databases only

---

**Document Version:** 5.0  
**Last Updated:** 2026-04-03  
**Author:** Infrastructure Team  
**Status:** ✅ **ALL PHASES COMPLETE** (2026-04-03 15:25 UTC)

**Key Achievements:**
- CapRover successfully removed from re-db
- Dokploy installed with 2-node Swarm cluster (re-db Manager, re-node-02 Worker)
- Traefik HA deployed with 2 replicas across both app servers
- SSL certificate generated (Let's Encrypt wildcard for *.quantyralabs.cc)
- All critical path mismatch bugs resolved
- Dashboard accessible at https://deploy.quantyralabs.cc
- Cloudflare DNS API configured for automatic wildcard certificates
- Complete traffic flow verified: Cloudflare → Traefik → App → Database
- HAProxy now dedicated to database traffic only (PostgreSQL 5000/5001, Redis 6379)

**Architecture Achieved:**
- Apps route directly via Cloudflare → Traefik (bypass HAProxy)
- HAProxy handles ONLY database connections (Option B architecture)
- 2-node Dokploy Swarm with 1 manager + 1 worker (stable quorum)
- Docker routing mesh enables cross-node Traefik communication
- All apps benefit from high availability across both app servers