# Operations Runbook

## Quick Reference

### Server Classification

| Type | Server | IP (Tailscale) | Public IP | Role | Specs |
|------|--------|----------------|-----------|------|-------|
| **Database** | re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL + Redis | 8 vCPU, 32GB RAM, 640GB NVMe |
| **Database** | re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL + Redis | 8 vCPU, 32GB RAM, 640GB NVMe |
| **Database** | re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL | 8 vCPU, 32GB RAM, 640GB NVMe |
| **App** | re-db | 100.92.26.38 | 208.87.128.115 | App Server | 12 vCPU, 48GB RAM, 720GB NVMe |
| **App** | re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) | 12 vCPU, 48GB RAM, 720GB NVMe |
| **Router** | router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy/Monitoring/Dashboard | 2 vCPU, 8GB RAM, 160GB SSD |
| **Router** | router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy | 2 vCPU, 8GB RAM, 160GB SSD |

### Connection Endpoints

| Service | Endpoint | Port | Notes |
|---------|----------|------|-------|
| PostgreSQL Write | router-01 | 5000 | Via HAProxy |
| PostgreSQL Read | router-01 | 5001 | Load balanced replicas |
| Redis Write | router-01 | 6379 | Master via HAProxy |
| Prometheus | router-01 | 9090 | Metrics |
| Grafana | router-01 | 3000 | Dashboards |
| Alertmanager | router-01 | 9093 | Alerts |
| HAProxy Stats | router-01/02 | 8404 | admin / jFNeZ2bhfrTjTK7aKApD |
| Dashboard | router-01 | 8080 | admin / DbAdmin2026! |

### Current Cluster State

**PostgreSQL Leader**: Check via `patronictl list` or dashboard
**Redis Master**: Check via `redis-cli INFO replication` or dashboard

---

## PaaS Operations

### Deploy an Application

**Via Dashboard:**
1. Navigate to http://100.102.220.16:8080
2. Select application → Deploy
3. Select branch and environment
4. Watch real-time progress

**Via API:**
```bash
curl -X POST -u admin:DbAdmin2026! \
  http://100.102.220.16:8080/api/apps/my-app/deploy-async \
  -H "Content-Type: application/json" \
  -d '{"branch": "main", "environment": "production"}'
```

**Via SSH (validation only):**
```bash
ssh root@100.92.26.38
docker service ls
docker ps
```

### Rollback a Deployment

**Via Dashboard:**
1. Go to Applications → [App] → Deployments
2. Find last successful deployment
3. Click "Rollback"

**Via Dokploy:**
1. Open application in Dokploy
2. Select previous successful deployment/image
3. Trigger rollback/redeploy

### Provision a New Domain

1. Dashboard → Applications → [App] → Domains
2. Add Domain → Configure:
   - Domain name
   - Environment (production/staging)
   - SSL enabled
3. Click Provision
4. Wait for SSL certificate (usually 1-2 minutes)

### Create a Database

**Via Dashboard:**
1. Applications → [App] → Database
2. Click "Create Database"
3. Credentials auto-generated

**Via psql:**
```bash
psql -h router-01 -p 5000 -U patroni_superuser -d postgres

CREATE DATABASE mydb;
CREATE USER myuser WITH PASSWORD 'secret';
GRANT ALL PRIVILEGES ON DATABASE mydb TO myuser;
```

### Add a Service (Redis/Meilisearch)

1. Applications → [App] → Services
2. Click "Add Service"
3. Select service type
4. Configure memory limits
5. Connection string auto-injected into environment

---

## Infrastructure Operations

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

---

## Incident Response

### Application Down

1. Check application status:
   ```bash
   ssh root@100.92.26.38
   docker service ls
   docker ps
   ```

2. Check logs:
   ```bash
   docker service logs <service_name> --tail 100
   docker logs <container_name> --tail 100 -f
   ```

3. Restart workload:
   ```bash
   docker service update --force <service_name>
   ```

### Database Issues

1. Check cluster status:
   ```bash
   patronictl list
   ```

2. Check connections:
   ```bash
   psql -h router-01 -p 5000 -c "SELECT count(*) FROM pg_stat_activity;"
   ```

3. Check replication lag:
   ```bash
   patronictl list
   ```

### Redis Issues

1. Check status:
   ```bash
   redis-cli -h 100.126.103.51 -p 6379 -a <password> INFO
   ```

2. Check memory:
   ```bash
   redis-cli -h 100.126.103.51 INFO memory
   ```

### HAProxy Issues

1. Check status:
   ```bash
   systemctl status haproxy
   ```

2. Check config:
   ```bash
   haproxy -c -f /etc/haproxy/haproxy.cfg
   ```

3. View stats: http://100.102.220.16:8404/stats

### SSL Certificate Issues

1. Check expiration:
   ```bash
   certbot certificates
   ```

2. Renew manually:
   ```bash
   certbot renew --cert-name example.com
   systemctl reload haproxy
   ```

---

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
   etcdctl --endpoints=http://100.102.220.16:2379,http://100.116.175.9:2379,http.115.75.119:2379 cluster-health
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

---

## Maintenance Windows

### Before Maintenance

1. Create silence in Alertmanager:
   ```bash
   curl -X POST http://100.102.220.16:9093/api/v1/silences \
     -H "Content-Type: application/json" \
     -d '{"matchers":[{"name":"alertname","value":".*","isRegex":true}],"startsAt":"2026-03-27T10:00:00Z","endsAt":"2026-03-27T12:00:00Z","createdBy":"admin","comment":"Scheduled maintenance"}'
   ```

2. Notify stakeholders
3. Document planned changes

### During Maintenance

1. Monitor progress
2. Keep logs
3. Update status page if applicable

### After Maintenance

1. Verify all services healthy:
   ```bash
   patronictl list
   redis-cli -h 100.102.220.16 ping
   curl -s http://100.102.220.16:9090/api/v1/targets | jq '.data.activeTargets[].health'
   ```

2. Remove silences:
   ```bash
   curl -X DELETE http://100.102.220.16:9093/api/v1/silence/<silence_id>
   ```

3. Send notification

---

## Backup & Recovery

### Database Backup

```bash
# Manual backup
pg_dump -h router-01 -p 5000 -U postgres mydb | gzip > backup.sql.gz

# Restore
gunzip -c backup.sql.gz | psql -h router-01 -p 5000 -U postgres mydb
```

### Redis Backup

```bash
redis-cli -h 100.126.103.51 BGSAVE
cp /var/lib/redis/dump.rdb /backup/redis-$(date +%Y%m%d).rdb
```

### Full System Recovery

1. Provision new servers
2. Run Ansible playbooks:
   ```bash
   ansible-playbook ansible/playbooks/provision.yml
   ```
3. Restore databases
4. Restore Redis
5. Verify all services
6. Sync HAProxy configs

---

## Contacts

- **Primary Admin**: jonathan@xotec.io
- **Slack Channel**: #infrastructure-alerts
- **Dashboard**: http://100.102.220.16:8080
