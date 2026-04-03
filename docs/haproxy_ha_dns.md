# HAProxy High Availability - Database Load Balancing

> **CRITICAL UPDATE (2026-04-03):** HAProxy now handles **DATABASE TRAFFIC ONLY**
> 
> Applications route directly via Cloudflare → Traefik (Option B architecture)
> HAProxy NO LONGER routes application traffic

## Architecture Overview

**CHANGED (2026-04-03):** HAProxy is now dedicated to database load balancing. All application traffic routes directly via Cloudflare to Traefik on the app servers.

```
┌─────────────────────────────────────────────────────────────────┐
│                    HAProxy - DATABASE ONLY                       │
│                                                                  │
│   HAProxy handles ONLY:                                         │
│   • PostgreSQL (Ports 5000, 5001)                              │
│   • Redis (Port 6379)                                          │
│   • Stats Dashboard (Port 8404)                                │
│                                                                  │
│   HAProxy NO LONGER handles:                                    │
│   ✗ Application traffic (HTTP/HTTPS)                           │
│   ✗ App SSL certificates                                        │
│   ✗ Domain routing                                              │
│                                                                  │
│   Applications route via:                                        │
│   Cloudflare → Traefik (re-db/re-node-02) → App Containers     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Why This Change?**
- Simplified architecture: Apps bypass HAProxy entirely
- Better performance: One less hop in traffic path
- Automatic SSL: Traefik handles Let's Encrypt
- Clear separation: HAProxy = Databases, Traefik = Apps

## Current Setup

Two HAProxy routers in active-active configuration for **DATABASE LOAD BALANCING ONLY**:

| Router | Public IP | Tailscale IP | Role |
|--------|-----------|--------------|------|
| router-01 | 172.93.54.112 | 100.102.220.16 | Database Load Balancer |
| router-02 | 23.29.118.6 | 100.116.175.9 | Database Load Balancer (Secondary) |

**Note:** Application traffic no longer routes through HAProxy. Apps use Cloudflare → Traefik directly.

## Configuration Files

### Directory Structure

```
/etc/haproxy/
├── haproxy.cfg              # Main config (PostgreSQL, Redis, Stats)
└── domains/
    ├── web_http.cfg         # Minimal (returns 404 for all requests)
    ├── web_https.cfg        # Minimal (returns 404 for all requests)
    └── web_backends.cfg     # not_found_backend only
```

**What Changed (2026-04-03):**
- Removed app-specific SSL certificates from `/etc/haproxy/certs/`
- Removed app routing ACLs and backends
- Removed `registry.conf` (no longer needed)
- HTTP/HTTPS frontends return 404 (apps route via Traefik)

### Database Endpoints (UNCHANGED)

Applications continue to use these endpoints:

**PostgreSQL:**
- **Write (RW)**: `100.102.220.16:5000` or `100.116.175.9:5000`
- **Read (RO)**: `100.102.220.16:5001` or `100.116.175.9:5001`

**Redis:**
- **Write**: `100.102.220.16:6379` or `100.116.175.9:6379`

### Main Config (haproxy.cfg)

Handles database services only:

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

# Redis write
frontend redis_write
    bind 100.102.220.16:6379
    mode tcp
    default_backend redis_master

# Redis read
frontend redis_read
    bind 100.102.220.16:6380
    mode tcp
    default_backend redis_replicas

# PostgreSQL backends
backend pg_primary
    mode tcp
    option httpchk GET /primary
    http-check expect status 200
    server node1 100.126.103.51:5432 check check-ssl verify none
    server node2 100.114.117.46:5432 check check-ssl verify none
    server node3 100.115.75.119:5432 check check-ssl verify none

backend pg_replicas
    mode tcp
    balance roundrobin
    option httpchk GET /replica
    http-check expect status 200
    server node1 100.126.103.51:5432 check check-ssl verify none
    server node2 100.114.117.46:5432 check check-ssl verify none
    server node3 100.115.75.119:5432 check check-ssl verify none

# Redis backends
backend redis_master
    mode tcp
    option httpchk GET /master
    http-check expect status 200
    server node1 100.126.103.51:6379 check
    server node2 100.114.117.46:6379 check

backend redis_replicas
    mode tcp
    balance roundrobin
    option httpchk GET /replica
    http-check expect status 200
    server node1 100.126.103.51:6379 check
    server node2 100.114.117.46:6379 check
```

### HTTP/HTTPS Frontends (Minimal - Returns 404)

