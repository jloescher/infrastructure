# Architecture Diagram

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Cloudflare                               │
│  DNS (Round-Robin) + WAF + DDoS Protection + SSL (Edge)         │
└─────────────────────────────────────────────────────────────────┘
                                │
                ┌───────────────┴───────────────┐
                ▼                               ▼
        ┌───────────────┐               ┌───────────────┐
        │   router-01   │               │   router-02   │
        │  HAProxy      │               │  HAProxy      │
        │  Dashboard    │               │  (Secondary)  │
        │  Monitoring   │               │               │
        └───────────────┘               └───────────────┘
                │                               │
        ┌───────┴───────────────────────────────┘
        │
        ├─────────────────────────────────────────────┐
        │                                             │
        ▼                                             ▼
┌───────────────────┐                       ┌───────────────────┐
│     re-db         │                       │    re-node-02     │
│  App Server       │                       │  App Server (ATL) │
│  nginx + PHP-FPM  │                       │  nginx + PHP-FPM  │
│  Node.js apps     │                       │  Node.js apps     │
└───────────────────┘                       └───────────────────┘
        │                                             │
        └─────────────────┬───────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   re-node-01  │ │   re-node-03  │ │   re-node-04  │
│  PostgreSQL   │ │  PostgreSQL   │ │  PostgreSQL   │
│  Redis Master │ │  Redis Replica│ │     etcd      │
│               │ │  (Leader)     │ │               │
└───────────────┘ └───────────────┘ └───────────────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                    Patroni Cluster
                    (HA PostgreSQL)
```

## Network Topology

All servers connected via Tailscale (100.64.0.0/10)

| Server | Tailscale IP | Public IP | Services |
|--------|--------------|-----------|----------|
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy, Dashboard, Prometheus, Grafana |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy |
| re-db | 100.92.26.38 | 208.87.128.115 | nginx, PHP-FPM, Node.js |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | nginx, PHP-FPM, Node.js |
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL, Redis |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL, etcd |

## Port Allocation

| Service | Port | Purpose |
|---------|------|---------|
| HAProxy HTTP | 80 | Redirect to HTTPS |
| HAProxy HTTPS | 443 | SSL termination |
| HAProxy Stats | 8404 | Admin interface |
| PostgreSQL RW | 5000 | Write endpoint (via HAProxy) |
| PostgreSQL RO | 5001 | Read endpoint (via HAProxy) |
| Redis | 6379 | Cache (via HAProxy) |
| Prometheus | 9090 | Metrics |
| Grafana | 3000 | Dashboards |
| Alertmanager | 9093 | Alerts |
| Dashboard | 8080 | PaaS UI |
| App Production | 8100-8199 | Laravel apps |
| App Staging | 9200-9299 | Staging apps |

## Traffic Flow

### Incoming Request Flow

```
User Request
     │
     ▼
┌─────────────┐
│ Cloudflare  │ ← SSL Termination at Edge
│ DNS + WAF   │ ← DDoS Protection
└─────────────┘
     │
     ▼ (Round-Robin DNS)
┌─────────────┐
│   HAProxy   │ ← Load Balancing
│  (router)   │ ← SSL Termination (internal)
└─────────────┘
     │
     ▼ (Host Header Routing)
┌─────────────┐
│   nginx     │ ← Static Files
│  (app)      │ ← PHP-FPM Proxy
└─────────────┘
     │
     ▼
┌─────────────┐
│  PHP-FPM    │ ← Laravel Application
│  Node.js    │ ← Next.js/Svelte App
└─────────────┘
     │
     ▼
┌─────────────┐
│ PostgreSQL  │ ← Database (via HAProxy)
│   Redis     │ ← Cache
└─────────────┘
```

### Database Connection Flow

```
Application
     │
     ▼
┌──────────────────────┐
│   HAProxy (5000)     │ ← Write Endpoint
│   HAProxy (5001)     │ ← Read Endpoint
└──────────────────────┘
     │
     ├──► re-node-01 (Replica)
     ├──► re-node-03 (Leader) ← Writes go here
     └──► re-node-04 (Replica)
