# Ansible Setup Progress

## ✅ Completed (Stage 1)

### SSH Hardening
- [x] Fixed `PermitRootLogin` on router-02 (was `yes`, now `prohibit-password`)
- [x] Disabled password authentication on router-02
- [x] Restarted SSH service

### Backup Infrastructure
- [x] Created `/backup` directories on all DB servers:
  - `/backup/pgbackrest` - PostgreSQL backups
  - `/backup/redis` - Redis backups
  - `/backup/configs` - Configuration backups
- [x] Installed `cron` on all DB servers
- [x] Deployed backup scripts to `/usr/local/bin/`:
  - `postgres_backup.sh` - PostgreSQL backup automation
  - `redis_backup.sh` - Redis backup automation
  - `sync_to_s3.sh` - S3 sync for offsite backups
- [x] Configured cron jobs:
  - PostgreSQL diff backup: Daily at 2:00 AM
  - PostgreSQL full backup: Sundays at 2:00 AM
  - Redis backup: Daily at 3:00 AM

## 🔄 Next Steps (Stage 2)

### Monitoring Enhancements
```bash
# Install Redis exporters
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/stage2-monitoring.yml
```

- [ ] Install Redis exporter on re-node-01, re-node-03
- [ ] Install HAProxy exporter on routers
- [ ] Update Prometheus scrape config
- [ ] Import Grafana dashboards

### Redis Sentinel (Stage 3)
- [ ] Install Redis Sentinel on router-01, router-02
- [ ] Configure for automatic failover
- [ ] Update application configs

### Configuration Backup (Stage 4)
- [ ] Create config backup script
- [ ] Add cron job for /backup/configs
- [ ] Set up S3 sync

## Quick Commands

```bash
# Test backup manually
ssh re-node-01 '/usr/local/bin/postgres_backup.sh diff'
ssh re-node-01 '/usr/local/bin/redis_backup.sh'

# View backup logs
ssh re-node-01 'tail -f /var/log/backup.log'

# Check cron jobs
ssh re-node-01 'crontab -l'

# Verify backup directories
ansible db_servers -i ansible/inventory/hosts.yml -m shell -a 'ls -la /backup/'
```

## Files Updated

| File | Purpose |
|------|---------|
| `~/.ssh/config` | Fixed re-db key, added public IP fallbacks |
| `ansible/inventory/hosts.yml` | Full server inventory with services |
| `ansible/playbooks/stage1-quickfixes.yml` | SSH + backup setup playbook |

## Inventory Summary

| Server | Ansible | SSH | Backups |
|--------|---------|-----|---------|
| re-node-01 | ✅ | ✅ | ✅ Scripts + Cron |
| re-node-03 | ✅ | ✅ | ✅ Scripts + Cron |
| re-node-04 | ✅ | ✅ | ✅ Scripts + Cron |
| router-01 | ✅ | ✅ | N/A |
| router-02 | ✅ | ✅ Fixed | N/A |
| re-db | ✅ | ✅ Fixed | N/A |
| re-node-02 | ✅ | ✅ Fixed | N/A |