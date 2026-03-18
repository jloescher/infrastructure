# Authentication Reference

## Contents
- Dashboard Authentication
- API Key Patterns
- Webhook Verification
- Basic Auth for Staging

## Dashboard Authentication

The dashboard uses simple session-based authentication with Flask's built-in sessions.

### WARNING: Hardcoded Credentials

**The Problem:**
```python
# BAD - Credentials in source control
USERS = {
    'admin': 'password123'  # Never do this
}
```

**The Fix:**
```python
# GOOD - Environment-based credentials
import os

DASHBOARD_USER = os.getenv('DASHBOARD_USER', 'admin')
DASHBOARD_PASS = os.getenv('DASHBOARD_PASS')

def verify_credentials(username, password):
    if not DASHBOARD_PASS:
        return False
    return username == DASHBOARD_USER and password == DASHBOARD_PASS
```

### Session-Based Login

```python
from flask import session, redirect, url_for

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if verify_credentials(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def require_auth(f):
    """Decorator to protect routes."""
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

@app.route('/admin')
@require_auth
def admin():
    return render_template('admin.html')
```

### WARNING: Missing CSRF Protection

This project does not use Flask-WTF for CSRF protection. For state-changing forms, consider:

```python
# Manual CSRF token implementation
import secrets

@app.before_request
def csrf_protect():
    if request.method == 'POST':
        token = session.pop('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token'):
            return jsonify({"error": "CSRF token missing"}), 403

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

# In templates: <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
app.jinja_env.globals['csrf_token'] = generate_csrf_token
```

## API Key Patterns

### Simple Token Auth

```python
API_KEYS = os.getenv('API_KEYS', '').split(',')

def require_api_key(f):
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "Missing API key"}), 401
        
        token = auth_header[7:]
        if token not in API_KEYS:
            return jsonify({"error": "Invalid API key"}), 403
        
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

@app.route('/api/internal/servers')
@require_api_key
def list_servers():
    return jsonify(get_servers())
```

## Webhook Verification

### GitHub Webhook Signature

```python
import hmac
import hashlib

def verify_github_signature(payload, signature):
    """Verify GitHub webhook signature."""
    secret = os.getenv('GITHUB_WEBHOOK_SECRET', '').encode()
    expected = 'sha256=' + hmac.new(
        secret, payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.route('/webhook/github', methods=['POST'])
def github_webhook():
    signature = request.headers.get('X-Hub-Signature-256', '')
    if not verify_github_signature(request.data, signature):
        return jsonify({"error": "Invalid signature"}), 401
    
    # Process webhook
    payload = request.get_json()
    return jsonify({"status": "processed"})
```

## Basic Auth for Staging

HAProxy handles basic auth for staging environments, but for application-level basic auth:

```python
from functools import wraps

def require_basic_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not verify_credentials(auth.username, auth.password):
            return ('Unauthorized', 401, {
                'WWW-Authenticate': 'Basic realm="Staging"'
            })
        return f(*args, **kwargs)
    return decorated

@app.route('/staging')
@require_basic_auth
def staging_dashboard():
    return render_template('staging.html')