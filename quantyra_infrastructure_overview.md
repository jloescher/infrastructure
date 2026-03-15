# Quantyra Infrastructure Overview - Current State

**Last Updated**: 2026-03-15  
**Data Source**: Live server reports

---

## Environment Summary

### DB Servers (3 nodes)
| Server | Tailscale IP | Public IP | Specs | Status |
|--------|-------------|-----------|-------|--------|
| re-node-01 | 100.126.103.51 | 104.225.216.26 | 8 vCPU, 32GB RAM, 640GB NVMe | ✅ Online |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | 8 vCPU, 32GB RAM, 640GB NVMe | ✅ Online |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | 8 vCPU, 32GB RAM, 640GB NVMe | ✅ Online |

### Routers (2 nodes)
| Server | Tailscale IP | Public IP | Specs | Status |
|--------|-------------|-----------|-------|--------|
| router-01 | 100.102.220.16 | 172.93.54.112 | 2 vCPU, 8GB RAM, 160GB SSD | ✅ Online |
| router-02 | 100.116.175.9 | 23.29.118.6 | 2 vCPU, 8GB RAM, 160GB SSD | ✅ Online |

### App Servers (2 nodes)
| Server | Tailscale IP | Public IP | Specs | Status |
|--------|-------------|-----------|-------|--------|
| re-db | 100.92.26.38 | 208.87.128.115 | 12 vCPU, 48GB RAM, 720GB NVMe | ✅ Online |
| re-node-02 | 100.101.39.22 | 23.29.118.8 | 12 vCPU, 48GB RAM, 720GB NVMe | ✅ Online (63 days) |

---

## PostgreSQL / Patroni

### Cluster Status
- **Cluster Name**: `quantyra_pg`
- **PostgreSQL Version**: 18.3
- **Patroni**: Running on all 3 nodes
- **HA**: Verified failover working

### Current Cluster Topology
```
re-node-01 (Leader or Replica)
    ├── re-node-03 (Replica)
    └── re-node-04 (Replica)
```

### Connection Endpoints (via HAProxy)

| Purpose | Primary Router | Secondary Router |
|---------|---------------|------------------|
| Write | 100.102.220.16:5000 | 100.116.175.9:5000 |
| Read | 100.102.220.16:5001 | 100.116.175.9:5001 |

### PostgreSQL Configuration
- **max_connections**: 300
- **shared_buffers**: 8GB
- **effective_cache_size**: 24GB
- **work_mem**: 64MB
- **wal_level**: replica
- **max_wal_senders**: 10

### Running Services (per node)
- `patroni.service` - HA cluster manager
- `postgresql` - Database server
- `pgbouncer.service` - Connection pooling (re-node-01 only)
- `postgres_exporter.service` - Prometheus metrics
- `node_exporter.service` - Node metrics

---

## Redis

### Current Topology
```
re-node-01 (Master) - 100.126.103.51:6379
    └── re-node-03 (Replica) - 100.114.117.46:6379
```

### Configuration
- **Version**: Redis 7
- **Max Memory**: 4GB per node
- **Eviction Policy**: allkeys-lru
- **Persistence**: RDB + AOF enabled
- **Auth**: Password protected

### Security
- `requirepass` enabled
- Renamed dangerous commands (CONFIG, FLUSHDB, FLUSHALL, KEYS)
- Protected mode enabled

### Sentinel (Planned)
- **Status**: Not yet configured
- **Target**: Install on router-01, router-02, and one DB node

---

## HAProxy

### router-01
- **Version**: 2.8
- **Ports**: 5000 (PG Write), 5001 (PG Read), 8404 (Stats)
- **Backends**: PostgreSQL cluster

### router-02
- **Version**: 2.8.16
- **Ports**: 5000 (PG Write), 5001 (PG Read), 80 (HTTP), 443 (HTTPS), 8405 (Metrics)
- **Backends**: PostgreSQL cluster + App servers

