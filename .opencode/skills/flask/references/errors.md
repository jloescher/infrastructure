# Errors Reference

## Contents
- Error Handler Registration
- Custom Exception Classes
- HTTP Status Codes
- Logging Patterns
- Client Error Responses

## Error Handler Registration

### Global Error Handlers

```python
@app.errorhandler(404)
def not_found(error):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not found"}), 404
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    # Log the full traceback
    app.logger.error(f"Server error: {error}", exc_info=True)
    
    if request.path.startswith('/api/'):
        return jsonify({"error": "Internal server error"}), 500
    return render_template('500.html'), 500

@app.errorhandler(psycopg2.Error)
def database_error(error):
    app.logger.error(f"Database error: {error}")
    return jsonify({"error": "Database unavailable"}), 503
```

## Custom Exception Classes

### Application-Specific Exceptions

```python
class InfrastructureError(Exception):
    """Base exception for infrastructure operations."""
    status_code = 500
    
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

class DeploymentError(InfrastructureError):
    """Deployment operation failed."""
    status_code = 400

class DomainNotFoundError(InfrastructureError):
    """Domain does not exist."""
    status_code = 404

class AuthenticationError(InfrastructureError):
    """Invalid credentials."""
    status_code = 401

# Error handler for custom exceptions
@app.errorhandler(InfrastructureError)
def handle_infrastructure_error(error):
    response = {"error": error.message}
    if error.payload:
        response.update(error.payload)
    return jsonify(response), error.status_code
```

## HTTP Status Codes

### Consistent Status Code Usage

| Code | Usage | Example |
|------|-------|---------|
| 200 | Success | GET request returned data |
| 201 | Created | Resource created successfully |
| 202 | Accepted | Async task queued |
| 400 | Bad Request | Validation failed |
| 401 | Unauthorized | Missing credentials |
| 403 | Forbidden | Valid auth, insufficient permissions |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Resource already exists |
| 422 | Unprocessable | Semantic validation failed |
| 500 | Server Error | Unexpected exception |
| 503 | Service Unavailable | Database unavailable |

### WARNING: Inconsistent Error Responses

**The Problem:**
```python
# BAD - Different error formats across endpoints
@app.route('/api/apps')
def list_apps():
    if error:
        return "Error occurred", 500  # Plain string

@app.route('/api/deploy')
def deploy():
    if error:
        return {"error": "Failed"}  # Dict without status
```

**The Fix:**
```python
# GOOD - Consistent JSON error format
def error_response(message, code=500, details=None):
    response = {"error": message, "code": code}
    if details:
        response["details"] = details
    return jsonify(response), code

@app.route('/api/apps')
def list_apps():
    try:
        apps = get_apps()
        return jsonify(apps)
    except Exception as e:
        return error_response("Failed to list apps", 500, str(e))
```

## Logging Patterns

### WARNING: Silent Failures

**The Problem:**
```python
# BAD - Error swallowed, no logging
@app.route('/api/health')
def health():
    try:
        check_database()
        return jsonify({"status": "ok"})
    except:
        return jsonify({"status": "error"}), 500
```

**The Fix:**
```python
# GOOD - Proper logging with context
import logging

logger = logging.getLogger(__name__)

@app.route('/api/health')
def health():
    try:
        check_database()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(
            f"Health check failed: {e}",
            extra={"endpoint": request.endpoint, "path": request.path},
            exc_info=True
        )
        return error_response("Health check failed", 503)
```

### Structured Logging

```python
import json

def log_request():
    """Log request details."""
    logger.info(
        f"{request.method} {request.path}",
        extra={
            "method": request.method,
            "path": request.path,
            "remote_addr": request.remote_addr,
            "user_agent": request.user_agent.string
        }
    )

@app.before_request
def before_request():
    log_request()
```

## Client Error Responses

### Validation Error Details

```python
def validate_app_config(config):
    errors = []
    if not config.get('name'):
        errors.append("name is required")
    if not config.get('repo'):
        errors.append("repo is required")
    if 'port' in config and not isinstance(config['port'], int):
        errors.append("port must be an integer")
    return errors

@app.route('/api/apps', methods=['POST'])
def create_app():
    config = request.get_json()
    errors = validate_app_config(config)
    if errors:
        return jsonify({
            "error": "Validation failed",
            "code": 400,
            "details": errors
        }), 400
    
    # Proceed with creation
```

### Exception Context Preservation

```python
def safe_operation():
    try:
        risky_call()
    except subprocess.CalledProcessError as e:
        raise DeploymentError(
            f"Command failed: {e.cmd}",
            details={
                "returncode": e.returncode,
                "stdout": e.stdout,
                "stderr": e.stderr
            }
        ) from e