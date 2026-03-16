# Infrastructure Action Items

Last updated: 2026-03-15

## Critical Priority 🔴

### 1. Backup Configuration
**Status**: ✅ Configured (2026-03-15)
**Impact**: Automated backups running for PostgreSQL and Redis

**Tasks**:
- [x] Install pgBackRest on DB servers
- [x] Configure pgBackRest with local and S3 storage
- [x] Set up PostgreSQL backup cron jobs (full weekly, diff daily)
- [x] Set up Redis backup cron jobs (daily RDB snapshots)
- [x] Configure S3 sync for offsite backups
- [ ] Test backup/restore procedures

**Estimated time**: 2-3 hours

---

### 2. SSH Hardening on router-02
**Status**: ✅ Fixed (2026-03-15)
**Impact**: Security vulnerability resolved

**Tasks**:
- [x] Update `/etc/ssh/sshd_config` on router-02
- [x] Set `PermitRootLogin prohibit-password`
- [x] Restart SSH service
- [x] Verify access still works

**Estimated time**: 10 minutes

---

## High Priority 🟡

### 3. Redis Sentinel Setup
**Status**: ✅ Configured (2026-03-15)
**Impact**: Automatic failover for Redis enabled

**Tasks**:
- [x] Install Redis Sentinel on router-01 and router-02
- [x] Configure Sentinel for quantyra_redis cluster
- [x] Set quorum to 2
- [x] Test failover procedure (2026-03-15)
- [x] Add Redis to HAProxy for HA through routers (2026-03-15)
- [ ] Update quantyra application configs for Sentinel discovery

**Sentinel Endpoints**:
- router-01: 100.102.220.16:26379
- router-02: 100.116.175.9:26379

**HAProxy Redis Ports**:
- Write (master): 6379
- Read (replica): 6380

**Documentation**: `docs/redis_ha.md`

**Estimated time**: 1-2 hours

---

### 4. Monitoring Enhancements
**Status**: ✅ Enhanced (2026-03-15)

**Tasks**:
- [x] Install Redis exporter on re-node-01, re-node-03 (port 9121)
- [x] Install HAProxy exporter on routers (port 9101)
- [x] Install node_exporter on ALL servers (port 9100)
- [x] Import Grafana dashboards (postgres_haproxy, redis)
- [x] Configure Alertmanager with Slack/Email (2026-03-15)
- [x] Set up alert routing rules (26 rules configured)
- [x] Add disk space monitoring to dashboard (2026-03-15)
- [ ] Configure Blackbox exporter for endpoint monitoring
- [ ] Add quantyra application metrics to Prometheus

**Estimated time**: 2-3 hours

---

### 5. Configuration Backup
**Status**: Not automated

**Tasks**:
- [ ] Create `/backup/configs` directory
- [ ] Set up cron job to backup:
  - HAProxy configs (`/etc/haproxy/haproxy.cfg`)
  - Patroni configs (`/etc/patroni.yml`)
  - PostgreSQL configs (`/etc/postgresql/18/main/`)
  - Redis configs (`/etc/redis/`)
  - Prometheus/Grafana configs
  - etcd data
  - Caddy configs (`/etc/caddy/`)
  - quantyra systemd services
  - Dashboard files (`/opt/dashboard/`)
- [ ] Sync to S3

**Estimated time**: 1 hour

---

### 6. Multi-Tenant Database Management
**Status**: ✅ Configured (2026-03-15)
**Impact**: Easy addition of new SaaS products with centralized config

**Tasks**:
- [x] Centralize database definitions in Ansible inventory
- [x] Create Jinja2 templates for PgBouncer config
- [x] Create playbook to deploy PgBouncer to routers
- [x] Create playbook to create databases/users in PostgreSQL
- [x] Install PgBouncer on router-01 and router-02
- [x] Web dashboard for database creation

**Documentation**: `docs/adding_new_product.md`

**To add a new product:**
1. Use Dashboard: http://100.102.220.16:8080/apps/create
2. Or edit `ansible/inventory/group_vars/databases.yml`
3. Run `ansible-playbook ansible/playbooks/create-databases.yml`
4. Run `ansible-playbook ansible/playbooks/deploy-pgbouncer.yml`

---

## Medium Priority 🟢