### Backend Configuration
```haproxy
# PostgreSQL Write
backend pg_primary
    server re-node-01 100.126.103.51:5432 check port 8008
    server re-node-03 100.114.117.46:5432 check port 8008
    server re-node-04 100.115.75.119:5432 check port 8008

# PostgreSQL Read
backend pg_replicas
    server re-node-03 100.114.117.46:5432 check port 8008
    server re-node-04 100.115.75.119:5432 check port 8008
    server re-node-01 100.126.103.51:5432 check port 8008 backup

# Web HTTP
backend apps_http
    server app1 100.92.26.38:80 check
    server app2 100.101.39.22:80 check

# Web HTTPS
backend apps_https
    server app1 100.92.26.38:443 check
    server app2 100.101.39.22:443 check
```

---

## etcd

### Location
- **Host**: router-01
- **Client Port**: 2379
- **Peer Port**: 2380
- **Purpose**: Patroni DCS (Distributed Configuration Store)

---

## Monitoring

### Prometheus (router-01)
- **Port**: 9090
- **Retention**: 30d
- **Targets**: All servers via node_exporter, postgres_exporter

### Grafana (router-01)
- **Port**: 3000
- **Status**: Running

### Exporters
| Server | node_exporter | postgres_exporter | redis_exporter |
|--------|---------------|-------------------|----------------|
| re-node-01 | ✅ :9100 | ✅ :9187 | ❌ Not installed |
| re-node-03 | ✅ :9100 | ✅ :9187 | ❌ Not installed |
| re-node-04 | ✅ :9100 | ✅ :9187 | N/A |
| router-01 | ✅ :9100 | N/A | N/A |
| router-02 | ✅ :9100 | N/A | N/A |
| re-db | ❌ Not installed | N/A | N/A |
| re-node-02 | ❌ Not installed | N/A | N/A |

---

## Security

### Firewall (UFW)
- **Status**: Active on all servers
- **Default Policy**: Deny incoming, Allow outgoing

### SSH
- **Status**: Key-based auth on most servers
- ⚠️ **Issue**: router-02 has `PermitRootLogin yes` (should be `prohibit-password`)

### fail2ban
- **Status**: Running on DB servers

---

## Backups

### Status: ⚠️ NOT CONFIGURED

**Critical Action Required**

| Service | Local Backup | S3 Sync | Cron Job |
|---------|-------------|---------|----------|
| PostgreSQL | ❌ | ❌ | ❌ |
| Redis | ❌ | ❌ | ❌ |
| Configs | ❌ | ❌ | ❌ |

**Recommended Setup**:
1. pgBackRest for PostgreSQL
2. Redis RDB daily snapshots
3. S3 sync for offsite storage

---

## Applications

### Current State
- **re-db**: Ports 80, 443, 8001, 9090 open (no Docker)
- **re-node-02**: Ports 80, 443 open (no Docker)

### Required Actions
1. Install Docker on app servers
2. Identify current applications
3. Containerize if needed
4. Deploy via Docker Compose

---

## Network

### Tailscale
- **Network**: 100.64.0.0/10
- **Status**: All nodes connected
- **Exit Node**: None configured

### Public IPs
| Server | Public IP | Provider |
|--------|-----------|----------|
| re-node-01 | 104.225.216.26 | SSD Nodes |
| re-node-03 | 172.93.54.145 | SSD Nodes |
| re-node-04 | 172.93.54.122 | SSD Nodes |
| router-01 | 172.93.54.112 | SSD Nodes |
| router-02 | 23.29.118.6 | SSD Nodes |
| re-db | 208.87.128.115 | SSD Nodes |
| re-node-02 | 23.29.118.8 | SSD Nodes |

---

## Upgrade Notes

### PostgreSQL Rolling Updates
1. Update replicas first (re-node-03, re-node-04)
2. Switchover leader
3. Update former leader (re-node-01)
4. Do NOT use `postgresql@18-main.service` directly after Patroni takeover

### Kernel Updates
- re-node-01, re-node-03, re-node-04: Running 6.8.0-106-generic
- router-01, router-02: Running 6.8.0-85-generic
- re-db, re-node-02: Running 6.8.0-90-generic

---

## Data Collection

Run the data collection script to generate updated reports:

```bash
# On each server
bash /path/to/collect_quantyra_infra_report.sh
```

Reports are stored in `reports/` directory.

---

## See Also

- [Action Items](action_items.md) - Tasks to complete infrastructure setup
- [Runbook](runbook.md) - Operational procedures
- [Disaster Recovery](disaster_recovery.md) - Backup and recovery procedures
- [Deployment Guide](deployment.md) - How to deploy applications