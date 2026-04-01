# DB-UI Backup & Restore Runbook

> Backup and recovery procedures for pgAdmin and Ivory database management tools.

## Service Overview

| Service | Port | Volume | Purpose |
|---------|------|--------|---------|
| pgAdmin | 8081 | `db-ui_pgadmin-data` | PostgreSQL database management UI |
| Ivory | 8082 | `db-ui_ivory-data` | PostgreSQL ERD and schema visualization |

**Server:** router-01 (100.102.220.16)

**Docker Compose:** `/opt/db-ui/docker-compose.yml`

---

## Daily Backup

### Automatic Backup

Backups run automatically at **03:00 UTC** daily via cron.

**Backup location:** `/backup/db-ui/`

**Files:**
- `pgadmin-YYYYMMDD-HHMMSS.tar.gz`
- `ivory-YYYYMMDD-HHMMSS.tar.gz`

**Retention:** 7 days

### Manual Backup

```bash
# Run backup manually
/usr/local/bin/backup-db-ui.sh

# Check backup files
ls -lh /backup/db-ui/
```

### Verify Backup

```bash
# Check backup log
cat /var/log/db-ui-backup.log

# Test backup integrity
cd /backup/db-ui
tar tzf pgadmin-*.tar.gz | head -10
tar tzf ivory-*.tar.gz | head -10
```

---

## Restore Procedure

### Restore pgAdmin

```bash
# 1. Stop pgAdmin container
docker stop pgadmin

# 2. Backup current volume (just in case)
docker run --rm -v db-ui_pgadmin-data:/data -v /backup/db-ui:/backup alpine \
    tar czf /backup/pgadmin-pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .

# 3. Clear existing data
docker volume rm db-ui_pgadmin-data
docker volume create db-ui_pgadmin-data

# 4. Restore from backup
docker run --rm -v db-ui_pgadmin-data:/data -v /backup/db-ui:/backup alpine \
    tar xzf /backup/pgadmin-YYYYMMDD-HHMMSS.tar.gz -C /data

# 5. Start pgAdmin
docker start pgadmin

# 6. Verify
curl -s http://localhost:8081 | head -10
```

### Restore Ivory

```bash
# 1. Stop Ivory container
docker stop ivory

# 2. Backup current volume
docker run --rm -v db-ui_ivory-data:/data -v /backup/db-ui:/backup alpine \
    tar czf /backup/ivory-pre-restore-$(date +%Y%m%d-%HMMSS).tar.gz -C /data .

# 3. Clear and restore
docker volume rm db-ui_ivory-data
docker volume create db-ui_ivory-data

docker run --rm -v db-ui_ivory-data:/data -v /backup/db-ui:/backup alpine \
    tar xzf /backup/ivory-YYYYMMDD-HHMMSS.tar.gz -C /data

# 4. Start Ivory
docker start ivory

# 5. Verify
curl -s http://localhost:8082 | head -10
```

---

## pgAdmin Configuration

### Access pgAdmin

```
URL: http://100.102.220.16:8081
Email: admin@quantyra.internal
Password: xgRsJByGrGMkWRHANq62
```

### Connect to PostgreSQL Cluster

**Write endpoint (RW):**
```
Host: 100.102.220.16 (or router-02: 100.116.175.9)
Port: 5000
Database: postgres
Username: patroni_superuser
Password: 2e7vBpaaVK4vTJzrKebC
```

**Read endpoint (RO):**
```
Host: 100.102.220.16 (or router-02)
Port: 5001
```

### Register Server in pgAdmin

1. Right-click "Servers" → "Register" → "Server"
2. **General tab:**
   - Name: `Quantyra Production`
3. **Connection tab:**
   - Host: `100.102.220.16`
   - Port: `5000`
   - Database: `postgres`
   - Username: `patroni_superuser`
   - Password: `2e7vBpaaVK4vTJzrKebC`
4. Click "Save"

### Create Database for Coolify App

1. Connect to `Quantyra Production` server
2. Right-click "Databases" → "Create" → "Database"
3. Enter database name (e.g., `myapp_production`)
4. Owner: Select or create a user
5. Click "Save"

### Create Database User

1. Open Query Tool on `postgres` database
2. Run:
```sql
-- Create user
CREATE USER myapp_user WITH PASSWORD 'secure_password';

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE myapp_production TO myapp_user;

-- Connect to the new database and grant schema permissions
\c myapp_production
GRANT ALL ON SCHEMA public TO myapp_user;
```

---

## Ivory Configuration

### Access Ivory

```
URL: http://100.102.220.16:8082
```

### Connect to Database

1. Click "New Connection"
2. Enter connection details:
   - Name: `Quantyra Production`
   - Host: `100.102.220.16`
   - Port: `5000`
   - Database: `postgres`
   - User: `patroni_superuser`
   - Password: `2e7vBpaaVK4vTJzrKebC`
3. Click "Connect"

### Generate ERD

1. Select a database/schema
2. Click "Generate ERD"
3. Drag tables to canvas
4. Export as PNG/SVG/PDF

---

## Troubleshooting

### pgAdmin Won't Start

```bash
# Check container status
docker logs pgadmin --tail 50

# Check volume permissions
docker run --rm -v db-ui_pgadmin-data:/data alpine ls -la /data

# Reset permissions
docker run --rm -v db-ui_pgadmin-data:/data alpine chown -R 5050:5050 /data
```

### Ivory Connection Failed

```bash
# Check if Ivory can reach PostgreSQL
docker exec ivory ping -c 2 100.102.220.16

# Check extra_hosts in compose file
docker inspect ivory | grep -A 10 ExtraHosts

# Verify PostgreSQL is accepting connections
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -l
```

### Backup Failed

```bash
# Check disk space
df -h /backup

# Check if volumes exist
docker volume ls | grep db-ui

# Check Alpine image availability
docker pull alpine:latest
```

---

## Cron Job Status

```bash
# Check if cron is running
systemctl status cron

# View cron jobs
crontab -l

# Check last backup
ls -lt /backup/db-ui/*.tar.gz | head -2
```

---

## Related Documentation

- [PAAS Complete Guide](paas-complete-guide.md)
- [PostgreSQL Cluster](patroni/) - Patroni configuration
- [Architecture](architecture.md) - Infrastructure overview