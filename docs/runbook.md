# Quantyra Infrastructure Runbook

## Quick Reference

### Server Classification

| Type | Server | IP (Tailscale) | Public IP | Role | Specs |
|------|--------|----------------|-----------|------|-------|
| **Database** | re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL + Redis | 8 vCPU, 32GB RAM, 640GB NVMe |
| **Database** | re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL + Redis | 8 vCPU, 32GB RAM, 640GB NVMe |
| **Database** | re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL | 8 vCPU, 32GB RAM, 640GB NVMe |
| **App** | re-db | 100.92.26.38 | 208.87.128.115 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |
| **App** | re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL pending) | 12 vCPU, 48GB RAM, 720GB NVMe |
| **Router** | router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy/PgBouncer/Monitoring | 2 vCPU, 8GB RAM, 160GB SSD |
| **Router** | router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy/PgBouncer | 2 vCPU, 8GB RAM, 160GB SSD |

### Connection Endpoints

| Service | Endpoint | Port | Notes |
|---------|----------|------|-------|
| PostgreSQL Write | router-01 | 5000 | Via HAProxy |
| PostgreSQL Read | router-01 | 5001 | Load balanced replicas |
| PostgreSQL (Pooled) | router-01 | 6432 | Via PgBouncer |
| Redis Write | router-01 | 6379 | Master via HAProxy |
| Redis Read | router-01 | 6380 | Replica via HAProxy |
| Prometheus | router-01 | 9090 | Metrics |
| Grafana | router-01 | 3000 | Dashboards |
| Alertmanager | router-01 | 9093 | Alerts |
| HAProxy Stats | router-01/02 | 8404 | admin / jFNeZ2bhfrTjTK7aKApD |
| Dashboard | router-01 | 8080 | admin / DbAdmin2026! |

### Current Cluster State

**PostgreSQL Leader**: Check via `patronictl list` or dashboard
**Redis Master**: Check via `redis-cli INFO replication` or dashboard

## Common Operations

### Dashboard Access

```
URL: http://100.102.220.16:8080
Username: admin
Password: DbAdmin2026!
```

Features:
- PostgreSQL/Redis status
- Disk space for all servers
- Database management
- Application deployment wizard
- Documentation viewer

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
curl -u admin:jFNeZ2bhfrTjTK7aKApD http://100.102.220.16:8404/stats

# Check PostgreSQL backends
echo "show stat" | nc 100.102.220.16:8404 | grep postgres
```

### Redis Operations

#### Check Redis Status

```bash
# Check Redis via HAProxy (master)
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk ping

# Check replication info
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO replication
```

#### Manual Failover (via Sentinel)

```bash
# Check Sentinel status
redis-cli -p 26379 SENTINEL master quantyra_redis

# Force failover
redis-cli -p 26379 SENTINEL failover quantyra_redis
```

### Monitoring Operations

#### Check Prometheus Targets

```bash
curl -s http://100.102.220.16:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, instance: .labels.instance, health: .health}'
```

#### Check Disk Space (via Prometheus)

```bash
# Query disk space for all servers
curl -s --get "http://100.102.220.16:9090/api/v1/query" \
  --data-urlencode "query=node_filesystem_avail_bytes{mountpoint='/',fstype='ext4'}" | jq
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
```

#### Manual Redis Backup

```bash
/usr/local/bin/redis_backup.sh
```

## Troubleshooting

### PostgreSQL Issues

#### High Connection Count

```bash
# Check current connections via HAProxy
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Kill idle connections
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < now() - interval '10 minutes';"
```

#### Replication Lag

```bash
# Check lag on primary
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres -c "SELECT client_addr, state, sent_lsn, replay_lsn FROM pg_stat_replication;"

# Check replay on specific replica
ssh re-node-03 "sudo -u postgres psql -c \"SELECT now() - pg_last_xact_replay_timestamp() AS replication_delay;\""
```

#### Patroni Not Starting

```bash
# Check Patroni logs
journalctl -u patroni -f

# Check etcd connectivity
etcdctl --endpoints=http://100.102.220.16:2379,http://100.116.175.9:2379,http://100.115.75.119:2379 cluster-health

# Reinitialize if needed
patronictl reinit quantyra_pg <node_name>
```

### Redis Issues

#### High Memory Usage

```bash
# Check memory usage
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO memory | grep used_memory_human

# Check big keys
redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk --bigkeys
```

### HAProxy Issues

#### Backend Down

```bash
# Check backend status
echo "show stat" | nc 100.102.220.16:8404 | grep -E "pxname|postgres|redis"

# Enable/disable server
echo "set server postgres_write/re-node-01 state ready" | nc 100.102.220.16:8404
echo "set server postgres_write/re-node-01 state maint" | nc 100.102.220.16:8404
```

### Dashboard Issues

#### Dashboard Not Loading

```bash
# Check service status
ssh router-01 "systemctl status dashboard"

# Restart dashboard
ssh router-01 "systemctl restart dashboard"

# Check logs
ssh router-01 "journalctl -u dashboard -f"
```

#### Disk Space Not Showing

```bash
# Check Prometheus is accessible
curl http://100.102.220.16:9090/api/v1/query?query=up

# Check node_exporter on a server
curl http://100.126.103.51:9100/metrics | head
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
   etcdctl --endpoints=http://100.102.220.16:2379,http://100.116.175.9:2379,http://100.115.75.119:2379 cluster-health
   ```

3. If etcd is down, restart it on all nodes:
   ```bash
   ssh router-01 'systemctl restart etcd'
   ssh router-02 'systemctl restart etcd'
   ssh re-node-04 'systemctl restart etcd'
   ```

4. Restart Patroni on all DB nodes:
   ```bash
   for node in 100.126.103.51 100.114.117.46 100.115.75.119; do
     ssh $node 'systemctl restart patroni'
   done
   ```

### Complete Redis Outage

1. Check Redis on both nodes:
   ```bash
   redis-cli -h 100.126.103.51 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk ping
   redis-cli -h 100.114.117.46 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk ping
   ```

2. Restart Redis:
   ```bash
   ssh re-node-01 'systemctl restart redis'
   ssh re-node-03 'systemctl restart redis'
   ```

3. Verify via HAProxy:
   ```bash
   redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk INFO replication
   ```

### Router Outage

1. Check router-01:
   ```bash
   ssh 100.102.220.16 'systemctl status haproxy etcd prometheus grafana-server dashboard'
   ```

2. If router-01 is down, traffic fails over to router-02

3. Restart services on router-01:
   ```bash
   ssh router-01
   systemctl restart haproxy
   systemctl restart etcd
   systemctl restart prometheus
   systemctl restart grafana-server
   systemctl restart dashboard
   ```

## Application Deployment

### Via Dashboard

1. Navigate to http://100.102.220.16:8080/apps/create
2. Select framework
3. Enter application details
4. Configure database (optional)
5. Click "Create Application"
6. Copy GitHub Actions workflow to repository
7. Add secrets to GitHub

### Manual Deployment

```bash
# Deploy to both app servers
ssh root@100.92.26.38 "cd /opt/apps/APP_NAME && git pull && systemctl restart APP_NAME"
ssh root@100.89.130.19 "cd /opt/apps/APP_NAME && git pull && systemctl restart APP_NAME"
```

## Contacts

- **Primary Admin**: jonathan@xotec.io
- **Slack Channel**: #infrastructure-alerts
- **Dashboard**: http://100.102.220.16:8080