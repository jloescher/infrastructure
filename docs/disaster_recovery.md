# Disaster Recovery Guide

## Overview

This document outlines disaster recovery procedures for the Quantyra infrastructure.

## Recovery Time Objectives (RTO)

| Service | RTO | RPO |
|---------|-----|-----|
| PostgreSQL | 15 minutes | 5 minutes |
| Redis | 10 minutes | 1 hour |
| Application | 30 minutes | 0 (stateless) |
| Monitoring | 1 hour | 24 hours |

## Backup Strategy

### PostgreSQL Backups

- **Full backups**: Weekly (Sunday 2 AM UTC)
- **Differential backups**: Daily (2 AM UTC)
- **WAL archiving**: Continuous
- **Retention**: 4 full backups, 30 differential backups
- **Location**: Local (/backup/pgbackrest) + S3

### Redis Backups

- **RDB snapshots**: Daily (2 AM UTC)
- **Retention**: 30 days
- **Location**: Local (/backup/redis) + S3

### Application Backups

- **Configuration**: Version controlled
- **Docker images**: Stored in GitHub Container Registry
- **Environment variables**: Stored in GitHub Secrets

## Recovery Procedures

### PostgreSQL Recovery

#### Point-in-Time Recovery (PITR)

1. Stop PostgreSQL on the target node:
   ```bash
   systemctl stop patroni
   systemctl stop postgresql
   ```

2. Remove existing data directory:
   ```bash
   rm -rf /var/lib/postgresql/18/main/*
   ```

3. Restore from pgBackRest:
   ```bash
   # Full restore to latest
   pgbackrest --stanza=main --delta restore
   
   # Point-in-time restore
   pgbackrest --stanza=main --delta --target-time="2024-01-15 10:30:00" restore
   ```

4. Start PostgreSQL:
   ```bash
   systemctl start postgresql
   ```

5. Verify recovery:
   ```bash
   psql -c "SELECT pg_is_in_recovery();"
   psql -c "SELECT * FROM pg_stat_wal_receiver;"
   ```

6. Rejoin Patroni cluster:
   ```bash
   systemctl start patroni
   patronictl list
   ```

#### Recovering from S3 Backup

1. Configure pgBackRest for S3:
   ```bash
   # Edit /etc/pgbackrest.conf
   [global]
   repo2-type=s3
   repo2-s3-bucket=your-backup-bucket
   repo2-s3-endpoint=s3.amazonaws.com
   repo2-s3-region=us-east-1
   repo2-path=/pgbackrest
   ```

2. Restore from S3:
   ```bash
   pgbackrest --stanza=main --repo=2 --delta restore
   ```

#### Complete Cluster Failure

1. Identify available backups:
   ```bash
   pgbackrest info
   ```

2. Restore on the first node (will become leader):
   ```bash
   ssh re-node-01
   systemctl stop patroni
   pgbackrest --stanza=main --delta restore
   systemctl start postgresql
   ```

3. Initialize new Patroni cluster:
   ```bash
   # Edit patroni.yml to bootstrap new cluster
   patronictl bootstrap
   ```

4. Join other nodes as replicas:
   ```bash
   # On re-node-03 and re-node-04
   systemctl stop patroni
   rm -rf /var/lib/postgresql/18/main/*
   patronictl reinit quantyra_pg re-node-03
   patronictl reinit quantyra_pg re-node-04
   systemctl start patroni
   ```

5. Verify cluster:
   ```bash
   patronictl list
   ```

### Redis Recovery

#### Recover from RDB Backup

1. Stop Redis:
   ```bash
   systemctl stop redis
   ```

2. Restore RDB file:
   ```bash
   # Copy backup
   cp /backup/redis/redis_backup_YYYYMMDD_HHMMSS.rdb.gz /tmp/
   gunzip /tmp/redis_backup_YYYYMMDD_HHMMSS.rdb.gz
   
   # Replace current RDB
   cp /tmp/redis_backup_YYYYMMDD_HHMMSS.rdb /var/lib/redis/dump.rdb
   chown redis:redis /var/lib/redis/dump.rdb
   ```

3. Start Redis:
   ```bash
   systemctl start redis
   ```

4. Verify:
   ```bash
   redis-cli INFO persistence
   redis-cli DBSIZE
   ```

#### Recover from S3

1. Download from S3:
   ```bash
   aws s3 cp s3://your-backup-bucket/redis/redis_backup_YYYYMMDD_HHMMSS.rdb.gz /tmp/
   ```

2. Follow steps 2-4 above.

#### Master Failure

