# Infrastructure Architecture

> Complete reference for the Quantyra infrastructure architecture, traffic flow, and load balancing.

## Overview

The infrastructure uses a multi-tier architecture with high availability at every layer:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              TRAFFIC FLOW DIAGRAM                                │
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
│  │  • DNS: Round-robin between router IPs                                  │    │
│  │  • HTTP Retry: If one router fails, retries the other                   │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                              │                    │                              │
│                              │ 50%                │ 50%                          │
│                              ▼                    ▼                              │
│                    172.93.54.112          23.29.118.6                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                       │                              │
                       │ Encrypted                    │ Encrypted
                       │ (Cloudflare → Router)        │ (Cloudflare → Router)
                       ▼                              ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ROUTER LAYER (HAProxy)                             │
│                                                                                 │
│   ┌─────────────────────────────┐    ┌─────────────────────────────┐           │
│   │       ROUTER-01             │    │       ROUTER-02             │           │
│   │    100.102.220.16           │    │    100.116.175.9            │           │
│   │    Public: 172.93.54.112    │    │    Public: 23.29.118.6      │           │
│   │                             │    │                             │           │
│   │  ┌───────────────────────┐  │    │  ┌───────────────────────┐  │           │
│   │  │ HAProxy Frontend      │  │    │  │ HAProxy Frontend      │  │           │
│   │  │ (web_https)           │  │    │  │ (web_https)           │  │           │
│   │  │                       │  │    │  │                       │  │           │
│   │  │ • Terminates SSL      │  │    │  │ • Terminates SSL      │  │           │
│   │  │ • Cert: Let's Encrypt │  │    │  │ • Cert: Let's Encrypt │  │           │
│   │  │ • Routes by Host hdr  │  │    │  │ • Routes by Host hdr  │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   │              │              │    │              │              │           │
│   │  ┌───────────▼───────────┐  │    │  ┌───────────▼───────────┐  │           │
│   │  │ HAProxy Backend       │  │    │  │ HAProxy Backend       │  │           │
│   │  │ (app_backend)         │  │    │  │ (app_backend)         │  │           │
│   │  │                       │  │    │  │                       │  │           │
│   │  │ • Round-robin LB      │  │    │  │ • Round-robin LB      │  │           │
│   │  │ • Health checks       │  │    │  │ • Health checks       │  │           │
│   │  │ • Failover if down    │  │    │  │ • Failover if down    │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   └──────────────┼──────────────┘    └──────────────┼──────────────┘           │
│                  │                                  │                           │
└──────────────────┼──────────────────────────────────┼───────────────────────────┘
                   │                                  │
                   │         Unencrypted              │
                   │      (Internal Tailscale)        │
                   │                                  │
         ┌─────────┴─────────┐            ┌──────────┴─────────┐
         ▼                   ▼            ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            APP SERVER LAYER                                      │
│                                                                                 │
│   ┌─────────────────────────────┐    ┌─────────────────────────────┐           │
│   │       APP SERVER 1          │    │       APP SERVER 2          │           │
│   │       re-db                 │    │       re-node-02            │           │
│   │    100.92.26.38             │    │    100.89.130.19            │           │
│   │                             │    │                             │           │
│   │  ┌───────────────────────┐  │    │  ┌───────────────────────┐  │           │
│   │  │ nginx (port 8100+)    │  │    │  │ nginx (port 8100+)    │  │           │
│   │  │ • Serves static files │  │    │  │ • Serves static files │  │           │
│   │  │ • Proxies PHP to FPM  │  │    │  │ • Proxies PHP to FPM  │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   │              │              │    │              │              │           │
│   │  ┌───────────▼───────────┐  │    │  ┌───────────▼───────────┐  │           │
│   │  │ PHP-FPM 8.5           │  │    │  │ PHP-FPM 8.5           │  │           │
│   │  │ • Laravel app         │  │    │  │ • Laravel app         │  │           │
│   │  │ • /opt/apps/{appname} │  │    │  │ • /opt/apps/{appname} │  │           │
│   │  └───────────┬───────────┘  │    │  └───────────┬───────────┘  │           │
│   └──────────────┼──────────────┘    └──────────────┼──────────────┘           │
│                  │                                  │                           │
└──────────────────┼──────────────────────────────────┼───────────────────────────┘
                   │                                  │
                   └──────────────┬───────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            DATABASE LAYER                                        │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    PostgreSQL / Patroni Cluster                         │   │
