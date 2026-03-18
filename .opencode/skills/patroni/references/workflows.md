# Patroni Workflows

## Contents
- Planned Failover Workflow
- Adding a Replica Node
- Debugging Replication Lag
- Disaster Recovery
- etcd Recovery

## Planned Failover Workflow

Copy this checklist and track progress:

- [ ] Step 1: Check cluster health with `patronictl list`
- [ ] Step 2: Verify replication lag is near zero
- [ ] Step 3: Run `patronictl switchover`
- [ ] Step 4: Verify application reconnects to new leader
- [ ] Step 5: Confirm old leader becomes replica

```bash
# Pre-check: All nodes running?
ssh root@100.102.220.16 'patronictl list'

# Verify lag < 1MB on all replicas
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c \
    "SELECT client_addr, 
            pg_wal_lsn_diff(sent_lsn, replay_lsn) as lag_bytes
     FROM pg_stat_replication;"

# Execute switchover (interactive prompt)
ssh root@100.102.220.16 'patronictl switchover'

# Post-check: New leader elected?
ssh root@100.102.220.16 'patronictl list'
```

## Debugging Replication Lag

```bash
# 1. Identify lagging replica
patronictl list

# 2. Check replication stats on leader
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c \
    "SELECT * FROM pg_stat_replication;"

# 3. Check WAL archive status
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c \
    "SELECT * FROM pg_stat_archiver;"

# 4. Verify network between nodes
ping 100.114.117.46  # re-node-03 from re-node-01
```

## Adding a Replica Node

Copy this checklist and track progress:

- [ ] Step 1: Prepare new server with PostgreSQL installed
- [ ] Step 2: Copy Patroni config from existing node
- [ ] Step 3: Add to etcd cluster
- [ ] Step 4: Start Patroni service
- [ ] Step 5: Verify streaming replication

```bash
# On existing node: Get base backup
pg_basebackup -h 100.102.220.16 -p 5000 -U replicator \
    -D /var/lib/postgresql/16/main -Fp -Xs -P

# On new node: Start Patroni
systemctl start patroni

# Verify: Check cluster status
patronictl list
```

## Disaster Recovery: Single Node Failure

### WARNING: Never Bootstrap Without etcd Consensus

**The Problem:**

```bash
# BAD - Forcing bootstrap with corrupt/missing etcd
patronictl bootstrap --force
```

**Why This Breaks:**
1. May create divergent timelines
2. Data loss when nodes rejoin
3. Split-brain scenario

**The Fix:**

```bash
# 1. Verify etcd quorum exists
etcdctl member list

# 2. If 2 of 3 etcd nodes healthy, remove failed node
etcdctl member remove <member-id>

# 3. Clean data directory on failed node
rm -rf /var/lib/postgresql/16/main/*

# 4. Rejoin as new replica
patronictl bootstrap
```

## etcd Recovery Workflow

Copy this checklist and track progress:

- [ ] Step 1: Check etcd cluster health on all 3 nodes
- [ ] Step 2: If quorum lost, restore from backup or rebuild
- [ ] Step 3: Verify `patronictl list` works on all nodes

```bash
# Check etcd on all nodes
for node in 100.126.103.51 100.114.117.46 100.115.75.119; do
    echo "=== $node ==="
    ssh root@$node 'etcdctl member list'
done

# If etcd is broken on one node, re-add it
etcdctl member add re-node-04 --peer-urls=http://100.115.75.119:2380
```

## Integration with HAProxy

See the **haproxy** skill for configuring PostgreSQL backend checks. Key points:

```haproxy
# HAProxy checks Patroni REST API for leader/replica detection
backend postgresql_write
    option httpchk GET /leader
    server re-node-01 100.126.103.51:5432 check port 8008
    server re-node-03 100.114.117.46:5432 check port 8008
    server re-node-04 100.115.75.119:5432 check port 8008