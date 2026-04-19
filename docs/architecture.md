# Infrastructure Architecture

> Complete reference for the Quantyra infrastructure architecture, traffic flow, and load balancing.
>
> **UPDATED 2026-04-03:** Architecture changed to Option B (Dokploy) - Apps route directly via Traefik, HAProxy handles databases only.

## Overview

The infrastructure uses a multi-tier architecture with high availability at every layer:

**CHANGED (2026-04-03):** Application traffic now routes directly via Cloudflare → Traefik (bypassing HAProxy). HAProxy handles ONLY database traffic (PostgreSQL).

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TRAFFIC FLOW DIAGRAM                                │
│                        (Option B - Dokploy Architecture)                         │
└─────────────────────────────────────────────────────────────────────────────────┘

                                     USER
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CLOUDFLARE (Anycast Edge)                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │  • Global CDN with 300+ PoPs                                            │    │
│  │  • DDoS Protection & WAF                                                │    │
│  │  • SSL: Cloudflare Edge Certificate (wildcard *.domain.tld)             │    │
│  │  • DNS: Round-robin between APP SERVER IPs                              │    │
│  │  • HTTP Retry: If one app server fails, retries the other               │    │
│  │                                                                          │    │
│  │  CHANGED: DNS now points to APP SERVERS, not routers                    │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                              │                    │                              │
│                              │ 50%                │ 50%                          │
│                              ▼                    ▼                              │
│                    208.87.128.115          23.227.173.245                        │
│                        (re-db)              (re-node-02)                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                        │                              │
                        │ Encrypted                    │ Encrypted
                        │ (Cloudflare → Traefik)       │ (Cloudflare → Traefik)
                        ▼                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         APP SERVER LAYER (Dokploy)                              │
│                                                                                 │
│   ┌─────────────────────────────┐    ┌─────────────────────────────┐           │
│   │       APP SERVER 1          │    │       APP SERVER 2          │           │
│   │       re-db                 │    │       re-node-02            │           │
│   │    100.92.26.38             │    │    100.89.130.19            │           │
│   │    Public: 208.87.128.115   │    │    Public: 23.227.173.245   │           │
│   │                             │    │                             │           │
│   │  ┌───────────────────────┐  │    │  ┌───────────────────────┐  │           │
│   │  │ Dokploy Manager       │  │    │  │ Dokploy Worker        │  │           │
│   │  │ • Dashboard :3000     │  │    │  │ • Runs app containers │  │           │
│   │  │ • PostgreSQL    │  │    │  │ • Traefik replica     │  │           │
│   │  └───────────────────────┘  │    │  └───────────────────────┘  │           │
│   │                             │    │                             │           │
│   │  ┌───────────────────────┐  │    │  ┌───────────────────────┐  │           │
│   │  │ Traefik (Swarm)       │  │    │  │ Traefik (Swarm)       │  │           │
│   │  │ • Port 80, 443        │  │    │  │ • Port 80, 443        │  │           │
│   │  │ • SSL (Let's Encrypt) │  │    │  │ • SSL (Let's Encrypt) │  │           │
│   │  │ • Routes by Host hdr  │  │    │  │ • Routes by Host hdr  │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   │              │              │    │              │              │           │
│   │  ┌───────────▼───────────┐  │    │  ┌───────────▼───────────┐  │           │
│   │  │ Docker Containers     │  │    │  │ Docker Containers     │  │           │
│   │  │ • Laravel apps        │  │    │  │ • Laravel apps        │  │           │
│   │  │ • Node.js apps        │  │    │  │ • Node.js apps        │  │           │
│   │  │ • 2+ replicas (HA)    │  │    │  │ • 2+ replicas (HA)    │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   └──────────────┼──────────────┘    └──────────────┼──────────────┘           │
│                  │                                  │                           │
└──────────────────┼──────────────────────────────────┼───────────────────────────┘
                   │                                  │
                   └──────────────┬───────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         DATABASE LAYER (HAProxy → Patroni)                │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    HAProxy (Database Only)                              │   │
