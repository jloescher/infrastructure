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

#### Dashboard-Based Recovery (Recommended)

The Quantyra PaaS Dashboard provides a web interface for application management:

**Access:** `http://100.102.220.16:8080` (Tailscale only)
**Credentials:** admin / DbAdmin2026!

**Recovery Actions:**

1. **Redeploy Application:**
   - Navigate to Applications → [App Name] → Deploy
   - Click "Deploy Production" or "Deploy Staging"
   - Monitor two-phase progress (Deploy → Domain Provisioning)

2. **Force Domain Provisioning:**
   - If deploy succeeds but domains fail
   - Applications → [App Name] → Force Provision Pending Domains

3. **Rollback to Previous Commit:**
   - Applications → [App Name] → Rollback
   - Select previous known-good commit

4. **Restart Services:**
   - Applications → [App Name] → Restart App / Reload Nginx / Reload PHP-FPM

#### Single App Server Failure

1. Traffic automatically fails over to other app server (HAProxy round-robin)

2. Replace or repair failed server

3. Run deployment from Dashboard or via webhook:
   ```bash
   # Trigger redeploy via webhook
   curl -X POST https://hooks.quantyralabs.cc/{app_name} \
     -H "X-Hub-Signature-256: {secret}" \
     -d '{"ref": "refs/heads/main"}'
   ```

4. Verify application health:
   ```bash
   # Check local health
   ssh root@100.92.26.38 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8100"
   ssh root@100.89.130.19 "curl -s -o /dev/null -w '%{http_code}' http://localhost:8100"
   ```

#### Complete Application Failure

1. Verify app servers are accessible:
   ```bash
   ssh root@100.92.26.38 "hostname"
   ssh root@100.89.130.19 "hostname"
   ```

2. Check runtime user exists:
   ```bash
   id webapps
   # If missing: useradd --system --create-home --home-dir /home/webapps --shell /usr/sbin/nologin webapps
   ```

3. Redeploy from Dashboard or trigger webhook

4. Verify both environments:
   - Production: `https://{domain}.tld`
   - Staging: `https://staging.{domain}.tld`

#### Application Port Configuration

Each application uses separate ports for production and staging:

| Environment | Port Range | Example |
|-------------|------------|---------|
| Production | 8100-8199 | rentalfixer: 8100 |
| Staging | 9200-9299 | rentalfixer-staging: 9200 |

**Port Assignment:**
- Ports are automatically assigned by dashboard during app creation
- Production port stored in `/opt/dashboard/config/applications.yml`
- Staging port = production_port + 1100

**Verify Port Configuration:**
```bash
# Check nginx configs
ls -la /etc/nginx/sites-enabled/

# Check which ports are listening
ss -tlnp | grep nginx
```

#### Permission Model Recovery

Applications use a non-root permission model:

| Path | Owner | Group | Mode | Purpose |
|------|-------|-------|------|---------|
| `/opt/apps/{app}` | webapps | webapps | 755/644 | Application code |
| `storage/` | webapps | www-data | 2775 | Laravel writable (setgid) |
| `bootstrap/cache/` | webapps | www-data | 2775 | Laravel writable (setgid) |
| `.env` | webapps | www-data | 640 | Environment config |

