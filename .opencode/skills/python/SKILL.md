---
name: python
description: Manages Python code patterns, dependencies, and Flask application development for the infrastructure dashboard. Use when writing Python code for the dashboard, managing dependencies, handling database connections, or implementing API endpoints.
---

# Python Skill

This project uses Python 3.x with Flask for the infrastructure dashboard. Code is organized with strict naming conventions and import ordering. The dashboard interacts with PostgreSQL via psycopg2, Redis for caching, and external APIs via requests.

## Quick Start

### Basic Flask Route

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})
```

### Database Connection Pattern

```python
import psycopg2
from contextlib import contextmanager

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(
        host=os.environ['PG_HOST'],
        port=os.environ['PG_PORT'],
        user=os.environ['PG_USER'],
        password=os.environ['PG_PASSWORD']
    )
    try:
        yield conn
    finally:
        conn.close()
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Functions | snake_case | `def provision_domain():` |
| Variables | snake_case | `app_name`, `environment` |
| Constants | SCREAMING_SNAKE_CASE | `APP_PORT_RANGE` |
| Files | lowercase with underscores | `app.py`, `provision_domain.sh` |
| Import Order | stdlib → external → internal | See patterns reference |

## Common Patterns

### Import Organization

**When:** Any Python file in the dashboard

```python
# 1. Standard library
import os
import subprocess
from datetime import datetime

# 2. External packages
from flask import Flask, render_template
import psycopg2
import redis
import requests

# 3. Internal imports (none in dashboard - single file)
```

### Environment-based Configuration

**When:** Managing secrets and configuration

```python
import os

PG_HOST = os.environ.get('PG_HOST', '100.102.220.16')
PG_PORT = int(os.environ.get('PG_PORT', 5000))

# NEVER hardcode credentials
# BAD: password = 'secret123'
```

## See Also

- [patterns](references/patterns.md) - Idiomatic Python patterns
- [types](references/types.md) - Type hints and data structures
- [modules](references/modules.md) - Module organization
- [errors](references/errors.md) - Exception handling

## Related Skills

- **flask** - Web framework patterns for the dashboard
- **postgresql** - Database interactions via psycopg2
- **redis** - Caching and session management
- **docker** - Container deployment for the dashboard