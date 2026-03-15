# Quantyra Infrastructure Runbook

## Quick Reference

### Server IPs (Tailscale)

| Server | IP | Role | Specs |
|--------|-----|------|-------|
| re-node-01 | 100.126.103.51 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| re-node-03 | 100.114.117.46 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| re-node-04 | 100.115.75.119 | DB Server | 8 vCPU, 32GB RAM, 640GB NVMe |
| router-01 | 100.102.220.16 | Router/Monitoring | 2 vCPU, 8GB RAM, 160GB SSD |
| router-02 | 100.116.175.9 | Router | 2 vCPU, 8GB RAM, 160GB SSD |
| re-db | 100.92.26.38 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |
| re-node-02 | 100.101.39.22 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |

### Connection Endpoints

| Service | Endpoint | Port |
|---------|----------|------|
| PostgreSQL Write | router-01 | 5000 |
| PostgreSQL Read | router-01 | 5001 |
| PostgreSQL Write (Secondary) | router-02 | 5000 |
| PostgreSQL Read (Secondary) | router-02 | 5001 |
| Redis Master | re-node-01 | 6379 |
| Redis Replica | re-node-03 | 6379 |
| Prometheus | router-01 | 9090 |
| Grafana | router-01 | 3000 |
| HAProxy Stats | router-01/02 | 8404 |

## Common Operations

### SSH Access

```bash
# SSH to any server via Tailscale
ssh root@100.126.103.51  # re-node-01

# Or use hostnames if configured in ~/.ssh/config
ssh re-node-01
```

### PostgreSQL Operations

#### Check Patroni Cluster Status

```bash
# On any DB node
patronictl list

# Check cluster health
patronictl query --format json
```

#### Manual Failover

```bash
# Check current leader
patronictl list

# Switchover to specific node
patronictl switchover --master <current_leader> --candidate <new_leader>

# Or let Patroni choose
patronictl switchover
```

#### Restart PostgreSQL (Rolling)

```bash
# On replicas first
ssh re-node-03 'sudo systemctl restart patroni'
ssh re-node-04 'sudo systemctl restart patroni'

# Wait for them to rejoin
patronictl list

# Switchover from leader
patronictl switchover

# Restart former leader
ssh re-node-01 'sudo systemctl restart patroni'
```

#### Check HAProxy Status

```bash
# Check HAProxy stats
curl -u admin:admin http://100.102.220.16:8404/stats

# Check PostgreSQL backends
echo "show stat" | nc 100.102.220.16:8404 | grep postgres
```

### Redis Operations

#### Check Redis Status

```bash
# Check Redis master
redis-cli -h 100.126.103.51 -p 6379 ping

# Check replication info
redis-cli -h 100.126.103.51 -p 6379 INFO replication
```

#### Manual Failover (if Sentinel configured)

```bash
# Check Sentinel status
redis-cli -p 26379 SENTINEL master quantyra_redis

# Force failover
redis-cli -p 26379 SENTINEL failover quantyra_redis
```

### Monitoring Operations

#### Check Prometheus Targets

```bash
curl http://100.102.220.16:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

#### Check Alertmanager Alerts

```bash
curl http://100.102.220.16:9093/api/v1/alerts | jq
```

#### Reload Prometheus Configuration

```bash
curl -X POST http://100.102.220.16:9090/-/reload
```

### Backup Operations

#### Manual PostgreSQL Backup

```bash
# Full backup
/usr/local/bin/postgres_backup.sh full

# Differential backup
/usr/local/bin/postgres_backup.sh diff

# Incremental backup
/usr/local/bin/postgres_backup.sh incr
```

#### Manual Redis Backup

```bash
/usr/local/bin/redis_backup.sh
```

#### Sync to S3

```bash
export S3_BUCKET="your-backup-bucket"
/usr/local/bin/sync_to_s3.sh /backup
```

## Troubleshooting

### PostgreSQL Issues

#### High Connection Count

```bash
# Check current connections
psql -h 100.102.220.16 -p 5000 -U postgres -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Kill idle connections
psql -h 100.102.220.16 -p 5000 -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"
```

#### Replication Lag

```bash
# Check lag on replicas
for node in 100.126.103.51 100.114.117.46 100.115.75.119; do
  echo "=== $node ==="
  psql -h $node -U postgres -c "SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn FROM pg_stat_replication;"
done

# Check replay on specific replica
psql -h 100.114.117.46 -U postgres -c "SELECT now() - pg_last_xact_replay_timestamp() AS replication_delay;"
```

#### Patroni Not Starting

```bash
# Check Patroni logs
journalctl -u patroni -f