│   │                                                                         │   │
│   │   re-node-01 (100.126.103.51) ─┐                                       │   │
│   │   re-node-03 (100.114.117.46) ─┼─► HA via Patroni (leader election)    │   │
│   │   re-node-04 (100.115.75.119) ─┘                                       │   │
│   │                                                                         │   │
│   │   Access via HAProxy on routers:                                       │   │
│   │   • Port 5000: Read/Write (leader)                                     │   │
│   │   • Port 5001: Read-only (replicas)                                    │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    Redis Cluster with Sentinel                          │   │
│   │                                                                         │   │
│   │   re-node-01 (100.126.103.51) ─► Master                                │   │
│   │   re-node-03 (100.114.117.46) ─► Replica                               │   │
│   │                                                                         │   │
│   │   Access via HAProxy on routers:                                       │   │
│   │   • Port 6379: Write (master)                                          │   │
│   │   • Port 6380: Read (replicas)                                         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Server Inventory

### Routers (HAProxy Load Balancers)

| Name | Tailscale IP | Public IP | Location | Role |
|------|--------------|-----------|----------|------|
| router-01 | 100.102.220.16 | 172.93.54.112 | NYC | Primary |
| router-02 | 100.116.175.9 | 23.29.118.6 | ATL | Secondary |

### App Servers

| Name | Tailscale IP | Public IP | Location | PHP | Node.js |
|------|--------------|-----------|----------|-----|---------|
| re-db | 100.92.26.38 | 208.87.128.115 | NYC | 8.5 | 20 |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | ATL | 8.5 | 20 |

### Database Servers

| Name | Tailscale IP | Role | Services |
|------|--------------|------|----------|
| re-node-01 | 100.126.103.51 | PostgreSQL, Redis Master | Patroni, Redis, Sentinel |
| re-node-03 | 100.114.117.46 | PostgreSQL Leader, Redis Replica | Patroni, Redis, Sentinel |
| re-node-04 | 100.115.75.119 | PostgreSQL Replica | Patroni |

## Load Balancing Strategy

### Layer 1: Cloudflare → Routers

**Method**: DNS Round-Robin with HTTP Retry

```
Client Request → Cloudflare DNS
                    ↓
        ┌───────────┴───────────┐
        ▼                       ▼
    Router-01               Router-02
   (172.93.54.112)        (23.29.118.6)
        │                       │
        │ (if fails)            │
        └───────────────────────┘
                    ↓
            Retry on other router
```

**Behavior**:
- Cloudflare returns both IPs in random order
- Client connects to first IP
- If connection fails, Cloudflare HTTP retry attempts the other IP
- No active health checks (requires Cloudflare Load Balancer - paid add-on)

**Limitations**:
- No automatic failover at DNS level
- Relies on HTTP client retry behavior
- Slight delay on first failed request

### Layer 2: Router → App Servers

**Method**: HAProxy Round-Robin with Active Health Checks

```
HAProxy Backend Configuration:
┌─────────────────────────────────────────┐
│  backend app_backend                     │
│    mode http                             │
│    balance roundrobin                    │
│    option httpchk GET /                  │
│    http-check expect status 200-499      │
│    server app1 100.92.26.38:8100 check   │
│    server app2 100.89.130.19:8100 check  │
└─────────────────────────────────────────┘
```

**Behavior**:
- Health check every 2 seconds
- If server fails 3 checks → marked DOWN
- If server passes 2 checks → marked UP
- Traffic distributed evenly between healthy servers
- Zero downtime during server failure

## SSL/TLS Architecture

### Certificate Chain

```
Let's Encrypt (CA)
    │
    ├── rentalfixer.app (on router-01)
    │   └── /etc/haproxy/certs/rentalfixer.app.pem
    │
    ├── rentalfixer.app (on router-02)
    │   └── /etc/haproxy/certs/rentalfixer.app.pem
    │
    ├── staging.rentalfixer.app (on router-01)
    │   └── /etc/haproxy/certs/staging.rentalfixer.app.pem
    │
    └── staging.rentalfixer.app (on router-02)
        └── /etc/haproxy/certs/staging.rentalfixer.app.pem
```

### SSL Termination Points

```
User ──HTTPS──► Cloudflare ──HTTPS──► Router ──HTTP──► App Server
       (Edge Cert)      (Origin Cert)    (Unencrypted internally)
```

**Certificate Types**:
1. **Cloudflare Edge Certificate** - Managed by Cloudflare
   - Wildcard certificate for *.domain.tld
   - Automatic renewal by Cloudflare
   
2. **Origin Certificate** - Let's Encrypt on routers
   - Per-domain certificates
   - DNS-01 challenge for validation
   - Auto-renewal via certbot timer

### Why No SSL Issues with Multiple Routers

Each router has its own independent Let's Encrypt certificate:
- Certificates are obtained separately on each router
- Both are valid for the same domain
- Cloudflare accepts either certificate
- No shared state required between routers

## HAProxy Configuration

### Consolidated Frontend Architecture

HAProxy uses a **single frontend** for all domains instead of separate frontends per domain:

