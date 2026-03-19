# Package Update Dashboard Design Specification

**Document Version**: 1.0  
**Date**: 2026-03-18  
**Author**: Product Strategy  
**Status**: Ready for Implementation

---

## Executive Summary

This document specifies the design for a package update management feature in the Quantyra infrastructure dashboard. The feature enables infrastructure administrators to view, review, and apply apt package updates across all VPS servers from a single interface.

---

## User Flow

### Overview

```
Dashboard → Servers List → Server Detail → Update Actions
    ↓            ↓              ↓              ↓
  Badge      Update Count   Package List   Confirmation
```

### Flow Description

1. **Dashboard Overview**
   - User sees "Updates Available" card showing total packages needing updates
   - Badge on "Servers" navigation item shows update count
   - Clicking leads to Servers page

2. **Servers List**
   - Enhanced table shows update count per server
   - Security updates highlighted with red badge
   - "Check for Updates" button to refresh package lists
   - "Update All Servers" action for bulk updates
   - Click server name → Server Detail

3. **Server Detail**
   - Full list of upgradable packages
   - Each package shows: name, current version, available version, security flag
   - Individual "Update" button per package
   - "Update All Packages" for server-wide update
   - Warning about services requiring restart

4. **Update Confirmation**
   - Modal confirmation before any update
   - Shows packages to be updated
   - Lists affected services
   - Requires explicit confirmation for bulk operations

---

## UI Mockups

### 1. Enhanced Servers Page

```
┌─────────────────────────────────────────────────────────────────────┐
│ Servers                                    [Check Updates] [Update All] │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Database Servers                                                 │ │
│ ├──────────────┬─────────────────┬───────────────┬────────────────┤ │
│ │ Name         │ Role            │ IP            │ Updates        │ │
│ ├──────────────┼─────────────────┼───────────────┼────────────────┤ │
│ │ re-node-01   │ PostgreSQL+Redis│ 100.126.103.51│ 🔒 3 updates   │ │
│ │              │                 │               │   2 security   │ │
│ ├──────────────┼─────────────────┼───────────────┼────────────────┤ │
│ │ re-node-03   │ PostgreSQL+Redis│ 100.114.117.46│ ✓ Up to date   │ │
│ ├──────────────┼─────────────────┼───────────────┼────────────────┤ │
│ │ re-node-04   │ PostgreSQL      │ 100.115.75.119│ 2 updates      │ │
│ └──────────────┴─────────────────┴───────────────┴────────────────┘ │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ App Servers                                                      │ │
│ ├──────────────┬─────────────────┬───────────────┬────────────────┤ │
│ │ re-db        │ App Server      │ 100.92.26.38  │ 🔒 12 updates  │ │
│ │              │                 │               │   5 security   │ │
│ ├──────────────┼─────────────────┼───────────────┼────────────────┤ │
│ │ re-node-02   │ App Server (ATL)│ 100.89.130.19 │ 1 update       │ │
│ └──────────────┴─────────────────┴───────────────┴────────────────┘ │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Routers (HAProxy + PgBouncer)                                    │ │
│ ├──────────────┬───────────────┬────────────────┬─────────────────┤ │
│ │ router-01    │ 100.102.220.16│ 172.93.54.112  │ ✓ Up to date    │ │
│ ├──────────────┼───────────────┼────────────────┼─────────────────┤ │
│ │ router-02    │ 100.116.175.9 │ 23.29.118.6    │ 3 updates       │ │
│ └──────────────┴───────────────┴────────────────┴─────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 2. Server Detail Page (NEW)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ← Back to Servers                                                    │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ re-node-01                                                       │ │
│ │ PostgreSQL + Redis │ 100.126.103.51 │ Uptime: 45 days           │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Available Updates (3 packages, 2 security)       [Update All]   │ │
│ ├──────────────┬──────────────┬──────────────┬─────────┬──────────┤ │
│ │ Package      │ Current      │ Available    │ Security│ Action   │ │
│ ├──────────────┼──────────────┼──────────────┼─────────┼──────────┤ │
│ │ openssl      │ 3.0.11-1     │ 3.0.13-1     │ 🔒 Yes  │ [Update] │ │
│ ├──────────────┼──────────────┼──────────────┼─────────┼──────────┤ │
│ │ libssl3      │ 3.0.11-1     │ 3.0.13-1     │ 🔒 Yes  │ [Update] │ │
│ ├──────────────┼──────────────┼──────────────┼─────────┼──────────┤ │
│ │ nginx        │ 1.24.0-1     │ 1.25.3-1     │ No      │ [Update] │ │
│ └──────────────┴──────────────┴──────────────┴─────────┴──────────┘ │
│                                                                      │
│ ⚠️ Services requiring restart after update:                         │
│    • nginx (if nginx package updated)                               │
│    • postgresql (if openssl/libssl3 updated - affects TLS)          │
│    • redis-server (if openssl/libssl3 updated - affects TLS)        │
│                                                                      │
│ Last checked: 2026-03-18 14:32 UTC  [Refresh]                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 3. Update Confirmation Modal

```
┌─────────────────────────────────────────────────────────────────────┐
│ Confirm Package Update                                        [X]   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ You are about to update 3 packages on re-node-01:                   │
│                                                                      │
│   • openssl (3.0.11-1 → 3.0.13-1) [Security]                        │
│   • libssl3 (3.0.11-1 → 3.0.13-1) [Security]                        │
│   • nginx (1.24.0-1 → 1.25.3-1)                                     │
│                                                                      │
│ ⚠️ The following services will require restart:                     │
│    nginx, postgresql, redis-server                                  │
│                                                                      │
│ [Cancel]                                              [Confirm Update] │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Backend Implementation