│   │                    router-01, router-02                                 │   │
│   │                                                                          │   │
│   │  CHANGED: HAProxy NO LONGER routes app traffic                          │   │
│   │  HAProxy handles ONLY: PostgreSQL                               │   │
│   │                                                                          │   │
│   │  • Port 5000: PostgreSQL Read/Write (leader)                            │   │
│   │  • Port 5001: PostgreSQL Read-only (replicas)                           │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                   │                                             │
│                                   ▼                                             │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    PostgreSQL / Patroni Cluster                         │   │
│   │                                                                          │   │
│   │   re-node-01 (100.126.103.51) ─┐                                       │   │
│   │   re-node-03 (100.114.117.46) ─┼─► HA via Patroni (leader election)    │   │
│   │   re-node-04 (100.115.75.119) ─┘                                       │   │
│   │                                                                          │   │
│   │   UNCHANGED: Patroni cluster configuration remains the same             │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Server Inventory

### App Servers (Dokploy Cluster)

**CHANGED (2026-04-03):** Now running Dokploy with Docker Swarm

| Name | Tailscale IP | Public IP | Location | Dokploy Role | Services |
|------|--------------|-----------|----------|--------------|----------|
| re-db | 100.92.26.38 | 208.87.128.115 | NYC | **Manager** | Dokploy Dashboard, Traefik, Docker containers |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | ATL | **Worker** | Traefik, Docker containers |

**Swarm Architecture:**
- 1 Manager + 1 Worker (stable quorum)
- Docker routing mesh for cross-node communication
- Traefik: 2 replicas (one per node)
- Apps: Can deploy 2+ replicas for HA

### Routers (HAProxy - Database Only)

**CHANGED (2026-04-03):** HAProxy now handles ONLY database traffic

| Name | Tailscale IP | Public IP | Location | Role |
|------|--------------|-----------|----------|------|
| router-01 | 100.102.220.16 | 172.93.54.112 | NYC | Database Load Balancer |
| router-02 | 100.116.175.9 | 23.29.118.6 | ATL | Database Load Balancer (Secondary) |

**HAProxy Scope:**
- PostgreSQL: Ports 5000 (RW), 5001 (RO)
- Stats: Port 8404
- **NO LONGER routes application traffic**

### Database Servers (Unchanged)

| Name | Tailscale IP | Role | Services |
|------|--------------|------|----------|
| re-node-01 | 100.126.103.51 | PostgreSQL | Patroni |
| re-node-03 | 100.114.117.46 | PostgreSQL Leader | Patroni |
| re-node-04 | 100.115.75.119 | PostgreSQL Replica | Patroni |

## Load Balancing Strategy

### CHANGED (2026-04-03): Option B Architecture

**Application Traffic:**
- Cloudflare DNS points to app server IPs (NOT router IPs)
- Cloudflare load balances between re-db and re-node-02
- Traefik on each app server handles SSL and routing
- Docker Swarm routing mesh enables cross-node communication

**Database Traffic (Unchanged):**
- HAProxy on routers proxies to Patroni
- Applications connect via HAProxy endpoints

### Layer 1: Cloudflare → App Servers (CHANGED)

**Method**: DNS Round-Robin with HTTP Retry

```
Client Request → Cloudflare DNS
                    ↓
         ┌───────────┴───────────┐
         ▼                       ▼
     App Server 1           App Server 2
    (208.87.128.115)       (23.227.173.245)
    (re-db)                 (re-node-02)
         │                       │
         │ (if fails)            │
         └───────────────────────┘
                    ↓
            Retry on other app server
```

**Behavior**:
- Cloudflare returns both app server IPs in random order
- Client connects to first IP
- If connection fails, Cloudflare HTTP retry attempts the other IP
- Traefik terminates SSL on each app server
- Docker routing mesh routes to available container

**Key Difference from Before**:
- **Before**: Cloudflare → Routers → App Servers
- **Now**: Cloudflare → App Servers (bypasses routers)

### Layer 2: Traefik → App Containers (NEW)

**Method**: Docker Swarm Routing Mesh

```
Traefik (Swarm Service)
         ↓
    Docker Routing Mesh
         ↓
    ┌────────────┐
    │ Container  │ ← Replica 1 (any node)
    │   #1       │
    └────────────┘
    ┌────────────┐
    │ Container  │ ← Replica 2 (any node)
    │   #2       │
    └────────────┘
```

