# PostgreSQL Workflows Reference

## Contents
- Cluster Failover
- Backup and Restore
- Migration Deployment
- User Management
- Troubleshooting

## Cluster Failover

### Emergency Failover

When the leader is unresponsive and Patroni hasn't auto-failovered:

```bash
# 1. Check current state
ssh router-01 "patronictl list"

# 2. If leader is down but no failover occurred, force it
ssh router-01 "patronictl failover --candidate re-node-03"

# 3. Verify new leader
ssh router-01 "patronictl list"
```

Copy this checklist and track progress:
- [ ] Confirm current leader is unreachable (`ping`, `ssh`)
- [ ] Check Patroni logs: `journalctl -u patroni -n 100`
- [ ] Run `patronictl list` to see member states
- [ ] Execute failover with specific candidate
- [ ] Verify application connections resume
- [ ] Investigate and fix old leader before rejoining

### Planned Switchover

```bash
# Maintenance window - graceful leader change
ssh router-01 "patronictl switchover --master re-node-03 --candidate re-node-04"
```

## Backup and Restore

### Daily Backup (Automated)

Backups run via cron on re-node-01:

```bash
# Verify backup exists
ls -la /backups/postgresql/daily/

# Manual backup
ssh re-node-01 "pg_dump -h 100.114.117.46 -U patroni_superuser quantyra | gzip > /backups/postgresql/manual-$(date +%Y%m%d).sql.gz"
```

### Point-in-Time Recovery

Copy this checklist and track progress:
- [ ] Stop Patroni on target node: `systemctl stop patroni`
- [ ] Clear data directory: `rm -rf /var/lib/postgresql/16/main/*`
- [ ] Restore base backup: `pg_basebackup -h leader -D /var/lib/postgresql/16/main/`
- [ ] Create recovery signal: `touch /var/lib/postgresql/16/main/recovery.signal`
- [ ] Configure `postgresql.conf` with `restore_command`
- [ ] Start Patroni: `systemctl start patroni`
- [ ] Verify recovery with `patronictl list`

## Migration Deployment

### Laravel Application Migration

```bash
# 1. Pre-deploy: Check pending migrations
ssh re-db "cd /opt/apps/{app} && php artisan migrate:status"

# 2. Enable maintenance mode (optional)
ssh re-db "cd /opt/apps/{app} && php artisan down"

# 3. Run migrations
ssh re-db "cd /opt/apps/{app} && php artisan migrate --force"

# 4. Verify app health
curl -f https://{app_domain}/health

# 5. Disable maintenance mode
ssh re-db "cd /opt/apps/{app} && php artisan up"
```

### Migration Rollback

```bash
# Rollback last batch
ssh re-db "cd /opt/apps/{app} && php artisan migrate:rollback --force"

# Rollback specific steps
ssh re-db "cd /opt/apps/{app} && php artisan migrate:rollback --step=3 --force"
```

## User Management

### Create Application User

```sql
-- Connect as superuser
CREATE USER app_laravel WITH PASSWORD 'secure_password';
GRANT CONNECT ON DATABASE quantyra TO app_laravel;
GRANT USAGE ON SCHEMA public TO app_laravel;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_laravel;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_laravel;
```

### Rotate Password

```sql
-- 1. Set new password
ALTER USER app_laravel WITH PASSWORD 'new_secure_password';

-- 2. Update application environment
# On app servers, update .env files
ssh re-db "sed -i 's/DB_PASSWORD=.*/DB_PASSWORD=new_secure_password/' /opt/apps/{app}/.env"

-- 3. Reload app without downtime
ssh re-db "systemctl reload php8.2-fpm-{app}"
```

## Troubleshooting

### High Connection Count

```bash
# Check active connections
psql -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Find long-running queries
psql -c "SELECT pid, now() - query_start AS duration, query FROM pg_stat_activity WHERE state != 'idle' ORDER BY duration DESC LIMIT 10;"

# Terminate specific query
psql -c "SELECT pg_terminate_backend(<pid>);"
```

### Replication Lag Investigation

```bash
# 1. Check lag metrics
ssh router-01 "curl -s localhost:9090/api/v1/query?query=postgresql_replication_lag"

# 2. On replica, check replay status
ssh re-node-04 "psql -c 'SELECT pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn(), pg_last_xact_replay_timestamp();'"

# 3. If lag is high, check network and disk I/O
ssh re-node-04 "iostat -x 1 5"
```

### Connection Pool Exhaustion

```bash
# Check HAProxy backend status
ssh router-01 "echo 'show stat' | socat stdio /var/run/haproxy.sock | grep postgres"

# Check PostgreSQL max connections
psql -c "SHOW max_connections;"
psql -c "SELECT count(*) FROM pg_stat_activity;"