### New Functions for app.py

```python
# ============================================================================
# Package Update Functions
# ============================================================================

def get_server_updates(server_ip, force_refresh=False):
    """
    Check for available package updates on a server.
    
    Args:
        server_ip: Server IP address
        force_refresh: If True, run apt-get update first
    
    Returns:
        {
            "success": bool,
            "packages": [
                {
                    "name": str,
                    "current_version": str,
                    "available_version": str,
                    "security": bool,
                    "priority": str  # "critical", "high", "normal"
                }
            ],
            "security_count": int,
            "total_count": int,
            "services_to_restart": [str],
            "last_checked": str (ISO timestamp)
        }
    """
    # Check Redis cache first
    cache_key = f"server_updates:{server_ip}"
    if not force_refresh:
        cached = redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    
    # Run apt-get update if forced refresh
    if force_refresh:
        ssh_command(server_ip, "apt-get update -qq", timeout=60)
    
    # Get list of upgradable packages
    result = ssh_command(
        server_ip,
        "apt list --upgradable 2>/dev/null | tail -n +2",
        timeout=30
    )
    
    if not result["success"]:
        return {"success": False, "error": result["stderr"], "packages": []}
    
    packages = []
    security_count = 0
    
    for line in result["stdout"].strip().split("\n"):
        if not line:
            continue
        
        # Parse: package/source version arch [upgradable from: old_version]
        parts = line.split()
        if len(parts) < 3:
            continue
        
        name = parts[0].split("/")[0]
        available_version = parts[1]
        
        # Extract current version
        current_version = ""
        for part in parts:
            if part.startswith("[upgradable from:"):
                current_version = part.replace("[upgradable from:", "").rstrip("]")
        
        # Check if security update
        # Security packages typically come from security repository
        security_check = ssh_command(
            server_ip,
            f"apt-cache policy {name} 2>/dev/null | grep -A1 '***' | head -1",
            timeout=10
        )
        is_security = "security" in security_check.get("stdout", "").lower()
        
        if is_security:
            security_count += 1
        
        packages.append({
            "name": name,
            "current_version": current_version,
            "available_version": available_version,
            "security": is_security,
            "priority": "critical" if is_security else "normal"
        })
    
    # Get services needing restart
    services = get_services_needing_restart(server_ip)
    
    response = {
        "success": True,
        "packages": packages,
        "security_count": security_count,
        "total_count": len(packages),
        "services_to_restart": services,
        "last_checked": datetime.utcnow().isoformat() + "Z"
    }
    
    # Cache for 1 hour
    redis_client.setex(cache_key, 3600, json.dumps(response))
    
    return response


def get_services_needing_restart(server_ip):
    """
    Detect services that need restart after package updates.
    
    Uses checkrestart (from debian-goodies) or needs-restarting.
    
    Returns:
        List of service names that need restart
    """
    # Try checkrestart first (Debian)
    result = ssh_command(
        server_ip,
        "command -v checkrestart >/dev/null 2>&1 && checkrestart 2>/dev/null | grep -oP 'service \\K\\S+' || echo ''",
        timeout=30
    )
    
    services = []
    if result["success"] and result["stdout"].strip():
        services = result["stdout"].strip().split("\n")
        services = [s for s in services if s]
    
    # If checkrestart not available, check for deleted libraries
    if not services:
        result = ssh_command(
            server_ip,
            "lsof 2>/dev/null | grep 'DEL.*\\.so' | awk '{print $1}' | sort -u",
            timeout=30
        )
        if result["success"]:
            # Map process names to service names
            process_to_service = {
                "nginx": "nginx",
                "postgres": "postgresql",
                "redis-server": "redis-server",
                "node": "node",
                "php-fpm": "php8.5-fpm",
                "haproxy": "haproxy"
            }
            for proc in result["stdout"].strip().split("\n"):
                if proc in process_to_service:
                    services.append(process_to_service[proc])
            services = list(set(services))
    
    return services


def update_packages(server_ip, packages=None):
    """
    Update packages on a server.
    
    Args:
        server_ip: Server IP address
        packages: List of specific packages to update, or None for all
    
    Returns:
        {
            "success": bool,
            "updated": [str],  # List of updated packages
            "errors": [str],
            "output": str
        }
    """
    if packages:
        # Update specific packages
        pkg_list = " ".join(packages)
        cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list} 2>&1"
    else:
        # Update all packages
        cmd = "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1"
    
    result = ssh_command(server_ip, cmd, timeout=300)
    
    updated = []
    errors = []
    
    if result["success"]:
        # Parse output for updated packages
        for line in result["stdout"].split("\n"):
            if "Unpacking" in line or "Setting up" in line:
                # Extract package name
                parts = line.split()
                if len(parts) >= 2:
                    pkg = parts[1].split(":")[0]  # Remove architecture
                    if pkg not in updated:
                        updated.append(pkg)
        
        # Clear cache after successful update
        redis_client.delete(f"server_updates:{server_ip}")
    else:
        errors.append(result["stderr"] or result["stdout"])
    
    return {
        "success": result["success"],
        "updated": updated,
        "errors": errors,
        "output": result["stdout"][-2000:] if len(result["stdout"]) > 2000 else result["stdout"]
    }


def restart_services(server_ip, services):
    """
    Restart specified services on a server.
    
    Args:
        server_ip: Server IP address
        services: List of service names to restart
    
    Returns:
        {
            "success": bool,
            "restarted": [str],
            "failed": [str]
        }
    """
    restarted = []
    failed = []
    
    for service in services:
        result = ssh_command(
            server_ip,
            f"systemctl restart {service} && systemctl is-active {service}",
            timeout=30
        )
        if result["success"] and "active" in result["stdout"]:
            restarted.append(service)
        else:
            failed.append(service)
    
    return {
        "success": len(failed) == 0,
        "restarted": restarted,
        "failed": failed
    }


def get_all_servers_updates(force_refresh=False):
    """
    Get update status for all servers.
    
    Returns:
        {
            "total_updates": int,
            "security_updates": int,
            "servers": {
                "server_name": {
                    "total": int,
                    "security": int,
                    "last_checked": str
                }
            }
        }
    """
    all_servers = DB_SERVERS + APP_SERVERS + ROUTERS
    results = {
        "total_updates": 0,
        "security_updates": 0,
        "servers": {}
    }
    
    for server in all_servers:
        updates = get_server_updates(server["ip"], force_refresh=force_refresh)
        if updates.get("success"):
            results["servers"][server["name"]] = {
                "total": updates["total_count"],
                "security": updates["security_count"],
                "last_checked": updates["last_checked"]
            }
            results["total_updates"] += updates["total_count"]
            results["security_updates"] += updates["security_count"]
    
    return results
```

