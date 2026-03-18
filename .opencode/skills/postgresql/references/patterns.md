# PostgreSQL Patterns Reference

## Contents
- Connection Management
- Query Patterns
- Schema Migrations
- Replication Handling
- Anti-Patterns

## Connection Management

### Environment-Based Configuration

```python
# GOOD: Centralize connection params
PG_CONFIG = {
    "host": os.environ.get("PG_HOST", "100.102.220.16"),
    "port": int(os.environ.get("PG_PORT", 5000)),
    "user": os.environ["PG_USER"],
    "password": os.environ["PG_PASSWORD"],
}

def get_conn(read_only=False):
    cfg = PG_CONFIG.copy()
    cfg["port"] = 5001 if read_only else 5000
    return psycopg2.connect(**cfg)
```

### Context Manager for Transactions

```python
from contextlib import contextmanager

@contextmanager
def transaction():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# Usage
with transaction() as conn:
    cursor = conn.cursor()
    cursor.execute("UPDATE apps SET status = %s", ("deploying",))
```

## Query Patterns

### Parameterized Queries (ALWAYS)

```python
# GOOD - Safe from SQL injection
cursor.execute(
    "SELECT * FROM apps WHERE name = %s AND env = %s",
    (app_name, environment)
)

# BAD - String formatting vulnerability
cursor.execute(f"SELECT * FROM apps WHERE name = '{app_name}'")
```

### Bulk Inserts with execute_values

```python
from psycopg2.extras import execute_values

data = [(app["name"], app["repo"]) for app in apps_list]
execute_values(
    cursor,
    "INSERT INTO apps (name, repo) VALUES %s",
    data
)
```

## Schema Migrations

### Laravel: Migration Command

```bash
# Production (forced non-interactive)
ssh re-db "cd /opt/apps/{app} && php artisan migrate --force"

# Check status first
ssh re-db "cd /opt/apps/{app} && php artisan migrate:status"
```

### Manual: Idempotent DDL

```sql
-- Add column if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apps' AND column_name = 'webhook_secret'
    ) THEN
        ALTER TABLE apps ADD COLUMN webhook_secret VARCHAR(255);
    END IF;
END $$;
```

## Replication Handling

### Forcing Read-After-Write Consistency

```python
# After write, read from leader to avoid stale data
def create_and_fetch(cursor, data):
    cursor.execute(
        "INSERT INTO deployments (app_id, status) VALUES (%s, %s) RETURNING *",
        (data["app_id"], "pending")
    )
    result = cursor.fetchone()
    # Return immediately - no need for separate read
    return result
```

### Monitoring Lag

```bash
# On any PostgreSQL node
psql -c "SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) AS lag_seconds;"
```

## Anti-Patterns

### WARNING: Writing to Read Endpoint

**The Problem:**

```python
# BAD - Write sent to replica port will fail or be ignored
conn = psycopg2.connect(port=5001)  # Read endpoint
cursor = conn.cursor()
cursor.execute("UPDATE apps SET status = 'active'")  # FAILS
```

**Why This Breaks:**
1. HAProxy route 5001 only targets replicas
2. PostgreSQL replicas are read-only by default
3. Error: `cannot execute UPDATE in a read-only transaction`

**The Fix:**

```python
# GOOD - Explicit write vs read routing
def get_conn(read_only=False):
    port = 5001 if read_only else 5000
    return psycopg2.connect(host=PG_HOST, port=port, ...)
```

### WARNING: Long-Running Transactions

**The Problem:**

```python
# BAD - Transaction held open during slow operation
with get_conn() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM large_table")  # Starts transaction
    time.sleep(300)  # Simulate slow processing
    # Transaction held for 5 minutes - blocks vacuum
```

**Why This Breaks:**
1. Prevents PostgreSQL from cleaning up dead tuples
2. Causes table bloat and performance degradation
3. Can block DDL operations

**The Fix:**

```python
# GOOD - Fetch all data, then process outside transaction
with get_conn() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM large_table")
    rows = cursor.fetchall()
# Process rows outside transaction
process_rows(rows)