# Services Reference

## Contents
- Service Organization Patterns
- Database Service Functions
- External API Integration
- Background Task Patterns
- Configuration Management

## Service Organization Patterns

The dashboard uses functional organization rather than class-based services.

### WARNING: God Functions

**The Problem:**
```python
# BAD - 200+ line function doing everything
@app.route('/deploy')
def deploy():
    # Validate input
    # Clone repo
    # Install deps
    # Build assets
    # Run migrations
    # Configure nginx
    # Update HAProxy
    # Health check
    # Return result
```

**Why This Breaks:**
1. Impossible to test individual steps
2. Single failure requires full rollback knowledge
3. No reusability between web and CLI contexts

**The Fix:**
```python
# GOOD - Composed service functions
@app.route('/deploy')
def deploy():
    try:
        result = deployment_service.deploy_app(
            name=request.form['app'],
            env=request.form['environment']
        )
        return jsonify(result)
    except DeploymentError as e:
        return jsonify({"error": str(e)}), 500

# In deployment_service.py or app.py functions
def deploy_app(name, env):
    validate_app_exists(name)
    clone_repository(name)
    install_dependencies(name, env)
    run_migrations(name)
    configure_web_server(name)
    update_load_balancer(name)
    return {"status": "success"}
```

## Database Service Functions

### WARNING: Connection Leaks

**The Problem:**
```python
# BAD - Connection never closed on exception
def get_app(name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM apps WHERE name = %s", (name,))
    return cur.fetchone()  # Connection left hanging
```

**The Fix:**
```python
# GOOD - Context manager ensures cleanup
def get_app(name):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM apps WHERE name = %s", (name,))
            return cur.fetchone()
    finally:
        conn.close()
```

### Transaction Wrapper

```python
def with_transaction(func):
    """Decorator for atomic database operations."""
    def wrapper(*args, **kwargs):
        conn = get_db_connection()
        try:
            result = func(conn, *args, **kwargs)
            conn.commit()
            return result
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    return wrapper

@with_transaction
def create_app(conn, name, config):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO applications (name, config) VALUES (%s, %s)",
            (name, json.dumps(config))
        )
```

## External API Integration

### Cloudflare API Pattern

```python
import requests

def cloudflare_request(endpoint, method='GET', data=None):
    headers = {
        'Authorization': f'Bearer {os.getenv("CLOUDFLARE_API_TOKEN")}',
        'Content-Type': 'application/json'
    }
    url = f'https://api.cloudflare.com/client/v4{endpoint}'
    
    try:
        resp = requests.request(
            method, url, headers=headers, json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
    except requests.Timeout:
        raise ExternalAPIError("Cloudflare API timeout")
    except requests.RequestException as e:
        raise ExternalAPIError(f"Cloudflare API error: {e}")
```

### GitHub API with Pagination

```python
def get_github_repos(org):
    repos = []
    page = 1
    while True:
        resp = requests.get(
            f'https://api.github.com/orgs/{org}/repos',
            params={'page': page, 'per_page': 100},
            headers={'Authorization': f'token {GITHUB_TOKEN}'},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos
```

## Background Task Patterns

### WARNING: Fire-and-Forget Errors

**The Problem:**
```python
# BAD - Thread errors swallowed, no logging
@app.route('/rebuild')
def rebuild():
    threading.Thread(target=long_task).start()
    return "Started"

def long_task():
    raise Exception("Failed")  # Disappears into the void
```

**The Fix:**
```python
# GOOD - Error handling in thread
import logging

@app.route('/rebuild')
def rebuild():
    thread = threading.Thread(target=long_task)
    thread.start()
    return jsonify({"status": "started", "task_id": generate_id()})

def long_task():
    try:
        do_work()
    except Exception as e:
        logging.error(f"Background task failed: {e}", exc_info=True)
        notify_admin(f"Task failed: {e}")
```

## Configuration Management

### Environment-Based Config

```python
class Config:
    PG_HOST = os.getenv('PG_HOST', 'localhost')
    PG_PORT = int(os.getenv('PG_PORT', '5432'))
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(32))

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True

config = {
    'production': ProductionConfig,
    'development': DevelopmentConfig
}