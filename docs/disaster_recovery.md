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

#### Dokploy Dashboard Recovery (Recommended)

**NEW (2026-04-03)**: Applications are deployed and managed via Dokploy.

**Access:** https://deploy.quantyralabs.cc
**Location:** re-db (Manager node only)

**Recovery Actions:**

1. **Redeploy Application:**
   - Navigate to Applications → [App Name] → Deploy
   - Click "Deploy" button
   - Monitor build and deployment logs
   - Verify health checks pass

2. **Rollback to Previous Deployment:**
   - Applications → [App Name] → Deployments
   - Find previous successful deployment
   - Click "Rollback"
   - Service updates automatically with zero downtime

3. **Scale Application:**
   - Applications → [App Name] → Settings
   - Change Replicas value
   - Click "Save & Redeploy"
   - Docker Swarm redistributes containers

4. **View Logs:**
   - Applications → [App Name] → Logs
   - Real-time log streaming
   - Filter by time range
   - Identify errors or issues

5. **Update Environment Variables:**
   - Applications → [App Name] → Environment
   - Add/Update/Delete variables
   - Click "Save"
   - Redeploy to apply changes

#### Single App Server Failure

**Scenario**: re-db (manager) or re-node-02 (worker) fails

**Impact**: Applications with 2+ replicas continue running on remaining node

**Recovery Steps**:

1. **Identify Failed Node**:
   ```bash
   # Check Swarm node status
   ssh root@100.92.26.38 "docker node ls"

   # Expected output shows failed node as "Down" or "Unavailable"
   ```

2. **Verify Applications Running**:
   ```bash
   # Check service status
   ssh root@100.92.26.38 "docker service ls"

   # Check service distribution
   ssh root@100.92.26.38 "docker service ps my_app"
   ```

3. **Traffic Automatic Failover**:
   - Cloudflare DNS returns both app server IPs
   - Clients automatically retry on other IP
   - Traefik on remaining node continues routing
   - No manual intervention required

4. **Replace or Repair Failed Node**:
   - Provision new server if hardware failure
   - Or repair existing server
   - Rejoin to Docker Swarm cluster:
   ```bash
   # On manager node (re-db)
   docker swarm join-token worker

   # On worker node (re-node-02)
   docker swarm join --token SWMTKN-1-xxx 100.92.26.38:2377
   ```

5. **Redistribute Services**:
   ```bash
   # Force service redistribution
   ssh root@100.92.26.38 "docker service update --force my_app"
   ```

6. **Verify Recovery**:
   ```bash
   # Check node status
   docker node ls

   # Check service distribution
   docker service ps my_app

   # Test application accessibility
   curl -I https://myapp.example.com
   ```

#### Dokploy Manager Failure (Critical)

**Scenario**: re-db (Dokploy manager) fails completely

**Impact**:
- Dokploy dashboard unavailable
- Applications continue running (Traefik on both nodes)
- Cannot deploy new applications or updates
- Services running on re-node-02 continue serving traffic

**Recovery Steps**:

1. **Verify Applications Still Running**:
   ```bash
   # SSH to worker node
   ssh root@100.89.130.19

   # Check running services
   docker service ls

   # Check Traefik is running
   docker ps | grep traefik
   ```

2. **Verify Traffic Still Flowing**:
   ```bash
   # Test application accessibility
   curl -I https://myapp.example.com

   # Expected: HTTP/2 200 (served by re-node-02)
   ```

3. **Restore Dokploy Manager**:

   **Option A: Repair Existing Manager**:
   ```bash
   # SSH to manager node (if accessible)
   ssh root@100.92.26.38

   # Check Dokploy service
   docker service ls | grep dokploy

   # Restart Dokploy
   docker service update dokploy --force

   # Check logs
   docker service logs dokploy --tail 100
   ```

   **Option B: Promote Worker to Manager** (if manager unrecoverable):
   ```bash
   # On worker node (re-node-02)
   ssh root@100.89.130.19

   # Promote to manager
   docker node promote re-node-02

   # Initialize new Dokploy instance
   # (requires Dokploy reinstallation)
   curl -sSL https://dokploy.com/install.sh | bash
   ```

