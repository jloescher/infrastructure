# Redis Workflows Reference

## Contents
- Failover Procedures
- Backup and Recovery
- Performance Troubleshooting
- Scaling Operations

## Manual Failover Procedure

Copy this checklist and track progress:
- [ ] Verify current master/replica status
- [ ] Check replication lag is near 0
- [ ] Initiate failover on Sentinel
- [ ] Verify application reconnection
- [ ] Update monitoring dashboards

### Step-by-Step

```bash
# 1. Check current status
ssh root@100.126.103.51 'redis-cli -p 26379 SENTINEL get-master-addr-by-name mymaster'

# 2. Check replication lag
redis-cli -h 100.114.117.46 -p 6379 -a $PASSWORD INFO replication | grep master_last_io_seconds_ago

# 3. Initiate failover
redis-cli -h 100.126.103.51 -p 26379 SENTINEL failover mymaster

# 4. Verify new master
ssh root@100.114.117.46 'redis-cli INFO replication | grep role'
```

## Backup and Recovery

### Create RDB Backup

```bash
# Trigger BGSAVE on master
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD BGSAVE

# Copy dump file (from replica to avoid master load)
scp root@100.114.117.46:/var/lib/redis/dump.rdb /backups/redis-$(date +%Y%m%d).rdb
```

### Restore from Backup

```bash
# Stop Redis on target
systemctl stop redis

# Restore dump file
cp /backups/redis-20260318.rdb /var/lib/redis/dump.rdb
chown redis:redis /var/lib/redis/dump.rdb

# Start Redis
systemctl start redis
```

## Performance Troubleshooting

### Slow Query Investigation

```bash
# Monitor slow commands in real-time
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD MONITOR | grep -E '(KEYS|HGETALL|LRANGE.*0.*-1)'

# Check slow log
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD SLOWLOG GET 10
```

### Memory Analysis

```bash
# Memory usage by key pattern
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD --bigkeys

# Detailed memory stats
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD INFO memory
```

### Replication Lag Diagnosis

```bash
# Check replication status
redis-cli -h 100.114.117.46 -p 6379 -a $PASSWORD INFO replication

# Common causes:
# 1. Large keys being transferred - Check client-output-buffer-limit
# 2. Network congestion - Check Tailscale status
# 3. High write rate on master - Consider spreading writes
```

## Scaling Operations

### Promote Replica to Master (Planned)

```bash
# 1. Stop replication
redis-cli -h 100.114.117.46 -p 6379 -a $PASSWORD REPLICAOF NO ONE

# 2. Update Sentinel configuration
redis-cli -h 100.126.103.51 -p 26379 SENTINEL remove mymaster
redis-cli -h 100.126.103.51 -p 26379 SENTINEL monitor mymaster 100.114.117.46 6379 2

# 3. Reconfigure old master as replica
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD REPLICAOF 100.114.117.46 6379
```

### Add New Replica

```bash
# On new replica server
redis-cli -p 6379 -a $PASSWORD REPLICAOF 100.126.103.51 6379

# Verify replication
redis-cli -p 6379 INFO replication | grep master_link_status
```

## Monitoring Checklist

Run daily:
```bash
# Memory usage trend
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD INFO memory | grep used_memory_human

# Connected clients
redis-cli -h 100.126.103.51 -p 6379 -a $PASSWORD INFO clients | grep connected_clients

# Replication lag
redis-cli -h 100.114.117.46 -p 6379 -a $PASSWORD INFO replication | grep master_last_io_seconds_ago