### New API Routes

```python
# ============================================================================
# Package Update API Routes
# ============================================================================

@app.route("/api/updates/status")
@requires_auth
def api_updates_status():
    """
    Get aggregated update status for all servers.
    Used for navigation badge and dashboard widget.
    """
    status = get_all_servers_updates()
    return jsonify(status)


@app.route("/api/servers/<server_name>/updates")
@requires_auth
def api_server_updates(server_name):
    """
    Get detailed update information for a specific server.
    """
    # Find server by name
    server = None
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        if s["name"] == server_name:
            server = s
            break
    
    if not server:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    updates = get_server_updates(server["ip"], force_refresh=force_refresh)
    
    return jsonify({
        "server": server_name,
        "ip": server["ip"],
        "success": updates.get("success", False),
        "packages": updates.get("packages", []),
        "security_count": updates.get("security_count", 0),
        "total_count": updates.get("total_count", 0),
        "services_to_restart": updates.get("services_to_restart", []),
        "last_checked": updates.get("last_checked"),
        "error": updates.get("error")
    })


@app.route("/api/updates/check", methods=["POST"])
@requires_auth
def api_check_updates():
    """
    Trigger update check on all servers.
    Returns task ID for status polling.
    """
    task_id = f"update_check_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Store initial task status
    redis_client.setex(f"task:{task_id}", 3600, json.dumps({
        "status": "running",
        "progress": 0,
        "total": len(DB_SERVERS + APP_SERVERS + ROUTERS),
        "servers_completed": [],
        "started_at": datetime.utcnow().isoformat()
    }))
    
    @run_in_thread
    def run_check():
        all_servers = DB_SERVERS + APP_SERVERS + ROUTERS
        completed = []
        
        for i, server in enumerate(all_servers):
            get_server_updates(server["ip"], force_refresh=True)
            completed.append(server["name"])
            
            # Update task progress
            redis_client.setex(f"task:{task_id}", 3600, json.dumps({
                "status": "running",
                "progress": i + 1,
                "total": len(all_servers),
                "servers_completed": completed,
                "started_at": datetime.utcnow().isoformat()
            }))
        
        # Mark complete
        redis_client.setex(f"task:{task_id}", 3600, json.dumps({
            "status": "complete",
            "progress": len(all_servers),
            "total": len(all_servers),
            "servers_completed": completed,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat()
        }))
    
    run_check()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "Update check started"
    }), 202


@app.route("/api/tasks/<task_id>")
@requires_auth
def api_task_status(task_id):
    """
    Get status of a background task.
    """
    task_data = redis_client.get(f"task:{task_id}")
    if not task_data:
        return jsonify({"success": False, "error": "Task not found"}), 404
    
    return jsonify(json.loads(task_data))


@app.route("/api/servers/<server_name>/updates", methods=["POST"])
@requires_auth
def api_update_server(server_name):
    """
    Update packages on a specific server.
    """
    # Find server
    server = None
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        if s["name"] == server_name:
            server = s
            break
    
    if not server:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    data = request.json or {}
    packages = data.get("packages")
    confirm = data.get("confirm", False)
    
    if not confirm:
        return jsonify({
            "success": False,
            "error": "Confirmation required. Set confirm: true in request body."
        }), 400
    
    # Run update
    result = update_packages(server["ip"], packages=packages)
    
    return jsonify(result)


@app.route("/api/updates/all", methods=["POST"])
@requires_auth
def api_update_all_servers():
    """
    Update packages on all servers.
    Requires explicit confirmation.
    """
    data = request.json or {}
    confirm = data.get("confirm", False)
    confirmation_text = data.get("confirmation_text", "")
    
    if not confirm or confirmation_text != "UPDATE ALL":
        return jsonify({
            "success": False,
            "error": "Type 'UPDATE ALL' in confirmation_text to proceed."
        }), 400
    
    task_id = f"update_all_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    all_servers = DB_SERVERS + APP_SERVERS + ROUTERS
    
    # Store initial task status
    redis_client.setex(f"task:{task_id}", 7200, json.dumps({
        "status": "running",
        "progress": 0,
        "total": len(all_servers),
        "servers_completed": [],
        "servers_failed": [],
        "started_at": datetime.utcnow().isoformat()
    }))
    
    @run_in_thread
    def run_updates():
        completed = []
        failed = []
        
        for i, server in enumerate(all_servers):
            result = update_packages(server["ip"])
            
            if result["success"]:
                completed.append({"name": server["name"], "updated": result["updated"]})
            else:
                failed.append({"name": server["name"], "error": result["errors"]})
            
            # Update task progress
            redis_client.setex(f"task:{task_id}", 7200, json.dumps({
                "status": "running",
                "progress": i + 1,
                "total": len(all_servers),
                "servers_completed": completed,
                "servers_failed": failed,
                "started_at": datetime.utcnow().isoformat()
            }))
        
        # Mark complete
        redis_client.setex(f"task:{task_id}", 7200, json.dumps({
            "status": "complete",
            "progress": len(all_servers),
            "total": len(all_servers),
            "servers_completed": completed,
            "servers_failed": failed,
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": datetime.utcnow().isoformat()
        }))
    
    run_updates()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "Update started on all servers"
    }), 202


@app.route("/api/servers/<server_name>/restart-services", methods=["POST"])
@requires_auth
def api_restart_services(server_name):
    """
    Restart services on a server after updates.
    """
    server = None
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        if s["name"] == server_name:
            server = s
            break
    
    if not server:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    data = request.json or {}
    services = data.get("services", [])
    
    if not services:
        return jsonify({"success": False, "error": "No services specified"}), 400
    
    result = restart_services(server["ip"], services)
    return jsonify(result)
```

