# Routes Reference

## Contents
- Route Registration Patterns
- URL Parameter Handling
- HTTP Method Selection
- Request Data Access
- Response Patterns

## Route Registration Patterns

### WARNING: Dynamic Route Generation

**The Problem:**
```python
# BAD - Routes generated in loops without proper endpoint names
for app in ['foo', 'bar', 'baz']:
    @app.route(f'/api/{app}/deploy')  # Missing endpoint parameter
    def deploy():  # Same function name overwritten each iteration
        return f"Deploy {app}"  # Closure captures last value only
```

**Why This Breaks:**
1. Flask uses function `__name__` as default endpoint; all routes get same endpoint
2. URL building with `url_for()` returns wrong URLs
3. Last iteration wins—earlier routes become inaccessible

**The Fix:**
```python
# GOOD - Explicit endpoints and unique handlers
def make_deploy_handler(app_name):
    def deploy():
        return f"Deploy {app_name}"
    deploy.__name__ = f'deploy_{app_name}'  # Unique endpoint name
    return deploy

for app in ['foo', 'bar', 'baz']:
    app.add_url_rule(
        f'/api/{app}/deploy',
        endpoint=f'deploy_{app}',
        view_func=make_deploy_handler(app)
    )
```

### Route Prefix Organization

Organize related routes using consistent prefixes:

```python
# Application management routes
@app.route('/applications')
def list_apps(): pass

@app.route('/applications/<name>')
def show_app(name): pass

@app.route('/applications/<name>/deploy')
def deploy_app(name): pass

@app.route('/applications/<name>/domains')
def app_domains(name): pass

# API namespace
@app.route('/api/v1/health')
def api_health(): pass
```

## URL Parameter Handling

### Type Converters

Always use converters for typed parameters:

```python
# GOOD - Explicit types
@app.route('/app/<string:name>')
def app_by_name(name): pass

@app.route('/server/<int:id>')
def server_by_id(id): pass  # Automatically validates integer

@app.route('/config/<path:subpath>')
def nested_config(subpath): pass  # Captures slashes
```

### Optional Parameters

```python
@app.route('/logs')
@app.route('/logs/<int:lines>')
def get_logs(lines=100):
    # /logs returns 100 lines, /logs/50 returns 50
    return jsonify({"lines": lines})
```

## HTTP Method Selection

### WARNING: Missing Method Validation

**The Problem:**
```python
# BAD - No method restriction accepts all verbs
@app.route('/api/delete')
def delete_resource():
    # Accepts GET, POST, PUT—dangerous for destructive ops
    pass
```

**The Fix:**
```python
# GOOD - Explicit method whitelist
@app.route('/api/delete', methods=['POST', 'DELETE'])
def delete_resource():
    # Only accepts POST/DELETE
    pass
```

### Method-Based Dispatch

```python
@app.route('/resource/<int:id>', methods=['GET', 'PUT', 'DELETE'])
def resource_handler(id):
    if request.method == 'GET':
        return get_resource(id)
    elif request.method == 'PUT':
        return update_resource(id, request.get_json())
    elif request.method == 'DELETE':
        return delete_resource(id)
```

## Request Data Access

### Query Parameters

```python
@app.route('/search')
def search():
    # Use .get() with defaults for optional params
    query = request.args.get('q', '')
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    if limit > 100:
        return jsonify({"error": "limit exceeds maximum"}), 400
```

### WARNING: Blind JSON Access

**The Problem:**
```python
# BAD - No validation, KeyError on missing fields
@app.route('/hook', methods=['POST'])
def webhook():
    data = request.get_json()
    repo = data['repository']['full_name']  # KeyError if structure wrong
```

**The Fix:**
```python
# GOOD - Defensive access with .get()
@app.route('/hook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True) or {}
    repo = data.get('repository', {}).get('full_name', 'unknown')
    if repo == 'unknown':
        return jsonify({"error": "invalid payload"}), 400
```

## Response Patterns

### JSON API Responses

```python
@app.route('/api/status')
def status():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    })

@app.route('/api/error')
def error():
    return jsonify({"error": "Not found", "code": 404}), 404
```

### Template Rendering

```python
@app.route('/dashboard')
def dashboard():
    return render_template(
        'dashboard.html',
        title="Infrastructure Dashboard",
        servers=get_servers(),
        alerts=get_active_alerts()
    )