**Behavior**:
- Traefik runs as Swarm service with 2 replicas
- Each replica listens on ports 80/443
- Docker routing mesh distributes traffic across replicas
- If one node fails, other replica continues serving
- Zero downtime during node failure

### Layer 3: HAProxy → Database Servers (Unchanged)

**Method**: HAProxy Round-Robin with Active Health Checks

**PostgreSQL**:
```
HAProxy Backend Configuration:
┌─────────────────────────────────────────┐
│  frontend pg_rw                          │
│    bind 100.102.220.16:5000             │
│    mode tcp                              │
│    default_backend pg_primary            │
│                                          │
│  backend pg_primary                       │
│    mode tcp                              │
│    option httpchk GET /primary           │
│    server node1 100.126.103.51:5432 check│
│    server node2 100.114.117.46:5432 check│
│    server node3 100.115.75.119:5432 check│
└─────────────────────────────────────────┘
```

**Behavior**:
- Port 5000: Routes to current Patroni leader
- Port 5001: Load balances across replicas
- Automatic failover when leader changes
- Health checks every 2 seconds

## SSL/TLS Architecture

**CHANGED (2026-04-03):** SSL termination moved from HAProxy to Traefik

### Certificate Chain (NEW Architecture)

```
Let's Encrypt (CA)
     │
     ├── *.quantyralabs.cc (Traefik on re-db/re-node-02)
     │   └── Wildcard certificate managed by Dokploy
     │   └── DNS-01 challenge via Cloudflare API
     │   └── Auto-renewal by Traefik
     │
     └── app-specific domains (Traefik on re-db/re-node-02)
         └── Per-domain certificates
         └── Auto-provisioned by Dokploy
```

### SSL Termination Points (CHANGED)

```
User ──HTTPS──► Cloudflare ──HTTPS──► Traefik ──HTTP──► App Container
       (Edge Cert)      (Origin Cert)    (Container)
```

**Certificate Types**:
1. **Cloudflare Edge Certificate** - Managed by Cloudflare
   - Wildcard certificate for *.domain.tld
   - Automatic renewal by Cloudflare
    
2. **Origin Certificate** - Let's Encrypt on Traefik
   - Wildcard certificates via DNS-01 challenge
   - Per-domain certificates auto-provisioned
   - Auto-renewal by Traefik

### Why No SSL Issues with Multiple App Servers

Each app server has Traefik with shared certificate storage:
- Certificates stored in Docker volume `dokploy-letsencrypt`
- Both Traefik replicas access same certificate store
- Let's Encrypt validates via DNS-01 (works behind Cloudflare proxy)
- No shared state required between app servers

### SSL Migration Notes

**Before (CapRover/HAProxy)**:
- HAProxy terminated SSL with per-domain certificates
- Certbot managed certificates via DNS-01 challenge
- Manual certificate provisioning per domain

**After (Dokploy/Traefik)**:
- Traefik terminates SSL with Let's Encrypt
- Automatic certificate provisioning via DNS-01
- Wildcard certificates supported
- Cloudflare API integration for DNS-01 challenge
- No manual certificate management required

## HAProxy Configuration

**CHANGED (2026-04-03):** HAProxy now handles DATABASE TRAFFIC ONLY

### Database-Only Architecture

HAProxy no longer routes application traffic. Applications route directly via Cloudflare → Traefik.

```
/etc/haproxy/
├── haproxy.cfg              # Main config (PostgreSQL, Redis, Stats)
└── domains/
    ├── web_http.cfg         # Minimal (returns 404 for all HTTP)
    ├── web_https.cfg        # Minimal (returns 404 for all HTTPS)
    └── web_backends.cfg     # not_found_backend only
```

**What Changed:**
- ❌ Removed: App routing ACLs and backends
- ❌ Removed: App SSL certificates from HAProxy
- ❌ Removed: coolify_backend, rentalfixer_backend, etc.
- ✅ Kept: PostgreSQL frontends (5000, 5001)
- ✅ Kept: Stats frontend (8404)

### Main Config (haproxy.cfg)

Handles infrastructure services only:

```haproxy
# Stats page - http://router:8404/stats
frontend stats
    bind *:8404
    mode http
    stats enable
    stats uri /stats
    stats auth admin:jFNeZ2bhfrTjTK7aKApD

# Prometheus metrics - http://router:8405/metrics
frontend haproxy_metrics
    bind :8405
    mode http
    http-request use-service prometheus-exporter if { path /metrics }

# PostgreSQL read/write
frontend pg_rw
    bind 100.102.220.16:5000
    mode tcp
    default_backend pg_primary

# PostgreSQL read-only
frontend pg_ro
    bind 100.102.220.16:5001
    mode tcp
    default_backend pg_replicas

```

### HTTP/HTTPS Frontends (Minimal - Returns 404)

```haproxy
# web_http.cfg - All HTTP requests get 404
frontend web_http
    bind :80
    mode http
    default_backend not_found_backend

# web_https.cfg - All HTTPS requests get 404
frontend web_https
    bind :443 ssl crt /etc/haproxy/certs/default.pem alpn h2,http/1.1
    mode http
    default_backend not_found_backend

# web_backends.cfg - Only not_found_backend
backend not_found_backend
    mode http
    http-request deny deny_status 404
```

**Note:** Apps no longer route through HAProxy. Use Traefik on app servers instead.

### Why This Change?

1. **Simplified Architecture**: Apps bypass HAProxy entirely
2. **Better Performance**: One less hop in the traffic path
3. **Automatic SSL**: Traefik handles Let's Encrypt automatically
4. **Cloudflare Load Balancing**: Direct to app servers
5. **Clear Separation**: HAProxy = Databases, Traefik = Apps

## Failover Scenarios

**CHANGED (2026-04-03):** Updated for Option B architecture

### Scenario 1: App Server Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | re-db goes down | - |
| 2 | Cloudflare sends request to re-db | Connection timeout/failure |
| 3 | Cloudflare HTTP retry to re-node-02 | Request succeeds |
| 4 | Traefik on re-node-02 routes to container | - |
| 5 | User sees response | Slight delay (1-2 seconds) |

**Result**: Zero downtime, slight latency increase on first failed request

**Note**: Apps should be deployed with 2+ replicas for full HA

### Scenario 2: Database Server Failure (Unchanged)

**PostgreSQL Primary Failure:**

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | PostgreSQL leader fails | - |
| 2 | Patroni detects failure | ~10 seconds |
| 3 | Patroni promotes new leader | ~5 seconds |
| 4 | HAProxy detects new leader | ~3 seconds |
| 5 | Applications reconnect | Automatic with connection pooling |

**Result**: ~15-20 seconds of write unavailability, reads continue

### Scenario 3: Router Failure (Database Access Only)

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | router-01 goes down | - |
| 2 | App tries to connect via router-01:5000 | Connection timeout |
| 3 | App retries via router-02:5000 | Connection succeeds |
| 4 | Database operation completes | Slight delay |

**Result**: Apps experience brief delay on database operations, no data loss

**Note**: Applications should be configured with both router IPs for database connections

## Client IP Forwarding

### Header Chain

```
Client IP: 1.2.3.4

Cloudflare receives request
    ↓ Adds CF-Connecting-IP: 1.2.3.4
    
HAProxy receives request
    ↓ Reads CF-Connecting-IP
    ↓ Sets X-Forwarded-For: 1.2.3.4
    ↓ Sets X-Real-IP: 1.2.3.4
    
Nginx receives request
    ↓ real_ip_header X-Forwarded-For
    ↓ real_ip_recursive on
    ↓ REMOTE_ADDR = 1.2.3.4
    
Application receives real client IP
```

### Nginx Configuration

```nginx
# /etc/nginx/nginx.conf or site config
set_real_ip_from 100.64.0.0/10;  # Tailscale CGNAT range
set_real_ip_from 10.0.0.0/8;     # Internal networks
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

### Laravel Application

```php
// app/Http/Middleware/TrustProxies.php
protected $proxies = '*';
protected $headers = Request::HEADER_X_FORWARDED_ALL;