### New Page Routes

```python
@app.route("/servers/<server_name>")
@requires_auth
def server_detail(server_name):
    """
    Server detail page with package updates.
    """
    server = None
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        if s["name"] == server_name:
            server = s
            break
    
    if not server:
        flash("Server not found", "error")
        return redirect(url_for("servers"))
    
    # Get server status
    server_status = check_servers_async([server])
    
    # Get updates
    updates = get_server_updates(server["ip"])
    
    return render_template(
        "server_detail.html",
        server=server,
        server_status=server_status.get(server_name, {}),
        updates=updates
    )
```

---

## Template Changes

### 1. Update base.html (Nav Badge)

```html
<!-- In nav-links section, update Servers link -->
<a href="/servers" class="{% if request.path == '/servers' %}active{% endif %}">
    Servers
    {% if updates_total and updates_total > 0 %}
    <span class="nav-badge">{{ updates_total }}</span>
    {% endif %}
</a>
```

### 2. Update servers.html (Add Updates Column)

See the UI mockup section above. Key changes:
- Add "Updates" column to each table
- Show badge with count and security indicator
- Make server name clickable (links to detail page)
- Add "Check Updates" and "Update All" buttons

### 3. Create server_detail.html (New Template)

```html
{% extends "base.html" %}
{% block title %}{{ server.name }} - Server Details{% endblock %}

{% block content %}
<div class="page-header">
    <h1>{{ server.name }}</h1>
    <a href="/servers" class="btn btn-secondary">← Back to Servers</a>
</div>

<div class="status-row">
    <div class="status-item">
        <span class="status-label">Role:</span>
        <span>{{ server.role or 'N/A' }}</span>
    </div>
    <div class="status-item">
        <span class="status-label">Tailscale IP:</span>
        <code>{{ server.ip }}</code>
    </div>
    <div class="status-item">
        <span class="status-label">Public IP:</span>
        <code>{{ server.public_ip }}</code>
    </div>
    <div class="status-item">
        <span class="status-label">Status:</span>
        {% if server_status.uptime != 'unreachable' %}
        <span class="status-badge status-healthy">● Online</span>
        {% else %}
        <span class="status-badge status-error">● Offline</span>
        {% endif %}
    </div>
</div>

<div class="card">
    <div class="page-header">
        <h2>Package Updates</h2>
        <div>
            <button onclick="refreshUpdates()" class="btn btn-secondary btn-sm">Refresh</button>
            {% if updates.packages and updates.packages|length > 0 %}
            <button onclick="updateAllPackages()" class="btn btn-sm">Update All ({{ updates.packages|length }})</button>
            {% endif %}
        </div>
    </div>
    
    {% if updates.success %}
        {% if updates.packages and updates.packages|length > 0 %}
        <div class="table-container">
            <table class="server-table">
                <thead>
                    <tr>
                        <th>Package</th>
                        <th>Current Version</th>
                        <th>Available Version</th>
                        <th>Security</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pkg in updates.packages %}
                    <tr data-package="{{ pkg.name }}">
                        <td><strong>{{ pkg.name }}</strong></td>
                        <td><code>{{ pkg.current_version }}</code></td>
                        <td><code>{{ pkg.available_version }}</code></td>
                        <td>
                            {% if pkg.security %}
                            <span class="status-badge status-error">🔒 Security</span>
                            {% else %}
                            <span class="status-badge" style="background: rgba(0,212,255,0.2); color: #00d4ff;">Normal</span>
                            {% endif %}
                        </td>
                        <td>
                            <button onclick="updatePackage('{{ pkg.name }}')" class="btn btn-sm">Update</button>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        {% if updates.services_to_restart and updates.services_to_restart|length > 0 %}
        <div class="alert alert-warning" style="margin-top: 1rem;">
            <strong>⚠️ Services requiring restart after update:</strong>
            <ul>
                {% for service in updates.services_to_restart %}
                <li>{{ service }}</li>
                {% endfor %}
            </ul>
        </div>
        {% endif %}
        
        {% else %}
        <div class="empty-state">
            <p>✓ All packages are up to date</p>
        </div>
        {% endif %}
        
        <p style="margin-top: 1rem; color: #8899a6; font-size: 0.875rem;">
            Last checked: {{ updates.last_checked or 'Never' }}
        </p>
        
    {% else %}
    <div class="alert alert-error">
        Failed to fetch updates: {{ updates.error or 'Unknown error' }}
    </div>
    {% endif %}
</div>

<!-- Update Confirmation Modal -->
<div id="updateModal" class="modal" style="display: none;">
    <div class="modal-content">
        <h3>Confirm Package Update</h3>
        <p id="modalMessage"></p>
        <div id="modalPackageList"></div>
        <div id="modalServiceWarning"></div>
        <div class="modal-actions">
            <button onclick="closeModal()" class="btn btn-secondary">Cancel</button>
            <button onclick="confirmUpdate()" class="btn">Confirm Update</button>
        </div>
    </div>
</div>

<script>
let pendingPackages = null;

function refreshUpdates() {
    window.location.href = '/servers/{{ server.name }}?refresh=true';
}

function updatePackage(packageName) {
    pendingPackages = [packageName];
    showModal(`Update package "${packageName}"?`, [packageName]);
}

function updateAllPackages() {
    const packages = [{% for pkg in updates.packages %}'{{ pkg.name }}'{% if not loop.last %}, {% endif %}{% endfor %}];
    pendingPackages = packages;
    showModal('Update all packages on {{ server.name }}?', packages);
}

function showModal(message, packages) {
    document.getElementById('modalMessage').textContent = message;
    
    let listHtml = '<ul>';
    packages.forEach(pkg => {
        listHtml += `<li>${pkg}</li>`;
    });
    listHtml += '</ul>';
    document.getElementById('modalPackageList').innerHTML = listHtml;
    
    {% if updates.services_to_restart and updates.services_to_restart|length > 0 %}
    document.getElementById('modalServiceWarning').innerHTML = `
        <div class="alert alert-warning" style="margin-top: 1rem;">
            <strong>⚠️ Services will need restart:</strong>
            {{ updates.services_to_restart|join(', ') }}
        </div>
    `;
    {% endif %}
    
    document.getElementById('updateModal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('updateModal').style.display = 'none';
    pendingPackages = null;
}

function confirmUpdate() {
    if (!pendingPackages) return;
    
    fetch('/api/servers/{{ server.name }}/updates', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            packages: pendingPackages.length === {{ updates.packages|length }} ? null : pendingPackages,
            confirm: true
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            alert('Update completed successfully! Updated: ' + data.updated.join(', '));
            window.location.reload();
        } else {
            alert('Update failed: ' + (data.error || data.errors?.join(', ')));
        }
        closeModal();
    })
    .catch(err => {
        alert('Error: ' + err);
        closeModal();
    });
}
</script>

<style>
.modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0,0,0,0.8);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal-content {
    background: #16213e;
    padding: 2rem;
    border-radius: 12px;
    max-width: 500px;
    width: 90%;
    border: 1px solid #2a3a5e;
}

.modal-actions {
    margin-top: 1.5rem;
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
}

.nav-badge {
    background: #e74c3c;
    color: white;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    margin-left: 0.25rem;
}
</style>
{% endblock %}
```