**web_http.cfg:**
```haproxy
frontend web_http
    bind :80
    mode http
    # All HTTP requests get 404 (apps route via Traefik)
    default_backend not_found_backend
```

**web_https.cfg:**
```haproxy
frontend web_https
    bind :443 ssl crt /etc/haproxy/certs/default.pem alpn h2,http/1.1
    mode http
    # All HTTPS requests get 404 (apps route via Traefik)
    default_backend not_found_backend
```

**web_backends.cfg:**
```haproxy
backend not_found_backend
    mode http
    http-request deny deny_status 404
```

**Note:** Applications no longer route through HAProxy. Use Dokploy/Traefik on app servers for application deployment.

## DNS Configuration

### CHANGED (2026-04-03): DNS Points to App Servers for Apps

**Application Domains:**
- DNS A records point to APP SERVER IPs (NOT router IPs)
- Cloudflare load balances between app servers
- Example: `myapp.domain.tld → 208.87.128.115, 23.227.173.245`

**Database Connections:**
- Applications connect via HAProxy router IPs (Tailscale)
- Use both router IPs for failover
- Example: `DB_HOST=100.102.220.16` with fallback to `100.116.175.9`

### For Database Access (PostgreSQL/Redis)

Applications should be configured with HAProxy router IPs:

**PostgreSQL Configuration:**
```bash
# Primary endpoint (write)
DB_HOST=100.102.220.16  # or 100.116.175.9 for failover
DB_PORT=5000            # Read/Write

# Replica endpoint (read)
DB_READ_HOST=100.102.220.16
DB_READ_PORT=5001       # Read-only
```

**Redis Configuration:**
```bash
REDIS_HOST=100.102.220.16  # or 100.116.175.9 for failover
REDIS_PORT=6379
```

**Connection String Examples:**
```bash
# PostgreSQL write
postgres://user:pass@100.102.220.16:5000/database

# PostgreSQL read
postgres://user:pass@100.102.220.16:5001/database

# Redis
redis://:password@100.102.220.16:6379/0
```

### For Application Domains (Cloudflare Proxied)

Applications are deployed via Dokploy and use direct app server IPs:

```
myapp.domain.tld       A    208.87.128.115  (re-db, Proxied)
myapp.domain.tld       A    23.227.173.245  (re-node-02, Proxied)
```

**Cloudflare handles:**
- DNS round-robin between app servers
- HTTP retry if one server fails
- SSL at edge (Cloudflare certificate)
- WAF and DDoS protection

