# etcd Cluster Configuration

## Overview

3-node etcd cluster for Patroni DCS (Distributed Configuration Store).

## Cluster Members

| Node | Name | Client URL | Peer URL |
|------|------|------------|----------|
| router-01 | router1-etcd | 100.102.220.16:2379 | 100.102.220.16:2380 |
| router-02 | router2-etcd | 100.116.175.9:2379 | 100.116.175.9:2380 |
| re-node-04 | renode04-etcd | 100.115.75.119:2379 | 100.115.75.119:2380 |

## Health Check

```bash
# Check cluster health
etcdctl endpoint health --cluster -w table

# Check member list
etcdctl member list -w table

# Check cluster status
etcdctl endpoint status --cluster -w table
```

## Failover Scenarios

### Single Node Failure
- Cluster remains operational (2/3 nodes = quorum)
- Patroni continues to function normally
- Replace failed node and rejoin cluster

### Two Node Failure
- Cluster loses quorum, becomes read-only
- Patroni cannot perform leader election
- Restore at least one failed node to recover

## Adding/Removing Members

### Add Member
```bash
# On existing cluster member
etcdctl member add new-node-name --peer-urls=http://NEW_IP:2380

# On new node, start with:
--initial-cluster-state=existing
--initial-cluster=existing-members...
```

### Remove Member
```bash
etcdctl member remove MEMBER_ID
```

## Backup

```bash
# Snapshot backup
etcdctl snapshot save /backup/etcd-snapshot.db

# Verify snapshot
etcdctl snapshot status /backup/etcd-snapshot.db -w table
```

## Restore from Backup

```bash
# Stop etcd on all nodes
# On first node:
etcdctl snapshot restore /backup/etcd-snapshot.db \
  --name router1-etcd \
  --initial-cluster router1-etcd=http://100.102.220.16:2380,router2-etcd=http://100.116.175.9:2380,renode04-etcd=http://100.115.75.119:2380 \
  --initial-cluster-token quantyra-etcd-cluster \
  --initial-advertise-peer-urls http://100.102.220.16:2380

# Copy data dir to other nodes with correct names
# Start all nodes
```

## Configuration Files

| File | Location |
|------|----------|
| Systemd service | `/etc/systemd/system/etcd.service` |
| Data directory | `/var/lib/etcd` |

## Firewall Rules

etcd ports are restricted to Tailscale network (100.64.0.0/10):
- Port 2379: Client API
- Port 2380: Peer communication

## Monitoring

**Prometheus targets:**
- http://100.102.220.16:2379/metrics
- http://100.116.175.9:2379/metrics
- http://100.115.75.119:2379/metrics

**Alerts configured:**
- EtcdDown
- EtcdHighFsyncDuration
- EtcdDBSizeHigh

## Patroni Integration

Patroni uses etcd for:
- Leader election
- Cluster state storage
- Configuration management

**Patroni config:**
```yaml
etcd3:
  hosts: 100.102.220.16:2379,100.116.175.9:2379,100.115.75.119:2379
```

With 3 etcd nodes, Patroni can tolerate loss of any single etcd node without impact.