1. Promote replica to master:
   ```bash
   # On replica (re-node-03)
   redis-cli -h 100.114.117.46 SLAVEOF NO ONE
   ```

2. Update application configuration to use new master

3. Update former master as replica:
   ```bash
   # On re-node-01 (after recovery)
   redis-cli -h 100.126.103.51 SLAVEOF 100.114.117.46 6379
   ```

### Application Recovery

#### Single App Server Failure

1. Traffic automatically fails over to other app server

2. Replace or repair failed server

3. Provision new server using Ansible:
   ```bash
   cd infrastructure/ansible
   ansible-playbook playbooks/provision.yml --limit re-db
   ```

4. Deploy application:
   ```bash
   ansible-playbook playbooks/deploy.yml --limit re-db
   ```

#### Complete Application Failure

1. Provision new app servers:
   ```bash
   ansible-playbook playbooks/provision.yml --limit app_servers
   ```

2. Deploy applications:
   ```bash
   ansible-playbook playbooks/deploy.yml --limit app_servers
   ```

3. Update DNS/Cloudflare if IPs changed

4. Verify application health:
   ```bash
   curl https://api.quantyra.com/health
   ```

### Router Failure

#### Single Router Failure

1. Traffic automatically fails over to other router (if using Cloudflare load balancing)

2. Replace or repair failed router:
   ```bash
   ansible-playbook playbooks/provision.yml --limit router-01
   ```

3. Restore HAProxy configuration:
   ```bash
   # Copy from backup or other router
   scp router-02:/etc/haproxy/haproxy.cfg router-01:/etc/haproxy/
   systemctl restart haproxy
   ```

4. Restore etcd (if router-01):
   ```bash
   systemctl restart etcd
   etcdctl cluster-health
   ```

5. Restore monitoring (if router-01):
   ```bash
   systemctl restart prometheus
   systemctl restart grafana-server
   ```

#### Complete Router Failure

1. Provision new routers

2. Restore HAProxy, etcd, and monitoring from backups

3. Update application configurations with new router IPs

4. Update Cloudflare DNS

### Monitoring Stack Recovery

#### Prometheus Failure

1. Restore Prometheus configuration:
   ```bash
   scp /backup/monitoring/prometheus/* router-01:/etc/prometheus/
   ```

2. Restart Prometheus:
   ```bash
   systemctl restart prometheus
   ```

3. Verify targets:
   ```bash
   curl http://localhost:9090/api/v1/targets
   ```

#### Grafana Failure

1. Restore Grafana data:
   ```bash
   scp /backup/monitoring/grafana/* router-01:/var/lib/grafana/
   ```

2. Restart Grafana:
   ```bash
   systemctl restart grafana-server
   ```

3. Verify:
   ```bash
   curl http://localhost:3000/api/health
   ```

## Testing Backup Integrity

### PostgreSQL Backup Test

```bash
# Create test restore
pgbackrest --stanza=main --target-time="now-1hour" --type=time --delta restore --target-action=pause

# Verify backup integrity
pgbackrest --stanza=main verify
```

### Redis Backup Test

```bash
# Restore to test instance
redis-server --port 6380 --dbfilename /tmp/test_dump.rdb

# Verify data
redis-cli -p 6380 DBSIZE
redis-cli -p 6380 KEYS "*"
```

## Communication Plan

### Incident Response

1. **Detection**: Automated alerts via Prometheus/Alertmanager
2. **Assessment**: Check severity and impact
3. **Communication**: Notify stakeholders via Slack
4. **Resolution**: Follow recovery procedures
5. **Post-mortem**: Document incident and improvements

### Stakeholder Notification

- **Severity 1 (Critical)**: Immediate notification to all stakeholders
- **Severity 2 (High)**: Notification within 15 minutes
- **Severity 3 (Medium)**: Notification within 1 hour
- **Severity 4 (Low)**: Notification in daily standup

## Appendix

### Required Secrets

- AWS Access Keys (for S3 backups)
- Slack Webhook URL
- PagerDuty Service Key
- SSH Private Key (for deployment)
- Database Passwords
- Redis Password (if configured)

### External Dependencies

- **Tailscale**: VPN connectivity
- **Cloudflare**: DNS and DDoS protection
- **AWS S3**: Backup storage
- **GitHub**: CI/CD and container registry

### Recovery Checklist

- [ ] Assess scope of failure
- [ ] Notify stakeholders
- [ ] Identify affected services
- [ ] Check backup availability
- [ ] Execute recovery procedure
- [ ] Verify service health
- [ ] Update monitoring
- [ ] Document incident
- [ ] Conduct post-mortem