// Usage
$ip = $request->ip(); // Returns real client IP
```

## Monitoring

### Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| HAProxy Stats | http://router:8404/stats | Load balancer dashboard |
| HAProxy Metrics | http://router:8405/metrics | Prometheus metrics |
| HAProxy Health | http://router:8405/health | Health check endpoint |
| Prometheus | http://100.102.220.16:9090 | Metrics collection |
| Grafana | http://100.102.220.16:3000 | Dashboards |
| Alertmanager | http://100.102.220.16:9093 | Alert management |
| Loki | http://100.102.220.16:3100 | Log aggregation |

### Centralized Logging

All servers send logs to Loki via Promtail:

```
┌─────────────────────────────────────────────────────────────────┐
│                     CENTRALIZED LOGGING                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                │
│  │ router   │     │   apps   │     │   dbs    │                │
│  │ -syslog  │     │ -syslog  │     │ -syslog  │                │
│  │ -auth    │     │ -auth    │     │ -auth    │                │
│  │ -haproxy │     │ -nginx   │     │ -postgres│                │
│  └────┬─────┘     │ -docker  │     │ -redis   │                │
│       │           └────┬─────┘     │ -patroni │                │
│       │                │           └────┬─────┘                │
│       │                │                │                       │
│       └────────────────┼────────────────┘                       │
│                        │                                        │
│                        ▼                                        │
│              ┌─────────────────┐                                │
│              │    Promtail     │                                │
│              │  (all servers)  │                                │
│              └────────┬────────┘                                │
│                       │                                         │
│                       ▼                                         │
│              ┌─────────────────┐                                │
│              │      Loki       │                                │
│              │   router-01     │                                │
│              │   port 3100     │                                │
│              └────────┬────────┘                                │
│                       │                                         │
│                       ▼                                         │
│              ┌─────────────────┐                                │
│              │     Grafana     │                                │
│              │   Explore view  │                                │
│              └─────────────────┘                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Log Retention:** 31 days

### Key Metrics

**HAProxy**:
- `haproxy_frontend_current_sessions` - Active connections
- `haproxy_backend_http_responses_total` - Response codes
- `haproxy_server_health_check_status` - Server health

**Application Servers**:
- `traefik_entrypoint_requests_total` - Traefik request volume
- `node_cpu_seconds_total` - CPU usage
- `node_memory_MemAvailable_bytes` - Available memory

## Network Topology

### Tailscale Network

All servers connected via Tailscale mesh VPN:

```
                    TAILNET: tailnet-name.ts.net
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────┴────┐          ┌────┴────┐          ┌────┴────┐
   │ Routers │          │   Apps  │          │   DBs   │
   └─────────┘          └─────────┘          └─────────┘
   router-01            re-db                re-node-01
   router-02            re-node-02           re-node-03
                                             re-node-04
```

**Benefits**:
- Encrypted traffic between all servers
- No need for VPN configuration
- Works behind NAT/firewalls
- Automatic key rotation

### Port Allocation

| Port Range | Purpose |
|------------|---------|
| 8100-8199 | Application ports (production) |
| 8200-8299 | Application ports (staging) |
| 5000 | PostgreSQL read/write |
| 5001 | PostgreSQL read-only |
| 8404 | HAProxy stats |
| 8405 | HAProxy metrics |
| 9090 | Prometheus |
| 9093 | Alertmanager |
| 3000 | Grafana |
| 3100 | Loki |
| 8080 | Dashboard |
| 9080 | Promtail |

## Security

### Firewall Rules

Each server has:
- Tailscale interface fully trusted
- SSH (22) from Tailscale only
- Application ports from routers only
- Monitoring ports from Prometheus only

### Cloudflare WAF

5 security rules applied to all proxied domains:

| Priority | Rule | Action |
|----------|------|--------|
| 1 | Allow legitimate bots | Allow |
| 2 | Challenge suspicious | Managed Challenge |
| 3 | Challenge known attackers | Managed Challenge |
| 4 | Challenge rate limit | Managed Challenge |
| 5 | Block SQL injection | Block |

### SSL/TLS Settings

- TLS 1.2 minimum
- HSTS enabled
- OCSP stapling enabled
- Automatic HTTP→HTTPS redirect

## Dokploy Architecture (NEW 2026-04-03)

### Overview

