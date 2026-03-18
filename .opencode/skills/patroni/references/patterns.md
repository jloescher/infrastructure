# Patroni Patterns

## Contents
- Connection Patterns
- Failover Patterns
- Monitoring Patterns
- Configuration Patterns

## Connection Patterns

### ALWAYS Use HAProxy Ports

**When:** Any application or script connecting to PostgreSQL.

```python
# GOOD - Use HAProxy ports
conn = psycopg2.connect(
    host="100.102.220.16",
    port=5000,  # Write via HAProxy
    user="patroni_superuser"
)
```

### WARNING: Direct Node Connections

**The Problem:**

```python
# BAD - Hardcoded node IP
conn = psycopg2.connect(
    host="100.126.103.51",  # re-node-01 - may not be leader!
    port=5432,
    user="patroni_superuser"
)
```

**Why This Breaks:**
1. Node may be a replica - writes will fail
2. After failover, old leader becomes replica
3. Connection strings become stale instantly

**The Fix:**

Use HAProxy endpoints or service discovery. See the **haproxy** skill for routing configuration.

## Failover Patterns

### Planned Switchover (Zero Downtime)

```bash
# 1. Verify cluster health
patronictl list

# 2. Initiate graceful switchover
patronictl switchover

# 3. Verify new leader elected
patronictl list
```

### WARNING: Force Failover

**The Problem:**

```bash
# BAD - Forcing failover without checking etcd
patronictl failover --force
```

**Why This Breaks:**
1. May cause split-brain if etcd is partitioned
2. Data loss risk if WAL hasn't replicated
3. Violates Patroni's safety guarantees

**The Fix:**

Always prefer `switchover` for planned maintenance. Only use `failover` in true disaster scenarios.

## Monitoring Patterns

### Replication Lag Check

```bash
# Check lag on all replicas
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c \
    "SELECT client_addr, 
            pg_size_pretty(pg_wal_lsn_diff(sent_lsn, replay_lsn)) as lag
     FROM pg_stat_replication;"
```

### etcd Cluster Health

```bash
# Verify all 3 nodes are in consensus
etcdctl member list
etcdctl endpoint health
```

## Configuration Patterns

### Dynamic Configuration Updates

```bash
# Update runtime parameter across cluster
patronictl edit-config

# Reload configuration without restart
patronictl reload
```

### WARNING: Editing PostgreSQL Configs Directly

**The Problem:**

```bash
# BAD - Editing postgresql.conf directly
vim /etc/postgresql/16/main/postgresql.conf
systemctl restart postgresql
```

**Why This Breaks:**
1. Patroni manages configuration - changes will be overwritten
2. Direct restart bypasses Patroni's safety checks
3. Cluster may elect a new leader unexpectedly

**The Fix:**

```bash
# GOOD - Use Patroni to manage config
patronictl edit-config
patronictl reload
# Or restart specific node
patronictl restart <cluster-name> <node-name>