**Traefik handles:**
- SSL termination (Let's Encrypt)
- Domain routing by Host header
- Container load balancing

## Health Check Endpoints

Both routers expose health endpoints:

```
http://172.93.54.112:8405/health
http://23.29.118.6:8405/health
```

For Prometheus metrics:
```
http://172.93.54.112:8405/metrics
http://23.29.118.6:8405/metrics
```

For HAProxy stats dashboard (auth: admin:jFNeZ2bhfrTjTK7aKApD):
```
http://172.93.54.112:8404/stats
http://23.29.118.6:8404/stats
```

## Load Balancing Behavior

### Application Traffic (CHANGED - No Longer Through HAProxy)

Applications route directly via Cloudflare → Traefik:

```
Client Request → Cloudflare
        ↓
    DNS Round-Robin (App Server IPs)
        ↓
    ┌────────────┐
    │ App Server │ ← Traefik handles routing
    │  #1 (re-db)│
    └────────────┘
    ┌────────────┐
    │ App Server │ ← Traefik handles routing
    │ #2 (ATL)   │
    └────────────┘
        ↓
    If one fails, Cloudflare HTTP retry
    attempts the other app server
```

**HAProxy is NOT involved in application traffic.**

### Database Traffic (Unchanged - Through HAProxy)

```
Application → HAProxy
        ↓
    Active Health Checks (every 2s)
        ↓
    ┌────────────┐
    │ PostgreSQL │ ← Primary/Replica detection
    │   Node     │
    └────────────┘
    ┌────────────┐
    │   Redis    │ ← Master/Replica detection
    │   Node     │
    └────────────┘
        ↓
    Routes to healthy database nodes
```

**Active health checks** - automatic failover when nodes fail.

## Failover Scenarios

### Router Failure (Database Access Only)

| Step | What Happens | Application Impact |
|------|--------------|-------------------|
| 1 | router-01 goes down | - |
| 2 | App tries DB connection via router-01 | Connection timeout |
| 3 | App retries via router-02 | Connection succeeds |
| 4 | Database operation completes | Slight delay |

**Result**: Brief delay on database operations, no data loss

**Best Practice**: Configure apps with both router IPs for automatic failover

### App Server Failure (Not Related to HAProxy)

Applications handle failover via Cloudflare/Traefik:

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | re-db goes down | - |
| 2 | Cloudflare sends request to re-db | Connection timeout |
| 3 | Cloudflare retries re-node-02 | Request succeeds |
| 4 | User sees response | Slight delay |

**HAProxy is not affected** - continues serving database traffic

### PostgreSQL Primary Failure

| Step | What Happens | Duration |
|------|--------------|----------|
| 1 | Leader fails | - |
| 2 | Patroni detects failure | ~10 seconds |
| 3 | New leader elected | ~5 seconds |
| 4 | HAProxy detects new leader | ~3 seconds |
| 5 | Total recovery | ~15-20 seconds |

### Redis Master Failure

| Step | What Happens | Duration |
|------|--------------|----------|
| 1 | Master fails | - |
| 2 | Sentinel detects | ~5 seconds |
| 3 | Replica promoted | ~2 seconds |
| 4 | HAProxy detects | ~3 seconds |
| 5 | Total recovery | ~10 seconds |

## Management Commands

### Reload Configuration

```bash
# Validate config first
haproxy -c -f /etc/haproxy/haproxy.cfg

# Reload
systemctl reload haproxy
```

### Show Stats

```bash
# Runtime stats
echo 'show stat' | socat stdio /run/haproxy/admin.sock

# Filter for database backends
echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep -E 'pg_|redis_'

# Show backend status
echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep -E 'pxname|pg_primary|pg_replicas|redis_master'
```

### Database Backend Management

```bash
# Check PostgreSQL backend health
echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep pg_

# Check Redis backend health
echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep redis

# Show all backends
echo 'show backend' | socat stdio /run/haproxy/admin.sock
```

### Connection Testing

```bash
# Test PostgreSQL write endpoint
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres -c "SELECT version();"

# Test PostgreSQL read endpoint
psql -h 100.102.220.16 -p 5001 -U patroni_superuser -d postgres -c "SELECT version();"

# Test Redis endpoint
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk PING
```

### Application Deployment (NOT Through HAProxy)

Applications are deployed via Dokploy:
- **Dashboard**: https://deploy.quantyralabs.cc
- **Documentation**: See `/docs/dokploy_migration_plan.md`
- **Traffic Flow**: Cloudflare → Traefik → App containers

## Monitoring

- **Prometheus**: http://100.102.220.16:9090
- **Alertmanager**: http://100.102.220.16:9093
- **Grafana**: http://100.102.220.16:3000

Alerts configured for:
- HAProxy down
- Backend server down
- High connection rates

## Testing Failover

```bash
# Stop HAProxy on router-01
ssh root@100.102.220.16 "systemctl stop haproxy"

# Verify traffic routes to router-02
curl -v https://rentalfixer.app

# Restart HAProxy
ssh root@100.102.220.16 "systemctl start haproxy"
```

## Troubleshooting

### Database Connection Issues

1. Check HAProxy is running: `systemctl status haproxy`
2. Check database backends: `echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep -E 'pg_|redis_'`
3. Test direct connection: `psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres`
4. Check Patroni cluster: `patronictl list`
5. Validate config: `haproxy -c -f /etc/haproxy/haproxy.cfg`

### Backend Health Issues

```bash
# Check backend status
echo 'show stat' | socat stdio /run/haproxy/admin.sock

# Look for:
# - status: UP or DOWN
# - lastchg: time since last status change
# - qlimit: queue limit (should be 0 for healthy backends)
```

### Router Failover Testing

```bash
# Test failover by stopping HAProxy on one router
ssh root@100.102.220.16 "systemctl stop haproxy"

# Verify apps can still connect via router-02
psql -h 100.116.175.9 -p 5000 -U patroni_superuser -d postgres -c "SELECT 1;"

# Restart HAProxy
ssh root@100.102.220.16 "systemctl start haproxy"
```

### Application 404 Errors

**IMPORTANT**: Applications NO LONGER route through HAProxy.

If applications return 404:
1. Check DNS points to app server IPs (NOT router IPs)
2. Verify Traefik is running on app servers
3. Check Dokploy dashboard: https://deploy.quantyralabs.cc
4. See Dokploy documentation for application troubleshooting

**HAProxy handles DATABASE traffic only.**