Dokploy is the primary deployment platform, replacing CapRover and the legacy Flask dashboard. It runs on a Docker Swarm cluster with Traefik for load balancing and SSL termination.

### Docker Swarm Configuration

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DOKPLOY SWARM CLUSTER                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   re-db (Manager)                    re-node-02 (Worker)                │
│   100.92.26.38                       100.89.130.19                      │
│                                                                          │
│   • Dokploy Dashboard (:3000)        • App containers                   │
│   • dokploy-postgres                 • Traefik replica                  │
│   • dokploy-redis                                                       │
│   • Traefik replica                 (1 Manager + 1 Worker)              │
│                                                                          │
│   Swarm Services:                                                        │
│   - dokploy: 1/1 replicas (manager only)                                │
│   - dokploy-traefik: 2/2 replicas (HA)                                  │
│   - dokploy-postgres: 1/1 replicas                                      │
│   - dokploy-redis: 1/1 replicas                                         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **1 Manager + 1 Worker**: Avoids split-brain scenarios with 2 managers
- **Docker Routing Mesh**: Enables cross-node communication
- **Traefik HA**: 2 replicas (one per node) with shared certificate storage
- **Management UI NOT HA**: Dashboard runs on manager only (acceptable for admin tool)

### Traffic Flow Through Dokploy

```
Cloudflare DNS
      ↓ (A records: both app server IPs)
      ├─ 208.87.128.115 (re-db)
      └─ 23.227.173.245 (re-node-02)
      ↓
Traefik (Docker Swarm service, 2 replicas)
      ↓ (SSL termination, Let's Encrypt)
      ↓ (Routes by Host header)
      ↓
Docker Containers (distributed via Swarm)
       ↓ (Connect to databases)
       ↓
HAProxy (router-01/02) → Patroni
```

### Dokploy Key Features

1. **Automatic SSL**: Let's Encrypt with DNS-01 challenge via Cloudflare API
2. **Git Integration**: Deploy from GitHub/GitLab with auto-deploy on push
3. **Environment Variables**: Secrets management per application
4. **Domain Management**: Automatic DNS and SSL provisioning
5. **Database Connections**: Connect to external Patroni cluster or managed containers
6. **Monitoring**: Built-in metrics and logs
7. **Multi-Replica Apps**: Deploy with 2+ replicas for HA

### Application Deployment Model

| Setting | Value | Reason |
|---------|-------|--------|
| Port | 0 (auto) | Detect from Dockerfile EXPOSE |
| Replicas | 2+ | High availability across nodes |
| Domain | *.domain.tld | Wildcard or per-domain SSL |
| Database | External | Use Patroni cluster via HAProxy |

### Connecting to External Databases

Applications deployed via Dokploy should connect to the existing Patroni cluster:

```bash
# PostgreSQL connection
DB_HOST=100.102.220.16  # or 100.116.175.9
DB_PORT=5000            # RW endpoint
DB_PORT=5001            # RO endpoint
```

**Note**: Database endpoints are UNCHANGED from previous architecture.

### Dokploy Dashboard Access

```
URL: https://deploy.quantyralabs.cc
Location: re-db only (not HA)
Purpose: Application and domain management
```

### Comparison: Old vs New Deployment

| Aspect | Before (CapRover/Flask) | After (Dokploy) |
|--------|-------------------------|-----------------|
| App Routing | Cloudflare → HAProxy → Traefik | Cloudflare → Traefik |
| SSL Management | Certbot on HAProxy | Traefik Let's Encrypt |
| Deployment | Flask dashboard or CapRover UI | Dokploy UI |
| Database | External Patroni | External Patroni (unchanged) |
| HA Model | HAProxy round-robin | Docker Swarm + Traefik |
| SSL Certificates | Manual provisioning | Automatic DNS-01 |

---

## Disaster Recovery

### Backup Strategy

| Component | Backup Method | Frequency | Retention |
|-----------|---------------|-----------|-----------|
| PostgreSQL | pg_dump + S3 | Hourly | 30 days |
| App configs | Git repository | On change | Forever |
| SSL certs | certbot renew | Auto | 90 days |

### Recovery Procedures

See `/docs/disaster_recovery.md` for detailed procedures.