# Check etcd connectivity
etcdctl --endpoints=http://100.102.220.16:2379 cluster-health

# Check PostgreSQL status
systemctl status postgresql

# If needed, reinitialize
patronictl reinit quantyra_pg <node_name>
```

### Redis Issues

#### High Memory Usage

```bash
# Check memory usage
redis-cli -h 100.126.103.51 INFO memory | grep used_memory_human

# Check big keys
redis-cli -h 100.126.103.51 --bigkeys

# Flush if needed (CAUTION!)
redis-cli -h 100.126.103.51 FLUSHALL
```

#### Connection Issues

```bash
# Check if Redis is listening
netstat -tlnp | grep 6379

# Check Redis config
redis-cli -h 100.126.103.51 CONFIG GET bind

# Check max connections
redis-cli -h 100.126.103.51 CONFIG GET maxclients
```

### HAProxy Issues

#### Backend Down

```bash
# Check backend status
echo "show stat" | nc 100.102.220.16:8404 | grep -E "pxname|postgres"

# Check specific server
echo "show stat" | nc 100.102.220.16:8404 | grep re-node-01

# Enable/disable server
echo "set server postgres_write/re-node-01 state ready" | nc 100.102.220.16:8404
echo "set server postgres_write/re-node-01 state maint" | nc 100.102.220.16:8404
```

### Monitoring Issues

#### Prometheus Not Scraping

```bash
# Check target status
curl http://100.102.220.16:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up")'

# Test exporter directly
curl http://100.126.103.51:9100/metrics | head

# Check Prometheus logs
journalctl -u prometheus -f
```

#### Grafana Dashboard Issues

```bash
# Restart Grafana
systemctl restart grafana-server

# Check Grafana logs
journalctl -u grafana-server -f

# Reset admin password
grafana-cli admin reset-admin-password <new_password>
```

### Network Issues

#### Tailscale Connectivity

```bash
# Check Tailscale status
tailscale status

# Ping all nodes
for ip in 100.126.103.51 100.114.117.46 100.115.75.119 100.102.220.16 100.116.175.9; do
  ping -c 2 $ip
done

# Restart Tailscale
systemctl restart tailscaled
```

#### Firewall Issues

```bash
# Check UFW status
ufw status verbose

# Check specific port
ufw status | grep 5432

# Allow port temporarily
ufw allow from 100.64.0.0/10 to any port 5432

# Reload firewall
ufw reload
```

## Emergency Procedures

### Complete PostgreSQL Outage

1. Check all Patroni nodes:
   ```bash
   for node in 100.126.103.51 100.114.117.46 100.115.75.119; do
     echo "=== $node ==="
     ssh $node 'patronictl list'
   done
   ```

2. Check etcd:
   ```bash
   etcdctl --endpoints=http://100.102.220.16:2379 cluster-health
   ```

3. If etcd is down, restart it:
   ```bash
   ssh 100.102.220.16 'systemctl restart etcd'
   ```

4. Restart Patroni on all nodes:
   ```bash
   for node in 100.126.103.51 100.114.117.46 100.115.75.119; do
     ssh $node 'systemctl restart patroni'
   done
   ```

5. Verify cluster:
   ```bash
   patronictl list
   ```

### Complete Redis Outage

1. Check Redis on both nodes:
   ```bash
   redis-cli -h 100.126.103.51 ping
   redis-cli -h 100.114.117.46 ping
   ```

2. Restart Redis:
   ```bash
   ssh 100.126.103.51 'systemctl restart redis'
   ssh 100.114.117.46 'systemctl restart redis'
   ```

3. Verify replication:
   ```bash
   redis-cli -h 100.126.103.51 INFO replication
   ```

### Router Outage

1. Check router-01:
   ```bash
   ssh 100.102.220.16 'systemctl status haproxy etcd prometheus grafana-server'
   ```

2. If router-01 is down, traffic should failover to router-02

3. Restart services on router-01:
   ```bash
   ssh 100.102.220.16
   systemctl restart haproxy
   systemctl restart etcd
   systemctl restart prometheus
   systemctl restart grafana-server
   ```

4. Verify HAProxy:
   ```bash
   curl -u admin:admin http://100.102.220.16:8404/stats
   ```

## Contacts

- **Primary Admin**: [Your Name] - [email]
- **On-call**: [On-call rotation]
- **Slack Channel**: #infrastructure-alerts
- **PagerDuty**: [Link to PagerDuty]