---

## CSS Additions

Add to `style.css`:

```css
/* Update badges */
.update-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.75rem;
    border-radius: 6px;
    font-size: 0.8rem;
    font-weight: 500;
}

.update-badge.security {
    background: rgba(231, 76, 60, 0.2);
    color: #e74c3c;
    border: 1px solid rgba(231, 76, 60, 0.3);
}

.update-badge.normal {
    background: rgba(243, 156, 18, 0.2);
    color: #f39c12;
    border: 1px solid rgba(243, 156, 18, 0.3);
}

.update-badge.uptodate {
    background: rgba(39, 174, 96, 0.2);
    color: #27ae60;
}

/* Nav badge for updates */
.nav-badge {
    background: #e74c3c;
    color: white;
    padding: 0.125rem 0.5rem;
    border-radius: 9999px;
    font-size: 0.7rem;
    margin-left: 0.25rem;
    vertical-align: middle;
}

/* Modal styles */
.modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.8);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.modal.active {
    display: flex;
}

.modal-content {
    background: #16213e;
    padding: 2rem;
    border-radius: 12px;
    max-width: 500px;
    width: 90%;
    border: 1px solid #2a3a5e;
}

.modal-content h3 {
    margin-top: 0;
    margin-bottom: 1rem;
}

.modal-actions {
    margin-top: 1.5rem;
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
}

/* Clickable server rows */
.server-table tbody tr:hover {
    background: rgba(0, 212, 255, 0.05);
    cursor: pointer;
}

.server-table td a {
    color: inherit;
    text-decoration: none;
}

/* Progress indicator */
.progress-bar {
    height: 4px;
    background: #2a3a5e;
    border-radius: 2px;
    overflow: hidden;
}

.progress-bar .fill {
    height: 100%;
    background: #00d4ff;
    transition: width 0.3s ease;
}
```

