---
name: postgresql
description: Handles PostgreSQL database operations and Patroni cluster management for the Quantyra infrastructure. Use when writing database queries, managing Patroni clusters, configuring connection pooling, running migrations, debugging replication lag, or performing backup/recovery operations.
---

# PostgreSQL Skill

Quantyra runs PostgreSQL 18.x in a 3-node Patroni cluster with HAProxy load balancing. Writes route to port 5000 (leader), reads to port 5001 (replicas). The dashboard uses **psycopg2** for direct connections.

## Quick Start

### Connection (Dashboard)

```python
import psycopg2

conn = psycopg2.connect(
    host="100.102.220.16",      # HAProxy router
    port=5000,                   # 5000=write, 5001=read
    user="patroni_superuser",
    password=os.environ["PG_PASSWORD"],
    database="quantyra"
)
```

### Check Cluster Health

```bash
ssh root@100.102.220.16 'patronictl list'
```

### Run Migrations (Laravel App)

```bash
cd /opt/apps/{app_name} && php artisan migrate --force
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Write endpoint | Leader-only | `router-01:5000` |
| Read endpoint | Load-balanced replicas | `router-01:5001` |
| Cluster state | Via Patroni | `patronictl list` |
| Replication lag | Monitor in Grafana | `postgresql_replication_lag` |
| Connection pooling | Per-app PHP-FPM | `pm.max_children` |

## Common Patterns

### Read/Write Splitting

**When:** Dashboard needs to offload reads without cluster-aware driver.

```python
def get_db_connection(read_only=False):
    port = 5001 if read_only else 5000
    return psycopg2.connect(host=PG_HOST, port=port, ...)
```

### Idempotent Migrations

**When:** Deploying apps that may run migrations multiple times.

```python
# Use IF NOT EXISTS for DDL
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL
    )
""")
```

## See Also

- [patterns](references/patterns.md)
- [workflows](references/workflows.md)

## Related Skills

- **patroni** - Cluster management and failover operations
- **python** - psycopg2 usage patterns
- **flask** - SQLAlchemy integration in dashboard
- **haproxy** - Connection routing and health checks
- **prometheus** - Query metrics and alerting rules