# Quantyra Infrastructure Complete Overview

> **Comprehensive reference documentation for the Quantyra multi-region VPS infrastructure.**
> 
> **Last Updated:** 2026-04-02
> **Document Purpose:** Provide complete context for AI assistants (Grok) to understand the entire infrastructure setup.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Server Inventory](#2-server-inventory)
3. [Service Architecture](#3-service-architecture)
4. [Coolify Configuration](#4-coolify-configuration)
5. [Database Infrastructure](#5-database-infrastructure)
6. [Backup and Recovery](#6-backup-and-recovery)
7. [Network Architecture](#7-network-architecture)
8. [Security Configuration](#8-security-configuration)
9. [Operational Procedures](#9-operational-procedures)
10. [Migration Notes](#10-migration-notes)
11. [Troubleshooting Guide](#11-troubleshooting-guide)
12. [Credentials Reference](#12-credentials-reference)

---

## 1. Executive Summary

### Current Infrastructure State

The Quantyra infrastructure is a multi-region VPS platform built on **7 servers** across **2 data centers** (NYC and ATL), providing:

- **High-availability PostgreSQL** via 3-node Patroni cluster with etcd DCS
- **Redis caching** with master-replica replication and Sentinel failover
- **Load balancing** via dual HAProxy routers with DNS round-robin
- **Application deployment** via Coolify (primary) and legacy Flask PaaS dashboard (deprecated)
- **Monitoring stack** with Prometheus, Grafana, and Alertmanager
- **Database management UIs** with pgAdmin and Ivory

### Key Architectural Decisions

| Decision | Implementation | Rationale |
|----------|----------------|-----------|
| Coolify as primary PaaS | Port 8000 on router-01 | Modern self-hosted PaaS, replaces custom Flask dashboard |
| PostgreSQL via Patroni | 3-node cluster with HAProxy proxy | Automatic failover, read/write splitting |
| Redis with Sentinel | Master on re-node-01, replica on re-node-03 | Automatic failover for cache layer |
| Tailscale VPN | All servers on 100.64.0.0/10 mesh | Encrypted inter-server communication |
| Cloudflare edge | DNS, WAF, DDoS protection | Security and global CDN |

### Recent Changes (2026-03 to 2026-04)

| Change | Date | Impact |
|--------|------|--------|
| Deprecated Flask PaaS dashboard | 2026-04-01 | Coolify is now primary deployment platform |
| Removed legacy PHP-FPM deployments | 2026-04-01 | All apps now managed by Coolify |
| Added daily backup for pgAdmin/Ivory | 2026-03-26 | 03:00 UTC backup with 7-day retention |
| Updated HAProxy routing to Coolify | 2026-04-02 | HAProxy routes all domains to Coolify backend |
| Implemented package update monitoring | 2026-03-19 | Dashboard shows available updates per server |
| Fixed PHP-FPM pool configuration | 2026-03-19 | Optimized for 12 vCPU/48GB servers |

### Technology Stack Summary

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Load Balancing | HAProxy | 2.8 | SSL termination, traffic routing |
| Deployment Platform | Coolify | Latest | Self-hosted PaaS |
| Database | PostgreSQL | 18.x | Primary data store via Patroni cluster |
| HA Layer | Patroni | 3.x | PostgreSQL high availability |
| DCS | etcd | 3.5.x | Distributed configuration store |
| Caching | Redis | 7.x | Session/cache with Sentinel |
| Monitoring | Prometheus | 2.48.x | Metrics collection and alerting |
| Visualization | Grafana | 10.2.x | Dashboards and alert management |
| DNS/CDN | Cloudflare | - | DNS, WAF, DDoS protection |
| VPN | Tailscale | 1.96.x | Mesh VPN for server communication |

---

## 2. Server Inventory

### Complete Server List

| Server | Tailscale IP | Public IP | Location | Role | Specs |
|--------|--------------|-----------|----------|------|-------|
| router-01 | 100.102.220.16 | 172.93.54.112 | NYC | HAProxy, Monitoring, Coolify, pgAdmin, Ivory | 2 vCPU, 8GB RAM |
| router-02 | 100.116.175.9 | 23.29.118.6 | ATL | HAProxy (Secondary) | 2 vCPU, 8GB RAM |
| re-db | 100.92.26.38 | 208.87.128.115 | NYC | App Server (Coolify proxy) | 12 vCPU, 48GB RAM |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | ATL | App Server (Coolify proxy) | 12 vCPU, 48GB RAM |
| re-node-01 | 100.126.103.51 | 104.225.216.26 | NYC | PostgreSQL, Redis Master | 8 vCPU, 32GB RAM |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | NYC | PostgreSQL Leader, Redis Replica | 8 vCPU, 32GB RAM |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | NYC | PostgreSQL Replica, etcd | 8 vCPU, 32GB RAM |

### Server Roles

#### Routers (HAProxy Load Balancers)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ROUTER LAYER                                    │
│                                                                          │
│  router-01 (Primary)              router-02 (Secondary)                 │
│  100.102.220.16                   100.116.175.9                          │
│  Public: 172.93.54.112            Public: 23.29.118.6                   │
│                                                                          │
│  Services:                        Services:                              │
│  • HAProxy (80, 443, 5000, 5001)  • HAProxy (80, 443, 5000, 5001)       │
│  • Coolify (8000)                 • HAProxy Stats (8404)                 │
│  • pgAdmin (8081)                                                        │
│  • Ivory (8082)                                                          │
│  • Prometheus (9090)                                                     │
│  • Grafana (3000)                                                        │
│  • Alertmanager (9093)                                                   │
│  • HAProxy Stats (8404)                                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

#### App Servers (Coolify Proxy Nodes)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        APP SERVER LAYER                                  │
│                                                                          │
│  re-db (Primary)                 re-node-02 (ATL)                        │
│  100.92.26.38                    100.89.130.19                           │
│  Public: 208.87.128.115          Public: 23.227.173.245                  │
│                                                                          │
│  Services:                        Services:                              │
│  • coolify-proxy (Traefik)        • coolify-proxy (Traefik)              │
│    - Port 80, 443, 8080             - Port 80, 443, 8080                 │
│  • coolify-sentinel               • coolify-sentinel                     │
│  • PHP 8.5 + nginx                • PHP 8.5 + nginx                      │
│  • Node.js 20                     • Node.js 20                           │
│                                                                          │
│  Capacity: 12 vCPU, 48GB RAM     Capacity: 12 vCPU, 48GB RAM            │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Database Servers (Patroni Cluster + Redis)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        DATABASE LAYER                                    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │              PostgreSQL / Patroni Cluster (3 nodes)             │    │
│  │                                                                  │    │
│  │  re-node-01              re-node-03             re-node-04      │    │
│  │  100.126.103.51          100.114.117.46         100.115.75.119  │    │
│  │  (Replica)               (Leader)               (Replica)       │    │
│  │                           │                                      │    │
│  │  └───────────────────────┼──────────────────────┘               │    │
│  │                          │                                       │    │
│  │         HAProxy Ports: 5000 (RW), 5001 (RO)                     │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                  Redis Cluster with Sentinel                    │    │
│  │                                                                  │    │
│  │  re-node-01              re-node-03                             │    │
│  │  100.126.103.51:6379     100.114.117.46:6379                    │    │
│  │  (Master)                (Replica)                              │    │
│  │                                                                  │    │
│  │  Sentinel: Port 26379 on both nodes                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                        etcd Cluster (DCS)                        │    │
│  │                                                                  │    │
│  │  re-node-04 is the etcd node for Patroni DCS                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Network Connectivity

All servers communicate via **Tailscale mesh VPN** (100.64.0.0/10 range):

```bash
# Verify Tailscale connectivity
tailscale status

# Example output:
# 100.102.220.16   router-01        linux  -
# 100.116.175.9    router-02        linux  -
# 100.92.26.38     re-db            linux  -
# 100.89.130.19    re-node-02       linux  -
# 100.126.103.51   re-node-01       linux  -
# 100.114.117.46   re-node-03       linux  -
# 100.115.75.119   re-node-04       linux  -
```

---

## 3. Service Architecture

### Services Running on Each Server

#### router-01 (100.102.220.16)

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| HAProxy | 80, 443 | HTTP/HTTPS load balancer | Active |
| HAProxy Stats | 8404 | HAProxy admin dashboard | Active |
| HAProxy (DB) | 5000, 5001 | PostgreSQL proxy (RW/RO) | Active |
| HAProxy (Redis) | 6379 | Redis proxy | Active |
| Coolify | 8000 | Main deployment platform | Active |
| pgAdmin | 8081 | PostgreSQL management UI | Active |
| Ivory | 8082 | PostgreSQL ERD visualization | Active |
| Prometheus | 9090 | Metrics collection | Active |
| Grafana | 3000 | Dashboards and visualization | Active |
| Alertmanager | 9093 | Alert routing | Active |
| coolify-db | 5432 | PostgreSQL for Coolify | Active |
| coolify-redis | 6379 | Redis for Coolify | Active |
| coolify-realtime | 6001 | WebSocket for Coolify | Active |
| coolify-sentinel | - | HA for Coolify | Active |

#### router-02 (100.116.175.9)

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| HAProxy | 80, 443 | HTTP/HTTPS load balancer | Active |
| HAProxy Stats | 8404 | HAProxy admin dashboard | Active |
| HAProxy (DB) | 5000, 5001 | PostgreSQL proxy (RW/RO) | Active |
| HAProxy (Redis) | 6379 | Redis proxy | Active |

#### re-db and re-node-02 (App Servers)

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| coolify-proxy (Traefik) | 80, 443, 8080 | Application routing | Active |
| coolify-sentinel | - | HA for Coolify | Active |
| nginx | Various | Legacy app serving (if needed) | Available |
| PHP-FPM 8.5 | Socket | PHP runtime | Available |
| Node.js 20 | Various | Node runtime | Available |

#### re-node-01, re-node-03, re-node-04 (Database Servers)

| Service | Port | Purpose | Status |
|---------|------|---------|--------|
| PostgreSQL | 5432 | Database server | Active |
| Patroni | 8008 | HA management | Active |
| etcd | 2379, 2380 | DCS (re-node-04 only) | Active |
| Redis | 6379 | Cache server | Active |
| Redis Sentinel | 26379 | HA for Redis | Active |

### Port Allocation Reference

| Port Range | Purpose | Notes |
|------------|---------|-------|
| 80, 443 | HTTP/HTTPS | Handled by HAProxy → Coolify proxy |
| 3000 | Grafana | Dashboard UI |
| 5000 | PostgreSQL (RW) | HAProxy routes to leader |
| 5001 | PostgreSQL (RO) | HAProxy load balances replicas |
| 6379 | Redis | HAProxy routes to master |
| 8000 | Coolify | Deployment platform UI |
| 8080 | coolify-proxy admin | Traefik dashboard |
| 8081 | pgAdmin | Database management UI |
| 8082 | Ivory | ERD visualization |
| 8404 | HAProxy Stats | Load balancer dashboard |
| 9090 | Prometheus | Metrics UI |
| 9093 | Alertmanager | Alert management UI |
| 8100-8199 | Production apps | Legacy PHP-FPM ports |
| 9200-9299 | Staging apps | Legacy PHP-FPM ports |

---

## 4. Coolify Configuration

### Overview

**Coolify** is a self-hosted PaaS alternative to Heroku/Vercel, running on router-01 (port 8000). It is now the primary deployment platform for all applications.

### Access

```
URL: http://100.102.220.16:8000
```

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         COOLIFY ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    Coolify Main Server                          │     │
│  │                    (router-01:8000)                             │     │
│  │                                                                 │     │
│  │  • coolify-db (PostgreSQL)                                      │     │
│  │  • coolify-redis                                                │     │
│  │  • coolify-realtime (WebSocket)                                 │     │
│  │  • coolify-sentinel (HA)                                        │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                          │                                               │
│                          │ SSH/Tailscale                                 │
│                          ▼                                               │
│  ┌────────────────────────────────────────────────────────────────┐     │
│  │                    App Servers (Targets)                        │     │
│  │                                                                 │     │
│  │  re-db (100.92.26.38)          re-node-02 (100.89.130.19)      │     │
│  │  • coolify-proxy (Traefik)      • coolify-proxy (Traefik)      │     │
│  │  • Docker containers            • Docker containers            │     │
│  └────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### What Coolify Manages

- **Application Deployment**: Docker-based deployments from Git repositories
- **Database Provisioning**: PostgreSQL, MySQL, Redis, MongoDB containers
- **SSL Certificates**: Let's Encrypt automatic SSL
- **Domain Management**: Custom domains with automatic DNS configuration
- **Environment Variables**: Secrets management per application
- **Container Orchestration**: Docker Compose generation and management

### How to Deploy Apps with Coolify

1. **Access Coolify UI**: Navigate to `http://100.102.220.16:8000`

2. **Add Server** (if not already added):
   - Go to Servers → Add Server
   - Select "Existing Server"
   - Enter Tailscale IP: `100.92.26.38` or `100.89.130.19`
   - SSH key authentication is pre-configured

3. **Create Application**:
   - Go to Projects → New Project
   - Add Resource → Application
   - Choose deployment type:
     - **Docker Compose**: For complex multi-container apps
     - **Dockerfile**: For custom container builds
     - **Static Site**: For Jamstack/SSG deployments
     - **Service**: For databases, caches, etc.

4. **Configure Git Repository**:
   - Repository URL: Your Git repo
   - Branch: `main` for production
   - Build settings: Auto-detected or custom

5. **Add Domains**:
   - Application → Configuration → Domains
   - Add domain (e.g., `myapp.domain.tld`)
   - SSL auto-provisioned via Let's Encrypt

6. **Deploy**:
   - Click "Deploy" button
   - Monitor deployment logs in real-time
   - Application becomes available at configured domain

### Domain Provisioning with Coolify + HAProxy

**Architecture (Updated 2026-04-02):**

All domains are provisioned through Coolify, with HAProxy handling SSL termination:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DOMAIN PROVISIONING FLOW                               │
│                                                                           │
│  1. Cloudflare DNS                                                        │
│     • Domain points to router IPs (DNS round-robin)                      │
│     • Both router-01 and router-02 IPs returned                          │
│                                                                           │
│  2. HAProxy (router-01, router-02)                                        │
│     • Terminates SSL (existing Let's Encrypt certificates)               │
│     • Routes ALL domains to coolify_backend                              │
│     • Sends plain HTTP to Coolify Traefik                                │
│                                                                           │
│  3. Coolify Traefik (re-db, re-node-02)                                   │
│     • Receives HTTP traffic on port 80                                    │
│     • Routes to appropriate Docker container                             │
│     • Domain mapping managed by Coolify                                  │
│                                                                           │
│  4. Application Container                                                 │
│     • Docker container running app                                        │
│     • Environment variables from Coolify                                  │
│     • Database from Patroni cluster or Coolify-managed                   │
└─────────────────────────────────────────────────────────────────────────┘
```

**How to Add a New Domain:**

1. **In Coolify UI**:
   - Go to Application → Configuration → Domains
   - Add domain (e.g., `myapp.domain.tld`)
   - Coolify configures Traefik routing

2. **SSL Certificate**:
   - HAProxy already has SSL certificates for existing domains
   - For new domains, add certificate to HAProxy:
     ```bash
     certbot certonly --dns-cloudflare --dns-cloudflare-credentials /root/.cloudflare.ini -d myapp.domain.tld
     cat /etc/letsencrypt/live/myapp.domain.tld/fullchain.pem /etc/letsencrypt/live/myapp.domain.tld/privkey.pem > /etc/haproxy/certs/myapp.domain.tld.pem
     systemctl reload haproxy
     ```

3. **DNS Configuration**:
   - Add A record in Cloudflare pointing to both router IPs:
     - `myapp.domain.tld` → 172.93.54.112 (router-01)
     - `myapp.domain.tld` → 23.29.118.6 (router-02)
   - Enable Cloudflare proxy (orange cloud)

**Note:** Coolify's built-in SSL is not used because HAProxy handles SSL termination. Coolify receives plain HTTP traffic.

### Database Provisioning with Coolify

1. **Create Database Service**:
   - Project → Add Resource → Service
   - Choose database type: PostgreSQL, MySQL, Redis, MongoDB
   - Configure resource limits and persistence

2. **Connect to External Patroni Cluster**:
   - For production apps, connect to existing Patroni cluster
   - Use HAProxy endpoints:
     - Write: `100.102.220.16:5000`
     - Read: `100.102.220.16:5001`

3. **Environment Variables**:
   ```bash
   DB_HOST=100.102.220.16
   DB_PORT=5000
   DB_DATABASE=myapp_production
   DB_USERNAME=myapp_user
   DB_PASSWORD=<from_secrets>
   ```

### Coolify vs Legacy Flask Dashboard

| Feature | Flask Dashboard | Coolify |
|---------|-----------------|---------|
| Status | **Deprecated** | **Active** |
| Framework Support | Laravel, Next.js, Svelte, Python, Go | Any Docker-compatible |
| Database | External Patroni cluster | Managed containers or external |
| SSL | DNS-01 via Cloudflare | HTTP-01 or DNS-01 |
| Deployment | SSH + scripts | Docker containers |
| UI | Basic | Modern, full-featured |
| Monitoring | Prometheus | Built-in + Prometheus |
| Backup | Manual | Automated |

### Migration Path from Flask Dashboard

1. **Existing Apps**:
   - Flask dashboard apps continue running via HAProxy routing
   - Migrate to Coolify when ready for container-based deployment

2. **New Apps**:
   - Use Coolify for all new deployments
   - Legacy Flask dashboard no longer maintained

3. **Databases**:
   - Continue using Patroni cluster for production databases
   - Coolify can manage its own databases for non-critical apps

---

## 5. Database Infrastructure

### PostgreSQL Cluster (Patroni)

#### Cluster Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     PATRONI CLUSTER TOPOLOGY                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐  │
│   │   re-node-01    │     │   re-node-03    │     │   re-node-04    │  │
│   │ 100.126.103.51  │     │ 100.114.117.46  │     │ 100.115.75.119  │  │
│   │                 │     │                 │     │                 │  │
│   │  PostgreSQL     │     │  PostgreSQL     │     │  PostgreSQL     │  │
│   │   (Replica)     │◄────│   (Leader)      │────►│   (Replica)     │  │
│   │                 │     │                 │     │                 │  │
│   │  Patroni        │     │  Patroni        │     │  Patroni        │  │
│   │  Redis (Master) │     │  Redis (Replica)│     │  etcd (DCS)     │  │
│   └─────────────────┘     └─────────────────┘     └─────────────────┘  │
│          │                        │                       │             │
│          └────────────────────────┼───────────────────────┘             │
│                                   │                                      │
│                                   ▼                                      │
│                    ┌─────────────────────────┐                          │
│                    │       HAProxy           │                          │
│                    │  (router-01, router-02) │                          │
│                    │                         │                          │
│                    │  Port 5000: RW (Leader) │                          │
│                    │  Port 5001: RO (Replicas)│                          │
│                    └─────────────────────────┘                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Connection Endpoints

| Purpose | Endpoint | Description |
|---------|----------|-------------|
| Read/Write | `router-01:5000` or `router-02:5000` | Routes to current leader |
| Read-Only | `router-01:5001` or `router-02:5001` | Load balanced across replicas |

#### Connection String Examples

```bash
# Write connection (production)
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres

# Read connection (reports)
psql -h 100.102.220.16 -p 5001 -U patroni_superuser -d postgres

# Application connection string
postgres://myapp_user:password@100.102.220.16:5000/myapp_production
```

#### Patroni Cluster Management

```bash
# Check cluster status
ssh root@100.102.220.16 'patronictl list'

# Example output:
# + Cluster: postgres-cluster -------+----+-----------+
# | Member      | Host          | Role    | State   |
# +-------------+---------------+---------+---------+
# | re-node-01  | 100.126.103.51| Replica | running |
# | re-node-03  | 100.114.117.46| Leader  | running |
# | re-node-04  | 100.115.75.119| Replica | running |
# +-------------+---------------+---------+---------+

# Manual failover
ssh root@100.102.220.16 'patronictl switchover'

# Reload configuration
ssh root@100.102.220.16 'patronictl reload postgres-cluster'
```

#### Database User Management

```sql
-- Create database
CREATE DATABASE myapp_production;

-- Create user
CREATE USER myapp_user WITH PASSWORD 'secure_password';

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE myapp_production TO myapp_user;

-- Connect to database and grant schema permissions
\c myapp_production
GRANT ALL ON SCHEMA public TO myapp_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO myapp_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO myapp_user;
```

### Redis Cluster

#### Cluster Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      REDIS CLUSTER TOPOLOGY                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────┐      ┌─────────────────────────┐         │
│   │      re-node-01         │      │      re-node-03         │         │
│   │    100.126.103.51       │      │    100.114.117.46       │         │
│   │                         │      │                         │         │
│   │   Redis Master :6379   │─────►│  Redis Replica :6379    │         │
│   │   Sentinel :26379       │◄─────│  Sentinel :26379        │         │
│   │                         │      │                         │         │
│   └─────────────────────────┘      └─────────────────────────┘         │
│              │                                  │                       │
│              └──────────────────┬───────────────┘                       │
│                                 │                                       │
│                                 ▼                                       │
│                   ┌─────────────────────────┐                          │
│                   │       HAProxy           │                          │
│                   │  (router-01, router-02) │                          │
│                   │                         │                          │
│                   │  Port 6379: Write       │                          │
│                   └─────────────────────────┘                          │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Connection Endpoints

```bash
# Connect to Redis master
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk

# Check replication status
redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO replication

# Check Sentinel status
redis-cli -h 100.126.103.51 -p 26379 SENTINEL master mymaster
```

#### Redis Management

```bash
# Check if node is master
redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO replication | grep role

# Manual failover via Sentinel
redis-cli -h 100.126.103.51 -p 26379 SENTINEL failover mymaster
```

### Database Management Tools

#### pgAdmin (Port 8081)

**Access:**
```
URL: http://100.102.220.16:8081
Email: admin@quantyra.internal
Password: xgRsJByGrGMkWRHANq62
```

**Features:**
- Visual database management
- Query tool with syntax highlighting
- ERD generation
- Backup/restore wizards
- User and permission management

**Connecting to Patroni Cluster:**
1. Right-click "Servers" → "Register" → "Server"
2. **General tab**: Name = `Quantyra Production`
3. **Connection tab**:
   - Host: `100.102.220.16`
   - Port: `5000`
   - Database: `postgres`
   - Username: `patroni_superuser`
   - Password: `2e7vBpaaVK4vTJzrKebC`
4. Click "Save"

#### Ivory (Port 8082)

**Access:**
```
URL: http://100.102.220.16:8082
```

**Features:**
- Automatic ERD generation from existing databases
- Visual schema exploration
- Export to PNG, SVG, PDF
- Schema comparison

**Connecting to Database:**
1. Click "New Connection"
2. Enter details:
   - Name: `Quantyra Production`
   - Host: `100.102.220.16`
   - Port: `5000`
   - Database: `postgres`
   - User: `patroni_superuser`
   - Password: `2e7vBpaaVK4vTJzrKebC`
3. Click "Connect"

---

## 6. Backup and Recovery

### Backup Overview

| Component | Backup Method | Frequency | Retention | Location |
|-----------|---------------|-----------|-----------|----------|
| pgAdmin data | Docker volume tarball | Daily @ 03:00 UTC | 7 days | `/backup/db-ui/` |
| Ivory data | Docker volume tarball | Daily @ 03:00 UTC | 7 days | `/backup/db-ui/` |
| PostgreSQL | pg_dump (per database) | Manual | As needed | Various |
| Coolify data | Docker volumes | Coolify managed | Varies | Docker volumes |
| Configuration | Git repository | On change | Forever | Infrastructure repo |

### pgAdmin and Ivory Backup

**Backup Script:** `/usr/local/bin/backup-db-ui.sh`

**Cron Schedule:** 03:00 UTC daily

**Manual Backup:**
```bash
# Run backup manually
/usr/local/bin/backup-db-ui.sh

# Check backup files
ls -lh /backup/db-ui/
```

**Backup Files:**
- `pgadmin-YYYYMMDD-HHMMSS.tar.gz`
- `ivory-YYYYMMDD-HHMMSS.tar.gz`

### Restore pgAdmin

```bash
# 1. Stop pgAdmin container
docker stop pgadmin

# 2. Backup current volume (just in case)
docker run --rm -v db-ui_pgadmin-data:/data -v /backup/db-ui:/backup alpine \
    tar czf /backup/pgadmin-pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

# 3. Clear and restore
docker volume rm db-ui_pgadmin-data
docker volume create db-ui_pgadmin-data

docker run --rm -v db-ui_pgadmin-data:/data -v /backup/db-ui:/backup alpine \
    tar xzf /backup/pgadmin-YYYYMMDD-HHMMSS.tar.gz -C /data

# 4. Start pgAdmin
docker start pgadmin

# 5. Verify
curl -s http://localhost:8081 | head -10
```

### Restore Ivory

```bash
# 1. Stop Ivory container
docker stop ivory

# 2. Backup current volume
docker run --rm -v db-ui_ivory-data:/data -v /backup/db-ui:/backup alpine \
    tar czf /backup/ivory-pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

# 3. Clear and restore
docker volume rm db-ui_ivory-data
docker volume create db-ui_ivory-data

docker run --rm -v db-ui_ivory-data:/data -v /backup/db-ui:/backup alpine \
    tar xzf /backup/ivory-YYYYMMDD-HHMMSS.tar.gz -C /data

# 4. Start Ivory
docker start ivory

# 5. Verify
curl -s http://localhost:8082 | head -10
```

### PostgreSQL Backup and Restore

#### Manual Database Backup

```bash
# Backup specific database
ssh root@100.102.220.16 "pg_dump -h localhost -p 5000 -U patroni_superuser -d myapp_production" > myapp_backup.sql

# Backup all databases
ssh root@100.102.220.16 "pg_dumpall -h localhost -p 5000 -U patroni_superuser" > all_databases.sql
```

#### Restore Database

```bash
# Restore specific database
ssh root@100.102.220.16 "psql -h localhost -p 5000 -U patroni_superuser -d myapp_production" < myapp_backup.sql

# Restore all databases
ssh root@100.102.220.16 "psql -h localhost -p 5000 -U patroni_superuser" < all_databases.sql
```

### Disaster Recovery

#### Complete Infrastructure Failure

1. **Provision new servers** via Ansible:
   ```bash
   ansible-playbook ansible/playbooks/provision.yml
   ```

2. **Restore databases**:
   - Install PostgreSQL/Patroni
   - Restore from pg_dump backups
   - Verify data integrity

3. **Restore Coolify**:
   - Install Docker and Coolify
   - Restore Docker volumes from backup

4. **Restore HAProxy configuration**:
   - Sync from Git repository
   - `/etc/haproxy/` configurations

5. **Update DNS**:
   - Update Cloudflare DNS with new server IPs

#### PostgreSQL Leader Failure

Automatic failover via Patroni:
- Detection: ~10 seconds
- Promotion: ~5 seconds
- HAProxy reconfiguration: ~3 seconds
- **Total downtime: ~15-20 seconds for writes, reads continue**

#### Redis Master Failure

Automatic failover via Sentinel:
- Detection: ~5 seconds
- Promotion: ~2 seconds
- HAProxy reconfiguration: ~3 seconds
- **Total downtime: ~10 seconds for writes, reads continue**

---

## 7. Network Architecture

### Traffic Flow (Updated 2026-04-02)

```
                                    USER
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLOUDFLARE (Anycast Edge)                       │
│  • Global CDN with 300+ PoPs                                           │
│  • DDoS Protection & WAF                                               │
│  • SSL: Cloudflare Edge Certificate                                    │
│  • DNS: Round-robin between router IPs                                 │
└─────────────────────────────────────────────────────────────────────────┘
                         │                              │
                         │ 50%                          │ 50%
                         ▼                              ▼
                172.93.54.112                  23.29.118.6
┌─────────────────────────────────────────────────────────────────────────┐
│                            ROUTER LAYER                                  │
│   router-01                              router-02                      │
│   • HAProxy (port 80 → HTTPS redirect)   • HAProxy (port 80 → redirect)│
│   • HAProxy (port 443 → Coolify)         • HAProxy (port 443 → Coolify) │
│   • SSL termination (all domains)        • SSL termination              │
│   • Coolify (port 8000)                  • Backup router                │
│   • Monitoring stack                                                     │
│   • pgAdmin, Ivory                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                         │                                  │
                         │ HTTP (port 80)                   │ HTTP (port 80)
                         └──────────────┬───────────────────┘
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          APP SERVER LAYER                                │
│   re-db (100.92.26.38)           re-node-02 (100.89.130.19)             │
│   • coolify-proxy (Traefik:80)    • coolify-proxy (Traefik:80)          │
│   • Docker containers             • Docker containers                   │
│   • Routes by Host header         • Routes by Host header               │
└─────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATABASE LAYER                                  │
│   PostgreSQL / Patroni Cluster (3 nodes)                                 │
│   Access: router-01:5000 (RW), router-01:5001 (RO)                      │
│                                                                          │
│   Redis Cluster with Sentinel                                            │
│   Master: re-node-01:6379, Replica: re-node-03:6379                     │
└─────────────────────────────────────────────────────────────────────────┘
```

**Key Changes:**
- HAProxy now routes ALL domains to coolify_backend
- No per-domain ACLs in HAProxy
- Coolify Traefik handles all app routing internally
- SSL certificates remain on HAProxy (not Coolify)

### Tailscale VPN

All servers are connected via Tailscale mesh VPN:

- **Network Range**: 100.64.0.0/10 (CGNAT range)
- **Encryption**: WireGuard
- **Authentication**: Tailscale admin console

**Benefits:**
- Encrypted traffic between all servers
- No VPN configuration needed
- Works behind NAT/firewalls
- Automatic key rotation

**Access:**
```bash
# Check Tailscale status
tailscale status

# Check IP
tailscale ip
```

### HAProxy Configuration

#### Current HAProxy Routing (Updated 2026-04-02)

All application domains are now routed through HAProxy to Coolify Traefik:

| Domain | Backend | Destination | Notes |
|--------|---------|-------------|-------|
| All domains | coolify_backend | re-db:80, re-node-02:80 | Routes to Coolify Traefik |
| - | not_found_backend | 404 response | Fallback for unmatched routes |

**Architecture:**
```
Cloudflare → HAProxy (SSL termination) → Coolify Traefik (HTTP) → Docker containers
```

HAProxy terminates SSL for all domains with existing certificates, then routes plain HTTP traffic to Coolify Traefik on port 80.

#### HAProxy Configuration Files

```
/etc/haproxy/
├── haproxy.cfg              # Main configuration
├── certs/                   # SSL certificates
│   ├── default.pem
│   ├── jonathanloescher.com.pem
│   ├── staging.jonathanloescher.com.pem
│   ├── rentalfixer.app.pem
│   ├── staging.rentalfixer.app.pem
│   ├── hooks.quantyralabs.cc.pem
│   └── ...
└── domains/
    ├── web_http.cfg         # HTTP frontend (redirects to HTTPS)
    ├── web_https.cfg        # HTTPS frontend (routes to coolify_backend)
    ├── web_backends.cfg     # coolify_backend + not_found_backend
    └── registry.conf        # Empty (Coolify manages domains)
```

#### Current Backend Configuration

```haproxy
# From /etc/haproxy/domains/web_backends.cfg

backend coolify_backend
    mode http
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200-499
    option forwardfor
    server re-db-coolify 100.92.26.38:80 check
    server re-node-02-coolify 100.89.130.19:80 check

backend not_found_backend
    mode http
    http-request deny deny_status 404
```

#### HAProxy Management

```bash
# Check HAProxy status
systemctl status haproxy

# Validate configuration
haproxy -c -f /etc/haproxy/haproxy.cfg

# Reload HAProxy
systemctl reload haproxy

# View HAProxy stats
# Open http://100.102.220.16:8404/stats
# Username: admin
# Password: jFNeZ2bhfrTjTK7aKApD
```

### Client IP Forwarding

Real client IPs are forwarded through the entire stack:

```
Client IP: 1.2.3.4

Cloudflare receives request
    ↓ Adds CF-Connecting-IP: 1.2.3.4
    
HAProxy receives request
    ↓ Sets X-Forwarded-For: 1.2.3.4
    ↓ Sets X-Real-IP: 1.2.3.4
    
Traefik/nginx receives request
    ↓ REMOTE_ADDR = 1.2.3.4
    
Application receives real client IP
```

---

## 8. Security Configuration

### Firewall Rules (UFW)

Each server has UFW configured:

```bash
# Default policies
ufw default deny incoming
ufw default allow outgoing

# Tailscale network (fully trusted)
ufw allow from 100.64.0.0/10

# SSH (Tailscale only, rate-limited)
ufw limit in on tailscale0 to any port 22

# Application ports (from routers only)
ufw allow from 100.102.220.16 to any port 8100:8199
ufw allow from 100.116.175.9 to any port 8100:8199

# Monitoring ports (from Prometheus only)
ufw allow from 100.102.220.16 to any port 9113
```

### SSH Configuration

**Key-based authentication only:**

```bash
# /etc/ssh/sshd_config
PasswordAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password
```

**SSH Keys Distributed:**
- `id_vps` - Primary access key
- `root@re-db` - Server-to-server from re-db
- `root@router-01` - Server-to-server from router-01
- `root@router-02` - Server-to-server from router-02

**Tailscale SSH: DISABLED** (using standard SSH keys)

### Cloudflare WAF

5 security rules applied to all proxied domains:

| Priority | Rule | Action |
|----------|------|--------|
| 1 | Allow legitimate bots | Allow |
| 2 | Challenge suspicious traffic | Managed Challenge |
| 3 | Challenge known attackers | Managed Challenge |
| 4 | Challenge rate-limited requests | Managed Challenge |
| 5 | Block SQL injection attempts | Block |

### SSL/TLS Configuration

- **Minimum TLS Version**: 1.2
- **HSTS**: Enabled (max-age=31536000; includeSubDomains; preload)
- **OCSP Stapling**: Enabled
- **Certificate Type**: Let's Encrypt via certbot
- **Challenge Method**: DNS-01 (Cloudflare)

### Security Headers (HAProxy)

```haproxy
http-response set-header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
http-response set-header X-Content-Type-Options "nosniff"
http-response set-header X-Frame-Options "SAMEORIGIN"
http-response set-header X-XSS-Protection "1; mode=block"
http-response set-header Referrer-Policy "strict-origin-when-cross-origin"
http-response set-header Permissions-Policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"
```

---

## 9. Operational Procedures

### Common Maintenance Tasks

#### Update Server Packages

```bash
# Check available updates (from dashboard)
# Or manually:
ssh root@<server_ip> "apt update && apt list --upgradable"

# Install security updates only
ssh root@<server_ip> "apt upgrade -y --with-new-pkgs"

# Full upgrade (use with caution)
ssh root@<server_ip> "apt full-upgrade -y"
```

#### Restart Services

```bash
# Restart HAProxy
ssh root@100.102.220.16 "systemctl reload haproxy"
ssh root@100.116.175.9 "systemctl reload haproxy"

# Restart PostgreSQL (via Patroni)
ssh root@100.114.117.46 "systemctl restart patroni"

# Restart Redis
ssh root@100.126.103.51 "systemctl restart redis-server"

# Restart Coolify
ssh root@100.102.220.16 "docker restart coolify"
```

#### Check Service Status

```bash
# All servers
ansible all -m ping

# Specific service
ssh root@100.102.220.16 "systemctl status haproxy"
ssh root@100.102.220.16 "systemctl status patroni"
ssh root@100.102.220.16 "systemctl status redis-server"

# Docker services
ssh root@100.102.220.16 "docker ps"
ssh root@100.92.26.38 "docker ps"
```

### Monitoring and Alerting

#### Access Monitoring Tools

| Tool | URL | Purpose |
|------|-----|---------|
| Prometheus | http://100.102.220.16:9090 | Metrics query |
| Grafana | http://100.102.220.16:3000 | Dashboards |
| Alertmanager | http://100.102.220.16:9093 | Alert management |
| HAProxy Stats | http://100.102.220.16:8404/stats | Load balancer status |

#### Key Metrics to Monitor

- **HAProxy**: `haproxy_frontend_current_sessions`, `haproxy_backend_http_responses_total`
- **PostgreSQL**: `pg_stat_database`, replication lag, connection count
- **Redis**: `connected_clients`, `used_memory`, `keyspace_hits/misses`
- **System**: CPU, memory, disk, network

#### Alert Rules

Key alerts configured in Prometheus:

- `PatroniClusterDown` - No leader in cluster
- `PatroniReplicationLag` - Replication lag > 30 seconds
- `RedisMasterDown` - No Redis master
- `HAProxyBackendDown` - Backend server unhealthy
- `PHPFPMPoolExhausted` - Less than 2 idle workers

### Health Check Commands

```bash
# Dashboard health
curl -s http://100.102.220.16:8080/health

# PostgreSQL cluster
patronictl list

# Redis status
redis-cli -h 100.126.103.51 -p 6379 -a <password> PING

# HAProxy stats
curl -s http://100.102.220.16:8404/stats

# Check all servers
ansible all -m shell -a "uptime"
```

### Log Locations

| Service | Log Path |
|---------|----------|
| HAProxy | `journalctl -u haproxy -f` |
| Patroni | `journalctl -u patroni -f` |
| PostgreSQL | `/var/log/postgresql/` |
| Redis | `/var/log/redis/redis-server.log` |
| PHP-FPM | `journalctl -u php8.5-fpm -f` |
| Nginx | `/var/log/nginx/error.log` |
| Dashboard | `journalctl -u dashboard -f` |
| Coolify | `docker logs coolify -f` |

---

## 10. Migration Notes

### Deprecated Components

#### Flask PaaS Dashboard (Port 8080)

**Status:** DEPRECATED

The custom Flask-based PaaS dashboard has been deprecated in favor of Coolify. It remains available for reference but is no longer actively developed.

**What was managed:**
- Application deployment (Laravel, Next.js, Svelte, Python, Go)
- Domain provisioning via Cloudflare
- Database creation on Patroni cluster
- Secrets management with SOPS
- Deployment history and rollback

**Migration Path:**
- New applications should use Coolify
- Existing deployments continue to work via HAProxy
- Database management can still use pgAdmin

#### Legacy PHP-FPM Deployments

**Status:** REMOVED

All legacy PHP-FPM deployments from `/opt/apps/` have been removed:

| App | Path | Status |
|-----|------|--------|
| jonathanloescher | `/opt/apps/jonathanloescher` | Removed |
| rentalfixer | `/opt/apps/rentalfixer` | Removed |

**Note:** HAProxy routing for these apps remains for reference, but backend servers are not running.

### HAProxy Routing Changes

**Before (2026-03):**
- All apps routed through HAProxy to PHP-FPM backends
- Per-domain SSL certificates
- Manual nginx + PHP-FPM configuration

**After (2026-04-02):**
- HAProxy routes ALL domains to coolify_backend
- Coolify proxy (Traefik) handles all application routing
- Container-based deployments
- SSL termination at HAProxy, HTTP internally to Coolify

### Current HAProxy Routing State (Updated 2026-04-02)

All domains route to Coolify Traefik:

```haproxy
# From /etc/haproxy/domains/web_backends.cfg

backend coolify_backend
    mode http
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200-499
    option forwardfor
    server re-db-coolify 100.92.26.38:80 check
    server re-node-02-coolify 100.89.130.19:80 check

backend not_found_backend
    mode http
    http-request deny deny_status 404
```

**Note:** HAProxy registry.conf is empty. Domain management is handled by Coolify.

### How to Migrate Apps to Coolify

1. **Create Coolify Application**:
   - Go to Coolify UI (http://100.102.220.16:8000)
   - Create new project and application
   - Connect Git repository

2. **Configure Database**:
   - Option A: Use external Patroni cluster (recommended for production)
   - Option B: Let Coolify provision managed PostgreSQL container

3. **Configure Environment**:
   - Set environment variables
   - Configure domains
   - SSL auto-provisioned

4. **Deploy**:
   - Click "Deploy"
   - Monitor deployment logs
   - Verify application works

5. **Update DNS** (if needed):
   - Update Cloudflare DNS to point to Coolify proxy
   - Or use Coolify's built-in DNS integration

6. **Remove Legacy HAProxy Routing**:
   - Remove domain from `/etc/haproxy/domains/registry.conf`
   - Rebuild HAProxy config
   - Reload HAProxy

---

## 11. Troubleshooting Guide

### Common Issues

#### Dashboard Can't Connect to Servers

```bash
# Verify Tailscale connection
tailscale status

# Test connectivity
ping 100.102.220.16

# Check SSH key
ls -la ~/.ssh/id_vps

# Test SSH
ssh -i ~/.ssh/id_vps root@100.102.220.16
```

#### HAProxy Shows 503 Service Unavailable

```bash
# Check backend health
curl -s http://100.102.220.16:8404/stats

# Check if app servers are running
ssh root@100.92.26.38 "docker ps"
ssh root@100.89.130.19 "docker ps"

# Check HAProxy logs
journalctl -u haproxy -f
```

#### PostgreSQL Connection Refused

```bash
# Check Patroni status
patronictl list

# Check if HAProxy is routing correctly
ssh root@100.102.220.16 "nc -zv localhost 5000"

# Check PostgreSQL logs
journalctl -u patroni -f
```

#### Redis Connection Issues

```bash
# Check Redis master
redis-cli -h 100.126.103.51 -p 6379 -a <password> PING

# Check Sentinel
redis-cli -h 100.126.103.51 -p 26379 SENTINEL master mymaster

# Check HAProxy routing
ssh root@100.102.220.16 "nc -zv localhost 6379"
```

#### Coolify Deployment Fails

```bash
# Check Coolify logs
docker logs coolify -f

# Check coolify-proxy status
docker logs coolify-proxy -f

# Check target server Docker
ssh root@100.92.26.38 "docker ps -a"
ssh root@100.92.26.38 "docker logs <container_name>"
```

#### SSL Certificate Issues

```bash
# Check certificate files
ls -la /etc/haproxy/certs/

# Check certificate expiration
openssl x509 -in /etc/haproxy/certs/rentalfixer.app.pem -noout -dates

# Renew certificate manually
certbot renew --dns-cloudflare --dns-cloudflare-credentials /root/.cloudflare.ini
```

### Diagnostic Commands

```bash
# Check all server connectivity
ansible all -m ping

# Check system resources
ansible all -m shell -a "free -h && df -h"

# Check running services
ansible all -m shell -a "systemctl list-units --type=service --state=running"

# Check Docker containers
ansible apps -m shell -a "docker ps"

# Check open ports
ssh root@<server> "ss -tlnp"

# Check firewall rules
ssh root@<server> "ufw status numbered"

# Check HAProxy stats
curl -s http://100.102.220.16:8404/stats | grep -A 5 "rentalfixer"
```

---

## 12. Credentials Reference

### Primary Credentials

| Service | URL | Username | Password |
|---------|-----|----------|----------|
| pgAdmin | http://100.102.220.16:8081 | admin@quantyra.internal | xgRsJByGrGMkWRHANq62 |
| HAProxy Stats | http://100.102.220.16:8404/stats | admin | jFNeZ2bhfrTjTK7aKApD |
| Coolify | http://100.102.220.16:8000 | (set during setup) | (set during setup) |
| Grafana | http://100.102.220.16:3000 | admin | admin |

### Database Credentials

| Service | Host | Port | Username | Password |
|---------|------|------|----------|----------|
| PostgreSQL (Superuser) | 100.102.220.16 | 5000 | patroni_superuser | 2e7vBpaaVK4vTJzrKebC |
| Redis | 100.102.220.16 | 6379 | - | CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk |

### API Tokens

| Service | Purpose | Token/ID |
|---------|---------|----------|
| Cloudflare API | DNS/WAF management | zf5ncwuOaaXz2IJ1BVBu8myf0HQt5IxkPje_Rm1V |
| Cloudflare Zone (xotec.io) | Zone management | 26470f68ef4dbbf7bf5a770630aa2a97 |
| Cloudflare Zone (rentalfixer.app) | Zone management | d565e98b12effe08e530da729b82c0b9 |

### SSH Access

**Primary SSH Key:** `~/.ssh/id_vps`

```bash
# Connect to any server
ssh -i ~/.ssh/id_vps root@<tailscale_ip>

# Example
ssh -i ~/.ssh/id_vps root@100.102.220.16
```

---

## Appendix A: File Paths Reference

### Configuration Files

| Component | Path | Purpose |
|-----------|------|---------|
| HAProxy Main | `/etc/haproxy/haproxy.cfg` | Main HAProxy configuration |
| HAProxy HTTP | `/etc/haproxy/domains/web_http.cfg` | HTTP frontend |
| HAProxy HTTPS | `/etc/haproxy/domains/web_https.cfg` | HTTPS frontend |
| HAProxy Backends | `/etc/haproxy/domains/web_backends.cfg` | Application backends |
| HAProxy Registry | `/etc/haproxy/domains/registry.conf` | Domain mapping |
| HAProxy Certs | `/etc/haproxy/certs/` | SSL certificates |
| Patroni Config | `/etc/patroni/config.yml` | Patroni cluster configuration |
| Redis Config | `/etc/redis/redis.conf` | Redis server configuration |
| Sentinel Config | `/etc/redis/sentinel.conf` | Redis Sentinel configuration |
| Prometheus Config | `/etc/prometheus/prometheus.yml` | Prometheus configuration |
| Prometheus Alerts | `/etc/prometheus/alerts.yml` | Alert rules |
| Grafana Dashboards | `/var/lib/grafana/dashboards/` | Dashboard JSON files |

### Backup Locations

| Component | Path |
|-----------|------|
| pgAdmin/Ivory backups | `/backup/db-ui/` |
| PostgreSQL dumps | Various (manual) |
| Configuration repo | `/root/infrastructure/` |

### Log Files

| Service | Path |
|---------|------|
| System logs | `/var/log/syslog` |
| Auth logs | `/var/log/auth.log` |
| HAProxy logs | `journalctl -u haproxy` |
| PostgreSQL logs | `/var/log/postgresql/` |
| Redis logs | `/var/log/redis/redis-server.log` |
| PHP-FPM logs | `/var/log/php8.5-fpm/` |
| Nginx logs | `/var/log/nginx/` |

---

## Appendix B: Useful Commands Quick Reference

### Ansible

```bash
ansible all -m ping                          # Test all servers
ansible apps -m shell -a "docker ps"         # Check Docker on app servers
ansible-playbook ansible/playbooks/provision.yml  # Provision servers
```

### HAProxy

```bash
haproxy -c -f /etc/haproxy/haproxy.cfg       # Validate config
systemctl reload haproxy                      # Reload configuration
journalctl -u haproxy -f                      # View logs
```

### PostgreSQL/Patroni

```bash
patronictl list                              # List cluster status
patronictl switchover                        # Manual failover
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -l  # List databases
```

### Redis

```bash
redis-cli -h 100.126.103.51 -p 6379 -a <password> PING  # Test connection
redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO replication  # Check replication
redis-cli -h 100.126.103.51 -p 26379 SENTINEL master mymaster  # Check Sentinel
```

### Docker

```bash
docker ps                                    # List running containers
docker logs <container> -f                   # View container logs
docker exec -it <container> bash             # Shell into container
docker-compose -f /opt/db-ui/docker-compose.yml ps  # Check db-ui stack
```

### Monitoring

```bash
# Prometheus query examples
curl -s 'http://100.102.220.16:9090/api/v1/query?query=up' | jq
curl -s 'http://100.102.220.16:9090/api/v1/query?query=haproxy_frontend_current_sessions' | jq

# Check alertmanager alerts
curl -s http://100.102.220.16:9093/api/v1/alerts | jq
```

---

## Appendix C: Architecture Decision Records

### ADR-001: Coolify as Primary PaaS

**Date:** 2026-04-01

**Status:** Accepted

**Context:**
The custom Flask-based PaaS dashboard (port 8080) required extensive maintenance and lacked features provided by modern PaaS solutions.

**Decision:**
Adopt Coolify as the primary deployment platform for all new applications.

**Consequences:**
- Positive: Modern UI, active development, container-based deployments, better DX
- Negative: Migration effort for existing apps, learning curve
- Neutral: Flask dashboard remains available for reference

### ADR-002: Consolidated HAProxy Frontend

**Date:** 2026-03

**Status:** Accepted

**Context:**
Multiple HAProxy frontends on port 443 caused SNI routing issues.

**Decision:**
Use a single frontend with multiple certificates, routing by Host header.

**Consequences:**
- Positive: Reliable SNI routing, simpler configuration
- Negative: All certificates in one bind line

### ADR-003: Tailscale as VPN Layer

**Date:** 2026-03

**Status:** Accepted

**Context:**
Server-to-server communication needed encryption without complex VPN setup.

**Decision:**
Use Tailscale mesh VPN for all inter-server communication.

**Consequences:**
- Positive: Zero-config VPN, automatic encryption, works behind NAT
- Negative: External dependency on Tailscale service

### ADR-004: Patroni for PostgreSQL HA

**Date:** 2025 (Initial setup)

**Status:** Accepted

**Context:**
PostgreSQL cluster needed automatic failover with minimal downtime.

**Decision:**
Use Patroni with etcd DCS for PostgreSQL high availability.

**Consequences:**
- Positive: Automatic failover, read/write splitting, well-tested solution
- Negative: Complexity, additional etcd cluster

---

*Document created: 2026-04-01*
*Last updated: 2026-04-02*
*Maintained by: Infrastructure Team*