```

### Redis Connection Flow

```
Application
     │
     ▼
┌──────────────────────┐
│   HAProxy (6379)     │ ← Write to Master
│   HAProxy (6380)     │ ← Read from Replica
└──────────────────────┘
     │
     ├──► re-node-01 (Master)
     └──► re-node-03 (Replica)
```

## High Availability Architecture

### PostgreSQL HA (Patroni)

```
┌─────────────────────────────────────────────────────────┐
│                     etcd Cluster                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │ router-01 │  │ router-02 │  │ re-node-04│           │
│  │  (etcd)   │  │  (etcd)   │  │  (etcd)   │           │
│  └───────────┘  └───────────┘  └───────────┘           │
└─────────────────────────────────────────────────────────┘
                         │
                         │ DCS (Distributed Configuration Store)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                  Patroni Cluster                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │ re-node-01│  │ re-node-03│  │ re-node-04│           │
│  │ (Replica) │  │ (Leader)  │  │ (Replica) │           │
│  └───────────┘  └───────────┘  └───────────┘           │
│       │              │              │                    │
│       └──────────────┼──────────────┘                    │
│                      │                                   │
│              Streaming Replication                       │
└─────────────────────────────────────────────────────────┘
```

### Redis HA (Sentinel)

```
┌─────────────────────────────────────────────────────────┐
│                   Sentinel Monitors                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │ re-node-01│  │ re-node-03│  │ router-01 │           │
│  │ (Sentinel)│  │ (Sentinel)│  │ (Sentinel)│           │
│  └───────────┘  └───────────┘  └───────────┘           │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Failover Coordination
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Redis Cluster                          │
│  ┌───────────┐         ┌───────────┐                    │
│  │ re-node-01│  ───►   │ re-node-03│                    │
│  │ (Master)  │  Replication (Replica)│                    │
│  └───────────┘         └───────────┘                    │
└─────────────────────────────────────────────────────────┘
```

## Monitoring Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Grafana                               │
│              (Dashboards & Visualization)                │
│                    :3000                                 │
└─────────────────────────────────────────────────────────┘
                         │
                         │ Queries
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Prometheus                             │
│            (Metrics Collection & Alerting)               │
│                    :9090                                 │
└─────────────────────────────────────────────────────────┘
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│node_exporter │ │postgres_     │ │redis_exporter│
│(all servers) │ │exporter      │ │(Redis nodes) │
└──────────────┘ └──────────────┘ └──────────────┘
        │              │              │
        ▼              ▼              ▼
   System         PostgreSQL        Redis
   Metrics        Metrics           Metrics
```

## SSL/TLS Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Cloudflare                            │
│         Edge SSL Certificate (Managed)                   │
│          *.domain.tld, domain.tld                        │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────┐
│                     HAProxy                              │
│    Let's Encrypt Certificates (DNS-01 Challenge)         │
│          Stored in /etc/haproxy/ssl/                     │
│          Auto-renewal via certbot                        │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTP (internal)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    nginx                                 │
│                 (No SSL - internal)                      │
└─────────────────────────────────────────────────────────┘
```

## Application Deployment Architecture

### Laravel Application

```
┌─────────────────────────────────────────────────────────┐
│                      nginx                               │
│                  /etc/nginx/sites-available/             │
│                         :8100                            │
└─────────────────────────────────────────────────────────┘
                         │
                         │ FastCGI
                         ▼