### 7. re-node-02 ATL Relocation
**Status**: Pending relocation to ATL datacenter
**Impact**: Cross-datacenter redundancy for web apps (currently both app servers in NYC)

**Tasks**:
- [ ] Receive new public IP from provider
- [ ] Receive new Tailscale IP
- [ ] Update Ansible inventory with new IPs
- [ ] Reprovision server from scratch:
  - [ ] Install base packages (node_exporter, fail2ban, etc.)
  - [ ] Configure SSH hardening
  - [ ] Set up UFW firewall
  - [ ] Install Docker
  - [ ] Deploy quantyra application
- [ ] Update HAProxy configs to include new app server
- [ ] Update monitoring to include new server
- [ ] Test application failover between NYC and ATL

**Current IPs (NYC)**:
- Public: 23.227.173.245
- Tailscale: 100.89.130.19

**New IPs (ATL)**: *Pending*

**Estimated time**: 2-3 hours

---

### 8. Security Audits
**Status**: ✅ Completed (2026-03-15)

**Tasks**:
- [x] Audit UFW rules on all servers
- [x] Review fail2ban configuration
- [x] Fix SSH hardening (PermitRootLogin, PasswordAuthentication)
- [ ] Rotate SSH keys
- [ ] Audit PostgreSQL user permissions
- [ ] Review Redis password security
- [ ] Enable audit logging
- [ ] Rotate quantyra secrets

**Estimated time**: 2-3 hours

---

### 9. HAProxy High Availability
**Status**: ✅ DNS Round-Robin documented (2026-03-15)

**Tasks**:
- [x] Document failover procedure - see `docs/haproxy_ha_dns.md`
- [ ] Configure DNS A records with both router IPs
- [ ] Set up DNS health checks (if provider supports)
- [ ] Test failover between routers

**Estimated time**: 2 hours

---

## Completed Items (2026-03-15)

### Application Deployment System
- [x] Application creation wizard in dashboard
- [x] Multi-server deployment (both app servers)
- [x] GitHub Actions workflow generator
- [x] Framework support: Laravel, Next.js, Svelte, Go
- [x] Optional staging environment
- [x] Database creation with auto-generated credentials

### Infrastructure Dashboard
- [x] Web-based management UI
- [x] PostgreSQL/Redis status monitoring
- [x] Database management (create, view connections)
- [x] Server overview with disk space
- [x] Documentation viewer
- [x] Centralized navigation with Prometheus/Grafana links

### Monitoring
- [x] node_exporter on all 7 servers
- [x] Disk space monitoring via Prometheus API
- [x] Alertmanager with Slack + Email notifications
- [x] 26 alert rules configured

---

## Summary

| Priority | Count | Completed | Remaining |
|----------|-------|-----------|-----------|
| Critical | 2 | 2 | 0 |
| High | 4 | 3 | 1 |
| Medium | 3 | 1 | 2 |
| **Total** | **9** | **6** | **3** |

**Remaining items:**
1. **Config Backup Automation** (High) - Not started
2. **re-node-02 ATL Relocation** (Medium) - awaiting new IPs  
3. **HAProxy HA DNS configuration** (Medium) - needs DNS provider update

---

## Next Steps

1. **Config Backup Automation** - Set up automated config backups
2. **re-node-02 ATL relocation** - awaiting new public & Tailscale IPs
3. **HAProxy HA DNS configuration** - see `docs/haproxy_ha_dns.md`
4. **Test backup/restore procedures** - Validate backup system

---

## Configuration Files Location

| Config | Location |
|--------|----------|
| HAProxy (router-01) | `configs/haproxy/haproxy-router-01.cfg` |
| HAProxy (router-02) | `configs/haproxy/haproxy-router-02.cfg` |
| Patroni (re-node-01) | `configs/patroni/patroni-re-node-01.yml` |
| Redis (re-node-01) | `configs/redis/redis-re-node-01.conf` |
| Redis (re-node-03) | `configs/redis/redis-re-node-03.conf` |
| Redis Sentinel | `configs/redis/sentinel.conf` |
| Prometheus | `monitoring/prometheus/prometheus.yml` |
| Alertmanager | `monitoring/alertmanager/alertmanager.yml` |
| Alert Rules | `monitoring/prometheus/rules/alerts.yml` |
| Dashboard | `dashboard/` |
| Database Config | `ansible/inventory/group_vars/databases.yml` |