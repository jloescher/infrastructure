# HAProxy High Availability - DNS Round-Robin

> **Note**: Infrastructure is branded "quantyra" but public domains use xotec.io

## Architecture Overview

The infrastructure uses a **consolidated frontend architecture** where all domains share a single HAProxy frontend, rather than having separate frontends per domain.

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONSOLIDATED FRONTEND                        │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  web_https (single frontend, port 443)                  │  │
│   │                                                          │  │
│   │  Bind: :443 ssl                                          │  │
│   │    crt /etc/haproxy/certs/domain1.pem                    │  │
│   │    crt /etc/haproxy/certs/domain2.pem                    │  │
│   │    crt /etc/haproxy/certs/domain3.pem                    │  │
│   │                                                          │  │
│   │  ACLs:                                                   │  │
│   │    acl is_domain1 hdr(host) -i domain1.tld               │  │
│   │    acl is_domain2 hdr(host) -i domain2.tld               │  │
│   │                                                          │  │
│   │  Routes:                                                 │  │
│   │    use_backend app1_backend if is_domain1                │  │
│   │    use_backend app2_backend if is_domain2                │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Why Consolidated?**
- Multiple frontends on port 443 cause SNI routing issues
- Single frontend with multiple certificates works reliably
- HAProxy uses Host header for routing after SSL termination
- Simpler configuration management

## Current Setup

Two HAProxy routers in active-active configuration:

| Router | Public IP | Tailscale IP | Role |
|--------|-----------|--------------|------|
| router-01 | 172.93.54.112 | 100.102.220.16 | Primary |
| router-02 | 23.29.118.6 | 100.116.175.9 | Secondary |

## Configuration Files

### Directory Structure

```
/etc/haproxy/
├── haproxy.cfg              # Main config (stats, metrics, PostgreSQL, Redis)
└── domains/
    ├── web_http.cfg         # Single HTTP frontend (redirects)
    ├── web_https.cfg        # Single HTTPS frontend (all domains)
    ├── web_backends.cfg     # All application backends
    └── registry.conf        # Domain → App → Port mapping
```

### Domain Registry

The `registry.conf` file tracks all registered domains:

```bash
# Format: domain=app_name=port
rentalfixer.app=rentalfixer=8100
staging.rentalfixer.app=rentalfixer_staging=8101
www.rentalfixer.app=rentalfixer_www_redirect=8100
```

This registry is used by `provision-domain.sh` to rebuild the consolidated configs.

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
```

### HTTP Frontend (web_http.cfg)

Single frontend for all HTTP redirects:

```haproxy
frontend web_http
    bind :80
    mode http

    # Redirect each domain to HTTPS
    http-request redirect scheme https code 301 if { hdr(host) -i rentalfixer.app }
    http-request redirect scheme https code 301 if { hdr(host) -i staging.rentalfixer.app }
```

### HTTPS Frontend (web_https.cfg)

Single frontend with all certificates:

```haproxy
frontend web_https
    bind :443 ssl \
        crt /etc/haproxy/certs/rentalfixer.app.pem \
        crt /etc/haproxy/certs/staging.rentalfixer.app.pem \
        alpn h2,http/1.1
    mode http

    # Client IP forwarding from Cloudflare
    http-request set-header X-Real-IP %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Real-IP %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-Proto https

    # ACLs for domain routing
    acl is_rentalfixer_app hdr(host) -i rentalfixer.app
    acl is_staging_rentalfixer_app hdr(host) -i staging.rentalfixer.app

    # WWW redirects
    acl is_www_rentalfixer_app hdr(host) -i www.rentalfixer.app
    http-request redirect location https://rentalfixer.app code 301 if is_www_rentalfixer_app

    # Set forwarded host
    http-request set-header X-Forwarded-Host rentalfixer.app if is_rentalfixer_app
    http-request set-header X-Forwarded-Host staging.rentalfixer.app if is_staging_rentalfixer_app

    # Route to backends
    use_backend rentalfixer_backend if is_rentalfixer_app
    use_backend rentalfixer_staging_backend if is_staging_rentalfixer_app

    # Default: 404 for unknown domains
    default_backend not_found_backend
```

### Backends (web_backends.cfg)

All application backends:

```haproxy
backend rentalfixer_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 100.92.26.38:8100 check
    server app2 100.101.39.22:8100 check

