# Python Errors Reference

## Contents
- Exception Hierarchy
- Try/Except Patterns
- Raising Exceptions
- Error Logging

## Exception Hierarchy

Catch specific exceptions, never bare `except:`.

```python
# GOOD - specific exceptions
try:
    conn = psycopg2.connect(**params)
    cur = conn.cursor()
    cur.execute(query)
except psycopg2.OperationalError as e:
    logger.error(f"Database connection failed: {e}")
    raise
except psycopg2.ProgrammingError as e:
    logger.error(f"Invalid SQL: {e}")
    return None
```

```python
# BAD - catches everything including KeyboardInterrupt
try:
    risky_operation()
except:  # Never do this
    pass
```

### WARNING: Bare Except Clauses

**The Problem:**

```python
# BAD - masks system exit and keyboard interrupt
try:
    process_data()
except:
    logger.error("Something went wrong")  # User can't Ctrl+C!
```

**Why This Breaks:**
1. Catches `SystemExit`, `KeyboardInterrupt`
2. Masks critical failures
3. Makes debugging impossible

**The Fix:**

```python
# GOOD - catch specific exceptions
try:
    process_data()
except Exception as e:  # Still broad, but doesn't catch system events
    logger.error(f"Processing failed: {e}")
    raise
```

## Try/Except Patterns

Keep try blocks small. Use else for success-only code.

```python
# GOOD - small try block
try:
    result = fetch_data()
except ConnectionError:
    return None
else:
    # Only runs if no exception
    cache_result(result)
    return process(result)
```

```python
# BAD - too much in try block
try:
    result = fetch_data()
    cache_result(result)  # What if this fails?
    process(result)
    return result
except ConnectionError:  # Can't tell which line failed
    ...
```

## Raising Exceptions

Use built-in exceptions for common cases. Create custom exceptions for domain errors.

```python
# GOOD - built-in exceptions
def get_port(app_name: str) -> int:
    if app_name not in registry:
        raise KeyError(f"App {app_name} not found")
    port = registry[app_name]
    if not (8100 <= port <= 8199):
        raise ValueError(f"Port {port} out of range")
    return port
```

```python
# GOOD - custom exception for domain
class DeploymentError(Exception):
    """Raised when deployment fails."""
    pass

def deploy_app(app_name: str):
    if not run_deploy_script(app_name):
        raise DeploymentError(f"Failed to deploy {app_name}")
```

## Error Logging

Log exceptions with context. Use `exc_info` for stack traces.

```python
import logging

logger = logging.getLogger(__name__)

# GOOD - with context
try:
    deploy_app(app_name)
except Exception as e:
    logger.error(f"Deployment failed for {app_name}: {e}", exc_info=True)
    raise
```

```python
# BAD - silent failure
try:
    deploy_app(app_name)
except Exception:
    pass  # Deployment failed silently!