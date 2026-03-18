---
name: flask
description: Handles Flask web application routes, templates, and API endpoints for the Quantyra infrastructure dashboard. Use when writing dashboard features, API endpoints, webhook handlers, database-backed routes, or template rendering.
---

# Flask Skill

Flask powers the infrastructure management dashboard in `dashboard/app.py`. The application follows a monolithic single-file pattern with Jinja2 templates, PostgreSQL for persistence, and Redis for caching. No Flask extensions like Flask-SQLAlchemy or Flask-Login are used—connections are managed manually.

## Quick Start

### Basic Route with Database Query

```python
from flask import Flask, render_template, request, jsonify
import psycopg2
import os

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('PG_HOST'),
        port=os.getenv('PG_PORT', '5000'),
        user=os.getenv('PG_USER'),
        password=os.getenv('PG_PASSWORD'),
        database='infrastructure'
    )

@app.route('/applications')
def list_applications():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM applications ORDER BY name")
            apps = cur.fetchall()
        return render_template('applications.html', applications=apps)
    finally:
        conn.close()
```

### API Endpoint with JSON Response

```python
@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"status": "healthy", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Route | `@app.route('/path')` | `@app.route('/api/deploy')` |
| Methods | `methods=['POST']` | `@app.route('/hook', methods=['POST'])` |
| Parameters | `<variable>` | `/app/<name>/deploy` |
| Query args | `request.args.get()` | `request.args.get('env', 'production')` |
| Form data | `request.form.get()` | `request.form.get('app_name')` |
| JSON body | `request.get_json()` | `request.get_json()['repository']` |

## Common Patterns

### Webhook Handler (Async Processing)

**When:** GitHub webhooks that must return immediately but trigger long-running tasks.

```python
import threading

@app.route('/webhook/deploy', methods=['POST'])
def webhook_deploy():
    payload = request.get_json()
    repo = payload.get('repository', {}).get('full_name')
    
    # Return 202 immediately, process async
    threading.Thread(
        target=process_deployment,
        args=(repo, payload)
    ).start()
    
    return jsonify({"status": "accepted"}), 202
```

### Database Connection with Context Manager

```python
from contextlib import contextmanager

@contextmanager
def db_cursor():
    conn = get_db_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Usage
with db_cursor() as cur:
    cur.execute("INSERT INTO logs (msg) VALUES (%s)", ("deployed",))
```

## See Also

- [routes](references/routes.md) - Route patterns and URL design
- [services](references/services.md) - Business logic organization
- [database](references/database.md) - PostgreSQL connection patterns
- [auth](references/auth.md) - Authentication and authorization
- [errors](references/errors.md) - Error handling and logging

## Related Skills

- **python** - General Python patterns
- **postgresql** - Database operations
- **redis** - Caching patterns
- **docker** - Containerization