backend rentalfixer_staging_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 100.92.26.38:8101 check
    server app2 100.101.39.22:8101 check

backend not_found_backend
    mode http
    http-request deny deny_status 404
```

## DNS Configuration

### For Database Access (PostgreSQL/Redis)

Create A records with both IPs:

```
db.xotec.io          A    172.93.54.112
db.xotec.io          A    23.29.118.6
```

**PostgreSQL:**
- Port 5000: Write (primary)
- Port 5001: Read (replicas)

**Redis:**
- Port 6379: Write (master)
- Port 6380: Read (replicas)

### For Web Traffic (Cloudflare Proxied)

```
domain.tld           A    172.93.54.112  (Proxied)
domain.tld           A    23.29.118.6    (Proxied)
www.domain.tld       A    172.93.54.112  (Proxied)
www.domain.tld       A    23.29.118.6    (Proxied)
staging.domain.tld   A    172.93.54.112  (Proxied)
staging.domain.tld   A    23.29.118.6    (Proxied)
```

### Recommended TTL

Set TTL to 60-300 seconds for faster failover:
- Lower TTL (60s): Faster failover, more DNS queries
- Higher TTL (300s): Less DNS overhead, slower failover

**Note**: With Cloudflare proxy enabled, TTL is less important as Cloudflare handles the routing.

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

### Cloudflare → Routers

```
Client Request → Cloudflare
        ↓
    DNS Round-Robin
        ↓
    ┌───────────┐
    │ Router-01 │ ← 50% of requests
    └───────────┘
    ┌───────────┐
    │ Router-02 │ ← 50% of requests
    └───────────┘
        ↓
    If one fails, Cloudflare HTTP retry
    attempts the other router
```

**No active health checks** - relies on HTTP retry behavior.

### Router → App Servers

```
HAProxy Backend
        ↓
    Active Health Checks (every 2s)
        ↓
    ┌────────────┐
    │ App Server │ ← check status
    │    #1      │
    └────────────┘
    ┌────────────┐
    │ App Server │ ← check status
    │    #2      │
    └────────────┘
        ↓
    Round-robin between healthy servers
```

**Active health checks** - automatic failover when servers fail.

## Failover Scenarios

### Router Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | Router-01 goes down | - |
| 2 | Cloudflare sends request to Router-01 | Connection timeout/failure |
| 3 | Cloudflare HTTP retry to Router-02 | Request succeeds |
| 4 | User sees response | Slight delay (1-2 seconds) |

### App Server Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | App Server 1 goes down | - |
| 2 | HAProxy health check fails (3 failures) | Server marked DOWN |
| 3 | All traffic goes to App Server 2 | - |
| 4 | User sees response | No impact |

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
haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains

# Reload
systemctl reload haproxy
```

### Show Stats

```bash
# Runtime stats
echo 'show stat' | socat stdio /run/haproxy/admin.sock

# Filter for specific backend
echo 'show stat' | socat stdio /run/haproxy/admin.sock | grep rentalfixer

# Show loaded certificates
echo 'show ssl cert' | socat stdio /run/haproxy/admin.sock
```

### Add New Domain

```bash
# Provision new domain (updates registry and rebuilds configs)
/opt/scripts/provision-domain.sh newdomain.tld appname 8102

# Or just rebuild from existing registry
/opt/scripts/provision-domain.sh --rebuild
```

### Remove Domain

```bash
# Remove from registry
sed -i '/^domain.tld=/d' /etc/haproxy/domains/registry.conf

# Remove certificate
rm /etc/haproxy/certs/domain.tld.pem

# Rebuild configs
/opt/scripts/provision-domain.sh --rebuild
```

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

### 503 Errors

1. Check HAProxy is running: `systemctl status haproxy`
2. Check backend servers: `echo 'show stat' | socat stdio /run/haproxy/admin.sock`
3. Check certificate exists: `ls -la /etc/haproxy/certs/`
4. Validate config: `haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains`

### Certificate Issues

```bash
# Check certificate validity
openssl x509 -in /etc/haproxy/certs/domain.tld.pem -noout -dates

# Renew certificate
certbot renew
systemctl reload haproxy
```

### Backend Not Routing

1. Check ACL matches: `acl is_domain hdr(host) -i domain.tld`
2. Check backend is defined in `web_backends.cfg`
3. Check domain is in `registry.conf`
4. Rebuild configs: `/opt/scripts/provision-domain.sh --rebuild`