---

## Implementation Phases

### Phase 1: Foundation (Est. 4-6 hours)
- [ ] Add `get_server_updates()` function
- [ ] Add `update_packages()` function
- [ ] Add `get_services_needing_restart()` function
- [ ] Add Redis caching for update data
- [ ] Add `/api/updates/status` endpoint

### Phase 2: Server List Enhancement (Est. 2-3 hours)
- [ ] Modify `servers.html` to add Updates column
- [ ] Update `/servers` route to include update counts
- [ ] Add nav badge with total update count
- [ ] Add "Check for Updates" button

### Phase 3: Server Detail Page (Est. 3-4 hours)
- [ ] Create `server_detail.html` template
- [ ] Add `/servers/<server_name>` route
- [ ] Add `/api/servers/<server_name>/updates` endpoint

### Phase 4: Update Actions (Est. 4-5 hours)
- [ ] Add POST endpoints for updates
- [ ] Implement confirmation modals
- [ ] Add task status polling
- [ ] Add progress indicators

### Phase 5: Polish & Safety (Est. 2-3 hours)
- [ ] Add service restart flow
- [ ] Add update logging
- [ ] Handle edge cases and errors
- [ ] Test on staging servers

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Update breaks service | Medium | High | Show services needing restart; require explicit restart confirmation |
| apt update hangs | Low | Medium | Add timeout to SSH commands; cache results |
| Security update missed | Low | High | Highlight security updates prominently; periodic auto-check |
| Cache shows stale data | Medium | Low | Allow manual refresh; clear cache after update |
| Update fails on one server | Medium | Medium | Stop bulk update on failure; log errors; show which servers succeeded |