┌─────────────────────────────────────────────────────────┐
│                     PHP-FPM                              │
│              /etc/php/8.5/fpm/pool.d/                    │
│                (per-application pool)                    │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    Laravel                               │
│              /var/www/app-name/                          │
│                 (git checkout)                           │
└─────────────────────────────────────────────────────────┘
```

### Node.js Application

```
┌─────────────────────────────────────────────────────────┐
│                   systemd                                │
│              /etc/systemd/system/app-name.service        │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Node.js                                │
│              /opt/apps/app-name/                         │
│           (npm install && npm run build)                 │
└─────────────────────────────────────────────────────────┘
```

## PaaS Architecture

### Dashboard Components

```
┌─────────────────────────────────────────────────────────┐
│                  Flask Dashboard                         │
│                   app.py + templates/                    │
│                      :8080                               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────┐    ┌──────────────────┐           │
│  │   Applications   │    │     Domains      │           │
│  │   Management     │    │   Provisioning   │           │
│  └──────────────────┘    └──────────────────┘           │
│                                                          │
│  ┌──────────────────┐    ┌──────────────────┐           │
│  │    Databases     │    │    Services      │           │
│  │   Management     │    │   (Redis, etc.)  │           │
│  └──────────────────┘    └──────────────────┘           │
│                                                          │
│  ┌──────────────────┐    ┌──────────────────┐           │
│  │     Secrets      │    │   Deployments    │           │
│  │   Management     │    │   Tracking       │           │
│  └──────────────────┘    └──────────────────┘           │
│                                                          │
└─────────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  PostgreSQL  │ │    Redis     │ │   SQLite     │
│(App Databases)│ │   (Cache)    │ │(PaaS State)  │
└──────────────┘ └──────────────┘ └──────────────┘
```

### Storage Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  PaaS State (SQLite)                     │
│                   /data/paas.db                          │
├─────────────────────────────────────────────────────────┤
│  • Applications                                          │
│  • Domains                                               │
│  • Secrets (AES-256-GCM encrypted)                       │
│  • Services                                              │
│  • Deployments                                           │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│             Application Databases (PostgreSQL)           │
│                  Via HAProxy ports                       │
├─────────────────────────────────────────────────────────┤
│  • myapp_production                                      │
│  • myapp_staging                                         │
│  • anotherapp_production                                 │
└─────────────────────────────────────────────────────────┘
```

## Security Architecture

### Network Segmentation

```
┌─────────────────────────────────────────────────────────┐
│                    Internet                              │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (443)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    Cloudflare                            │
│         WAF + DDoS + Rate Limiting                       │
└─────────────────────────────────────────────────────────┘
                         │
                         │ HTTPS (443)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                 Tailscale Network                        │
│                 100.64.0.0/10                            │
├─────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐ │
│  │              Routers (HAProxy)                      │ │
│  │  • Public ports: 80, 443, 8404                      │ │
│  │  • Tailscale: Full mesh                            │ │
│  └────────────────────────────────────────────────────┘ │
│                         │                                │
│  ┌────────────────────────────────────────────────────┐ │
│  │              App Servers                            │ │
│  │  • Public ports: None (via routers only)           │ │
│  │  • Tailscale: Full mesh                            │ │
│  └────────────────────────────────────────────────────┘ │
│                         │                                │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Database Nodes                         │ │
│  │  • Public ports: None                              │ │
│  │  • Tailscale: Full mesh                            │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Firewall Rules (UFW)

```
┌─────────────────────────────────────────────────────────┐
│                    Router Nodes                          │
├─────────────────────────────────────────────────────────┤
│  Allow: 80, 443 (from any)                              │
│  Allow: 8404 (from Tailscale)                           │
│  Allow: 22 (from Tailscale, rate-limited)               │
│  Allow: All from 100.64.0.0/10 (Tailscale)              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    App Servers                           │
├─────────────────────────────────────────────────────────┤
│  Allow: 8100-8199 (from routers only)                   │
│  Allow: 9200-9299 (from routers only)                   │
│  Allow: 22 (from Tailscale, rate-limited)               │
│  Allow: All from 100.64.0.0/10 (Tailscale)              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    Database Nodes                        │
├─────────────────────────────────────────────────────────┤
│  Allow: 5432 (from routers only)                        │
│  Allow: 6379 (from routers + app servers)               │
│  Allow: 22 (from Tailscale, rate-limited)               │
│  Allow: All from 100.64.0.0/10 (Tailscale)              │
└─────────────────────────────────────────────────────────┘
```