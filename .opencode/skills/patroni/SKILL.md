---
name: patroni
description: Manages Patroni PostgreSQL high availability and etcd DCS. Use when checking cluster status, performing failovers, debugging replication lag, configuring Patroni, or troubleshooting etcd consensus issues.
---

# Patroni Skill

Patroni manages a 3-node PostgreSQL HA cluster with automatic failover via etcd. All connections go through HAProxy (ports 5000/5001) - never connect directly to PostgreSQL nodes.

## Quick Start

### Check Cluster Status

```bash
ssh root@100.102.220.16 'patronictl list'
```

### Initiate Failover

```bash
ssh root@100.102.220.16 'patronictl switchover'
```

### Check etcd Health

```bash
ssh root@100.102.220.16 'etcdctl member list'
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Leader | Write operations | Port 5000 via HAProxy |
| Replica | Read-only queries | Port 5001 via HAProxy |
| etcd DCS | Leader election | Runs on all 3 nodes |
| patronictl | CLI management | `patronictl list` |
| Switchover | Planned failover | `patronictl switchover` |
| Failover | Automatic recovery | Triggered by health checks |

## Common Patterns

### Read/Write Split

**When:** Application needs to separate read and write traffic.

```python
# Write to leader
write_conn = psycopg2.connect(
    host="100.102.220.16",
    port=5000,  # RW port via HAProxy
    user="patroni_superuser",
    password=PG_PASSWORD
)

# Read from replicas
read_conn = psycopg2.connect(
    host="100.102.220.16",
    port=5001,  # RO port load balances replicas
    user="patroni_superuser",
    password=PG_PASSWORD
)
```

### Health Check Before Operations

**When:** Before running migrations or maintenance.

```bash
# Verify leader is healthy
patronictl list | grep "Leader" | grep "running"

# Check replication lag
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c \
    "SELECT client_addr, state, sync_state FROM pg_stat_replication;"
```

## See Also

- [patterns](references/patterns.md)
- [workflows](references/workflows.md)

## Related Skills

- **postgresql** - Direct PostgreSQL operations and queries
- **haproxy** - Load balancer routing traffic to Patroni cluster
- **ansible** - Server provisioning and configuration management