```
/etc/haproxy/domains/
├── web_http.cfg       # Single HTTP frontend (redirects to HTTPS)
├── web_https.cfg      # Single HTTPS frontend (all certificates)
├── web_backends.cfg   # All application backends
└── registry.conf      # Domain → App → Port mapping
```

**Why Consolidated?**
- Multiple frontends on port 443 cause SNI routing issues
- Single frontend with multiple certificates works reliably
- ACLs route traffic based on Host header
- Easier to manage and debug

### HTTP Frontend (web_http.cfg)

```haproxy
frontend web_http
    bind :80
    mode http
    
    # Redirect each domain to HTTPS
    http-request redirect scheme https code 301 if { hdr(host) -i rentalfixer.app }
    http-request redirect scheme https code 301 if { hdr(host) -i staging.rentalfixer.app }
```

### HTTPS Frontend (web_https.cfg)

```haproxy
frontend web_https
    # All certificates in one bind line
    bind :443 ssl \
        crt /etc/haproxy/certs/rentalfixer.app.pem \
        crt /etc/haproxy/certs/staging.rentalfixer.app.pem \
        alpn h2,http/1.1
    mode http
    
    # Client IP forwarding
    http-request set-header X-Real-IP %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Real-IP %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-Proto https
    
    # ACLs for routing
    acl is_rentalfixer_app hdr(host) -i rentalfixer.app
    acl is_staging_rentalfixer_app hdr(host) -i staging.rentalfixer.app
    
    # Host-specific headers
    http-request set-header X-Forwarded-Host rentalfixer.app if is_rentalfixer_app
    http-request set-header X-Forwarded-Host staging.rentalfixer.app if is_staging_rentalfixer_app
    
    # Routing
    use_backend rentalfixer_backend if is_rentalfixer_app
    use_backend rentalfixer_staging_backend if is_staging_rentalfixer_app
    
    # Default: 404
    default_backend not_found_backend
```

### Backends (web_backends.cfg)

```haproxy
backend rentalfixer_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 100.92.26.38:8100 check
    server app2 100.89.130.19:8100 check

backend rentalfixer_staging_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 100.92.26.38:8101 check
    server app2 100.89.130.19:8101 check

backend not_found_backend
    mode http
    http-request deny deny_status 404
```

### Domain Registry

The `registry.conf` file tracks all domains:

```
rentalfixer.app=rentalfixer=8100
staging.rentalfixer.app=rentalfixer_staging=8101
www.rentalfixer.app=rentalfixer_www_redirect=8100
```

Format: `domain=app_name=port`

## Failover Scenarios

### Scenario 1: Router Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | Router-01 goes down | - |
| 2 | Cloudflare sends request to Router-01 | Connection timeout/failure |
| 3 | Cloudflare HTTP retry to Router-02 | Request succeeds on Router-02 |
| 4 | User sees response | Slight delay (1-2 seconds) |

**Result**: Zero downtime, slight latency increase on first failed request

### Scenario 2: App Server Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | App Server 1 goes down | - |
| 2 | HAProxy health check fails | Server marked DOWN after 6 seconds |
| 3 | HAProxy routes all traffic to App Server 2 | - |
| 4 | User sees response | No impact |

**Result**: Zero downtime, no user-visible impact

### Scenario 3: PostgreSQL Primary Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | PostgreSQL leader fails | - |
| 2 | Patroni detects failure | ~10 seconds |
| 3 | Patroni promotes new leader | ~5 seconds |
| 4 | HAProxy detects new leader | ~3 seconds |
| 5 | Applications reconnect | Automatic with connection pooling |

**Result**: ~15-20 seconds of write unavailability, reads continue

### Scenario 4: Redis Master Failure

| Step | What Happens | User Impact |
|------|--------------|-------------|
| 1 | Redis master fails | - |
| 2 | Sentinel detects failure | ~5 seconds |
| 3 | Sentinel promotes replica | ~2 seconds |
| 4 | HAProxy detects new master | ~3 seconds |
| 5 | Applications reconnect | Automatic |

**Result**: ~10 seconds of write unavailability, reads continue

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
│  └────┬─────┘     │ -php-fpm │     │ -redis   │                │
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
- `nginx_connections_active` - Active nginx connections
- `phpfpm_processes_active` - Active PHP processes
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
| 6379 | Redis write |
| 6380 | Redis read |
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

## Disaster Recovery

### Backup Strategy

| Component | Backup Method | Frequency | Retention |
|-----------|---------------|-----------|-----------|
| PostgreSQL | pg_dump + S3 | Hourly | 30 days |
| Redis | RDB snapshots | Hourly | 7 days |
| App configs | Git repository | On change | Forever |
| SSL certs | certbot renew | Auto | 90 days |

### Recovery Procedures

See `/docs/disaster_recovery.md` for detailed procedures.