**Fix Permissions:**
```bash
APP_NAME="rentalfixer"
APP_DIR="/opt/apps/$APP_NAME"

# Fix ownership
chown -R webapps:webapps $APP_DIR

# Fix writable directories
chgrp -R www-data $APP_DIR/storage $APP_DIR/bootstrap/cache
chmod -R ug+rwX $APP_DIR/storage $APP_DIR/bootstrap/cache
find $APP_DIR/storage $APP_DIR/bootstrap/cache -type d -exec chmod 2775 {} \;

# Fix .env
chgrp www-data $APP_DIR/.env
chmod 640 $APP_DIR/.env
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

### Dashboard Recovery

The PaaS Dashboard runs on router-01 and manages application deployments.

#### Dashboard Service Failure

1. Check service status:
   ```bash
   ssh root@100.102.220.16 "systemctl status dashboard"
   ```

2. Restart dashboard:
   ```bash
   ssh root@100.102.220.16 "systemctl restart dashboard"
   ```

3. Check logs:
   ```bash
   ssh root@100.102.220.16 "journalctl -u dashboard -n 100"
   ```

#### Dashboard Code Recovery

1. Dashboard code is stored in repo at `dashboard/` and `configs/dashboard/`

2. Restore from repo:
   ```bash
   # On router-01
   cd /opt/dashboard
   git pull  # If using git
   
   # Or copy from local repo
   scp -r dashboard/* root@100.102.220.16:/opt/dashboard/
   ```

3. Restart service:
   ```bash
   systemctl restart dashboard
   ```

#### Dashboard Configuration Files

| File | Purpose |
|------|---------|
| `/opt/dashboard/app.py` | Main application code |
| `/opt/dashboard/config/applications.yml` | Application registry |
| `/opt/dashboard/config/databases.yml` | Database registry |
| `/opt/dashboard/secrets/*.yaml` | SOPS-encrypted app secrets |
| `/opt/dashboard/secrets/age.key` | AGE private key (DO NOT LOSE) |
| `/opt/dashboard/templates/*.html` | UI templates |

**CRITICAL: Backup AGE Key**
```bash
# Backup the AGE key - this cannot be recovered if lost
cp /opt/dashboard/secrets/age.key /backup/age.key
```

### Secrets Recovery

All application secrets are encrypted with SOPS using AGE encryption.

#### Secrets Storage

| Location | Content |
|----------|---------|
| `/opt/dashboard/secrets/{app}.yaml` | Per-app secrets (SOPS encrypted) |
| `/opt/dashboard/secrets/age.key` | AGE private key (router-01 only) |
| Repo: `secrets/*.yaml` | Encrypted secrets (version controlled) |

#### Secrets Structure

Each app's secrets file contains scoped secrets:

```yaml
production:
  DB_USERNAME: ...
  DB_PASSWORD: ...
shared:
  APP_KEY: ...
staging:
  STAGING_DB_USERNAME: ...
  STAGING_DB_PASSWORD: ...
```

#### Recover Secrets from Backup

1. Restore AGE key (required for decryption):
   ```bash
   scp /backup/age.key root@100.102.220.16:/opt/dashboard/secrets/age.key
   chmod 600 /opt/dashboard/secrets/age.key
   ```

2. Restore encrypted secrets files:
   ```bash
   scp -r /backup/secrets/*.yaml root@100.102.220.16:/opt/dashboard/secrets/
   ```

3. Verify SOPS can decrypt:
   ```bash
   ssh root@100.102.220.16 "sops -d /opt/dashboard/secrets/rentalfixer.yaml | head -20"
   ```

#### Manual Secret Recovery

If secrets are lost but database credentials need recovery:

1. Check database registry:
   ```bash
   ssh root@100.102.220.16 "cat /opt/dashboard/config/databases.yml"
   ```

2. Reset database passwords if needed:
   ```bash
   # Connect to PostgreSQL primary
   psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d postgres
   
   # Reset password
   ALTER USER rentalfixer_user WITH PASSWORD 'new_password';
   ```

3. Update secrets via Dashboard UI:
   - Navigate to Applications → [App] → Secrets
   - Update the affected secrets
   - Redeploy to apply changes

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

| Secret | Location | Purpose |
|--------|----------|---------|
| AGE Private Key | `/opt/dashboard/secrets/age.key` | SOPS decryption (router-01 only) |
| PostgreSQL Superuser | AGENTS.md | Database administration |
| Redis Password | AGENTS.md | Redis authentication |
| Cloudflare API Token | `/root/.secrets/cloudflare.ini` | DNS/API access |
| Dashboard Auth | AGENTS.md | Dashboard login |
| HAProxy Stats Auth | AGENTS.md | HAProxy stats page |
| SSH Keys | `~/.ssh/authorized_keys` | Server access |

### Critical Configuration Files

| File | Server | Purpose |
|------|--------|---------|
| `/opt/dashboard/secrets/age.key` | router-01 | SOPS encryption key |
| `/opt/dashboard/config/applications.yml` | router-01 | Application registry |
| `/opt/dashboard/config/databases.yml` | router-01 | Database registry |
| `/etc/haproxy/domains/registry.conf` | router-01, router-02 | Domain routing |
| `/etc/haproxy/certs/*.pem` | router-01, router-02 | SSL certificates |
| `/etc/hosts.override` | All servers | Tailscale hostname mapping |

### Toolchain Versions

| Tool | Version | Servers |
|------|---------|---------|
| PHP | 8.5 | App servers |
| Composer | 2.9.5 | App servers |
| Node.js | 20.x | App servers |
| PostgreSQL Client | 18.3 | App servers |
| nginx | latest | App servers |
| HAProxy | 2.8.x | Routers |

### External Dependencies

- **Tailscale**: VPN connectivity (required for all server communication)
- **Cloudflare**: DNS, DDoS protection, SSL (DNS-01 challenge)
- **GitHub**: Source code hosting, webhooks for deploy triggers
- **Let's Encrypt**: SSL certificates via certbot

### Recovery Checklist

- [ ] Assess scope of failure
- [ ] Check Tailscale connectivity
- [ ] Verify SSH access to all servers
- [ ] Notify stakeholders
- [ ] Identify affected services
- [ ] Check backup availability
- [ ] Verify AGE key is accessible
- [ ] Execute recovery procedure
- [ ] Verify service health
- [ ] Test application endpoints
- [ ] Update monitoring
- [ ] Document incident
- [ ] Conduct post-mortem