# Infrastructure Action Items

Generated from server reports collected on 2026-03-15

## Critical Priority 🔴

### 1. Backup Configuration
**Status**: Not configured
**Impact**: No automated backups for PostgreSQL or Redis

**Tasks**:
- [ ] Install pgBackRest on DB servers
- [ ] Configure pgBackRest with local and S3 storage
- [ ] Set up PostgreSQL backup cron jobs (full weekly, diff daily)
- [ ] Set up Redis backup cron jobs (daily RDB snapshots)
- [ ] Configure S3 sync for offsite backups
- [ ] Test backup/restore procedures

**Files to deploy**:
- `backups/scripts/postgres_backup.sh` → `/usr/local/bin/`
- `backups/scripts/redis_backup.sh` → `/usr/local/bin/`
- `backups/scripts/sync_to_s3.sh` → `/usr/local/bin/`
- `backups/configs/pgbackrest.conf` → `/etc/pgbackrest.conf`

**Estimated time**: 2-3 hours

---

### 2. SSH Hardening on router-02
**Status**: PermitRootLogin yes
**Impact**: Security vulnerability

**Tasks**:
- [ ] Update `/etc/ssh/sshd_config` on router-02
- [ ] Set `PermitRootLogin prohibit-password`
- [ ] Restart SSH service
- [ ] Verify access still works

**Command**:
```bash
ssh router-02 'sed -i "s/PermitRootLogin yes/PermitRootLogin prohibit-password/" /etc/ssh/sshd_config && systemctl restart ssh'
```

**Estimated time**: 10 minutes

---

## High Priority 🟡

### 3. Docker Installation on App Servers
**Status**: Not installed
**Impact**: Cannot deploy containerized applications

**Tasks**:
- [ ] Install Docker on re-db
- [ ] Install Docker on re-node-02
- [ ] Install Docker Compose
- [ ] Configure Docker daemon for metrics
- [ ] Create deploy user with Docker access
- [ ] Set up application directories

**Ansible command**:
```bash
ansible-playbook ansible/playbooks/provision.yml --limit app_servers --tags docker
```

**Estimated time**: 30 minutes

---

### 4. Redis Sentinel Setup
**Status**: Not configured
**Impact**: No automatic failover for Redis

**Tasks**:
- [ ] Install Redis Sentinel on router-01 and router-02
- [ ] Configure Sentinel for quantyra_redis cluster
- [ ] Set quorum to 2
- [ ] Test failover procedure
- [ ] Update application configs for Sentinel discovery

**Estimated time**: 1-2 hours

---

### 5. Application Deployment
**Status**: App servers running but no containerized apps
**Impact**: Applications not properly managed

**Tasks**:
- [ ] Identify what's currently running on ports 80/443/8001/9090
- [ ] Containerize existing applications
- [ ] Deploy via Docker Compose
- [ ] Configure HAProxy health checks
- [ ] Set up CI/CD pipeline

**Estimated time**: 4-8 hours (depends on apps)

---

## Medium Priority 🟢

### 6. Monitoring Enhancements
**Status**: Basic monitoring in place

**Tasks**:
- [ ] Install Redis exporter on re-node-01, re-node-03
- [ ] Install HAProxy exporter on routers
- [ ] Import Grafana dashboards
- [ ] Configure Alertmanager with Slack/PagerDuty
- [ ] Set up alert routing rules
- [ ] Configure Blackbox exporter for endpoint monitoring

**Estimated time**: 2-3 hours

---

### 7. Configuration Backup
**Status**: Not automated

**Tasks**:
- [ ] Create `/backup/configs` directory
- [ ] Set up cron job to backup:
  - HAProxy configs
  - Patroni configs
  - Redis configs
  - Prometheus/Grafana configs
  - etcd data
- [ ] Sync to S3

**Estimated time**: 1 hour

---

### 8. Security Audits
**Status**: Basic security in place

**Tasks**:
- [ ] Audit UFW rules on all servers
- [ ] Review fail2ban configuration
- [ ] Rotate SSH keys
- [ ] Audit PostgreSQL user permissions
- [ ] Review Redis password security
- [ ] Enable audit logging

**Estimated time**: 2-3 hours

---

## Quick Wins

These can be done immediately:

```bash
# 1. Fix SSH on router-02
ssh router-02 'sed -i "s/PermitRootLogin yes/PermitRootLogin prohibit-password/" /etc/ssh/sshd_config && systemctl restart ssh'

# 2. Create backup directories on all DB servers
ansible db_servers -m file -a "path=/backup state=directory mode=0755"

# 3. Install Redis exporters
ansible re-node-01,re-node-03 -m apt -a "name=redis_exporter state=present"

# 4. Check what's running on app servers
ansible app_servers -m shell -a "ss -tlnp | grep -E ':80|:443|:8001|:9090'"
```

---

## Summary

| Priority | Count | Estimated Time |
|----------|-------|----------------|
| Critical | 2 | 3 hours |
| High | 3 | 8-12 hours |
| Medium | 3 | 6-7 hours |
| **Total** | **8** | **17-22 hours** |

---

## Next Steps

1. **Immediate**: Fix SSH on router-02
2. **This Week**: Set up backups (critical)
3. **Next Week**: Docker installation and app deployment
4. **Following Week**: Redis Sentinel and monitoring enhancements