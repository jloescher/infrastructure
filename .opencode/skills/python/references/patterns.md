# Python Patterns Reference

## Contents
- Import Organization
- Mutable Default Arguments
- Context Managers for Resources
- String Formatting
- List/Dict Comprehensions

## Import Organization

Always order imports: stdlib → third-party → local.

```python
# GOOD
import os
import sys
from datetime import datetime

from flask import Flask
import psycopg2
import redis
```

```python
# BAD - mixed order
from flask import Flask
import os
import psycopg2
from datetime import datetime
```

### WARNING: Mutable Default Arguments

**The Problem:**

```python
# BAD - shared state across calls
def get_apps(status='active', cache=[]):
    if not cache:
        cache = fetch_from_db()
    return cache
```

**Why This Breaks:**
1. The list is created once at function definition time
2. All calls share the same list object
3. Modifications persist between calls

**The Fix:**

```python
# GOOD - create inside function
def get_apps(status='active', cache=None):
    if cache is None:
        cache = fetch_from_db()
    return cache
```

## Context Managers for Resources

Always use context managers for database connections and files.

```python
# GOOD - automatic cleanup
with psycopg2.connect(**conn_params) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM apps")
        return cur.fetchall()
# Connection closed automatically
```

```python
# BAD - resource leak on exception
conn = psycopg2.connect(**conn_params)
cur = conn.cursor()
cur.execute("SELECT * FROM apps")  # If this fails, connection leaks
```

## String Formatting

Use f-strings for readability. Use parameterized queries for SQL.

```python
# GOOD - f-strings for non-SQL
message = f"Deploying {app_name} to {environment}"

# GOOD - parameterized queries for SQL
cur.execute("SELECT * FROM apps WHERE name = %s", (app_name,))
```

```python
# BAD - string concatenation
message = "Deploying " + app_name + " to " + environment

# CRITICAL: Never use f-strings for SQL
cur.execute(f"SELECT * FROM apps WHERE name = '{app_name}'")  # SQL injection risk
```

## List/Dict Comprehensions

Use comprehensions for simple transformations. Use loops for complex logic.

```python
# GOOD - simple transformation
app_names = [app['name'] for app in apps if app['status'] == 'active']

# GOOD - dict comprehension
app_ports = {app['name']: app['port'] for app in apps}
```

```python
# BAD - overcomplicated comprehension
result = [complex_operation(app) for app in apps 
          if condition1(app) and condition2(app) and nested_call(app)]
# Use a regular loop instead