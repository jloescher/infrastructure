# Python Modules Reference

## Contents
- Module Structure
- Circular Imports
- Absolute vs Relative Imports
- Single File Pattern (Dashboard)

## Module Structure

Organize modules by functionality. The dashboard currently uses a single-file pattern.

```python
# dashboard/app.py - current structure
"""
Dashboard application main module.
Handles web routes, database operations, and external API calls.
"""

import os
import subprocess
from datetime import datetime

from flask import Flask, render_template, jsonify
import psycopg2
import redis

# Configuration
APP_PORT_RANGE = range(8100, 8200)

# Database helpers
def get_db_conn():
    ...

# Route handlers
@app.route('/')
def index():
    ...
```

### WARNING: Circular Imports

**The Problem:**

```python
# app.py
from models import App
from utils import format_app

# models.py
from app import db  # Circular import!
```

**Why This Breaks:**
1. Import system enters infinite loop
2. Modules partially initialized
3. AttributeError on seemingly available imports

**The Fix:**

```python
# GOOD - late import inside function
def get_app():
    from app import db  # Import when needed
    return db.query(App).first()

# GOOD - merge into single module if tightly coupled
# dashboard/app.py contains everything (current pattern)
```

## Absolute vs Relative Imports

Use absolute imports always. Relative imports break when module is run directly.

```python
# GOOD - absolute import
from dashboard.config import settings

# BAD - relative import
from .config import settings  # Fails if run as script
```

## Single File Pattern (Dashboard)

The dashboard uses a single `app.py` file. This is acceptable for moderate complexity.

```python
# dashboard/app.py organization pattern:

# 1. Imports
# 2. Configuration constants
# 3. Database connection helpers
# 4. External API clients (GitHub, Cloudflare)
# 5. Flask route handlers
# 6. Main block

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

When to split into multiple files:
- Routes exceed 500 lines
- Reusable utilities needed by other scripts
- Testing requires isolated modules