---

## Questions Answered

### 1. Should updates require confirmation or run automatically?
**Answer**: Updates require explicit confirmation. This is infrastructure; accidental updates could cause downtime.

### 2. How to handle updates that require service restarts?
**Answer**: 
- Detect services needing restart using `checkrestart` or `lsof`
- Show warning before update
- Prompt for restart after update completes
- Allow deferring restart with clear warning

### 3. Should there be a "staging" approach?
**Answer**: Not applicable in the traditional sense. These are infrastructure servers. However:
- Bulk updates process servers sequentially
- If one fails, remaining servers are not updated
- User can manually update one server first, verify, then proceed

### 4. How to show update progress/results?
**Answer**:
- Use async task pattern with task ID
- Poll `/api/tasks/<task_id>` for status
- Show progress bar: "Updating server 3/7..."
- Display final results: success/failure per server

### 5. Should we schedule automatic update checks?
**Answer**: Yes, via:
- Background task running every 6 hours
- Updates cached in Redis
- Nav badge always reflects current status
- User can trigger manual check anytime

---

## Appendix: Server Inventory

| Server | Tailscale IP | Role | Considerations |
|--------|--------------|------|----------------|
| re-node-01 | 100.126.103.51 | PostgreSQL + Redis Master | Primary Redis; update with caution |
| re-node-03 | 100.114.117.46 | PostgreSQL + Redis Replica | Patroni member |
| re-node-04 | 100.115.75.119 | PostgreSQL + etcd | etcd quorum member |
| re-db | 100.92.26.38 | App Server | nginx + PHP-FPM |
| re-node-02 | 100.89.130.19 | App Server (ATL) | nginx + PHP-FPM |
| router-01 | 100.102.220.16 | HAProxy + Monitoring | Dashboard host; HAProxy primary |
| router-02 | 100.116.175.9 | HAProxy (Secondary) | HAProxy backup |

---

*Document prepared for backend-engineer implementation.*