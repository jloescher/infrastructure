# Database Reference

## Contents
- Connection Management
- Query Patterns
- Transaction Handling
- N+1 Prevention
- Connection Pooling

## Connection Management

### WARNING: Global Connection Objects

**The Problem:**
```python
# BAD - Global connection shared across requests
conn = psycopg2.connect(
    host=os.getenv('PG_HOST'),
    port=os.getenv('PG_PORT'),
    user=os.getenv('PG_USER'),
    password=os.getenv('PG_PASSWORD')
)

@app.route('/data')
def get_data():
    cur = conn.cursor()  # Race conditions, not thread-safe
    cur.execute("SELECT * FROM data")
    return jsonify(cur.fetchall())
```

**Why This Breaks:**
1. `psycopg2` connections are not thread-safe
2. Concurrent requests corrupt cursor state
3. Connection timeouts not handled per-request

**The Fix:**
```python
# GOOD - Connection per request
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT', '5000'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
        database='infrastructure',
        connect_timeout=10
    )

@app.route('/data')
def get_data():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM data")
            return jsonify(cur.fetchall())
    finally:
        conn.close()
```

### Connection Factory with Retry

```python
import time

def get_db_connection(retries=3):
    for attempt in range(retries):
        try:
            return psycopg2.connect(
                host=os.getenv('PG_HOST'),
                port=os.getenv('PG_PORT', '5000'),
                user=os.getenv('PG_USER'),
                password=os.getenv('PG_PASSWORD'),
                database='infrastructure',
                connect_timeout=10
            )
        except psycopg2.OperationalError as e:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))
```

## Query Patterns

### Parameterized Queries (ALWAYS)

```python
# GOOD - Parameterized prevents injection
def get_app_by_name(name):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, config FROM applications WHERE name = %s",
                (name,)  # Tuple for single parameter
            )
            return cur.fetchone()
    finally:
        conn.close()

# Multiple parameters
def create_app(name, config, created_by):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO applications (name, config, created_by, created_at)
                   VALUES (%s, %s, %s, NOW()) RETURNING id""",
                (name, json.dumps(config), created_by)
            )
            return cur.fetchone()[0]
    finally:
        conn.close()
```

### WARNING: String Concatenation in Queries

**The Problem:**
```python
# BAD - SQL injection vulnerability
def search_apps(term):
    cur.execute(f"SELECT * FROM apps WHERE name LIKE '%{term}%'")
```

**The Fix:**
```python
# GOOD - Parameterized with wildcards
def search_apps(term):
    cur.execute(
        "SELECT * FROM apps WHERE name LIKE %s",
        (f'%{term}%',)
    )
```

## Transaction Handling

### Explicit Transaction Control

```python
def transfer_domain(old_app, new_app, domain):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Verify old app owns domain
            cur.execute(
                "SELECT 1 FROM domains WHERE name = %s AND app_id = %s",
                (domain, old_app)
            )
            if not cur.fetchone():
                raise ValueError("Domain not owned by old app")
            
            # Update to new app
            cur.execute(
                "UPDATE domains SET app_id = %s WHERE name = %s",
                (new_app, domain)
            )
            
            # Log transfer
            cur.execute(
                "INSERT INTO domain_transfers (domain, from_app, to_app) VALUES (%s, %s, %s)",
                (domain, old_app, new_app)
            )
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()
```

## N+1 Prevention

### Batch Queries with JOINs

**The Problem:**
```python
# BAD - N+1 query per application
def get_apps_with_domains():
    apps = get_all_apps()  # 1 query
    for app in apps:
        app['domains'] = get_domains_for_app(app['id'])  # N queries
    return apps
```

**The Fix:**
```python
# GOOD - Single query with JOIN
def get_apps_with_domains():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT a.id, a.name, d.name as domain
                FROM applications a
                LEFT JOIN domains d ON a.id = d.app_id
                ORDER BY a.name
            """)
            apps = {}
            for row in cur.fetchall():
                app_id, app_name, domain = row
                if app_id not in apps:
                    apps[app_id] = {'id': app_id, 'name': app_name, 'domains': []}
                if domain:
                    apps[app_id]['domains'].append(domain)
            return list(apps.values())
    finally:
        conn.close()
```

## Connection Pooling

### WARNING: No Built-in Pooling

This project does not use `psycopg2.pool` or SQLAlchemy connection pooling. Each request creates a new connection.

**Missing Solution:**
Consider adding `psycopg2.pool.ThreadedConnectionPool` for production workloads:

```python
from psycopg2 import pool

# Initialize once at startup
connection_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,
    host=os.getenv('PG_HOST'),
    port=os.getenv('PG_PORT', '5000'),
    user=os.getenv('PG_USER'),
    password=os.getenv('PG_PASSWORD'),
    database='infrastructure'
)

def get_pooled_connection():
    return connection_pool.getconn()

def release_connection(conn):
    connection_pool.putconn(conn)