4. **Restore Dokploy Database** (if needed):
   ```bash
   # Restore from backup
   cat dokploy_backup_YYYYMMDD.sql | docker exec -i dokploy-postgres psql -U dokploy dokploy
   ```

5. **Verify Dashboard Access**:
   ```bash
   curl -I https://deploy.quantyralabs.cc
   # Expected: HTTP/2 200
   ```

#### Complete Application Failure

**Scenario**: Both app servers fail or all containers stop

**Recovery Steps**:

1. **Verify Server Accessibility**:
   ```bash
   ping 100.92.26.38      # re-db
   ping 100.89.130.19     # re-node-02
   ```

2. **Check Docker Swarm Status**:
   ```bash
   ssh root@100.92.26.38 "docker node ls"
   ssh root@100.89.130.19 "docker node ls"
   ```

3. **Restart Docker Services**:
   ```bash
   # On both app servers
   systemctl restart docker

   # Wait for Swarm to stabilize
   sleep 30

   # Check services
   docker service ls
   ```

4. **Redeploy All Applications**:
   ```bash
   # Via Dokploy Dashboard
   # Applications → [Each App] → Deploy

   # Or via CLI
   for service in $(docker service ls -q); do
     docker service update --force $service
   done
   ```

5. **Verify Applications**:
   ```bash
   # Check all services running
   docker service ls

   # Check service distribution
   docker service ps my_app

   # Test accessibility
   curl -I https://myapp.example.com
   ```

#### Traefik Failure

**Scenario**: Traefik load balancer fails

**Symptoms**:
- Applications return 502/503 errors
- SSL certificates not working
- Routing broken

**Recovery Steps**:

1. **Check Traefik Service Status**:
   ```bash
   ssh root@100.92.26.38
   docker service ps dokploy-traefik
   ```

2. **Check Traefik Logs**:
   ```bash
   docker service logs dokploy-traefik --tail 100
   ```

3. **Restart Traefik**:
   ```bash
   # Force update
   docker service update dokploy-traefik --force

   # Wait for replicas to start
   sleep 10

   # Verify
   docker service ps dokploy-traefik
   ```

4. **Verify Traefik Configuration**:
   ```bash
   # Check config file
   cat /etc/dokploy/traefik/traefik.yml

   # Check dynamic configs
   ls -la /etc/dokploy/traefik/dynamic/
   ```

5. **Test Routing**:
   ```bash
   curl -I https://myapp.example.com
   curl -I https://deploy.quantyralabs.cc
   ```

#### Docker Swarm Split-Brain

**Scenario**: Network partition causes both nodes to act as managers

**Prevention**: Use 1 manager + 1 worker (odd number of managers)

**Recovery**:
```bash
   # On manager node
   ssh root@100.92.26.38
   docker node ls

   # If both show as managers, demote worker
   docker node demote re-node-02

   # Verify
   docker node ls
   ```

#### Database Connection Issues from Applications

**Symptoms**: Application logs show database connection refused or timeout

**Diagnosis**:
```bash
   # Test HAProxy endpoint from app server
   ssh root@100.92.26.38
   psql -h 100.102.220.16 -p 5000 -U patroni_superuser -d myapp_production -c "SELECT 1;"

   # Test Redis
   redis-cli -h 100.102.220.16 -p 6379 -a CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk PING
   ```

**Common Causes**:
1. HAProxy down (check `systemctl status haproxy` on routers)
2. Database credentials wrong in environment variables
3. Database not created
4. Network partition between app servers and routers

**Solutions**:
1. Restart HAProxy: `systemctl restart haproxy` (on both routers)
2. Verify credentials in Dokploy environment variables
3. Create database: See Database Creation section
4. Check Tailscale connectivity: `tailscale ping 100.102.220.16`

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