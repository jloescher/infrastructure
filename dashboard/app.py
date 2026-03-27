from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
import yaml
import os
import subprocess
import time
import psycopg2
import redis
import requests
from functools import wraps
import secrets
import markdown
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import re
import json
import hmac
import hashlib
import shlex

try:
    from nacl import encoding, public
    PYNACL_AVAILABLE = True
except ImportError:
    PYNACL_AVAILABLE = False

try:
    import database as paas_db
    from gist_sync import GistSyncService, get_sync_service
    PAAS_DB_AVAILABLE = True
    paas_db.init_database()
except ImportError:
    PAAS_DB_AVAILABLE = False

try:
    from websocket import init_socketio, emit_progress, socketio
    from tasks.deploy import deploy_application_task
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    socketio = None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

if WEBSOCKET_AVAILABLE and socketio:
    init_socketio(app)

AUTH_USER = os.environ.get("DASHBOARD_USER", "admin")
AUTH_PASS = os.environ.get("DASHBOARD_PASS", "DbAdmin2026!")

ENV_FILE = "/opt/dashboard/config/.env"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

CLOUDFLARE_API_TOKEN = ""
CLOUDFLARE_ZONE_ID = ""
CLOUDFLARE_ZONE_NAME = ""
PUBLIC_BASE_URL = ""
WEBHOOK_PUBLIC_HOST = "hooks.quantyralabs.cc"

if os.path.exists(ENV_FILE):
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1]
            elif line.startswith("CLOUDFLARE_API_TOKEN="):
                CLOUDFLARE_API_TOKEN = line.split("=", 1)[1]
            elif line.startswith("CLOUDFLARE_ZONE_ID="):
                CLOUDFLARE_ZONE_ID = line.split("=", 1)[1]
            elif line.startswith("CLOUDFLARE_ZONE_NAME="):
                CLOUDFLARE_ZONE_NAME = line.split("=", 1)[1]
            elif line.startswith("PUBLIC_BASE_URL="):
                PUBLIC_BASE_URL = line.split("=", 1)[1].strip()
            elif line.startswith("WEBHOOK_PUBLIC_HOST="):
                WEBHOOK_PUBLIC_HOST = line.split("=", 1)[1].strip()

BASE_DIR = "/opt/dashboard"
DB_CONFIG_PATH = os.path.join(BASE_DIR, "config", "databases.yml")
APPS_CONFIG_PATH = os.path.join(BASE_DIR, "config", "applications.yml")
DOCS_PATH = os.path.join(BASE_DIR, "docs")

PG_HOST = os.environ.get("PG_HOST", "100.102.220.16")
PG_PORT = int(os.environ.get("PG_PORT", 5000))
PG_USER = os.environ.get("PG_USER", "patroni_superuser")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "2e7vBpaaVK4vTJzrKebC")

REDIS_HOST = os.environ.get("REDIS_HOST", "100.126.103.51")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk")

# Redis client for caching (package updates, task status, etc.)
redis_client = redis.Redis(
    host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
    decode_responses=True, socket_connect_timeout=5
)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://100.102.220.16:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://100.102.220.16:3000")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip()
WEBHOOK_PUBLIC_HOST = os.environ.get("WEBHOOK_PUBLIC_HOST", WEBHOOK_PUBLIC_HOST).strip() or "hooks.quantyralabs.cc"
APP_RUNTIME_USER = "webapps"

ROUTERS = [
    {"name": "router-01", "ip": "100.102.220.16", "public_ip": "172.93.54.112"},
    {"name": "router-02", "ip": "100.116.175.9", "public_ip": "23.29.118.6"}
]

APP_SERVERS = [
    {"name": "re-db", "ip": "100.92.26.38", "public_ip": "208.87.128.115", "role": "App Server"},
    {"name": "re-node-02", "ip": "100.89.130.19", "public_ip": "23.227.173.245", "role": "App Server (ATL)"}
]

APP_PORT_RANGE = {"production": {"start": 8100, "end": 8199}, "staging": {"start": 9200, "end": 9299}}
allocated_ports = {}

def get_next_redis_db():
    """
    Get the next available Redis DB number.
    DB 0 is reserved for system/monitoring.
    Apps start from DB 1.
    """
    applications = load_applications()
    used_dbs = set()
    
    for app_name, app in applications.items():
        if app.get("redis_enabled") and app.get("redis_db") is not None:
            used_dbs.add(app["redis_db"])
    
    # Start from DB 1 (DB 0 is reserved for system)
    next_db = 1
    while next_db in used_dbs:
        next_db += 1
    
    return next_db


def get_next_port(app_name):
    applications = load_applications()
    used_ports = set()
    for app_data in applications.values():
        if app_data.get("port"):
            used_ports.add(app_data["port"])
    
    for port in range(APP_PORT_RANGE["production"]["start"], APP_PORT_RANGE["production"]["end"]):
        if port not in used_ports:
            return port
    return APP_PORT_RANGE["production"]["start"]

def get_staging_port(production_port):
    return production_port + 1100


def configure_laravel_nginx(app_name, server_ip, port):
    nginx_config = f"""server {{
    listen {port};
    server_name _;
    root /opt/apps/{app_name}/public;
    index index.php;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        fastcgi_pass unix:/run/php/php8.5-fpm-{app_name}.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
    }}

    location ~ /\\.(?!well-known).* {{
        deny all;
    }}
}}
"""
    
    config_path = f"/etc/nginx/sites-available/{app_name}"
    enabled_path = f"/etc/nginx/sites-enabled/{app_name}"
    
    escaped_config = nginx_config.replace("'", "'\"'\"'")
    result = ssh_command(server_ip, f"echo '{escaped_config}' > {config_path} && ln -sf {config_path} {enabled_path} && nginx -t && systemctl reload nginx")
    return result


def configure_php_fpm_pool(app_name, server_ip, is_staging=False):
    max_children = 40 if is_staging else 80
    start_servers = 4 if is_staging else 8
    min_spare = 2 if is_staging else 4
    max_spare = 8 if is_staging else 16
    max_requests = 500 if is_staging else 1000
    
    pool_config = f"""[{app_name}]
user = www-data
group = www-data
listen = /run/php/php8.5-fpm-{app_name}.sock
listen.owner = www-data
listen.group = www-data
pm = dynamic
pm.max_children = {max_children}
pm.start_servers = {start_servers}
pm.min_spare_servers = {min_spare}
pm.max_spare_servers = {max_spare}
pm.process_idle_timeout = 10s
pm.max_requests = {max_requests}
request_slowlog_timeout = 5s
slowlog = /var/log/php8.5-fpm/{app_name}-slow.log
php_admin_value[disable_functions] = exec,passthru,shell_exec,system
php_admin_flag[log_errors] = on
php_admin_value[error_log] = /var/log/php8.5-fpm/{app_name}-error.log
"""
    
    pool_path = f"/etc/php/8.5/fpm/pool.d/{app_name}.conf"
    
    escaped_config = pool_config.replace("'", "'\"'\"'")
    result = ssh_command(server_ip, f"echo '{escaped_config}' > {pool_path} && systemctl restart php8.5-fpm")
    return result


def setup_laravel_app(app_name, server_ip, port):
    results = []
    
    fpm_result = configure_php_fpm_pool(app_name, server_ip)
    if not fpm_result["success"]:
        return {"success": False, "error": f"PHP-FPM pool failed: {fpm_result.get('stderr', 'Unknown error')}"}
    
    nginx_result = configure_laravel_nginx(app_name, server_ip, port)
    if not nginx_result["success"]:
        return {"success": False, "error": f"nginx config failed: {nginx_result.get('stderr', 'Unknown error')}"}
    
    return {"success": True, "port": port}


def remove_laravel_app(app_name, server_ip, port):
    ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}.conf && systemctl restart php8.5-fpm")
    ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name} /etc/nginx/sites-available/{app_name} && systemctl reload nginx")
    return {"success": True}

DB_SERVERS = [
    {"name": "re-node-01", "ip": "100.126.103.51", "public_ip": "104.225.216.26", "role": "PostgreSQL + Redis"},
    {"name": "re-node-03", "ip": "100.114.117.46", "public_ip": "172.93.54.145", "role": "PostgreSQL + Redis"},
    {"name": "re-node-04", "ip": "100.115.75.119", "public_ip": "172.93.54.122", "role": "PostgreSQL"}
]


def grant_schema_permissions(db_name, db_user, db_admin):
    """Grant schema-level permissions and set up default privileges for both admin and app users.
    
    This ensures that:
    1. Both users have full access to the public schema
    2. Future tables created by EITHER user will have proper permissions
    3. All existing tables and sequences are accessible
    """
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=db_name
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        # Grant schema access to both users
        cur.execute("GRANT ALL ON SCHEMA public TO {};".format(db_user))
        cur.execute("GRANT ALL ON SCHEMA public TO {};".format(db_admin))
        
        # Set default privileges for tables created by ADMIN user
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT ALL ON TABLES TO {};".format(db_admin, db_user))
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT ALL ON SEQUENCES TO {};".format(db_admin, db_user))
        
        # Set default privileges for tables created by APP user (migrations run as app user)
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT ALL ON TABLES TO {};".format(db_user, db_user))
        cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public GRANT ALL ON SEQUENCES TO {};".format(db_user, db_user))
        
        # Grant access to all existing tables and sequences
        cur.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {};".format(db_user))
        cur.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {};".format(db_user))
        cur.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {};".format(db_admin))
        cur.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {};".format(db_admin))
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Warning: Failed to grant schema permissions for {db_name}: {e}")
        return False


def regrant_app_db_permissions(app_name, environment="production"):
    """Re-grant permissions on all tables for an app's database user.
    
    This should be called after migrations run to ensure the app user has
    access to any newly created tables. Called automatically during deployment
    for Laravel apps via run_pull_deploy().
    
    Args:
        app_name: The application name
        environment: "production" or "staging"
    
    Returns:
        dict with "success" bool and optional "message" or "error"
    """
    applications = load_applications()
    if app_name not in applications:
        return {"success": False, "error": "App not found"}
    
    app = applications[app_name]
    
    db_name = app.get("database")
    db_user = app.get("db_user")
    
    if environment == "staging":
        db_name = app.get("staging_database")
        db_user = app.get("staging_db_user")
    
    if not db_name or not db_user:
        return {"success": False, "error": "Database not configured for this app"}
    
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database=db_name
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {};".format(db_user))
        cur.execute("GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {};".format(db_user))
        
        cur.close()
        conn.close()
        print(f"Re-granted permissions on {db_name} to {db_user}")
        return {"success": True, "message": f"Granted permissions on all tables in {db_name} to {db_user}"}
    except Exception as e:
        print(f"Error re-granting permissions for {app_name}: {e}")
        return {"success": False, "error": str(e)}


def check_auth(username, password):
    return username == AUTH_USER and password == AUTH_PASS


def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return "Access denied", 401, {"WWW-Authenticate": 'Basic realm="Dashboard"'}
        return f(*args, **kwargs)
    return decorated


def load_databases():
    if PAAS_DB_AVAILABLE:
        try:
            with paas_db.get_db() as conn:
                rows = conn.execute('SELECT * FROM databases ORDER BY name').fetchall()
                databases = {}
                for row in rows:
                    db = dict(row)
                    databases[db['name']] = {
                        'name': db['name'],
                        'description': db.get('description', ''),
                        'owner': db.get('owner', 'app_admin'),
                        'environment': db.get('environment', 'shared'),
                        'app_name': db.get('app_id'),
                        'pool_size': db.get('pool_size', 20)
                    }
                return databases
        except Exception:
            pass
    
    if os.path.exists(DB_CONFIG_PATH):
        with open(DB_CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f)
            return data.get("databases", {}) if data else {}
    return {}


def save_databases(databases):
    if PAAS_DB_AVAILABLE:
        try:
            with paas_db.get_db() as conn:
                for name, db in databases.items():
                    conn.execute('''
                        INSERT OR REPLACE INTO databases (id, name, description, owner, environment, pool_size)
                        VALUES ((SELECT id FROM databases WHERE name = ?), ?, ?, ?, ?, ?)
                    ''', (name, name, db.get('description', ''), db.get('owner', 'app_admin'), 
                          db.get('environment', 'shared'), db.get('pool_size', 20)))
                conn.commit()
            return
        except Exception:
            pass
    
    os.makedirs(os.path.dirname(DB_CONFIG_PATH), exist_ok=True)
    data = {"databases": databases}
    with open(DB_CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_applications():
    if PAAS_DB_AVAILABLE:
        try:
            apps = paas_db.list_applications()
            applications = {}
            for app in apps:
                app_name = app['name']
                applications[app_name] = {
                    'name': app_name,
                    'display_name': app.get('display_name', app_name),
                    'description': app.get('description', ''),
                    'framework': app.get('framework', 'laravel'),
                    'git_repo': app.get('repository', ''),
                    'production_branch': app.get('production_branch', 'main'),
                    'staging_branch': app.get('staging_branch', 'staging'),
                    'staging_env': bool(app.get('create_staging', 1)),
                    'target_servers': json.loads(app.get('target_servers', '[]')),
                    'port': app.get('port'),
                    'redis_enabled': bool(app.get('redis_enabled', 0)),
                    'redis_db': app.get('redis_db'),
                    'domains': [],
                    'server_commits': {},
                    'created_at': app.get('created_at', '')
                }
                
                domains = paas_db.get_domains_for_app(app['id'])
                for d in domains:
                    applications[app_name]['domains'].append({
                        'name': d['domain'],
                        'type': d['environment'],
                        'base_domain': d['domain'],
                        'dns_label': d.get('dns_label', '@'),
                        'www_redirect': bool(d.get('is_www', 0)),
                        'ssl_enabled': bool(d.get('ssl_enabled', 1)),
                        'provisioned': bool(d.get('provisioned', 0)),
                        'status': d.get('status', 'pending'),
                        'password': d.get('password'),
                        'error': d.get('error', '')
                    })
            
            return applications
        except Exception as e:
            print(f"Error loading from SQLite: {e}")
    
    if os.path.exists(APPS_CONFIG_PATH):
        with open(APPS_CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f)
            applications = data.get("applications", {}) if data else {}
            changed = False
            for app_name in list(applications.keys()):
                before = json.dumps(applications[app_name], sort_keys=True)
                applications[app_name] = ensure_app_domain_schema(applications[app_name])
                after = json.dumps(applications[app_name], sort_keys=True)
                if before != after:
                    changed = True
            if changed:
                save_applications(applications)
            return applications
    return {}


def save_applications(applications):
    if PAAS_DB_AVAILABLE:
        try:
            for app_name, app in applications.items():
                existing = paas_db.get_application(name=app_name)
                
                app_data = {
                    'name': app_name,
                    'display_name': app.get('display_name', app_name),
                    'description': app.get('description', ''),
                    'framework': app.get('framework', 'laravel'),
                    'repository': app.get('git_repo', ''),
                    'production_branch': app.get('production_branch', 'main'),
                    'staging_branch': app.get('staging_branch', 'staging'),
                    'create_staging': app.get('staging_env', True),
                    'target_servers': app.get('target_servers', []),
                    'port': app.get('port'),
                    'redis_enabled': app.get('redis_enabled', False),
                    'redis_db': app.get('redis_db')
                }
                
                if existing:
                    paas_db.update_application(existing['id'], app_data)
                    app_id = existing['id']
                else:
                    app_id = paas_db.create_application(app_data)
                
                for domain in app.get('domains', []):
                    domain_data = {
                        'app_id': app_id,
                        'domain': domain.get('name', domain.get('domain')),
                        'environment': domain.get('type', 'production'),
                        'is_www': domain.get('www_redirect', False),
                        'dns_label': domain.get('dns_label', '@'),
                        'ssl_enabled': domain.get('ssl_enabled', True),
                        'provisioned': domain.get('provisioned', False),
                        'status': domain.get('status', 'pending'),
                        'password': domain.get('password')
                    }
                    existing_domain = paas_db.get_domains_for_app(app_id)
                    domain_exists = any(d['domain'] == domain_data['domain'] for d in existing_domain)
                    if not domain_exists:
                        paas_db.create_domain(domain_data)
            
            return
        except Exception as e:
            print(f"Error saving to SQLite: {e}")
    
    os.makedirs(os.path.dirname(APPS_CONFIG_PATH), exist_ok=True)
    data = {"applications": applications}
    with open(APPS_CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_public_base_url():
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL.rstrip("/")
    return request.host_url.rstrip("/")


def get_webhook_base_url():
    return f"https://{WEBHOOK_PUBLIC_HOST}".rstrip("/")


def build_domains_from_configs(domain_configs, enable_security):
    domains = []
    for config in domain_configs:
        base_domain = (config.get("domain") or "").strip().lower()
        if not base_domain:
            continue

        prod_config = config.get("production", {})
        prod_type = prod_config.get("type", "root")
        prod_prefix = (prod_config.get("prefix") or "").strip().lower()

        if prod_type == "root":
            domains.append({
                "name": base_domain,
                "type": "production",
                "base_domain": base_domain,
                "dns_label": "@",
                "production_mode": "root",
                "www_redirect": True,
                "ssl_enabled": True,
                "dns_provisioned": False,
                "provisioned": False,
                "status": "pending",
                "security_enabled": enable_security,
                "error": "",
                "created_at": datetime.utcnow().isoformat()
            })
        else:
            label = prod_prefix or "www"
            domains.append({
                "name": f"{label}.{base_domain}",
                "type": "production",
                "base_domain": base_domain,
                "dns_label": label,
                "production_mode": "subdomain",
                "www_redirect": False,
                "ssl_enabled": True,
                "dns_provisioned": False,
                "provisioned": False,
                "status": "pending",
                "security_enabled": enable_security,
                "error": "",
                "created_at": datetime.utcnow().isoformat()
            })

        staging_config = config.get("staging", {})
        staging_type = staging_config.get("type", "none")
        staging_prefix = (staging_config.get("prefix") or "staging").strip().lower()
        staging_password = staging_config.get("password") or secrets.token_urlsafe(12)
        if staging_type == "subdomain":
            domains.append({
                "name": f"{staging_prefix}.{base_domain}",
                "type": "staging",
                "base_domain": base_domain,
                "dns_label": staging_prefix,
                "ssl_enabled": True,
                "dns_provisioned": False,
                "provisioned": False,
                "status": "pending",
                "security_enabled": enable_security,
                "password": staging_password,
                "error": "",
                "created_at": datetime.utcnow().isoformat()
            })

        for cname in config.get("cnames", []):
            label = (cname or "").strip().lower()
            if not label:
                continue
            domains.append({
                "name": f"{label}.{base_domain}",
                "type": "cname",
                "base_domain": base_domain,
                "dns_label": label,
                "ssl_enabled": True,
                "dns_provisioned": False,
                "provisioned": False,
                "status": "pending",
                "security_enabled": enable_security,
                "error": "",
                "created_at": datetime.utcnow().isoformat()
            })
    return domains


def ensure_app_domain_schema(app):
    if not app.get("github_webhook_secret"):
        app["github_webhook_secret"] = secrets.token_urlsafe(32)

    domains = app.get("domains", []) or []
    for d in domains:
        if "status" not in d:
            d["status"] = "provisioned" if d.get("provisioned") else "pending"
        if "error" not in d:
            d["error"] = ""
        if "dns_label" not in d:
            base_domain = d.get("base_domain")
            name = d.get("name", "")
            if d.get("type") == "production" and base_domain and name == base_domain:
                d["dns_label"] = "@"
                d["production_mode"] = "root"
                d["www_redirect"] = True
            elif base_domain and name.endswith(f".{base_domain}"):
                d["dns_label"] = name[:-(len(base_domain) + 1)]
            else:
                d["dns_label"] = "@"

    if app.get("domain_configs"):
        converted = build_domains_from_configs(app.get("domain_configs", []), app.get("enable_security", True))
        existing_names = {d.get("name") for d in domains}
        for d in converted:
            if d.get("name") not in existing_names:
                domains.append(d)

    app["domains"] = domains
    app.pop("domain_configs", None)
    return app


def get_reserved_base_domains(applications, exclude_app=None):
    reserved = {}
    for name, app in applications.items():
        if exclude_app and name == exclude_app:
            continue
        for domain in app.get("domains", []) or []:
            base = (domain.get("base_domain") or "").strip().lower()
            if base:
                reserved[base] = name
    return reserved


def is_safe_identifier(value):
    return bool(re.match(r"^[a-z][a-z0-9_]*$", value or ""))


def resolve_public_ip(server_ip):
    for server in APP_SERVERS + DB_SERVERS + ROUTERS:
        if server.get("ip") == server_ip:
            public_ip = (server.get("public_ip") or "").strip()
            if public_ip and public_ip != server_ip:
                return public_ip
    return None


import socket

def ssh_command(server_ip, command, timeout=30):
    # Check if we're running on the same server - use local execution
    local_ips = ["127.0.0.1", "localhost", "127.0.1.1"]
    
    # Get Tailscale IP if available
    try:
        result = subprocess.run(
            ["ip", "addr", "show", "tailscale0"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            import re
            match = re.search(r'inet ([0-9.]+)/', result.stdout)
            if match:
                local_ips.append(match.group(1))
    except:
        pass
    
    def run_local(run_timeout):
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=run_timeout
        )
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    
    def run_target(target_ip, run_timeout):
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
             "-o", "BatchMode=yes", f"root@{target_ip}", command],
            capture_output=True, text=True, timeout=run_timeout
        )
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    
    # Use local execution if on same server
    if server_ip in local_ips:
        try:
            return run_local(timeout)
        except subprocess.TimeoutExpired:
            return {"success": False, "stdout": "", "stderr": "Local command timed out"}
        except Exception as e:
            return {"success": False, "stdout": "", "stderr": str(e)}
    
    public_ip = resolve_public_ip(server_ip)
    primary_timeout = timeout

    try:
        primary = run_target(server_ip, primary_timeout)
        tailscale_gate = "Tailscale SSH requires an additional check"
        if tailscale_gate in (primary.get("stdout") or "") or tailscale_gate in (primary.get("stderr") or ""):
            if public_ip:
                fallback = run_target(public_ip, timeout)
                if fallback.get("success"):
                    return fallback
                fallback["stderr"] = f"Primary ({server_ip}) blocked by Tailscale check; fallback ({public_ip}) failed: {fallback.get('stderr', '').strip()}"
                return fallback
        
        if primary.get("stdout"):
            return primary
        
        ssh_error_patterns = ["Connection refused", "Connection timed out", "No route to host", "Host key verification failed", "Permission denied"]
        stderr_lower = (primary.get("stderr") or "").lower()
        is_ssh_error = any(p.lower() in stderr_lower for p in ssh_error_patterns)
        
        if not is_ssh_error and primary.get("stderr"):
            return primary
        
        if public_ip:
            fallback = run_target(public_ip, timeout)
            if fallback.get("success"):
                return fallback
            fallback["stderr"] = f"Primary ({server_ip}) failed: {primary.get('stderr', '').strip()} | Fallback ({public_ip}) failed: {fallback.get('stderr', '').strip()}"
            return fallback
        return primary
    except subprocess.TimeoutExpired:
        if public_ip:
            try:
                fallback = run_target(public_ip, timeout)
                if fallback.get("success"):
                    return fallback
                fallback["stderr"] = f"Primary ({server_ip}) timed out | Fallback ({public_ip}) failed: {fallback.get('stderr', '').strip()}"
                return fallback
            except subprocess.TimeoutExpired:
                return {"success": False, "stdout": "", "stderr": f"Primary ({server_ip}) timed out; fallback ({public_ip}) timed out"}
        return {"success": False, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def run_as_app_user(command):
    return f"sudo -u {APP_RUNTIME_USER} -H bash -lc {shlex.quote(command)}"


def ensure_app_runtime_user(server_ip):
    cmd = (
        f"id -u {APP_RUNTIME_USER} >/dev/null 2>&1 || "
        f"useradd --system --create-home --home-dir /home/{APP_RUNTIME_USER} "
        f"--shell /usr/sbin/nologin {APP_RUNTIME_USER}"
    )
    return ssh_command(server_ip, cmd)


def ensure_app_directory_permissions(server_ip, app_name):
    app_dir = f"/opt/apps/{app_name}"
    cmd = (
        "mkdir -p /opt/apps && chmod 755 /opt/apps && "
        f"test -d {app_dir} && chown -R {APP_RUNTIME_USER}:{APP_RUNTIME_USER} {app_dir} || true"
    )
    return ssh_command(server_ip, cmd)


def ensure_laravel_runtime_permissions(server_ip, app_name):
    app_dir = f"/opt/apps/{app_name}"
    cmd = (
        f"mkdir -p {app_dir}/storage {app_dir}/bootstrap/cache && "
        f"chgrp -R www-data {app_dir}/storage {app_dir}/bootstrap/cache && "
        f"chmod -R ug+rwX {app_dir}/storage {app_dir}/bootstrap/cache && "
        f"find {app_dir}/storage {app_dir}/bootstrap/cache -type d -exec chmod 2775 {{}} \\;"
    )
    return ssh_command(server_ip, cmd)


def run_local_command(command, timeout=30):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def run_router_command(router, command, timeout=30):
    if router.get("ip") == "100.102.220.16":
        return run_local_command(command, timeout=timeout)

    public_ip = (router.get("public_ip") or "").strip()
    if public_ip and public_ip != router.get("ip"):
        primary_timeout = min(timeout, 45)
        primary = ssh_command(public_ip, command, timeout=primary_timeout)
        if primary.get("success"):
            return primary

        remaining_timeout = max(timeout - primary_timeout, 30)
        fallback = ssh_command(router["ip"], command, timeout=remaining_timeout)
        if fallback.get("success"):
            return fallback
        fallback["stderr"] = f"Primary ({public_ip}) failed: {primary.get('stderr', '').strip()} | Fallback ({router.get('ip')}) failed: {fallback.get('stderr', '').strip()}"
        return fallback

    primary_timeout = min(timeout, 45)
    primary = ssh_command(router["ip"], command, timeout=primary_timeout)
    if primary.get("success"):
        return primary

    return primary


def clone_repo_to_servers(app_name, git_repo, servers, github_token=None):
    results = []
    
    clone_url = git_repo
    if github_token and "github.com" in git_repo:
        if git_repo.startswith("https://github.com/"):
            clone_url = git_repo.replace("https://github.com/", f"https://{github_token}@github.com/")
    
    for server in servers:
        app_dir = f"/opt/apps/{app_name}"

        user_result = ensure_app_runtime_user(server["ip"])
        if not user_result["success"]:
            results.append({"server": server["name"], "status": "error", "message": f"Failed to ensure runtime user '{APP_RUNTIME_USER}': {summarize_command_error(user_result)}"})
            continue
        
        check_result = ssh_command(server["ip"], f"test -d {app_dir} && echo exists")
        if "exists" in check_result.get("stdout", ""):
            ssh_command(server["ip"], f"git config --global --add safe.directory {app_dir}")
            results.append({"server": server["name"], "status": "exists", "message": f"Directory {app_dir} already exists"})
            continue
        
        mkdir_result = ssh_command(server["ip"], "mkdir -p /opt/apps && chmod 755 /opt/apps")
        if not mkdir_result["success"]:
            results.append({"server": server["name"], "status": "error", "message": f"Failed to create /opt/apps: {mkdir_result['stderr']}"})
            continue

        prep_cmd = f"mkdir -p {app_dir} && chown {APP_RUNTIME_USER}:{APP_RUNTIME_USER} {app_dir}"
        prep_result = ssh_command(server["ip"], prep_cmd)
        if not prep_result["success"]:
            results.append({"server": server["name"], "status": "error", "message": f"Failed to prepare app directory: {prep_result['stderr']}"})
            continue

        ssh_command(server["ip"], f"git config --global --add safe.directory {app_dir}")
        
        clone_cmd = run_as_app_user(f"cd {app_dir} && git clone {shlex.quote(clone_url)} .")
        clone_result = ssh_command(server["ip"], clone_cmd, timeout=120)
        if clone_result["success"]:
            ensure_app_directory_permissions(server["ip"], app_name)
            results.append({"server": server["name"], "status": "cloned", "message": f"Cloned to {app_dir}"})
        else:
            err = summarize_command_error(clone_result)
            results.append({"server": server["name"], "status": "error", "message": f"Clone failed: {err}"})
    
    return results


def detect_build_tools(server_ip, app_dir):
    """
    Detect build tools and frameworks from config files.
    Returns a dict with detected tools and their build commands.
    """
    tools = {
        "framework": None,
        "bundler": None,
        "build_command": None,
        "install_command": "npm install",
        "output_dir": None,
        "config_files": []
    }
    
    config_checks = [
        ("vite.config.js", "vite"),
        ("vite.config.ts", "vite"),
        ("next.config.js", "nextjs"),
        ("next.config.mjs", "nextjs"),
        ("svelte.config.js", "sveltekit"),
        ("nuxt.config.js", "nuxt"),
        ("nuxt.config.ts", "nuxt"),
        ("gatsby-config.js", "gatsby"),
        ("angular.json", "angular"),
        ("vue.config.js", "vue"),
        ("webpack.config.js", "webpack"),
        ("rollup.config.js", "rollup"),
        ("tsconfig.json", "typescript"),
        ("package.json", "package"),
    ]
    
    for config_file, tool_name in config_checks:
        check = ssh_command(server_ip, f"test -f {app_dir}/{config_file} && echo exists")
        if "exists" in check.get("stdout", ""):
            tools["config_files"].append(config_file)
            if not tools["framework"]:
                tools["framework"] = tool_name
    
    if "package.json" in tools["config_files"]:
        package_json = ssh_command(server_ip, f"cat {app_dir}/package.json 2>/dev/null")
        if package_json["success"]:
            try:
                import json
                pkg = json.loads(package_json["stdout"])
                scripts = pkg.get("scripts", {})
                
                if "build" in scripts:
                    tools["build_command"] = "npm run build"
                if "dev" in scripts and not tools["build_command"]:
                    tools["build_command"] = "npm run build"
                if "postinstall" in scripts:
                    tools["install_command"] = "npm install"
                
                dependencies = pkg.get("dependencies", {})
                dev_deps = pkg.get("devDependencies", {})
                all_deps = {**dependencies, **dev_deps}
                
                if "next" in all_deps:
                    tools["framework"] = "nextjs"
                    tools["output_dir"] = ".next"
                elif "@sveltejs/kit" in all_deps:
                    tools["framework"] = "sveltekit"
                    tools["output_dir"] = ".svelte-kit"
                elif "vite" in all_deps:
                    tools["framework"] = "vite"
                    tools["bundler"] = "vite"
                    tools["output_dir"] = "dist"
                elif "nuxt" in all_deps:
                    tools["framework"] = "nuxt"
                    tools["output_dir"] = ".output"
                elif "gatsby" in all_deps:
                    tools["framework"] = "gatsby"
                    tools["output_dir"] = "public"
                elif "@angular/core" in all_deps:
                    tools["framework"] = "angular"
                    tools["output_dir"] = "dist"
                elif "vue" in all_deps:
                    tools["framework"] = "vue"
                    tools["output_dir"] = "dist"
                elif "webpack" in all_deps:
                    tools["bundler"] = "webpack"
                    tools["output_dir"] = "dist"
                
            except json.JSONDecodeError:
                pass
    
    return tools


def get_build_command(server_ip, app_dir, detected_tools=None):
    """
    Get the appropriate build command based on detected tools and package.json scripts.
    Returns the build command to run, or None if no build needed.
    """
    if not detected_tools:
        detected_tools = detect_build_tools(server_ip, app_dir)
    
    has_package_json = ssh_command(server_ip, f"test -f {app_dir}/package.json && echo yes")
    if "yes" not in has_package_json.get("stdout", ""):
        return None
    
    package_json = ssh_command(server_ip, f"cat {app_dir}/package.json 2>/dev/null")
    if not package_json["success"]:
        return None
    
    try:
        import json
        pkg = json.loads(package_json["stdout"])
        scripts = pkg.get("scripts", {})
        
        build_commands = [
            ("build", "npm run build"),
            ("compile", "npm run compile"),
            ("bundle", "npm run bundle"),
            ("prod", "npm run prod"),
            ("production", "npm run production"),
        ]
        
        for script_name, command in build_commands:
            if script_name in scripts:
                return command
        
        framework = detected_tools.get("framework")
        if framework == "nextjs":
            return "npm run build"
        elif framework == "sveltekit":
            return "npm run build"
        elif framework == "nuxt":
            return "npm run build"
        elif framework == "gatsby":
            return "npm run build"
        elif framework == "angular":
            return "npm run build"
        elif framework == "vite":
            return "npm run build"
        
        if scripts:
            return "npm run build"
        
    except json.JSONDecodeError:
        pass
    
    return None


def get_install_command(server_ip, app_dir):
    """
    Get the appropriate install command based on lock files present.
    """
    has_npm = ssh_command(server_ip, f"test -f {app_dir}/package-lock.json && echo yes")
    has_yarn = ssh_command(server_ip, f"test -f {app_dir}/yarn.lock && echo yes")
    has_pnpm = ssh_command(server_ip, f"test -f {app_dir}/pnpm-lock.yaml && echo yes")
    
    if "yes" in has_pnpm.get("stdout", ""):
        return "pnpm install"
    elif "yes" in has_yarn.get("stdout", ""):
        return "yarn install"
    else:
        return "npm install"


def run_frontend_build(server_ip, app_dir):
    """
    Detect and run frontend build process.
    Returns dict with build results.
    """
    node_check = ensure_nodejs_20(server_ip)
    if not node_check["success"]:
        return {"success": False, "message": f"Node.js setup failed: {node_check['message']}"}
    
    detected_tools = detect_build_tools(server_ip, app_dir)
    
    if not detected_tools["config_files"]:
        return {"success": True, "message": "No frontend build tools detected, skipping"}
    
    install_cmd = get_install_command(server_ip, app_dir)
    clean_install = run_as_app_user(f"cd {app_dir} && rm -rf node_modules package-lock.json yarn.lock pnpm-lock.yaml && {install_cmd}")
    
    install_result = ssh_command(server_ip, clean_install, timeout=300)
    if not install_result["success"]:
        err = install_result.get('stderr') or install_result.get('stdout', 'Unknown error')[-500:]
        return {"success": False, "message": f"Install failed: {err}"}
    
    build_cmd = get_build_command(server_ip, app_dir, detected_tools)
    if not build_cmd:
        return {"success": True, "message": "No build script found, skipping build"}
    
    build_result = ssh_command(server_ip, run_as_app_user(f"cd {app_dir} && {build_cmd} 2>&1"), timeout=300)
    if not build_result["success"]:
        err = build_result.get('stderr') or build_result.get('stdout', 'Unknown error')[-500:]
        return {"success": False, "message": f"Build failed: {err}"}
    
    framework = detected_tools.get("framework", "unknown")
    output_dir = detected_tools.get("output_dir", "dist")
    
    return {
        "success": True,
        "message": f"Build completed successfully",
        "framework": framework,
        "output_dir": output_dir,
        "tools_detected": detected_tools["config_files"]
    }


def ensure_nodejs_20(server_ip):
    check_result = ssh_command(server_ip, "node --version 2>/dev/null | grep -E '^v20' && echo ok || echo need_upgrade")
    if "ok" in check_result.get("stdout", ""):
        return {"success": True, "message": "Node.js 20 already installed"}
    
    install_result = ssh_command(server_ip, 
        "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs 2>&1 | tail -3",
        timeout=120)
    
    if install_result["success"]:
        verify = ssh_command(server_ip, "node --version")
        return {"success": True, "message": f"Node.js installed: {verify.get('stdout', '').strip()}"}
    return {"success": False, "message": f"Failed to install Node.js 20: {install_result.get('stderr', '')}"}


def run_framework_setup(app_name, framework, servers, db_config=None, redis_config=None, app_url=None, environment="production"):
    """
    Run framework setup on servers.
    
    Args:
        app_name: Application name
        framework: Framework type (laravel, nextjs, etc.)
        servers: List of server dicts
        db_config: Database configuration dict
        redis_config: Redis configuration dict
        app_url: Application URL (e.g., https://example.com)
        environment: Environment name (production, staging, development)
    """
    results = []
    
    for server in servers:
        app_dir = f"/opt/apps/{app_name}"

        user_result = ensure_app_runtime_user(server["ip"])
        if not user_result["success"]:
            results.append({"server": server["name"], "status": "error", "message": f"Failed to ensure runtime user '{APP_RUNTIME_USER}': {summarize_command_error(user_result)}"})
            continue
        ensure_app_directory_permissions(server["ip"], app_name)

        if framework == "laravel":
            composer_cmd = run_as_app_user(f"cd {app_dir} && composer install --no-dev --optimize-autoloader 2>&1")
            composer_result = ssh_command(server["ip"], composer_cmd, timeout=300)
            
            if composer_result["success"]:
                build_result = run_frontend_build(server["ip"], app_dir)
                if not build_result["success"]:
                    results.append({"server": server["name"], "status": "error", "message": build_result["message"]})
                    continue
                
                env_result = ssh_command(server["ip"], run_as_app_user(f"cd {app_dir} && cp .env.example .env 2>/dev/null || true"))
                
                env_updates = [
                    f"sed -i 's/APP_ENV=.*/APP_ENV={environment}/' {app_dir}/.env",
                    f"sed -i 's/^DB_CONNECTION=.*/DB_CONNECTION=pgsql/' {app_dir}/.env",
                    f"grep -q '^DB_CONNECTION=' {app_dir}/.env || echo 'DB_CONNECTION=pgsql' >> {app_dir}/.env",
                ]
                
                if environment == "staging":
                    env_updates.append(f"sed -i 's/APP_DEBUG=.*/APP_DEBUG=true/' {app_dir}/.env")
                else:
                    env_updates.append(f"sed -i 's/APP_DEBUG=.*/APP_DEBUG=false/' {app_dir}/.env")
                
                if db_config:
                    db_vars = {
                        "DB_HOST": db_config['host'],
                        "DB_PORT": db_config['port'],
                        "DB_DATABASE": db_config['database'],
                        "DB_USERNAME": db_config['username'],
                        "DB_PASSWORD": db_config['password'],
                    }
                    for var_name, var_value in db_vars.items():
                        env_updates.append(f"sed -i 's/^{var_name}=.*/{var_name}={var_value}/' {app_dir}/.env")
                        env_updates.append(f"grep -q '^{var_name}=' {app_dir}/.env || echo '{var_name}={var_value}' >> {app_dir}/.env")
                        
                if redis_config:
                    redis_vars = {
                        "REDIS_HOST": redis_config['host'],
                        "REDIS_PASSWORD": redis_config['password'],
                        "REDIS_PORT": redis_config['port'],
                    }
                    if redis_config.get('db') is not None:
                        redis_vars["REDIS_DB"] = str(redis_config['db'])
                    for var_name, var_value in redis_vars.items():
                        env_updates.append(f"sed -i 's/^{var_name}=.*/{var_name}={var_value}/' {app_dir}/.env")
                        env_updates.append(f"grep -q '^{var_name}=' {app_dir}/.env || echo '{var_name}={var_value}' >> {app_dir}/.env")
                        
                if app_url:
                    env_updates.extend([
                        f"sed -i 's|APP_URL=.*|APP_URL={app_url}|' {app_dir}/.env",
                        f"grep -q '^APP_URL=' {app_dir}/.env || echo 'APP_URL={app_url}' >> {app_dir}/.env",
                    ])
                ssh_command(server["ip"], run_as_app_user(" && ".join(env_updates)))

                ssh_command(server["ip"], run_as_app_user(f"cd {app_dir} && php artisan key:generate --force 2>/dev/null || true"))

                ssh_command(server["ip"], run_as_app_user(f"cd {app_dir} && php artisan storage:link 2>/dev/null || true"))
                ensure_laravel_runtime_permissions(server["ip"], app_name)
                results.append({
                    "server": server["name"],
                    "status": "composer_installed",
                    "output": f"Composer installed, {build_result['message']}"
                })
            else:
                results.append({"server": server["name"], "status": "error", "message": composer_result["stderr"][-500:] if composer_result["stderr"] else "Unknown error"})
                
        elif framework in ["nextjs", "svelte", "vue", "nuxt", "gatsby", "angular"]:
            build_result = run_frontend_build(server["ip"], app_dir)
            if build_result["success"]:
                detected_framework = build_result.get("framework", framework)
                results.append({
                    "server": server["name"], 
                    "status": "built", 
                    "output": f"{detected_framework} build completed: {build_result['message']}"
                })
            else:
                results.append({"server": server["name"], "status": "error", "message": build_result["message"]})
                
        elif framework == "go":
            build_result = ssh_command(server["ip"], run_as_app_user(f"cd {app_dir} && go build -o bin/{app_name} . 2>&1"), timeout=300)
            
            if build_result["success"]:
                results.append({"server": server["name"], "status": "built", "output": "Go binary built"})
            else:
                results.append({"server": server["name"], "status": "error", "message": build_result["stderr"][-500:] if build_result.get("stderr") else "Unknown error"})
    
        elif framework == "python":
            venv_path = f"{app_dir}/venv"
            venv_result = ssh_command(server["ip"], run_as_app_user(f"python3 -m venv {venv_path} 2>&1"))
            
            if venv_result["success"]:
                requirements_check = ssh_command(server["ip"], f"test -f {app_dir}/requirements.txt && echo exists")
                pip_output = ""
                
                if "exists" in requirements_check.get("stdout", ""):
                    pip_result = ssh_command(server["ip"], run_as_app_user(f"{venv_path}/bin/pip install -r {app_dir}/requirements.txt 2>&1"), timeout=300)
                    pip_output = " dependencies installed" if pip_result["success"] else f" pip failed: {pip_result.get('stderr', '')[:100]}"
                
                results.append({
                    "server": server["name"], 
                    "status": "venv_created", 
                    "output": f"Python venv created{pip_output}"
                })
            else:
                results.append({"server": server["name"], "status": "error", "message": venv_result["stderr"][-500:] if venv_result.get("stderr") else "Unknown error"})
    
    return results


def get_framework_env_vars(framework, environment="production", app_url=None, db_config=None, redis_config=None):
    """
    Get framework-specific environment variables.
    
    Returns a dict of environment variables for the given framework and environment.
    """
    env_vars = {}
    
    if framework == "laravel":
        env_vars["APP_ENV"] = environment
        env_vars["APP_DEBUG"] = "true" if environment == "staging" else "false"
        if app_url:
            env_vars["APP_URL"] = app_url
            env_vars["ASSET_URL"] = app_url
    
    elif framework in ["nextjs", "svelte", "vue", "nuxt", "gatsby", "angular"]:
        env_vars["NODE_ENV"] = "production" if environment == "production" else "development"
        if app_url:
            env_vars["NEXT_PUBLIC_URL"] = app_url if framework == "nextjs" else None
            env_vars["NUXT_PUBLIC_URL"] = app_url if framework == "nuxt" else None
    
    elif framework == "python":
        env_vars["APP_ENV"] = environment
        env_vars["FLASK_ENV"] = "development" if environment == "staging" else "production"
        env_vars["DJANGO_SETTINGS_MODULE"] = f"config.settings.{environment}"
    
    elif framework == "go":
        env_vars["APP_ENV"] = environment
    
    if db_config:
        if framework == "laravel":
            pass
        else:
            env_vars["DATABASE_URL"] = f"postgres://{db_config['username']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    
    if redis_config:
        if framework == "laravel":
            pass
        else:
            redis_db = redis_config.get('db', 0)
            env_vars["REDIS_URL"] = f"redis://:{redis_config['password']}@{redis_config['host']}:{redis_config['port']}/{redis_db}"
    
    return {k: v for k, v in env_vars.items() if v is not None}


def create_systemd_service(app_name, framework, server_ip, db_url=None, redis_url=None, env_vars=None):
    user_result = ensure_app_runtime_user(server_ip)
    if not user_result["success"]:
        return {"success": False, "stdout": "", "stderr": f"Failed to ensure runtime user '{APP_RUNTIME_USER}': {summarize_command_error(user_result)}"}

    if framework == "laravel":
        return {"success": True, "message": "Laravel uses nginx + PHP-FPM, not systemd service"}
    elif framework == "nextjs":
        service_content = f"""[Unit]
Description={app_name} Next.js Application
After=network.target

[Service]
Type=simple
User=webapps
Group=webapps
WorkingDirectory=/opt/apps/{app_name}
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5
"""
    elif framework == "svelte":
        service_content = f"""[Unit]
Description={app_name} Svelte Application
After=network.target

[Service]
Type=simple
User=webapps
Group=webapps
WorkingDirectory=/opt/apps/{app_name}
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5
"""
    elif framework == "python":
        service_content = f"""[Unit]
Description={app_name} Python Application
After=network.target

[Service]
Type=simple
User=webapps
Group=webapps
WorkingDirectory=/opt/apps/{app_name}
ExecStart=/opt/apps/{app_name}/venv/bin/gunicorn --bind 0.0.0.0:8000 app:app
Restart=always
RestartSec=5
"""
    else:
        service_content = f"""[Unit]
Description={app_name} Go Application
After=network.target

[Service]
Type=simple
User=webapps
Group=webapps
WorkingDirectory=/opt/apps/{app_name}
ExecStart=/opt/apps/{app_name}/bin/{app_name}
Restart=always
RestartSec=5
"""
    
    if db_url or redis_url or env_vars:
        env_section = "\nEnvironment="
        if db_url:
            env_section += f"DATABASE_URL={db_url} "
        if redis_url:
            env_section += f"REDIS_URL={redis_url} "
        if env_vars:
            for key, value in env_vars.items():
                env_section += f"{key}={value} "
        service_content += env_section.rstrip() + "\n"
    
    service_content += """\n[Install]
WantedBy=multi-user.target
"""
    
    service_path = f"/etc/systemd/system/{app_name}.service"
    
    escaped_content = service_content.replace("'", "'\"'\"'")
    result = ssh_command(server_ip, f"echo '{escaped_content}' > {service_path} && systemctl daemon-reload && systemctl enable {app_name}")
    
    return result


def configure_app_environment(app_name, server_ip, env_vars):
    env_file = f"/opt/apps/{app_name}/.env"
    
    env_content = ""
    for key, value in env_vars.items():
        env_content += f"{key}={value}\n"
    
    escaped_content = env_content.replace("'", "'\"'\"'")
    result = ssh_command(server_ip, f"echo '{escaped_content}' > {env_file} && chown {APP_RUNTIME_USER}:{APP_RUNTIME_USER} {env_file} && chmod 640 {env_file}")
    
    return result


def get_app_base_url(app, environment="production"):
    domains = app.get("domains", []) or []
    for domain in domains:
        if domain.get("type") == environment and domain.get("name"):
            return f"https://{domain['name']}"
    return None


def get_deploy_target_name(app_name, environment="production"):
    return f"{app_name}-staging" if environment == "staging" else app_name


def ensure_laravel_app_key(app_name, environment="production"):
    current_value = get_app_secret(app_name, "APP_KEY", scope=environment)
    if current_value and str(current_value).strip():
        return current_value

    shared_value = get_app_secret(app_name, "APP_KEY", scope="shared")
    if shared_value and str(shared_value).strip():
        return shared_value

    random_bytes = os.urandom(32)
    app_key = "base64:" + base64.b64encode(random_bytes).decode("ascii")
    set_app_secret(app_name, "APP_KEY", app_key, "Auto-generated Laravel APP_KEY", scope="shared")
    return app_key


def build_deploy_env_material(app_name, app, environment="production"):
    framework = app.get("framework", "")
    deploy_target_name = get_deploy_target_name(app_name, environment)
    additional_vars = {"APP_NAME": deploy_target_name}

    if framework in ["nextjs", "svelte", "vue", "nuxt", "gatsby", "angular", "nodejs"]:
        additional_vars["NODE_ENV"] = "production" if environment == "production" else "development"
    else:
        additional_vars["APP_ENV"] = environment

    if framework == "laravel":
        additional_vars["APP_ENV"] = environment
        additional_vars["APP_DEBUG"] = "true" if environment == "staging" else "false"
        additional_vars["DB_CONNECTION"] = "pgsql"

        app_url = get_app_base_url(app, environment)
        if app_url:
            additional_vars["APP_URL"] = app_url
            additional_vars["ASSET_URL"] = app_url

        db_name = app.get("staging_database") if environment == "staging" else app.get("database")
        if db_name:
            additional_vars["DB_HOST"] = str(PG_HOST)
            additional_vars["DB_PORT"] = str(PG_PORT)
            additional_vars["DB_DATABASE"] = db_name

        username_key = "STAGING_DB_USERNAME" if environment == "staging" else "DB_USERNAME"
        password_key = "STAGING_DB_PASSWORD" if environment == "staging" else "DB_PASSWORD"

        secret_vars = export_secrets_for_deployment(app_name, environment)
        if secret_vars.get(username_key):
            additional_vars["DB_USERNAME"] = secret_vars.get(username_key)
        if secret_vars.get(password_key):
            additional_vars["DB_PASSWORD"] = secret_vars.get(password_key)

        app_key = ensure_laravel_app_key(app_name, environment)
        if app_key:
            additional_vars["APP_KEY"] = app_key

        if db_name and ("DB_USERNAME" not in additional_vars or "DB_PASSWORD" not in additional_vars):
            databases = load_databases()
            db_info = databases.get(db_name, {})
            owner = db_info.get("owner")
            users = db_info.get("users", [])
            selected_user = None
            if owner:
                selected_user = next((u for u in users if u.get("name") == owner and u.get("password")), None)
            if not selected_user:
                selected_user = next((u for u in users if u.get("password")), None)
            if selected_user:
                additional_vars.setdefault("DB_USERNAME", selected_user.get("name", ""))
                additional_vars.setdefault("DB_PASSWORD", selected_user.get("password", ""))

        if app.get("redis_enabled"):
            additional_vars["REDIS_HOST"] = str(REDIS_HOST)
            additional_vars["REDIS_PORT"] = str(REDIS_PORT)
            additional_vars["REDIS_PASSWORD"] = str(REDIS_PASSWORD)

    merged_vars = export_secrets_for_deployment(app_name, environment)
    for k, v in additional_vars.items():
        merged_vars[k] = v

    required_keys = []
    if framework == "laravel":
        required_keys = [
            "APP_KEY",
            "DB_CONNECTION",
            "DB_HOST",
            "DB_PORT",
            "DB_DATABASE",
            "DB_USERNAME",
            "DB_PASSWORD",
        ]
        if app.get("redis_enabled"):
            required_keys.extend(["REDIS_HOST", "REDIS_PORT", "REDIS_PASSWORD"])

    missing_keys = [k for k in required_keys if not str(merged_vars.get(k, "")).strip()]
    env_content = generate_env_file_content(app_name, environment, additional_vars)
    return {"env_content": env_content, "missing_keys": missing_keys}


def write_runtime_env_to_servers(app_name, app, servers, environment="production", deploy_target_name=None):
    target_name = deploy_target_name or get_deploy_target_name(app_name, environment)
    material = build_deploy_env_material(app_name, app, environment)
    if material.get("missing_keys"):
        missing = ", ".join(material["missing_keys"])
        return {
            "success": False,
            "errors": [f"Missing required deploy secrets for {environment}: {missing}"],
            "servers": {},
        }

    encoded_env = base64.b64encode(material["env_content"].encode("utf-8")).decode("ascii")
    server_results = {}
    errors = []

    for server in servers:
        env_path = f"/opt/apps/{target_name}/.env"
        tmp_path = f"/opt/apps/{target_name}/.env.tmp"
        cmd = (
            f"mkdir -p /opt/apps/{target_name} && "
            f"printf '%s' '{encoded_env}' | base64 -d > {tmp_path} && "
            f"chown {APP_RUNTIME_USER}:www-data {tmp_path} && "
            f"chmod 640 {tmp_path} && mv {tmp_path} {env_path}"
        )
        result = ssh_command(server["ip"], cmd, timeout=60)
        server_results[server["name"]] = "written" if result.get("success") else "failed"
        if not result.get("success"):
            errors.append(f"{server['name']} env write failed: {summarize_command_error(result)}")

    return {"success": len(errors) == 0, "errors": errors, "servers": server_results}


def sync_runtime_env_for_app(app_name, app):
    results = {"production": {}, "staging": {}, "errors": []}

    production_sync = write_runtime_env_to_servers(
        app_name,
        app,
        APP_SERVERS,
        environment="production",
        deploy_target_name=get_deploy_target_name(app_name, "production"),
    )
    results["production"] = production_sync.get("servers", {})
    if not production_sync.get("success"):
        results["errors"].extend(production_sync.get("errors", []))

    if app.get("staging_env") and app.get("staging_database"):
        staging_sync = write_runtime_env_to_servers(
            app_name,
            app,
            APP_SERVERS,
            environment="staging",
            deploy_target_name=get_deploy_target_name(app_name, "staging"),
        )
        results["staging"] = staging_sync.get("servers", {})
        if not staging_sync.get("success"):
            results["errors"].extend(staging_sync.get("errors", []))

    results["success"] = len(results["errors"]) == 0
    return results


def parse_github_repo(git_repo):
    if not git_repo:
        return None, None
    
    match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', git_repo)
    if match:
        return match.group(1), match.group(2)
    
    match = re.match(r'git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$', git_repo)
    if match:
        return match.group(1), match.group(2)
    
    return None, None


def encrypt_secret(public_key_b64, secret_value):
    if not PYNACL_AVAILABLE:
        return None
    
    public_key_bytes = base64.b64decode(public_key_b64)
    public_key = public.PublicKey(public_key_bytes)
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def get_github_public_key(owner, repo, token):
    if not token:
        return None, "No GitHub token configured"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data["key"], data["key_id"]
        else:
            return None, f"Failed to get public key: {resp.status_code}"
    except Exception as e:
        return None, str(e)


def set_github_secret(owner, repo, token, secret_name, secret_value):
    if not token:
        return False, "No GitHub token configured"
    
    public_key, key_id = get_github_public_key(owner, repo, token)
    if not public_key:
        return False, key_id
    
    encrypted_value = encrypt_secret(public_key, secret_value)
    if not encrypted_value:
        return False, "Failed to encrypt secret"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
    
    try:
        resp = requests.put(url, headers=headers, json=data, timeout=10)
        if resp.status_code in [201, 204]:
            return True, None
        else:
            return False, f"Failed to set secret: {resp.status_code}"
    except Exception as e:
        return False, str(e)


def delete_github_secret(owner, repo, token, secret_name):
    if not token:
        return False, "No GitHub token configured"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.delete(url, headers=headers, timeout=10)
        if resp.status_code in [204, 404]:
            return True, None
        else:
            return False, f"Failed to delete secret: {resp.status_code}"
    except Exception as e:
        return False, str(e)


def list_github_secrets(owner, repo, token):
    if not token:
        return None, "No GitHub token configured"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return [s["name"] for s in data.get("secrets", [])], None
        else:
            return None, f"Failed to list secrets: {resp.status_code}"
    except Exception as e:
        return None, str(e)


def push_app_secrets_to_github(app_name, app_data, db_password=None, redis_url=None):
    git_repo = app_data.get("git_repo")
    if not git_repo:
        return {"success": False, "error": "No git repo configured"}
    
    owner, repo = parse_github_repo(git_repo)
    if not owner or not repo:
        return {"success": False, "error": "Invalid GitHub repo URL"}
    
    if not GITHUB_TOKEN:
        return {"success": False, "error": "No GitHub token configured in Settings"}
    
    secrets_to_push = {
        "DEPLOY_HOST": "100.102.220.16",
        "DEPLOY_USER": "admin",
        "DEPLOY_PASSWORD": "DbAdmin2026!"
    }
    
    db_name = app_data.get("database")
    if db_name and db_password:
        db_admin = f"{app_name}_admin"
        secrets_to_push["DATABASE_URL"] = f"postgres://{db_admin}:{db_password}@{PG_HOST}:6432/{db_name}"
    
    if redis_url:
        secrets_to_push["REDIS_URL"] = redis_url
    
    results = {"success": True, "pushed": [], "failed": []}
    for secret_name, secret_value in secrets_to_push.items():
        success, error = set_github_secret(owner, repo, GITHUB_TOKEN, secret_name, secret_value)
        if success:
            results["pushed"].append(secret_name)
        else:
            results["failed"].append({"name": secret_name, "error": error})
            results["success"] = False
    
    return results


def get_pg_databases():
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database="postgres", connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
        dbs = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return dbs
    except Exception:
        return []


def terminate_db_connections(cur, db_name):
    cur.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid();",
        (db_name,)
    )


def drop_database_safely(cur, db_name):
    terminate_db_connections(cur, db_name)
    cur.execute(f"DROP DATABASE IF EXISTS {db_name};")


def drop_users_safely(cur, users):
    errors = []
    for user in users:
        if not user:
            continue
        try:
            cur.execute(f"REASSIGN OWNED BY {user} TO {PG_USER};")
            cur.execute(f"DROP OWNED BY {user};")
        except Exception:
            pass
        try:
            cur.execute(f"DROP USER IF EXISTS {user};")
        except Exception as e:
            errors.append(f"{user}: {str(e)}")
    return errors


def collect_db_cleanup_targets(databases, app_name=None, primary_db=None, include_primary=True, include_staging=True):
    db_targets = set()
    user_targets = set()
    config_keys = set()

    if primary_db:
        if include_primary:
            db_targets.add(primary_db)
            config_keys.add(primary_db)
        if include_staging:
            staging_db = f"{primary_db}_staging"
            db_targets.add(staging_db)
            config_keys.add(staging_db)

    if app_name:
        if include_primary:
            user_targets.update({f"{app_name}_user", f"{app_name}_admin"})
        if include_staging:
            user_targets.update({f"{app_name}_staging_user", f"{app_name}_staging_admin"})

        for key, db_info in databases.items():
            if db_info.get("app") != app_name:
                continue
            is_staging = key.endswith("_staging")
            if (is_staging and include_staging) or ((not is_staging) and include_primary):
                db_targets.add(key)
                config_keys.add(key)

    for key in list(config_keys):
        db_info = databases.get(key, {})
        owner = db_info.get("owner")
        if owner:
            user_targets.add(owner)
        for user in db_info.get("users", []):
            name = user.get("name")
            if name:
                user_targets.add(name)

    return sorted(db_targets), sorted(user_targets), sorted(config_keys)


def cleanup_database_artifacts(app_name=None, primary_db=None, include_primary=True, include_staging=True):
    databases = load_databases()
    db_targets, user_targets, config_keys = collect_db_cleanup_targets(
        databases,
        app_name=app_name,
        primary_db=primary_db,
        include_primary=include_primary,
        include_staging=include_staging,
    )

    result = {
        "dropped_databases": [],
        "dropped_users": [],
        "removed_configs": [],
        "errors": []
    }

    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database="postgres"
        )
        conn.autocommit = True
        cur = conn.cursor()

        for db_name in db_targets:
            try:
                drop_database_safely(cur, db_name)
                result["dropped_databases"].append(db_name)
            except Exception as e:
                result["errors"].append(f"database {db_name}: {str(e)}")

        user_errors = drop_users_safely(cur, user_targets)
        if user_errors:
            result["errors"].extend([f"user {e}" for e in user_errors])
        else:
            result["dropped_users"].extend(user_targets)

        cur.close()
        conn.close()
    except Exception as e:
        result["errors"].append(f"database connection: {str(e)}")

    changed = False
    for key in config_keys:
        if key in databases:
            del databases[key]
            result["removed_configs"].append(key)
            changed = True
    if changed:
        save_databases(databases)

    return result


def get_pg_cluster_status():
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database="postgres", connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute("SELECT pg_is_in_recovery();")
        is_replica = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"status": "healthy", "is_replica": is_replica, "role": "replica" if is_replica else "primary"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_redis_info():
    try:
        r = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
            decode_responses=True, socket_connect_timeout=5
        )
        info = r.info()
        return {
            "status": "healthy",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            "role": info.get("role", "unknown")
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_prometheus_alerts():
    try:
        resp = requests.get(f"{PROMETHEUS_URL}/api/v1/alerts", timeout=5)
        data = resp.json()
        alerts = data.get("data", {}).get("alerts", [])
        return [a for a in alerts if a.get("state") == "firing"]
    except Exception:
        return []


def check_server(server):
    try:
        server_ip = server['ip']
        
        # Check if we're checking the local server
        local_ips = ["127.0.0.1", "localhost", "127.0.1.1"]
        try:
            result = subprocess.run(
                ["ip", "addr", "show", "tailscale0"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                import re
                match = re.search(r'inet ([0-9.]+)/', result.stdout)
                if match:
                    local_ips.append(match.group(1))
        except:
            pass
        
        # Use local execution if on same server
        if server_ip in local_ips:
            result = subprocess.run(
                ["uptime", "-p"],
                capture_output=True, text=True, timeout=5
            )
            uptime = result.stdout.strip().replace("up ", "") if result.returncode == 0 else "unreachable"
            return server["name"], {"ip": server["ip"], "public_ip": server.get("public_ip", ""), "uptime": uptime}
        
        # Use SSH for remote servers
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
             "-o", "BatchMode=yes", f"root@{server_ip}", "uptime -p 2>/dev/null || echo 'unreachable'"],
            capture_output=True, text=True, timeout=5
        )
        uptime = result.stdout.strip().replace("up ", "") if result.returncode == 0 else "unreachable"
        return server["name"], {"ip": server["ip"], "public_ip": server.get("public_ip", ""), "uptime": uptime}
    except Exception:
        return server["name"], {"ip": server["ip"], "public_ip": server.get("public_ip", ""), "uptime": "unreachable"}


def check_servers_async(servers):
    results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_server, s): s for s in servers}
        for future in as_completed(futures, timeout=30):
            try:
                name, data = future.result(timeout=5)
                results[name] = data
            except Exception:
                server = futures[future]
                results[server["name"]] = {"ip": server["ip"], "public_ip": server.get("public_ip", ""), "uptime": "error"}
    return results


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
                    "priority": str
                }
            ],
            "security_count": int,
            "total_count": int,
            "services_to_restart": [str],
            "last_checked": str (ISO timestamp)
        }
    """
    cache_key = f"server_updates:{server_ip}"
    
    if not force_refresh:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
    
    if force_refresh:
        ssh_command(server_ip, "apt-get update -qq 2>/dev/null", timeout=60)
    
    result = ssh_command(
        server_ip,
        "apt list --upgradable 2>/dev/null | tail -n +2",
        timeout=30
    )
    
    if not result["success"]:
        return {"success": False, "error": result.get("stderr", "Unknown error"), "packages": []}
    
    packages = []
    security_count = 0
    
    for line in result["stdout"].strip().split("\n"):
        if not line:
            continue
        
        parts = line.split()
        if len(parts) < 3:
            continue
        
        name = parts[0].split("/")[0]
        available_version = parts[1]
        
        # Extract current version from [upgradable from: VERSION]
        current_version = ""
        if "[upgradable from:" in line:
            import re
            match = re.search(r'\[upgradable from: ([^\]]+)\]', line)
            if match:
                current_version = match.group(1)
        
        security_check = ssh_command(
            server_ip,
            f"apt-cache policy {name} 2>/dev/null | grep -A1 '***' | head -1",
            timeout=10
        )
        is_security = "security" in (security_check.get("stdout") or "").lower()
        
        if is_security:
            security_count += 1
        
        packages.append({
            "name": name,
            "current_version": current_version,
            "available_version": available_version,
            "security": is_security,
            "priority": "critical" if is_security else "normal"
        })
    
    services = get_services_needing_restart(server_ip)
    
    response = {
        "success": True,
        "packages": packages,
        "security_count": security_count,
        "total_count": len(packages),
        "services_to_restart": services,
        "last_checked": datetime.utcnow().isoformat() + "Z"
    }
    
    try:
        redis_client.setex(cache_key, 3600, json.dumps(response))
    except Exception:
        pass
    
    return response


def get_services_needing_restart(server_ip):
    """
    Detect services that need restart after package updates.
    
    Returns:
        List of service names that need restart
    """
    services = []
    
    result = ssh_command(
        server_ip,
        "command -v checkrestart >/dev/null 2>&1 && checkrestart 2>/dev/null | grep -oP 'service \\K\\S+' || echo ''",
        timeout=30
    )
    
    if result["success"] and result["stdout"].strip():
        services = [s for s in result["stdout"].strip().split("\n") if s]
    
    if not services:
        result = ssh_command(
            server_ip,
            "lsof 2>/dev/null | grep 'DEL.*\\.so' | awk '{print $1}' | sort -u",
            timeout=30
        )
        if result["success"]:
            process_to_service = {
                "nginx": "nginx",
                "postgres": "postgresql",
                "redis-server": "redis-server",
                "node": "node",
                "php-fpm": "php8.5-fpm",
                "haproxy": "haproxy",
                "patroni": "patroni",
                "etcd": "etcd"
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
            "updated": [str],
            "errors": [str],
            "output": str
        }
    """
    if packages:
        pkg_list = " ".join(packages)
        cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install -y {pkg_list} 2>&1"
    else:
        cmd = "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1"
    
    result = ssh_command(server_ip, cmd, timeout=300)
    
    updated = []
    errors = []
    
    if result["success"]:
        for line in result["stdout"].split("\n"):
            if "Unpacking" in line or "Setting up" in line:
                parts = line.split()
                if len(parts) >= 2:
                    pkg = parts[1].split(":")[0]
                    if pkg not in updated:
                        updated.append(pkg)
        
        try:
            redis_client.delete(f"server_updates:{server_ip}")
        except Exception:
            pass
    else:
        errors.append(result.get("stderr") or result.get("stdout", "Unknown error")[-500:])
    
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
        else:
            results["servers"][server["name"]] = {
                "total": 0,
                "security": 0,
                "last_checked": None,
                "error": updates.get("error", "Unknown error")
            }
    
    return results


def find_server_by_name(server_name):
    """Find server by name in all server lists."""
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        if s["name"] == server_name:
            return s
    return None


@app.route("/")
@requires_auth
def index():
    pg_status = get_pg_cluster_status()
    redis_info = get_redis_info()
    alerts = get_prometheus_alerts()
    pg_databases = get_pg_databases()
    databases = load_databases()
    
    return render_template("index.html",
        pg_status=pg_status,
        redis_info=redis_info,
        alerts=alerts,
        pg_databases=pg_databases,
        databases=databases,
        routers=ROUTERS,
        app_servers=APP_SERVERS,
        db_servers=DB_SERVERS,
        prometheus_url=PROMETHEUS_URL,
        grafana_url=GRAFANA_URL
    )


@app.route("/databases")
@requires_auth
def databases():
    databases = load_databases()
    for db in databases.values():
        display_password = db.get("password")
        if not display_password and db.get("users"):
            first_user = db.get("users", [])[0]
            display_password = first_user.get("password")
            if not display_password and first_user.get("password_hash"):
                display_password = "Not recoverable"
        db["display_password"] = display_password or "-"
    pg_databases = get_pg_databases()
    return render_template("databases.html", databases=databases, pg_databases=pg_databases)


@app.route("/databases/add", methods=["GET", "POST"])
@requires_auth
def add_database():
    if request.method == "POST":
        db_name = request.form.get("db_name", "").strip().lower()
        description = request.form.get("description", "").strip()
        admin_user = request.form.get("admin_user", "").strip()
        admin_password = request.form.get("admin_password", "").strip()
        pool_size = int(request.form.get("pool_size", 20))
        is_superuser = "superuser" in request.form
        
        if not db_name or not admin_user or not admin_password:
            flash("Database name, admin user, and password are required", "error")
            return redirect(url_for("add_database"))
        
        if not is_safe_identifier(db_name) or not is_safe_identifier(admin_user):
            flash("Database name and admin user must start with a letter and contain only lowercase letters, numbers, and underscores", "error")
            return redirect(url_for("add_database"))
        
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, database="postgres"
            )
            cur = conn.cursor()
            
            cur.execute("CREATE USER {} WITH PASSWORD %s;".format(admin_user), (admin_password,))
            if is_superuser:
                cur.execute("ALTER USER {} WITH SUPERUSER CREATEDB;".format(admin_user))
            conn.commit()
            
            cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (admin_user,))
            admin_hash = cur.fetchone()[0]
            
            cur.execute("CREATE DATABASE {} OWNER {};".format(db_name, admin_user))
            conn.commit()
            
            cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {};".format(db_name, admin_user))
            conn.commit()
            
            cur.close()
            conn.close()
            
            databases = load_databases()
            databases[db_name] = {
                "name": db_name,
                "description": description,
                "owner": admin_user,
                "users": [{"name": admin_user, "password_hash": admin_hash, "roles": ["SUPERUSER", "CREATEDB"] if is_superuser else ["CREATEDB"]}],
                "pgbouncer_pool_size": pool_size,
                "pgbouncer_max_clients": pool_size * 10
            }
            save_databases(databases)
            
            flash(f"Database '{db_name}' created successfully", "success")
            return redirect(url_for("databases"))
            
        except Exception as e:
            flash(f"Error: {str(e)}", "error")
            return redirect(url_for("add_database"))
    
    return render_template("add_database.html")


@app.route("/databases/<db_name>/connection")
@requires_auth
def connection_string(db_name):
    databases = load_databases()
    if db_name not in databases:
        flash("Database not found", "error")
        return redirect(url_for("databases"))
    return render_template("connection.html", db_name=db_name, db=databases[db_name], redis_password=REDIS_PASSWORD)


@app.route("/servers")
@requires_auth
def servers():
    server_status = check_servers_async(DB_SERVERS + APP_SERVERS + ROUTERS)
    updates_status = get_all_servers_updates()
    return render_template("servers.html", 
        servers=server_status, 
        db_servers=DB_SERVERS, 
        app_servers=APP_SERVERS, 
        routers=ROUTERS,
        updates_status=updates_status)


@app.route("/api/generate-workflow", methods=["POST"])
@requires_auth
def api_generate_workflow():
    data = request.json
    framework = data.get("framework", "laravel")
    app_name = data.get("app_name", "app")
    staging_env = data.get("staging_env", False)
    create_db = data.get("create_db", False)
    db_name = data.get("db_name", app_name)
    
    workflow = generate_github_workflow(framework, app_name, ["re-db", "re-node-02"], staging_env, create_db, db_name)
    return jsonify({"workflow": workflow})


@app.route("/api/cloudflare/zones")
@requires_auth
def api_cloudflare_zones():
    if not CLOUDFLARE_API_TOKEN:
        return jsonify({"error": "Cloudflare API token not configured", "zones": []})
    
    zones = cf_list_zones()
    return jsonify({"zones": zones})


@app.route("/api/cloudflare/zones/<zone_id>/dns")
@requires_auth
def api_cloudflare_dns_records(zone_id):
    if not CLOUDFLARE_API_TOKEN:
        return jsonify({"error": "Cloudflare API token not configured", "records": []})
    
    result = cf_list_dns_records(zone_id)
    if result.get("success"):
        return jsonify({"success": True, "records": result.get("result", [])})
    else:
        return jsonify({"success": False, "error": result.get("error", "Failed to fetch DNS records"), "records": []})


@app.route("/api/github/validate")
@requires_auth
def api_github_validate():
    repo_url = request.args.get("repo", "").strip()
    if not repo_url:
        return jsonify({"valid": False, "error": "Repository URL is required"})
    
    result = validate_github_repo(repo_url, GITHUB_TOKEN)
    return jsonify(result)


@app.route("/apps")
@requires_auth
def apps():
    applications = load_applications()
    return render_template("apps.html", app_servers=APP_SERVERS, routers=ROUTERS, applications=applications)


@app.route("/apps/create", methods=["GET", "POST"])
@requires_auth
def create_app():
    if request.method == "POST":
        framework = request.form.get("framework")
        app_name = request.form.get("app_name", "").strip().lower()
        app_description = request.form.get("app_description", "").strip()
        git_repo = request.form.get("git_repo", "").strip()
        create_db = "create_db" in request.form
        db_name = request.form.get("db_name", app_name).strip().lower()
        pool_size = int(request.form.get("db_pool_size", 20))
        create_redis = "create_redis" in request.form
        deploy_now = "deploy_now" in request.form
        production_domain = request.form.get("production_domain", "").strip().lower()
        domain_configs_json = request.form.get("domain_configs", "[]")
        enable_security = "enable_security" in request.form or request.form.get("enable_security") == "1"
        
        production_branch = request.form.get("production_branch", "main").strip() or "main"
        staging_branch = request.form.get("staging_branch", "staging").strip() or "staging"
        
        try:
            domain_configs = json.loads(domain_configs_json) if domain_configs_json else []
        except:
            domain_configs = []
        
        create_staging_checkbox = "create_staging" in request.form
        create_staging_from_domains = any(
            dc.get("staging", {}).get("type") != "none" 
            for dc in domain_configs
        )
        create_staging = create_staging_checkbox or create_staging_from_domains
        
        if not app_name or not framework or not git_repo:
            flash("Application name, framework, and GitHub repository are required", "error")
            return redirect(url_for("create_app"))

        if not is_safe_identifier(app_name):
            flash("Application name must start with a letter and contain only lowercase letters, numbers, and underscores", "error")
            return redirect(url_for("create_app"))

        if create_db and not is_safe_identifier(db_name):
            flash("Database name must start with a letter and contain only lowercase letters, numbers, and underscores", "error")
            return redirect(url_for("create_app"))
        
        results = {"app_name": app_name, "framework": framework, "errors": [], "created": []}
        target_servers = [s["name"] for s in APP_SERVERS]
        
        applications = load_applications()
        if app_name in applications:
            flash(f"Application '{app_name}' already exists", "error")
            return redirect(url_for("create_app"))

        reserved_domains = get_reserved_base_domains(applications)
        requested_domains = [
            (cfg.get("domain") or "").strip().lower()
            for cfg in domain_configs
            if (cfg.get("domain") or "").strip()
        ]
        conflicting_domains = [d for d in requested_domains if d in reserved_domains]
        if conflicting_domains:
            conflicts = [f"{d} (used by {reserved_domains[d]})" for d in conflicting_domains]
            flash(f"Domain already assigned to another app: {', '.join(conflicts)}", "error")
            return redirect(url_for("create_app"))
        
        repo_validation = validate_github_repo(git_repo, GITHUB_TOKEN)
        if not repo_validation.get("valid"):
            flash(f"Invalid GitHub repository: {repo_validation.get('error')}", "error")
            return redirect(url_for("create_app"))
        
        if create_db:
            try:
                db_user = f"{app_name}_user"
                db_admin = f"{app_name}_admin"
                db_user_password = secrets.token_urlsafe(16)
                db_admin_password = secrets.token_urlsafe(16)
                
                conn = psycopg2.connect(
                    host=PG_HOST, port=PG_PORT, user=PG_USER,
                    password=PG_PASSWORD, database="postgres"
                )
                conn.autocommit = True
                cur = conn.cursor()
                
                cur.execute("CREATE USER {} WITH PASSWORD %s;".format(db_user), (db_user_password,))
                cur.execute("CREATE USER {} WITH PASSWORD %s CREATEDB;".format(db_admin), (db_admin_password,))
                
                cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (db_user,))
                user_hash = cur.fetchone()[0]
                cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (db_admin,))
                admin_hash = cur.fetchone()[0]
                
                cur.execute("CREATE DATABASE {} OWNER {};".format(db_name, db_admin))
                cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {};".format(db_name, db_user))
                cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {};".format(db_name, db_admin))
                
                grant_schema_permissions(db_name, db_user, db_admin)
                
                set_app_secret(app_name, "DB_USERNAME", db_user, "Database user for production", scope="production")
                set_app_secret(app_name, "DB_PASSWORD", db_user_password, "Database password for production", scope="production")
                set_app_secret(app_name, "DB_ADMIN_USERNAME", db_admin, "Database admin user for production", scope="production")
                set_app_secret(app_name, "DB_ADMIN_PASSWORD", db_admin_password, "Database admin password for production", scope="production")
                
                staging_db_name = None
                staging_user = None
                staging_admin = None
                staging_user_password = None
                staging_admin_password = None
                staging_user_hash = None
                staging_admin_hash = None
                
                if create_staging:
                    staging_db_name = f"{db_name}_staging"
                    staging_user = f"{app_name}_staging_user"
                    staging_admin = f"{app_name}_staging_admin"
                    staging_user_password = secrets.token_urlsafe(16)
                    staging_admin_password = secrets.token_urlsafe(16)
                    
                    cur.execute("CREATE USER {} WITH PASSWORD %s;".format(staging_user), (staging_user_password,))
                    cur.execute("CREATE USER {} WITH PASSWORD %s CREATEDB;".format(staging_admin), (staging_admin_password,))
                    
                    cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (staging_user,))
                    staging_user_hash = cur.fetchone()[0]
                    cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (staging_admin,))
                    staging_admin_hash = cur.fetchone()[0]
                    
                    cur.execute("CREATE DATABASE {} OWNER {};".format(staging_db_name, staging_admin))
                    cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {};".format(staging_db_name, staging_user))
                    cur.execute("GRANT ALL PRIVILEGES ON DATABASE {} TO {};".format(staging_db_name, staging_admin))
                    
                    grant_schema_permissions(staging_db_name, staging_user, staging_admin)
                    
                    set_app_secret(app_name, "STAGING_DB_USERNAME", staging_user, "Database user for staging", scope="staging")
                    set_app_secret(app_name, "STAGING_DB_PASSWORD", staging_user_password, "Database password for staging", scope="staging")
                    set_app_secret(app_name, "STAGING_DB_ADMIN_USERNAME", staging_admin, "Database admin user for staging", scope="staging")
                    set_app_secret(app_name, "STAGING_DB_ADMIN_PASSWORD", staging_admin_password, "Database admin password for staging", scope="staging")
                
                cur.close()
                conn.close()
                
                databases = load_databases()
                databases[db_name] = {
                    "name": db_name,
                    "description": app_description or f"{app_name} database",
                    "owner": db_admin,
                    "users": [
                        {"name": db_user, "password": db_user_password, "password_hash": user_hash, "roles": []},
                        {"name": db_admin, "password": db_admin_password, "password_hash": admin_hash, "roles": ["CREATEDB"]}
                    ],
                    "pgbouncer_pool_size": pool_size,
                    "pgbouncer_max_clients": pool_size * 10,
                    "app": app_name
                }
                
                if create_staging:
                    databases[staging_db_name] = {
                        "name": staging_db_name,
                        "description": f"{app_name} staging database",
                        "owner": staging_admin,
                        "users": [
                            {"name": staging_user, "password": staging_user_password, "password_hash": staging_user_hash, "roles": []},
                            {"name": staging_admin, "password": staging_admin_password, "password_hash": staging_admin_hash, "roles": ["CREATEDB"]}
                        ],
                        "pgbouncer_pool_size": pool_size,
                        "pgbouncer_max_clients": pool_size * 10,
                        "app": app_name,
                        "environment": "staging"
                    }
                
                save_databases(databases)
                
                results["created"].append(f"Database: {db_name}")
                results["created"].append(f"Users: {db_user}, {db_admin}")
                if create_staging:
                    results["created"].append(f"Staging database: {staging_db_name}")
                    results["created"].append(f"Staging users: {staging_user}, {staging_admin}")
                results["db_user"] = db_user
                results["db_user_password"] = db_user_password
                results["db_admin"] = db_admin
                results["db_admin_password"] = db_admin_password
                if create_staging:
                    results["staging_db_name"] = staging_db_name
                    results["staging_db_user"] = staging_user
                    results["staging_db_user_password"] = staging_user_password
                    results["staging_db_admin"] = staging_admin
                    results["staging_db_admin_password"] = staging_admin_password
                
            except Exception as e:
                results["errors"].append(f"Database creation failed: {str(e)}")
        
        port = get_next_port(app_name)
        
        if git_repo and deploy_now:
            results["clone_results"] = clone_repo_to_servers(app_name, git_repo, APP_SERVERS, GITHUB_TOKEN)
            clone_failed_all = True
            for r in results["clone_results"]:
                if r["status"] == "cloned":
                    results["created"].append(f"Cloned repo to {r['server']}")
                    clone_failed_all = False
                elif r["status"] == "exists":
                    results["created"].append(f"Repo directory exists on {r['server']}")
                    clone_failed_all = False
                else:
                    results["errors"].append(f"{r['server']}: {r['message']}")
            
            if clone_failed_all:
                if create_db:
                    try:
                        conn = psycopg2.connect(
                            host=PG_HOST, port=PG_PORT, user=PG_USER,
                            password=PG_PASSWORD, database="postgres"
                        )
                        conn.autocommit = True
                        cur = conn.cursor()
                        cur.execute("DROP DATABASE IF EXISTS {};".format(db_name))
                        cur.execute("DROP USER IF EXISTS {};".format(f"{app_name}_user"))
                        cur.execute("DROP USER IF EXISTS {};".format(f"{app_name}_admin"))
                        if create_staging:
                            cur.execute("DROP DATABASE IF EXISTS {};".format(f"{db_name}_staging"))
                            cur.execute("DROP USER IF EXISTS {};".format(f"{app_name}_staging_user"))
                            cur.execute("DROP USER IF EXISTS {};".format(f"{app_name}_staging_admin"))
                        cur.close()
                        conn.close()
                    except:
                        pass
                flash(f"Failed to clone repository to any server. Check the git URL and try again.", "error")
                return render_template("create_app_result.html", results=results, 
                    app_name=app_name, framework=framework, git_repo=git_repo,
                    target_servers=target_servers, staging_env=create_staging,
                    create_db=create_db, db_name=db_name, create_redis=create_redis,
                    workflow="", app_servers=APP_SERVERS,
                    webhook_secret="", webhook_base_url=get_webhook_base_url())
        
        pending_domains = build_domains_from_configs(domain_configs, enable_security)
        webhook_secret = secrets.token_urlsafe(32)
        
        redis_db = get_next_redis_db() if create_redis else None

        applications[app_name] = {
            "name": app_name,
            "description": app_description,
            "framework": framework,
            "git_repo": git_repo,
            "target_servers": target_servers,
            "staging_env": create_staging,
            "production_branch": production_branch,
            "staging_branch": staging_branch if create_staging else None,
            "database": db_name if create_db else None,
            "db_user": results.get("db_user") if create_db else None,
            "db_user_password": results.get("db_user_password") if create_db else None,
            "db_admin": results.get("db_admin") if create_db else None,
            "db_admin_password": results.get("db_admin_password") if create_db else None,
            "staging_database": results.get("staging_db_name") if create_staging else None,
            "staging_db_user": results.get("staging_db_user") if create_staging else None,
            "staging_db_user_password": results.get("staging_db_user_password") if create_staging else None,
            "staging_db_admin": results.get("staging_db_admin") if create_staging else None,
            "staging_db_admin_password": results.get("staging_db_admin_password") if create_staging else None,
            "redis_enabled": create_redis,
            "redis_db": redis_db,
            "port": port if framework == "laravel" else None,
            "domains": pending_domains,
            "production_domain": production_domain,
            "enable_security": enable_security,
            "github_webhook_secret": webhook_secret,
            "created_at": datetime.utcnow().isoformat(),
            "build_commands": {
                "install": request.form.get("install_cmd", ""),
                "build": request.form.get("build_cmd", ""),
                "migrate": request.form.get("migrate_cmd", ""),
                "start": request.form.get("start_cmd", "")
            }
        }
        save_applications(applications)
        results["created"].append(f"Application: {app_name}")
        
        workflow = generate_github_workflow(framework, app_name, target_servers, create_staging, create_db, db_name)
        applications[app_name]["deploy_workflow"] = workflow
        save_applications(applications)
        
        if create_db:
            db_user = results.get("db_user")
            db_user_password = results.get("db_user_password")
            db_admin = results.get("db_admin")
            db_admin_password = results.get("db_admin_password")
            
            if db_user and db_user_password:
                if not get_app_secret(app_name, "DB_USERNAME"):
                    set_app_secret(app_name, "DB_USERNAME", db_user, "Database user for production", scope="production")
                if not get_app_secret(app_name, "DB_PASSWORD"):
                    set_app_secret(app_name, "DB_PASSWORD", db_user_password, "Database password for production", scope="production")
            if db_admin and db_admin_password:
                if not get_app_secret(app_name, "DB_ADMIN_USERNAME"):
                    set_app_secret(app_name, "DB_ADMIN_USERNAME", db_admin, "Database admin user for production", scope="production")
                if not get_app_secret(app_name, "DB_ADMIN_PASSWORD"):
                    set_app_secret(app_name, "DB_ADMIN_PASSWORD", db_admin_password, "Database admin password for production", scope="production")
            
            if create_staging:
                staging_db_user = results.get("staging_db_user")
                staging_db_user_password = results.get("staging_db_user_password")
                staging_db_admin = results.get("staging_db_admin")
                staging_db_admin_password = results.get("staging_db_admin_password")
                
                if staging_db_user and staging_db_user_password:
                    if not get_app_secret(app_name, "STAGING_DB_USERNAME"):
                        set_app_secret(app_name, "STAGING_DB_USERNAME", staging_db_user, "Database user for staging", scope="staging")
                    if not get_app_secret(app_name, "STAGING_DB_PASSWORD"):
                        set_app_secret(app_name, "STAGING_DB_PASSWORD", staging_db_user_password, "Database password for staging", scope="staging")
                if staging_db_admin and staging_db_admin_password:
                    if not get_app_secret(app_name, "STAGING_DB_ADMIN_USERNAME"):
                        set_app_secret(app_name, "STAGING_DB_ADMIN_USERNAME", staging_db_admin, "Database admin user for staging", scope="staging")
                    if not get_app_secret(app_name, "STAGING_DB_ADMIN_PASSWORD"):
                        set_app_secret(app_name, "STAGING_DB_ADMIN_PASSWORD", staging_db_admin_password, "Database admin password for staging", scope="staging")
        
        if deploy_now:
            deploy_results = run_pull_deploy(app_name, branch="main", rolling=True)
            results["deploy_results"] = deploy_results
            if deploy_results.get("domains", {}).get("provisioned"):
                results["created"].append(f"Domains: {', '.join(deploy_results['domains']['provisioned'])}")
            if deploy_results.get("errors"):
                results["errors"].extend(deploy_results["errors"])
            
            if create_staging and deploy_results.get("success_flag"):
                staging_results = run_pull_deploy(app_name, branch=staging_branch, rolling=True)
                results["staging_deploy_results"] = staging_results
                if staging_results.get("errors"):
                    results["errors"].extend([f"Staging: {e}" for e in staging_results["errors"]])
        
        results["pull_deploy"] = True
        results["deploy_endpoint"] = f"/api/apps/{app_name}/deploy"
        results["webhook_endpoint"] = f"/api/webhooks/github/{app_name}"
        
        return render_template("create_app_result.html", results=results, 
            app_name=app_name, framework=framework, git_repo=git_repo,
            target_servers=target_servers, staging_env=create_staging,
            create_db=create_db, db_name=db_name, create_redis=create_redis,
            workflow=workflow, app_servers=APP_SERVERS, production_domain=production_domain,
            public_base_url=get_public_base_url(), webhook_secret=webhook_secret,
            webhook_base_url=get_webhook_base_url())
    
    cf_zones = []
    if CLOUDFLARE_API_TOKEN:
        cf_zones = cf_list_zones()
    
    applications = load_applications()
    reserved_domains = sorted(get_reserved_base_domains(applications).keys())
    return render_template("create_app.html", app_servers=APP_SERVERS, cf_zones=cf_zones,
        cf_configured=bool(CLOUDFLARE_API_TOKEN), reserved_domains=reserved_domains)


@app.route("/apps/<app_name>/delete", methods=["POST"])
@requires_auth
def delete_app(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    delete_db = request.form.get("delete_database") == "true"
    framework = app.get("framework", "")
    
    for server in APP_SERVERS:
        server_ip = server["ip"]
        
        if framework in ["nextjs", "svelte", "nodejs"]:
            ssh_command(server_ip, f"pm2 delete {app_name} 2>/dev/null || true")
            ssh_command(server_ip, f"pm2 delete {app_name}-staging 2>/dev/null || true")
        
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}")
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}-staging")
        
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}-staging")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}-staging")
        
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}.conf")
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}-staging.conf")
        
        ssh_command(server_ip, "systemctl reload nginx || true")
        ssh_command(server_ip, "systemctl reload php8.5-fpm || true")
    
    for domain in app.get("domains", []):
        domain_name = domain.get("name")
        if domain_name:
            remove_domain_from_routers(domain_name)
    
    if delete_db and app.get("database"):
        db_name = app["database"]
        cleanup = cleanup_database_artifacts(app_name=app_name, primary_db=db_name, include_primary=True, include_staging=True)
        if cleanup["errors"]:
            flash(f"Database cleanup completed with warnings: {'; '.join(cleanup['errors'])}", "warning")
        else:
            flash(f"Database '{db_name}' and staging artifacts deleted", "success")
    
    secrets_file = f"/opt/dashboard/secrets/{app_name}.yaml"
    if os.path.exists(secrets_file):
        try:
            os.remove(secrets_file)
        except Exception as e:
            flash(f"Warning: Failed to delete secrets file: {str(e)}", "warning")
    
    del applications[app_name]
    save_applications(applications)
    
    flash(f"Application '{app_name}' deleted completely", "success")
    return redirect(url_for("apps"))


@app.route("/apps/<app_name>/staging/delete", methods=["POST"])
@requires_auth
def delete_staging(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    framework = app.get("framework", "")
    
    for server in APP_SERVERS:
        server_ip = server["ip"]
        
        if framework in ["nextjs", "svelte", "nodejs"]:
            ssh_command(server_ip, f"pm2 delete {app_name}-staging 2>/dev/null || true")
        
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}-staging")
        
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}-staging")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}-staging")
        
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}-staging.conf")
        
        ssh_command(server_ip, "systemctl reload nginx || true")
        ssh_command(server_ip, "systemctl reload php8.5-fpm || true")
    
    staging_domains = [d for d in app.get("domains", []) if d.get("type") == "staging"]
    for domain in staging_domains:
        domain_name = domain.get("name")
        if domain_name:
            remove_domain_from_routers(domain_name)
    
    if app.get("database"):
        cleanup = cleanup_database_artifacts(
            app_name=app_name,
            primary_db=app["database"],
            include_primary=False,
            include_staging=True
        )
        if cleanup["errors"]:
            flash(f"Staging database cleanup warnings: {'; '.join(cleanup['errors'])}", "warning")
    
    app["domains"] = [d for d in app.get("domains", []) if d.get("type") != "staging"]
    applications[app_name] = app
    save_applications(applications)
    
    flash(f"Staging environment for '{app_name}' deleted", "success")
    return redirect(url_for("app_status", app_name=app_name))


def validate_github_signature(payload, signature_header, secret):
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def provision_pending_domains(app_name, app):
    if not CLOUDFLARE_API_TOKEN:
        return {"provisioned": [], "errors": ["Cloudflare not configured"]}

    app_port = app.get("port", 8100)
    domains = app.get("domains", [])
    zone_map = {z["name"]: z["id"] for z in cf_list_zones()}
    router_ips = [r["public_ip"] for r in ROUTERS]
    provisioned = []
    errors = []

    for domain in domains:
        if domain.get("type") == "www_redirect":
            continue
        if domain.get("status") == "provisioned":
            continue

        domain_name = domain.get("name")
        base_domain = domain.get("base_domain")
        zone_id = zone_map.get(base_domain)
        if not domain_name or not base_domain or not zone_id:
            domain["status"] = "failed"
            domain["error"] = "Zone not found in Cloudflare"
            errors.append(f"{domain_name}: zone not found")
            continue

        dns_label = domain.get("dns_label") or (domain_name[:-(len(base_domain) + 1)] if domain_name.endswith(f".{base_domain}") else "@")
        domain_type = domain.get("type", "production")

        if domain_type == "cname":
            records_result = cf_list_dns_records(zone_id)
            if records_result.get("success"):
                existing = [r for r in records_result.get("result", []) if r.get("name") == domain_name and r.get("type") in ["A", "CNAME"]]
                if existing:
                    domain["status"] = "failed"
                    domain["error"] = "Conflicting DNS record exists. Delete it in Cloudflare first."
                    errors.append(f"{domain_name}: conflicting DNS record exists")
                    continue

        dns_success = False
        if domain_type == "production" and domain.get("production_mode") == "root":
            root_result = cf_replace_a_records(base_domain, router_ips, zone_id)
            www_result = cf_replace_a_records(f"www.{base_domain}", router_ips, zone_id)
            dns_success = root_result.get("success") and www_result.get("success")
            ssl_results = provision_domain_on_routers(domain_name, app_name, app_port, www_domain=f"www.{base_domain}")
        else:
            dns_result = cf_replace_a_records(domain_name, router_ips, zone_id)
            dns_success = dns_result.get("success")
            if domain_type == "staging":
                staging_password = domain.get("password")
                ssl_results = provision_domain_on_routers(
                    domain_name, f"{app_name}-staging", get_staging_port(app_port), 
                    is_staging=True, staging_password=staging_password
                )
            elif domain_type == "cname":
                ssl_results = provision_domain_on_routers(domain_name, f"{app_name}-{dns_label}", app_port)
            else:
                ssl_results = provision_domain_on_routers(domain_name, app_name, app_port)

        ssl_errors = [f"{r.get('router')}: {r.get('error', 'SSL provisioning failed')}" for r in ssl_results if not r.get("success")]
        ssl_success = all(r.get("success") for r in ssl_results)
        all_success = dns_success and ssl_success

        domain["dns_provisioned"] = dns_success
        domain["provisioned"] = all_success
        domain["status"] = "provisioned" if all_success else "failed"
        if all_success:
            domain["error"] = ""
        elif not dns_success and not ssl_success:
            domain["error"] = "DNS and SSL provisioning failed"
        elif not dns_success:
            domain["error"] = "DNS provisioning failed"
        else:
            domain["error"] = "; ".join(ssl_errors) if ssl_errors else "SSL provisioning failed"
        domain["last_attempt_at"] = datetime.utcnow().isoformat()

        if all_success and domain.get("security_enabled"):
            cf_create_security_rules(domain_name, zone_id)

        if all_success and domain_type == "production" and domain.get("production_mode") == "root":
            update_app_url(app_name, f"https://{domain_name}")

        if all_success:
            provisioned.append(domain_name)
        else:
            errors.append(f"{domain_name}: {domain.get('error')}")

    app["domains"] = domains
    return {"provisioned": provisioned, "errors": errors}


def check_domain_http_health(domain_name, domain_type, max_retries=3, retry_delay=5):
    url = f"https://{domain_name}"
    last_status = 0
    last_error = None
    
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, timeout=15, allow_redirects=True)
            status_code = resp.status_code
            
            if status_code == 403:
                last_status = status_code
                last_error = "Cloudflare WAF or SSL mode issue (403)"
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
            
            if domain_type == "staging":
                healthy = status_code in [200, 401]
            else:
                healthy = status_code == 200
            return {"success": healthy, "status_code": status_code, "url": url}
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    
    return {"success": False, "status_code": last_status, "url": url, "error": last_error or f"HTTP {last_status}"}


def check_local_app_health(server_ip, app_port):
    cmd = f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{app_port} 2>/dev/null || echo '000'"
    result = ssh_command(server_ip, cmd, timeout=20)
    code = (result.get("stdout") or "000").strip()
    return code in ["200", "301", "302"], code


def summarize_command_error(result, max_len=500):
    ansi_re = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

    def clean(text):
        text = ansi_re.sub("", text or "")
        text = text.replace("\r", "\n")
        return text.strip()

    stderr = clean(result.get("stderr") or "")
    if stderr:
        return stderr[-max_len:]

    stdout = clean(result.get("stdout") or "")
    if stdout:
        lines = [line for line in stdout.splitlines() if line.strip()]
        if not lines:
            return stdout[-max_len:]
        priority_patterns = [
            r"unable to locate",
            r"error",
            r"exception",
            r"failed",
            r"traceback",
            r"in .* line"
        ]
        important = [line for line in lines if any(re.search(p, line, re.IGNORECASE) for p in priority_patterns)]
        selected = important[-6:] if important else lines[-8:]
        tail = "\n".join(selected)
        return tail[-max_len:]

    return "Unknown error"


def update_last_deploy_status(app, results):
    app["last_deploy"] = {
        "at": datetime.utcnow().isoformat(),
        "success": bool(results.get("success_flag")),
        "errors": results.get("errors", []),
        "phases": results.get("phases", {}),
        "aborted": bool(results.get("aborted")),
        "message": results.get("message", ""),
        "branch": results.get("branch", "main"),
        "environment": results.get("environment", "production"),
    }
    app["last_deploy_status"] = "success" if results.get("success_flag") else "failed"
    app["last_deploy_at"] = app["last_deploy"]["at"]
    app["last_deploy_branch"] = results.get("branch", "main")
    app["last_deploy_environment"] = results.get("environment", "production")


def rollback_server_to_commit(server_ip, deploy_target_name, commit_sha, branch="main", environment="production"):
    if not commit_sha:
        return {"success": False, "error": "No rollback commit available"}
    cmd = f"cd /opt/apps/{deploy_target_name} && git reset --hard {commit_sha} && /opt/scripts/deploy-app.sh {deploy_target_name} {branch} {environment}"
    result = ssh_command(server_ip, cmd, timeout=600)
    return {"success": result.get("success", False), "error": result.get("stderr", "")}


def run_pull_deploy(app_name, branch="main", rolling=True):
    applications = load_applications()
    if app_name not in applications:
        return {"success": False, "error": "Application not found", "status_code": 404}

    app = applications[app_name]
    production_branch = app.get("production_branch", "main")
    staging_branch = app.get("staging_branch", "staging")
    
    if branch == production_branch:
        deploy_environment = "production"
    elif branch == staging_branch:
        deploy_environment = "staging"
    else:
        return {
            "success_flag": True,
            "ignored": True,
            "message": f"Branch '{branch}' ignored (only '{production_branch}' and '{staging_branch}' deploy)",
            "branch": branch,
        }

    if deploy_environment == "staging" and not app.get("staging_env"):
        return {
            "success_flag": False,
            "errors": ["Staging deploy requested but staging environment is not enabled for this app"],
            "status_code": 400,
        }

    deploy_target_name = get_deploy_target_name(app_name, deploy_environment)
    now = datetime.utcnow().isoformat()
    results = {
        "servers": {},
        "errors": [],
        "success": [],
        "rolling": rolling,
        "branch": branch,
        "environment": deploy_environment,
        "deploy_target": deploy_target_name,
        "phases": {
            "deploy": {"status": "pending", "started_at": now},
            "domain_provisioning": {"status": "pending"}
        }
    }
    app_port = app.get("port", 8100)
    if deploy_environment == "staging":
        app_port = get_staging_port(app_port)
    server_commits = app.get("server_commits", {})

    git_repo = app.get("git_repo")
    if git_repo:
        clone_results = clone_repo_to_servers(deploy_target_name, git_repo, APP_SERVERS, GITHUB_TOKEN)
        if not any(r.get("status") in ["cloned", "exists"] for r in clone_results):
            results["errors"].append("Failed to clone repository to app servers")
            results["clone_results"] = clone_results
            results["phases"]["deploy"]["status"] = "failed"
            results["phases"]["deploy"]["completed_at"] = datetime.utcnow().isoformat()
            results["phases"]["domain_provisioning"] = {
                "status": "skipped",
                "reason": "Deploy phase failed"
            }
            results["success_flag"] = False
            update_last_deploy_status(app, results)
            applications[app_name] = app
            save_applications(applications)
            return results
        for r in clone_results:
            if r.get("status") in ["cloned", "exists"]:
                results["success"].append(f"{r['server']} clone: {r['status']}")

    env_sync = write_runtime_env_to_servers(
        app_name,
        app,
        APP_SERVERS,
        environment=deploy_environment,
        deploy_target_name=deploy_target_name,
    )
    results["env_materialization"] = env_sync.get("servers", {})
    if not env_sync.get("success"):
        results["errors"].extend(env_sync.get("errors", []))
        results["phases"]["deploy"]["status"] = "failed"
        results["phases"]["deploy"]["completed_at"] = datetime.utcnow().isoformat()
        results["phases"]["domain_provisioning"] = {
            "status": "skipped",
            "reason": "Deploy phase failed"
        }
        results["success_flag"] = False
        update_last_deploy_status(app, results)
        applications[app_name] = app
        save_applications(applications)
        return results
    for server_name, status in env_sync.get("servers", {}).items():
        if status == "written":
            results["success"].append(f"{server_name} env: written")

    framework = app.get("framework", "")
    if framework == "laravel":
        for server in APP_SERVERS:
            pool_check = ssh_command(server["ip"], f"test -f /etc/php/8.5/fpm/pool.d/{deploy_target_name}.conf && echo exists", timeout=10)
            if "exists" not in (pool_check.get("stdout") or ""):
                setup_result = setup_laravel_app(deploy_target_name, server["ip"], app_port)
                if not setup_result.get("success"):
                    results["errors"].append(f"{server['name']}: Laravel setup failed - {setup_result.get('error', 'unknown error')}")
                    results["phases"]["deploy"]["status"] = "failed"
                    results["phases"]["deploy"]["completed_at"] = datetime.utcnow().isoformat()
                    results["phases"]["domain_provisioning"] = {"status": "skipped", "reason": "Deploy phase failed"}
                    results["success_flag"] = False
                    update_last_deploy_status(app, results)
                    applications[app_name] = app
                    save_applications(applications)
                    return results
                results["success"].append(f"{server['name']}: Laravel nginx+php-fpm configured")

    primary_server = APP_SERVERS[0]
    secondary_servers = APP_SERVERS[1:]
    deploy_cmd = f"/opt/scripts/deploy-app.sh {deploy_target_name} {branch} {deploy_environment} 2>&1"

    primary_before = ssh_command(primary_server["ip"], f"cd /opt/apps/{deploy_target_name} && git rev-parse HEAD", timeout=30)
    primary_before_commit = (primary_before.get("stdout") or "").strip()

    result = ssh_command(primary_server["ip"], deploy_cmd, timeout=600)
    primary_healthy = False
    primary_health_code = "000"
    if result.get("success"):
        primary_healthy, primary_health_code = check_local_app_health(primary_server["ip"], app_port)

    results["servers"][primary_server["name"]] = {
        "success": result["success"] and primary_healthy,
        "output": result["stdout"][-2000:] if result["stdout"] else "",
        "error": result["stderr"][-500:] if result.get("stderr") else None,
        "health_code": primary_health_code,
        "role": "primary"
    }

    if result["success"] and primary_healthy:
        results["success"].append(primary_server["name"])
        for server in secondary_servers:
            before = ssh_command(server["ip"], f"cd /opt/apps/{deploy_target_name} && git rev-parse HEAD", timeout=30)
            before_commit = (before.get("stdout") or "").strip()

            result = ssh_command(server["ip"], deploy_cmd, timeout=600)
            secondary_healthy = False
            secondary_health_code = "000"
            if result.get("success"):
                secondary_healthy, secondary_health_code = check_local_app_health(server["ip"], app_port)

            results["servers"][server["name"]] = {
                "success": result["success"] and secondary_healthy,
                "output": result["stdout"][-2000:] if result["stdout"] else "",
                "error": result["stderr"][-500:] if result.get("stderr") else None,
                "health_code": secondary_health_code,
                "role": "secondary"
            }

            if result["success"] and secondary_healthy:
                results["success"].append(server["name"])
                after = ssh_command(server["ip"], f"cd /opt/apps/{deploy_target_name} && git rev-parse HEAD", timeout=30)
                server_commits[server["name"]] = (after.get("stdout") or before_commit).strip()
            else:
                if result.get("success") and not secondary_healthy:
                    if before_commit:
                        rb = rollback_server_to_commit(server["ip"], deploy_target_name, before_commit, branch=branch, environment=deploy_environment)
                        rb_note = " (rollback ok)" if rb.get("success") else f" (rollback failed: {rb.get('error', '')[-120:]})"
                        results["errors"].append(f"{server['name']}: health check failed ({secondary_health_code}){rb_note}")
                    else:
                        results["errors"].append(
                            f"{server['name']}: health check failed ({secondary_health_code}) (initial deploy failed; rollback unavailable - no known-good commit)"
                        )
                else:
                    results["errors"].append(f"{server['name']}: {summarize_command_error(result)}")
    else:
        if result.get("success") and not primary_healthy:
            if primary_before_commit:
                rb = rollback_server_to_commit(primary_server["ip"], deploy_target_name, primary_before_commit, branch=branch, environment=deploy_environment)
                rb_note = " (rollback ok)" if rb.get("success") else f" (rollback failed: {rb.get('error', '')[-120:]})"
                results["errors"].append(f"{primary_server['name']}: health check failed ({primary_health_code}){rb_note}")
            else:
                results["errors"].append(
                    f"{primary_server['name']}: health check failed ({primary_health_code}) (initial deploy failed; rollback unavailable - no known-good commit)"
                )
        else:
            results["errors"].append(f"{primary_server['name']}: {summarize_command_error(result)}")
        results["aborted"] = True
        if not primary_before_commit:
            results["message"] = "Rolling deployment aborted - primary failed (initial deployment, rollback unavailable)"
        else:
            results["message"] = "Rolling deployment aborted - primary failed"

    if len(results["errors"]) == 0:
        results["phases"]["deploy"]["status"] = "success"
    else:
        results["phases"]["deploy"]["status"] = "failed"
    results["phases"]["deploy"]["completed_at"] = datetime.utcnow().isoformat()

    # Re-grant database permissions after migrations for Laravel apps
    # This ensures the app user has access to all newly created tables
    if len(results["errors"]) == 0 and framework == "laravel":
        regrant_result = regrant_app_db_permissions(app_name, deploy_environment)
        if regrant_result.get("success"):
            results["success"].append(f"Database permissions re-granted for {deploy_environment}")
        else:
            # Log warning but don't fail deployment - permissions were likely already correct
            results["errors"].append(f"Database permissions warning: {regrant_result.get('error', 'unknown error')}")

    if len(results["errors"]) == 0:
        if deploy_environment == "production":
            domain_results = provision_pending_domains(app_name, app)
            results["domains"] = domain_results
            if domain_results.get("provisioned"):
                results["success"].append(f"Domains provisioned: {', '.join(domain_results['provisioned'])}")
            if domain_results.get("errors"):
                results["errors"].extend(domain_results["errors"])

            if domain_results.get("errors"):
                results["phases"]["domain_provisioning"] = {
                    "status": "failed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "provisioned": domain_results.get("provisioned", []),
                    "errors": domain_results.get("errors", [])
                }
            else:
                results["phases"]["domain_provisioning"] = {
                    "status": "success",
                    "completed_at": datetime.utcnow().isoformat(),
                    "provisioned": domain_results.get("provisioned", [])
                }
        else:
            results["phases"]["domain_provisioning"] = {
                "status": "skipped",
                "reason": "Staging deploy does not run domain provisioning"
            }
    else:
        results["phases"]["domain_provisioning"] = {
            "status": "skipped",
            "reason": "Deploy phase failed"
        }

    if len(results["errors"]) == 0:
        domain_health = []
        for domain in app.get("domains", []):
            if domain.get("status") != "provisioned":
                continue
            
            domain_type = domain.get("type")
            if domain_type not in ["production", "staging"]:
                continue
            
            if deploy_environment == "production" and domain_type != "production":
                continue
            if deploy_environment == "staging" and domain_type != "staging":
                continue
            
            check = check_domain_http_health(domain.get("name"), domain_type)
            domain_health.append({"domain": domain.get("name"), **check})
            if not check.get("success"):
                results["errors"].append(f"{domain.get('name')}: domain health check failed ({check.get('status_code')})")
        if domain_health:
            results["domain_health"] = domain_health

    if len(results["errors"]) == 0:
        for server in APP_SERVERS:
            commit = ssh_command(server["ip"], f"cd /opt/apps/{deploy_target_name} && git rev-parse HEAD", timeout=30)
            commit_sha = (commit.get("stdout") or "").strip()
            if commit_sha:
                server_commits[server["name"]] = commit_sha

    app["server_commits"] = server_commits
    results["success_flag"] = len(results["errors"]) == 0
    update_last_deploy_status(app, results)
    applications[app_name] = app
    save_applications(applications)

    return results


@app.route("/api/apps/<app_name>/deploy", methods=["POST"])
@requires_auth
def api_pull_deploy(app_name):
    branch = request.json.get("branch", "main") if request.is_json else "main"
    rolling = request.json.get("rolling", True) if request.is_json else True
    results = run_pull_deploy(app_name, branch=branch, rolling=rolling)
    if results.get("status_code"):
        return jsonify(results), results["status_code"]
    return jsonify(results)


@app.route("/api/apps/<app_name>/redeploy", methods=["POST"])
@requires_auth
def api_redeploy(app_name):
    branch = request.json.get("branch", "main") if request.is_json else "main"
    results = run_pull_deploy(app_name, branch=branch, rolling=True)
    status = 200 if results.get("success_flag") else 500
    return jsonify(results), status


@app.route("/api/apps/<app_name>/rollback", methods=["POST"])
@requires_auth
def api_rollback(app_name):
    applications = load_applications()
    app = applications.get(app_name)
    if not app:
        return jsonify({"success": False, "error": "Application not found"}), 404

    commits = app.get("server_commits", {})
    results = {"success": [], "errors": [], "servers": {}}
    app_port = app.get("port", 8100)

    for server in APP_SERVERS:
        commit = commits.get(server["name"])
        rb = rollback_server_to_commit(server["ip"], app_name, commit)
        healthy, code = check_local_app_health(server["ip"], app_port)
        ok = rb.get("success") and healthy
        results["servers"][server["name"]] = {
            "success": ok,
            "rollback_success": rb.get("success"),
            "health_code": code,
            "commit": commit
        }
        if ok:
            results["success"].append(f"{server['name']} rolled back to {commit[:8]}")
        else:
            results["errors"].append(f"{server['name']} rollback failed")

    results["success_flag"] = len(results["errors"]) == 0
    status = 200 if results["success_flag"] else 500
    return jsonify(results), status


@app.route("/api/apps/<app_name>/deploy-async", methods=["POST"])
@requires_auth
def api_deploy_async(app_name):
    """Start an async deployment with real-time progress tracking."""
    if not WEBSOCKET_AVAILABLE:
        return jsonify({"success": False, "error": "WebSocket support not available"}), 503
    
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database not available"}), 503
    
    applications = load_applications()
    app = applications.get(app_name)
    if not app:
        return jsonify({"success": False, "error": "Application not found"}), 404
    
    data = request.json or {}
    branch = data.get("branch", "main")
    environment = data.get("environment", "production")
    commit = data.get("commit")
    
    app_id = paas_db.get_setting(f'app_id_{app_name}')
    if not app_id:
        app_id = paas_db.generate_id()
        paas_db.set_setting(f'app_id_{app_name}', app_id)
    
    deployment_id = paas_db.create_deployment(app_id, environment, branch, commit)
    
    for server in APP_SERVERS:
        for step_info in paas_db.DEPLOYMENT_STEPS if hasattr(paas_db, 'DEPLOYMENT_STEPS') else []:
            paas_db.create_deployment_step(deployment_id, server["name"], step_info)
    
    task = deploy_application_task.delay(deployment_id, app_name, environment, branch, commit)
    
    return jsonify({
        "success": True,
        "deployment_id": deployment_id,
        "task_id": task.id,
        "message": f"Deployment started for {app_name}",
        "websocket_room": f"deployment:{deployment_id}"
    }), 202


@app.route("/api/deployments/<deployment_id>")
@requires_auth
def api_get_deployment_status(deployment_id):
    """Get deployment status and progress."""
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database not available"}), 503
    
    deployment = paas_db.get_deployment(deployment_id)
    if not deployment:
        return jsonify({"success": False, "error": "Deployment not found"}), 404
    
    progress = paas_db.get_deployment_progress(deployment_id) if hasattr(paas_db, 'get_deployment_progress') else {}
    steps = paas_db.get_deployment_steps(deployment_id) if hasattr(paas_db, 'get_deployment_steps') else []
    
    return jsonify({
        "success": True,
        "deployment": deployment,
        "progress": progress,
        "steps": steps
    })


@app.route("/api/deployments/<deployment_id>/cancel", methods=["POST"])
@requires_auth
def api_cancel_deployment(deployment_id):
    """Cancel a running deployment."""
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database not available"}), 503
    
    deployment = paas_db.get_deployment(deployment_id)
    if not deployment:
        return jsonify({"success": False, "error": "Deployment not found"}), 404
    
    if deployment.get("status") not in ["pending", "running"]:
        return jsonify({"success": False, "error": "Deployment already completed"}), 400
    
    paas_db.update_deployment(deployment_id, {
        "status": "cancelled",
        "finished_at": datetime.utcnow().isoformat()
    })
    
    if WEBSOCKET_AVAILABLE:
        emit_progress(deployment_id, "deployment_cancelled", {
            "timestamp": datetime.utcnow().isoformat()
        })
    
    return jsonify({"success": True, "message": "Deployment cancelled"})


@app.route("/api/deployments/<deployment_id>/logs")
@requires_auth
def api_deployment_logs(deployment_id):
    """Get deployment logs."""
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database not available"}), 503
    
    steps = paas_db.get_deployment_steps(deployment_id) if hasattr(paas_db, 'get_deployment_steps') else []
    
    logs = []
    for step in steps:
        logs.append({
            "server": step.get("server"),
            "step": step.get("step"),
            "status": step.get("status"),
            "output": step.get("output", ""),
            "started_at": step.get("started_at"),
            "finished_at": step.get("finished_at")
        })
    
    return jsonify({
        "success": True,
        "deployment_id": deployment_id,
        "logs": logs
    })


@app.route("/api/websocket/health")
def api_websocket_health():
    """WebSocket health check endpoint."""
    return jsonify({
        "websocket_available": WEBSOCKET_AVAILABLE,
        "paas_db_available": PAAS_DB_AVAILABLE,
        "status": "healthy" if WEBSOCKET_AVAILABLE else "unavailable"
    })


@app.route("/api/apps/<app_name>/regrant-permissions", methods=["POST"])
@requires_auth
def api_regrant_permissions(app_name):
    """Manually re-grant database permissions for an app.
    
    Useful for fixing permission issues without redeploying.
    Can target specific environment with ?environment=staging
    """
    environment = request.args.get("environment", "production")
    result = regrant_app_db_permissions(app_name, environment=environment)
    status = 200 if result.get("success") else 400
    return jsonify(result), status


@app.route("/api/apps/<app_name>/domains/force-provision", methods=["POST"])
@requires_auth
def api_force_provision_domains(app_name):
    applications = load_applications()
    app = applications.get(app_name)
    if not app:
        return jsonify({"success": False, "error": "Application not found"}), 404

    pending = [d for d in app.get("domains", []) if d.get("status") != "provisioned" and d.get("type") != "www_redirect"]
    if not pending:
        return jsonify({
            "success": True,
            "message": "No pending domains to provision",
            "provisioned": [],
            "errors": []
        }), 200

    lock_path = f"/tmp/dashboard-force-provision-{app_name}.lock"
    if os.path.exists(lock_path):
        stale = False
        try:
            lock_age = int(datetime.utcnow().timestamp() - os.path.getmtime(lock_path))
            with open(lock_path, "r") as fh:
                pid_text = (fh.read() or "").strip()
            lock_pid = int(pid_text) if pid_text else 0
            if lock_age > 1800:
                stale = True
            elif lock_pid:
                try:
                    os.kill(lock_pid, 0)
                except OSError:
                    stale = True
            else:
                stale = True
        except Exception:
            stale = True

        if stale:
            try:
                os.remove(lock_path)
            except Exception:
                pass
        else:
            return jsonify({"success": False, "error": "Force provisioning already in progress"}), 409

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
    except FileExistsError:
        return jsonify({"success": False, "error": "Force provisioning already in progress"}), 409

    try:
        result = provision_pending_domains(app_name, app)
        applications[app_name] = app
        save_applications(applications)
    finally:
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

    success = len(result.get("errors", [])) == 0
    return jsonify({
        "success": success,
        "provisioned": result.get("provisioned", []),
        "errors": result.get("errors", []),
        "pending_count": len([d for d in app.get("domains", []) if d.get("status") != "provisioned" and d.get("type") != "www_redirect"])
    }), (200 if success else 500)


import threading
from functools import wraps

def run_in_thread(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=f, args=args, kwargs=kwargs)
        thread.daemon = True
        thread.start()
    return wrapper


@app.route("/api/webhooks/github/<app_name>", methods=["POST"])
@app.route("/<app_name>", methods=["POST"])
def github_webhook_deploy(app_name):
    incoming_host = (request.host or "").split(":")[0].lower()
    if incoming_host != WEBHOOK_PUBLIC_HOST.lower():
        return jsonify({"success": False, "error": "Not found"}), 404

    applications = load_applications()
    app = applications.get(app_name)
    if not app:
        return jsonify({"success": False, "error": "Application not found"}), 404

    webhook_secret = app.get("github_webhook_secret", "")
    signature = request.headers.get("X-Hub-Signature-256", "")
    payload = request.get_data() or b""

    if not validate_github_signature(payload, signature, webhook_secret):
        return jsonify({"success": False, "error": "Invalid webhook signature"}), 403

    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return jsonify({"success": True, "message": "pong"})
    if event != "push":
        return jsonify({"success": True, "ignored": True, "event": event})

    body = request.get_json(silent=True) or {}
    ref = body.get("ref", "")
    branch = ref.split("/")[-1] if ref.startswith("refs/heads/") else "main"

    applications = load_applications()
    app = applications.get(app_name, {})
    production_branch = app.get("production_branch", "main")
    staging_branch = app.get("staging_branch", "staging")

    if branch not in [production_branch, staging_branch]:
        return jsonify({
            "success": True,
            "ignored": True,
            "branch": branch,
            "message": f"Branch ignored (only {production_branch} and {staging_branch} trigger deploy)",
        }), 200

    @run_in_thread
    def run_deploy_async():
        run_pull_deploy(app_name, branch=branch, rolling=True)
    
    run_deploy_async()
    
    return jsonify({
        "success": True,
        "message": "Deploy started",
        "branch": branch,
        "environment": "staging" if branch == staging_branch else "production"
    }), 202


@app.route("/apps/<app_name>/deploy", methods=["GET", "POST"])
@requires_auth
def deploy_app(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    
    if request.method == "POST":
        selected_servers = request.form.getlist("servers")
        force_reclone = "force_reclone" in request.form
        restart_service = "restart_service" in request.form
        
        if not selected_servers:
            flash("Select at least one server", "error")
            return redirect(url_for("deploy_app", app_name=app_name))
        
        results = {"errors": [], "success": [], "servers": {}}
        
        target_servers = [s for s in APP_SERVERS if s["name"] in selected_servers]
        
        git_repo = app.get("git_repo")
        framework = app.get("framework", "go")
        
        db_url = None
        redis_url = None
        db_name = app.get("database")
        
        if db_name:
            databases = load_databases()
            if db_name in databases:
                db_admin = databases[db_name].get("owner", f"{app_name}_admin")
                for user in databases[db_name].get("users", []):
                    if user.get("name") == db_admin:
                        db_password = "RETRIEVED_FROM_CONFIG"
                        db_url = f"postgres://{db_admin}:RETRIEVED@{PG_HOST}:6432/{db_name}"
                        break
        
        if force_reclone and git_repo:
            for server in target_servers:
                app_dir = f"/opt/apps/{app_name}"
                rm_result = ssh_command(server["ip"], f"rm -rf {app_dir}")
                if rm_result["success"]:
                    results["success"].append(f"Removed {app_dir} on {server['name']}")
                else:
                    results["errors"].append(f"Failed to remove {app_dir} on {server['name']}")
        
        if git_repo:
            clone_results = clone_repo_to_servers(app_name, git_repo, target_servers, GITHUB_TOKEN)
            for r in clone_results:
                server_name = r["server"]
                results["servers"][server_name] = {"clone": r["status"]}
                if r["status"] in ["cloned", "exists"]:
                    results["success"].append(f"Clone on {server_name}: {r['status']}")
                else:
                    results["errors"].append(f"Clone on {server_name}: {r['message']}")
            
            db_config = None
            redis_config = None
            if db_name:
                databases = load_databases()
                if db_name in databases:
                    db_admin = databases[db_name].get("owner", f"{app_name}_admin")
                    for user in databases[db_name].get("users", []):
                        if user.get("name") == db_admin:
                            db_password = user.get("password", "")
                            db_config = {
                                "host": PG_HOST,
                                "port": str(PG_PORT),
                                "database": db_name,
                                "username": db_admin,
                                "password": db_password
                            }
                            break
            
            if app.get("redis_enabled"):
                redis_config = {
                    "host": REDIS_HOST,
                    "port": str(REDIS_PORT),
                    "password": REDIS_PASSWORD,
                    "db": app.get("redis_db", 0)
                }
            
            app_url = None
            domains = app.get("domains", [])
            for d in domains:
                if d.get("type") == "production" and d.get("name"):
                    app_url = f"https://{d['name']}"
                    break
            
            setup_results = run_framework_setup(app_name, framework, target_servers, db_config, redis_config, app_url)
            for r in setup_results:
                server_name = r["server"]
                if server_name not in results["servers"]:
                    results["servers"][server_name] = {}
                results["servers"][server_name]["setup"] = r["status"]
                if r["status"] in ["composer_installed", "npm_installed", "built", "venv_created"]:
                    results["success"].append(f"Setup on {server_name}: {r.get('output', r['status'])}")
                else:
                    results["errors"].append(f"Setup on {server_name}: {r.get('message', 'Unknown error')}")

        env_sync = write_runtime_env_to_servers(app_name, app, target_servers, environment="production")
        results["env_materialization"] = env_sync.get("servers", {})
        if env_sync.get("success"):
            for server_name, status in env_sync.get("servers", {}).items():
                if status == "written":
                    results["success"].append(f"Env on {server_name}: written")
        else:
            results["errors"].extend(env_sync.get("errors", []))
            return render_template("deploy_result.html",
                app_name=app_name,
                app=app,
                results=results,
                selected_servers=selected_servers)

        env_vars = {
            "APP_NAME": app_name,
            "APP_ENV": "production",
            "NODE_ENV": "production"
        }
        
        for server in target_servers:
            svc_result = create_systemd_service(app_name, framework, server["ip"], db_url, redis_url, env_vars)
            if server["name"] not in results["servers"]:
                results["servers"][server["name"]] = {}
            results["servers"][server["name"]]["systemd"] = "created" if svc_result["success"] else "failed"
            
            if svc_result["success"]:
                results["success"].append(f"Systemd service on {server['name']}")
            else:
                results["errors"].append(f"Systemd on {server['name']}: {svc_result['stderr']}")
            
            if restart_service:
                restart_result = ssh_command(server["ip"], f"systemctl restart {app_name} || systemctl start {app_name}")
                results["servers"][server["name"]]["restart"] = "ok" if restart_result["success"] else "failed"
        
        return render_template("deploy_result.html",
            app_name=app_name,
            app=app,
            results=results,
            selected_servers=selected_servers)
    
    server_status = {}
    for server in APP_SERVERS:
        check = ssh_command(server["ip"], f"test -d /opt/apps/{app_name} && echo exists || echo missing")
        status_check = ssh_command(server["ip"], f"systemctl is-active {app_name} 2>/dev/null || echo inactive")
        server_status[server["name"]] = {
            "ip": server["ip"],
            "public_ip": server.get("public_ip", ""),
            "cloned": "exists" in check.get("stdout", ""),
            "service_status": status_check.get("stdout", "").strip()
        }
    
    return render_template("deploy_app.html",
        app_name=app_name,
        app=app,
        app_servers=APP_SERVERS,
        server_status=server_status)


@app.route("/apps/<app_name>/status")
@requires_auth
def app_status(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    framework = app.get("framework", "laravel")
    app_port = app.get("port", 8100)
    pending_domain_count = len([d for d in app.get("domains", []) if d.get("status") != "provisioned" and d.get("type") != "www_redirect"])
    
    server_status = {}
    for server in APP_SERVERS:
        cloned_check = ssh_command(server["ip"], f"test -d /opt/apps/{app_name} && echo exists || echo missing")
        
        nginx_status = ssh_command(server["ip"], "systemctl is-active nginx 2>/dev/null || echo inactive")
        phpfpm_status = ssh_command(server["ip"], "systemctl is-active php8.5-fpm 2>/dev/null || echo inactive")
        
        app_active_check = ssh_command(server["ip"], f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{app_port} 2>/dev/null || echo '000'")
        app_http_code = app_active_check.get("stdout", "000").strip()
        app_active = app_http_code not in ["000", "502", "503"]
        
        logs_result = ssh_command(server["ip"], f"tail -n 20 /var/log/nginx/error.log 2>/dev/null || echo 'No logs available'")
        
        server_status[server["name"]] = {
            "ip": server["ip"],
            "public_ip": server.get("public_ip", ""),
            "cloned": "exists" in cloned_check.get("stdout", ""),
            "nginx_status": nginx_status.get("stdout", "").strip(),
            "phpfpm_status": phpfpm_status.get("stdout", "").strip(),
            "app_active": app_active,
            "app_http_code": app_http_code,
            "logs": logs_result.get("stdout", "Unable to fetch logs")
        }
    
    return render_template("app_status.html",
        app_name=app_name,
        app=app,
        app_servers=APP_SERVERS,
        server_status=server_status,
        webhook_base_url=get_webhook_base_url(),
        pending_domain_count=pending_domain_count,
        last_deploy=app.get("last_deploy", {}),
        pg_host=PG_HOST,
        pg_port=PG_PORT,
        redis_host=REDIS_HOST,
        redis_port=REDIS_PORT)


@app.route("/api/apps/<app_name>/restart", methods=["POST"])
@requires_auth
def api_restart_app(app_name):
    data = request.get_json() or {}
    server_ip = data.get("server")
    
    applications = load_applications()
    if app_name not in applications:
        return jsonify({"success": False, "error": "App not found"})
    
    app = applications[app_name]
    framework = app.get("framework", "laravel")
    
    if framework == "laravel":
        result = ssh_command(server_ip, "systemctl reload nginx && systemctl reload php8.5-fpm")
    else:
        result = ssh_command(server_ip, "systemctl reload nginx")
    
    return jsonify({"success": result.get("returncode", 1) == 0, "error": result.get("stderr", "")})


@app.route("/api/apps/<app_name>/reload-nginx", methods=["POST"])
@requires_auth
def api_reload_nginx(app_name):
    data = request.get_json() or {}
    server_ip = data.get("server")
    
    result = ssh_command(server_ip, "systemctl reload nginx")
    return jsonify({"success": result.get("returncode", 1) == 0, "error": result.get("stderr", "")})


@app.route("/api/apps/<app_name>/reload-phpfpm", methods=["POST"])
@requires_auth
def api_reload_phpfpm(app_name):
    data = request.get_json() or {}
    server_ip = data.get("server")
    
    result = ssh_command(server_ip, "systemctl reload php8.5-fpm")
    return jsonify({"success": result.get("returncode", 1) == 0, "error": result.get("stderr", "")})


@app.route("/api/apps/<app_name>/clear-cache", methods=["POST"])
@requires_auth
def api_clear_cache(app_name):
    data = request.get_json() or {}
    server_ip = data.get("server")
    
    applications = load_applications()
    if app_name not in applications:
        return jsonify({"success": False, "error": "App not found"})
    
    app = applications[app_name]
    framework = app.get("framework", "laravel")
    
    if framework == "laravel":
        result = ssh_command(server_ip, f"cd /opt/apps/{app_name} && php artisan cache:clear && php artisan config:clear && php artisan view:clear")
    else:
        return jsonify({"success": False, "error": "Cache clear not supported for this framework"})
    
    return jsonify({
        "success": result.get("returncode", 1) == 0, 
        "error": result.get("stderr", ""),
        "output": result.get("stdout", "")
    })


@app.route("/api/apps/<app_name>/run-seeds", methods=["POST"])
@requires_auth
def api_run_seeds(app_name):
    data = request.get_json() or {}
    seeder_class = data.get("class", "")
    environment = data.get("environment", "production")
    
    applications = load_applications()
    if app_name not in applications:
        return jsonify({"success": False, "error": "App not found"})
    
    app = applications[app_name]
    framework = app.get("framework", "laravel")
    
    if framework != "laravel":
        return jsonify({"success": False, "error": "Seeds only supported for Laravel apps"})
    
    target_servers = app.get("target_servers", [])
    if not target_servers:
        return jsonify({"success": False, "error": "No target servers configured"})
    
    app_dir = f"/opt/apps/{app_name}"
    if environment == "staging" and app.get("staging_env"):
        app_dir = f"/opt/apps/{app_name}-staging"
    
    seed_cmd = "php artisan db:seed --force"
    if seeder_class:
        seed_cmd += f" --class={seeder_class}"
    
    results = {}
    all_success = True
    primary_server = target_servers[0] if target_servers else None
    
    for server_name in target_servers:
        server_ip = None
        for s in APP_SERVERS:
            if s["name"] == server_name:
                server_ip = s["ip"]
                break
        
        if not server_ip:
            results[server_name] = {"success": False, "error": "Server not found"}
            all_success = False
            continue
        
        if server_name != primary_server:
            results[server_name] = {
                "success": True,
                "stdout": "Skipped (seeds run on primary server only to avoid duplicate key errors)",
                "stderr": ""
            }
            continue
        
        result = ssh_command(server_ip, f"cd {app_dir} && {seed_cmd}")
        success = result.get("success", False)
        results[server_name] = {
            "success": success,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", "")
        }
        if not success:
            all_success = False
    
    return jsonify({
        "success": all_success,
        "results": results,
        "command": seed_cmd,
        "app_dir": app_dir
    })


def cf_api_request(method, endpoint, data=None):
    if not CLOUDFLARE_API_TOKEN:
        return {"success": False, "error": "Cloudflare API token not configured"}
    
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    url = f"https://api.cloudflare.com/client/v4{endpoint}"
    
    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            return {"success": False, "error": f"Unsupported method: {method}"}
        
        result = resp.json()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def cf_list_zones():
    all_zones = []
    page = 1
    per_page = 50
    
    while True:
        result = cf_api_request("GET", f"/zones?page={page}&per_page={per_page}")
        if result.get("success"):
            zones = result.get("result", [])
            all_zones.extend([{"id": z["id"], "name": z["name"]} for z in zones])
            
            result_info = result.get("result_info", {})
            total_pages = result_info.get("total_pages", 1)
            
            if page >= total_pages:
                break
            page += 1
        else:
            break
    
    return sorted(all_zones, key=lambda x: x["name"])


def cf_create_dns_record(name, content, proxied=True, record_type="A", zone_id=None):
    use_zone_id = zone_id or CLOUDFLARE_ZONE_ID
    if not use_zone_id:
        return {"success": False, "error": "Cloudflare Zone ID not configured"}
    
    data = {
        "type": record_type,
        "name": name,
        "content": content,
        "proxied": proxied,
        "ttl": 1
    }
    
    return cf_api_request("POST", f"/zones/{use_zone_id}/dns_records", data)


def cf_delete_dns_record(name, zone_id=None):
    use_zone_id = zone_id or CLOUDFLARE_ZONE_ID
    if not use_zone_id:
        return {"success": False, "error": "Cloudflare Zone ID not configured"}
    
    result = cf_api_request("GET", f"/zones/{use_zone_id}/dns_records?type=A&name={name}")
    if result.get("success") and result.get("result"):
        record_id = result["result"][0]["id"]
        return cf_api_request("DELETE", f"/zones/{use_zone_id}/dns_records/{record_id}")
    return {"success": False, "error": "Record not found"}


def cf_replace_a_records(name, contents, zone_id):
    if not zone_id:
        return {"success": False, "error": "Zone ID required"}

    existing = cf_api_request("GET", f"/zones/{zone_id}/dns_records?type=A&name={name}")
    if existing.get("success"):
        for record in existing.get("result", []):
            cf_api_request("DELETE", f"/zones/{zone_id}/dns_records/{record.get('id')}")

    created = []
    for content in contents:
        created.append(cf_create_dns_record(name, content, zone_id=zone_id))

    success = all(r.get("success") for r in created)
    return {"success": success, "results": created}


def cf_list_dns_records(zone_id):
    if not zone_id:
        return {"success": False, "error": "Zone ID required"}
    
    all_records = []
    page = 1
    per_page = 100
    
    while True:
        result = cf_api_request("GET", f"/zones/{zone_id}/dns_records?page={page}&per_page={per_page}")
        if result.get("success"):
            records = result.get("result", [])
            all_records.extend(records)
            
            result_info = result.get("result_info", {})
            total_pages = result_info.get("total_pages", 1)
            
            if page >= total_pages:
                break
            page += 1
        else:
            return {"success": False, "error": result.get("error", "Failed to fetch DNS records")}
    
    return {"success": True, "result": all_records}


def cf_check_dns_conflicts(zone_id, records_to_create):
    result = cf_list_dns_records(zone_id)
    if not result.get("success"):
        return {"has_conflicts": False, "records": [], "error": result.get("error")}
    
    existing = result.get("result", [])
    conflicts = []
    overrides = []
    
    for record in records_to_create:
        name = record.get("name", "")
        record_type = record.get("type", "A")
        
        for existing_record in existing:
            if existing_record.get("name") == name and existing_record.get("type") == record_type:
                if name in ["@", "www", "staging"] or name.endswith(".www") or name.endswith(".staging"):
                    overrides.append({
                        "name": name,
                        "type": record_type,
                        "existing_content": existing_record.get("content"),
                        "action": "override"
                    })
                else:
                    conflicts.append({
                        "name": name,
                        "type": record_type,
                        "existing_content": existing_record.get("content"),
                        "action": "block"
                    })
    
    return {
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts,
        "overrides": overrides,
        "records": existing
    }


def cf_create_firewall_rule(expression, action, description, priority=None, zone_id=None):
    use_zone_id = zone_id or CLOUDFLARE_ZONE_ID
    if not use_zone_id:
        return {"success": False, "error": "Cloudflare Zone ID not configured"}
    
    data = {
        "filter": {
            "expression": expression,
            "paused": False
        },
        "action": action,
        "description": description,
        "paused": False
    }
    
    if priority:
        data["priority"] = priority
    
    return cf_api_request("POST", f"/zones/{use_zone_id}/firewall/rules", data)


def cf_create_security_rules(app_domain, zone_id=None):
    use_zone_id = zone_id or CLOUDFLARE_ZONE_ID
    if not use_zone_id:
        return {"success": False, "error": "Cloudflare Zone ID not configured"}
    
    rules = [
        {
            "expression": '(cf.client.bot) or (cf.verified_bot_category in {"Search Engine Crawler" "Search Engine Optimization" "Monitoring & Analytics" "Advertising & Marketing" "Page Preview" "Academic Research" "Security" "Accessibility" "Webhooks" "Feed Fetcher"}) or (http.user_agent contains "letsencrypt" and http.request.uri.path contains "acme-challenge")',
            "action": "allow",
            "description": "Allow legitimate bots and LetsEncrypt",
            "priority": 1
        },
        {
            "expression": '(http.user_agent contains "yandex") or (http.user_agent contains "sogou") or (http.user_agent contains "semrush") or (http.user_agent contains "aherfs") or (http.user_agent contains "baidu") or (http.user_agent contains "python-requests") or (http.user_agent contains "neevabot") or (http.user_agent contains "CF-UC") or (http.user_agent contains "sitelock") or (http.user_agent contains "crawl" and not cf.client.bot) or (http.user_agent contains "bot" and not cf.client.bot) or (http.user_agent contains "Bot" and not cf.client.bot) or (http.user_agent contains "Crawl" and not cf.client.bot) or (http.user_agent contains "spider" and not cf.client.bot) or (http.user_agent contains "mj12bot") or (http.user_agent contains "ZoominfoBot") or (http.user_agent contains "mojeek") or (ip.src.asnum in {135061 23724 4808} and http.user_agent contains "siteaudit")',
            "action": "managed_challenge",
            "description": "Challenge bad bots with captcha",
            "priority": 2
        },
        {
            "expression": '(ip.src.asnum in {7224 16509 14618 15169 8075 396982} and not cf.client.bot and not cf.verified_bot_category in {"Search Engine Crawler" "Search Engine Optimization" "Monitoring & Analytics" "Advertising & Marketing" "Page Preview" "Academic Research" "Security" "Accessibility" "Webhooks" "Feed Fetcher" "Aggregator"} and not http.request.uri.path contains "acme-challenge")',
            "action": "managed_challenge",
            "description": "Challenge suspicious cloud provider traffic",
            "priority": 3
        },
        {
            "expression": '(ip.src.asnum in {60068 9009 16247 51332 212238 131199 22298 29761 62639 206150 210277 46562 8100 3214 206092 206074 206164 213074}) or (http.request.uri.path contains "wp-login") or (http.request.uri.path contains "wp-content") or (http.request.uri.path contains "wp-includes") or (http.request.uri.path contains "wp-admin") or (http.request.uri.path contains "php") or (http.request.uri_path contains "wp") or (http.request.uri.path contains "admin")',
            "action": "managed_challenge",
            "description": "Challenge WordPress scanners",
            "priority": 4
        },
        {
            "expression": '(ip.src.asnum in {200373 198571 26496 31815 18450 398101 50673 7393 14061 205544 199610 21501 16125 51540 264649 39020 30083 35540 55293 36943 32244 6724 63949 7203 201924 30633 208046 36352 25264 32475 23033 32475 212047 32475 31898 210920 211252 16276 23470 136907 12876 210558 132203 61317 212238 37963 13238 2639 20473 63018 395954 19437 207990 27411 53667 27176 396507 206575 20454 51167 60781 62240 398493 206092 63023 213230 26347 20738 45102 24940 57523 8100 8560 6939 14178 46606 197540 397630 9009 11878}) or (http.request.uri.path contains "xmlrpc") or (http.request.uri.path contains "wp-config") or (http.request.uri.path contains "wlwmanifest") or (cf.verified_bot_category in {"AI Crawler" "Other"}) or (ip.src.country in {"T1"}) or (http.request.uri.path contains ".env")',
            "action": "block",
            "description": "Block malicious ASNs and attack patterns",
            "priority": 5
        }
    ]
    
    results = []
    for rule in rules:
        result = cf_create_firewall_rule(rule["expression"], rule["action"], rule["description"], rule.get("priority"), use_zone_id)
        results.append({
            "description": rule["description"],
            "action": rule["action"],
            "success": result.get("success", False),
            "error": str(result.get("errors", [{}])[0].get("message", "")) if not result.get("success") else ""
        })
    
    return results
    
    return results


def provision_domains_cloudflare(app_name, base_domain, staging_subdomain="staging", zone_id=None):
    use_zone_id = zone_id or CLOUDFLARE_ZONE_ID
    if not CLOUDFLARE_API_TOKEN or not use_zone_id:
        return {"success": False, "error": "Cloudflare not configured"}
    
    prod_name = app_name
    staging_name = f"{staging_subdomain}.{app_name}"
    
    results = {
        "production": {"domain": f"{prod_name}.{base_domain}", "records": []},
        "staging": {"domain": f"{staging_name}.{base_domain}", "records": []}
    }
    
    for router in ROUTERS:
        cf_result = cf_create_dns_record(prod_name, router["public_ip"], zone_id=use_zone_id)
        results["production"]["records"].append({
            "router": router["name"],
            "success": cf_result.get("success", False),
            "error": str(cf_result.get("errors", [{}])[0].get("message", "")) if not cf_result.get("success") else ""
        })
        
        cf_result = cf_create_dns_record(staging_name, router["public_ip"], zone_id=use_zone_id)
        results["staging"]["records"].append({
            "router": router["name"],
            "success": cf_result.get("success", False),
            "error": str(cf_result.get("errors", [{}])[0].get("message", "")) if not cf_result.get("success") else ""
        })
    
    all_success = all(
        r["success"] 
        for env in ["production", "staging"] 
        for r in results[env]["records"]
    )
    
    results["success"] = all_success
    return results


def validate_github_repo(repo_url, token=None):
    if not repo_url:
        return {"valid": False, "error": "Repository URL is required"}
    
    owner_repo = None
    
    if repo_url.startswith("https://github.com/"):
        owner_repo = repo_url.replace("https://github.com/", "").rstrip("/").rstrip(".git")
    elif repo_url.startswith("git@github.com:"):
        owner_repo = repo_url.replace("git@github.com:", "").rstrip(".git")
    elif "/" in repo_url and not repo_url.startswith("http") and not repo_url.startswith("git@"):
        owner_repo = repo_url
    
    if not owner_repo or "/" not in owner_repo:
        return {"valid": False, "error": "Invalid GitHub URL format. Use: https://github.com/owner/repo"}
    
    parts = owner_repo.split("/")
    if len(parts) != 2:
        return {"valid": False, "error": "Invalid repository format"}
    
    owner, repo = parts
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    elif GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            return {
                "valid": True,
                "private": data.get("private", False),
                "owner": owner,
                "repo": repo,
                "full_name": data.get("full_name", f"{owner}/{repo}"),
                "error": None
            }
        elif resp.status_code == 404:
            return {"valid": False, "error": "Repository not found. Check the URL and ensure it exists."}
        elif resp.status_code == 403:
            return {"valid": False, "error": "Access denied. Repository may be private and requires authentication."}
        elif resp.status_code == 401:
            return {"valid": False, "error": "Authentication required. Check your GitHub token."}
        else:
            return {"valid": False, "error": f"GitHub API error: {resp.status_code}"}
    except requests.exceptions.Timeout:
        return {"valid": False, "error": "Request timed out. Please try again."}
    except Exception as e:
        return {"valid": False, "error": f"Failed to validate repository: {str(e)}"}


def update_app_url(app_name, app_url, servers=None):
    """
    Update APP_URL and ASSET_URL in .env file for Laravel apps.
    """
    if servers is None:
        servers = APP_SERVERS
    
    framework = None
    applications = load_applications()
    if app_name in applications:
        framework = applications[app_name].get("framework")
    
    if framework != "laravel":
        return {"success": True, "message": "Not a Laravel app, skipping APP_URL update"}
    
    results = []
    for server in servers:
        app_dir = f"/opt/apps/{app_name}"
        env_updates = [
            f"sed -i 's|APP_URL=.*|APP_URL={app_url}|' {app_dir}/.env",
            f"sed -i 's|ASSET_URL=.*|ASSET_URL={app_url}|' {app_dir}/.env 2>/dev/null || true",
            f"cd {app_dir} && php artisan config:clear 2>/dev/null",
        ]
        result = ssh_command(server["ip"], " && ".join(env_updates))
        results.append({
            "server": server["name"],
            "success": result.get("returncode", 1) == 0,
            "output": result.get("stdout", "")
        })
    
    return {"success": all(r["success"] for r in results), "results": results}


def provision_domain_on_routers(domain, app_name, app_port, www_domain=None, is_staging=False, staging_password=None, git_repo=None, git_branch="main"):
    results = []
    
    for router in ROUTERS:
        cmd = f"/opt/scripts/provision-domain.sh {domain} {app_name} {app_port}"
        if www_domain:
            cmd += f" --www {www_domain}"
        if is_staging:
            cmd += " --staging"
        if staging_password:
            cmd += f" --password {staging_password}"
        if git_repo:
            cmd += f" --repo {git_repo}"
        if git_branch:
            cmd += f" --branch {git_branch}"
        
        result = run_router_command(router, cmd, timeout=600)
        verify_cert = run_router_command(router, f"test -f /etc/haproxy/certs/{domain}.pem", timeout=20)
        verify_registry = run_router_command(router, f"grep -q '^{re.escape(domain)}=' /etc/haproxy/domains/registry.conf", timeout=20)
        router_success = result.get("success", False) and verify_cert.get("success", False) and verify_registry.get("success", False)
        verify_error = ""
        if not verify_cert.get("success", False):
            verify_error += "certificate missing; "
        if not verify_registry.get("success", False):
            verify_error += "registry entry missing; "

        results.append({
            "router": router["name"],
            "success": router_success,
            "output": result.get("stdout", ""),
            "error": (result.get("stderr", "") + ("; " + verify_error.strip() if verify_error else "")).strip("; ")
        })
    
    return results


def remove_domain_from_routers(domain):
    results = []
    escaped_domain = re.escape(domain)
    
    for router in ROUTERS:
        rm_cert = run_router_command(router, f"rm -f /etc/haproxy/certs/{domain}.pem", timeout=60)
        rm_registry = run_router_command(router, f"sed -i '/^{escaped_domain}=/d' /etc/haproxy/domains/registry.conf", timeout=60)
        rebuild = run_router_command(router, "/opt/scripts/provision-domain.sh --rebuild 2>/dev/null || systemctl reload haproxy", timeout=120)
        results.append({
            "router": router["name"],
            "success": rm_cert.get("success", False) and rm_registry.get("success", False) and rebuild.get("success", False)
        })
    
    return results


@app.route("/apps/<app_name>/domains", methods=["GET", "POST"])
@requires_auth
def app_domains(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    reserved_domains = get_reserved_base_domains(applications, exclude_app=app_name)

    cf_zones = []
    if CLOUDFLARE_API_TOKEN:
        cf_zones = cf_list_zones()
    
    if request.method == "POST":
        action = request.form.get("action", "add_domain")
        
        if action == "provision_full":
            domain_configs_json = request.form.get("domain_configs", "[]")
            enable_security = "enable_security" in request.form
            
            try:
                domain_configs = json.loads(domain_configs_json)
            except:
                domain_configs = []
            
            if not domain_configs:
                flash("No domains configured", "warning")
                return redirect(url_for("app_domains", app_name=app_name))

            requested_domains = [
                (cfg.get("domain") or "").strip().lower()
                for cfg in domain_configs
                if (cfg.get("domain") or "").strip()
            ]
            conflicting_domains = [d for d in requested_domains if d in reserved_domains]
            if conflicting_domains:
                conflicts = [f"{d} (used by {reserved_domains[d]})" for d in conflicting_domains]
                flash(f"Domain already assigned to another app: {', '.join(conflicts)}", "error")
                return redirect(url_for("app_domains", app_name=app_name))

            new_domains = build_domains_from_configs(domain_configs, enable_security)
            existing_names = {d.get("name") for d in app.get("domains", [])}
            for d in new_domains:
                if d.get("name") not in existing_names:
                    app.setdefault("domains", []).append(d)

            applications[app_name] = app
            save_applications(applications)

            provision_result = provision_pending_domains(app_name, app)
            applications[app_name] = app
            save_applications(applications)

            if provision_result.get("provisioned"):
                flash(f"Provisioned: {', '.join(provision_result['provisioned'])}", "success")
            if provision_result.get("errors"):
                flash("; ".join(provision_result["errors"]), "warning")
            if not provision_result.get("provisioned") and not provision_result.get("errors"):
                flash("No domains were provisioned", "warning")

            return redirect(url_for("app_domains", app_name=app_name))
        
        elif action == "add_domain":
            domain = request.form.get("domain", "").strip().lower()
            ssl_enabled = "ssl_enabled" in request.form
            domain_type = request.form.get("domain_type", "production")
            staging_password = request.form.get("staging_password", "").strip() or secrets.token_urlsafe(12)
            
            if not domain:
                flash("Domain is required", "error")
                return redirect(url_for("app_domains", app_name=app_name))
            
            if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$', domain):
                flash("Invalid domain format", "error")
                return redirect(url_for("app_domains", app_name=app_name))
            
            domains = app.get("domains", [])
            if any(d.get("name") == domain for d in domains):
                flash(f"Domain {domain} already exists", "error")
                return redirect(url_for("app_domains", app_name=app_name))

            parts = domain.split(".")
            if len(parts) < 2:
                flash("Invalid domain format", "error")
                return redirect(url_for("app_domains", app_name=app_name))

            base_domain = ".".join(parts[-2:])
            if base_domain in reserved_domains:
                flash(f"Domain {base_domain} is already assigned to app {reserved_domains[base_domain]}", "error")
                return redirect(url_for("app_domains", app_name=app_name))
            dns_label = domain.replace(f".{base_domain}", "") if domain != base_domain else "@"
            domain_data = {
                "name": domain,
                "type": domain_type,
                "base_domain": base_domain,
                "dns_label": dns_label,
                "production_mode": "root" if (domain_type == "production" and domain == base_domain) else "subdomain",
                "ssl_enabled": ssl_enabled,
                "dns_provisioned": False,
                "provisioned": False,
                "status": "pending",
                "security_enabled": app.get("enable_security", True),
                "error": "",
                "created_at": datetime.utcnow().isoformat()
            }

            if domain_type == "staging":
                domain_data["password"] = staging_password

            domains.append(domain_data)
            app["domains"] = domains
            applications[app_name] = app
            save_applications(applications)

            if ssl_enabled:
                provision_result = provision_pending_domains(app_name, app)
                applications[app_name] = app
                save_applications(applications)
                if provision_result.get("provisioned"):
                    flash(f"Provisioned: {', '.join(provision_result['provisioned'])}", "success")
                if provision_result.get("errors"):
                    flash("; ".join(provision_result["errors"]), "warning")
            else:
                flash(f"Domain {domain} added as pending", "success")
            
            return redirect(url_for("app_domains", app_name=app_name))
    
    return render_template("app_domains.html",
        app_name=app_name,
        app=app,
        app_servers=APP_SERVERS,
        routers=ROUTERS,
        cf_configured=bool(CLOUDFLARE_API_TOKEN),
        cf_zones=cf_zones,
        cf_zone_name=CLOUDFLARE_ZONE_NAME,
        reserved_domains=sorted(reserved_domains.keys()))


@app.route("/apps/<app_name>/domains/<domain>/delete", methods=["POST"])
@requires_auth
def delete_app_domain(app_name, domain):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    domains = app.get("domains", [])
    
    original_count = len(domains)
    domain_obj = next((d for d in domains if d.get("name") == domain), None)
    domains = [d for d in domains if d.get("name") != domain]
    
    if len(domains) == original_count:
        flash("Domain not found", "error")
        return redirect(url_for("app_domains", app_name=app_name))
    
    app["domains"] = domains
    applications[app_name] = app
    save_applications(applications)
    
    if domain_obj and domain_obj.get("provisioned"):
        remove_domain_from_routers(domain)
    
    flash(f"Domain {domain} removed", "success")
    return redirect(url_for("app_domains", app_name=app_name))


def configure_nginx_for_app(app_name, domain, framework, ssl_enabled):
    results = []
    
    if framework == "laravel":
        port = 8000
    elif framework in ["nextjs", "svelte"]:
        port = 3000
    else:
        port = 8080
    
    nginx_config = f"""server {{
    listen 80;
    server_name {domain};
    
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    
    for server in APP_SERVERS:
        config_path = f"/etc/nginx/sites-available/{domain}"
        enabled_path = f"/etc/nginx/sites-enabled/{domain}"
        
        escaped_config = nginx_config.replace("'", "'\"'\"'")
        result = ssh_command(server["ip"], f"echo '{escaped_config}' > {config_path} && ln -sf {config_path} {enabled_path} && nginx -t && systemctl reload nginx")
        results.append({"server": server["name"], "success": result["success"], "error": result.get("stderr", "")})
    
    all_success = all(r["success"] for r in results)
    return {"success": all_success, "results": results}


def remove_nginx_config(app_name, domain):
    for server in APP_SERVERS:
        ssh_command(server["ip"], f"rm -f /etc/nginx/sites-enabled/{domain} /etc/nginx/sites-available/{domain} && systemctl reload nginx")


@app.route("/databases/<db_name>/delete", methods=["POST"])
@requires_auth
def delete_database(db_name):
    databases = load_databases()
    
    if db_name not in databases:
        flash("Database not found in configuration", "error")
        return redirect(url_for("databases"))
    
    db_info = databases.get(db_name, {})
    app_name = db_info.get("app")

    if db_name.endswith("_staging"):
        primary_db = db_name[:-8]
        cleanup = cleanup_database_artifacts(
            app_name=app_name,
            primary_db=primary_db,
            include_primary=False,
            include_staging=True
        )
    else:
        cleanup = cleanup_database_artifacts(
            app_name=app_name,
            primary_db=db_name,
            include_primary=True,
            include_staging=False
        )

    if cleanup["errors"]:
        flash(f"Database cleanup completed with warnings: {'; '.join(cleanup['errors'])}", "warning")
    else:
        flash(f"Database '{db_name}' deleted", "success")
    
    return redirect(url_for("databases"))


def generate_github_workflow(framework, app_name, target_servers, staging_env, create_db, db_name):
    deploy_servers = [
        {"name": "re-db", "ip": "100.92.26.38"},
        {"name": "re-node-02", "ip": "100.89.130.19"}
    ]
    
    gh_secret = "${{ secrets."
    gh_context = "${{ "
    gh_close = " }}"
    
    if framework == "laravel":
        build_steps = """      - name: Install Dependencies
        run: composer install --no-dev --optimize-autoloader
      - name: Build Assets
        run: |
          npm ci
          npm run build
      - name: Optimize
        run: |
          php artisan config:cache
          php artisan route:cache
          php artisan view:cache"""
        deploy_script = """            cd /opt/apps/{app_name}
            git pull origin {gh_context}github.ref_name{gh_close}
            composer install --no-dev --optimize-autoloader
            php artisan migrate --force
            php artisan config:cache
            php artisan route:cache
            php artisan view:cache
            sudo systemctl restart {app_name}"""
    elif framework == "nextjs":
        build_steps = """      - name: Install Dependencies
        run: npm ci
      - name: Build
        run: npm run build"""
        deploy_script = """            cd /opt/apps/{app_name}
            git pull origin {gh_context}github.ref_name{gh_close}
            npm ci --production
            npm run build
            sudo systemctl restart {app_name}"""
    elif framework == "svelte":
        build_steps = """      - name: Install Dependencies
        run: npm ci
      - name: Build
        run: npm run build"""
        deploy_script = """            cd /opt/apps/{app_name}
            git pull origin {gh_context}github.ref_name{gh_close}
            npm ci --production
            npm run build
            sudo systemctl restart {app_name}"""
    elif framework == "python":
        build_steps = """      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install Dependencies
        run: |
          python -m venv venv
          . venv/bin/activate
          pip install -r requirements.txt"""
        deploy_script = """            cd /opt/apps/{app_name}
            git pull origin {gh_context}github.ref_name{gh_close}
            /opt/apps/{app_name}/venv/bin/pip install -r requirements.txt
            sudo systemctl restart {app_name}"""
    else:
        build_steps = """      - name: Set up Go
        uses: actions/setup-go@v4
        with:
          go-version: '1.21'
      - name: Build
        run: go build -o bin/{app_name} ./..."""
        deploy_script = """            cd /opt/apps/{app_name}
            git pull origin {gh_context}github.ref_name{gh_close}
            go build -o bin/{app_name} .
            sudo systemctl restart {app_name}"""
    
    deploy_jobs = ""
    for server in deploy_servers:
        deploy_jobs += f"""
  deploy-{server['name']}:
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to {server['name']}
        uses: appleboy/ssh-action@master
        with:
          host: {gh_secret}DEPLOY_HOST{gh_close}
          username: {gh_secret}DEPLOY_USER{gh_close}
          password: {gh_secret}DEPLOY_PASSWORD{gh_close}
          script: |
{deploy_script.format(app_name=app_name, gh_context=gh_context, gh_close=gh_close)}
"""
    
    staging_block = ""
    if staging_env:
        staging_block = f"""
  staging:
    runs-on: ubuntu-latest
    environment: staging
    if: github.ref == 'refs/heads/staging'
    steps:
      - uses: actions/checkout@v4
{build_steps}
      - name: Deploy to Staging
        uses: appleboy/ssh-action@master
        with:
          host: {gh_secret}DEPLOY_HOST{gh_close}
          username: {gh_secret}DEPLOY_USER{gh_close}
          password: {gh_secret}DEPLOY_PASSWORD{gh_close}
          script: |
            cd /opt/apps/{app_name}-staging
            git pull origin {gh_context}github.ref_name{gh_close}
            composer install --no-dev --optimize-autoloader 2>/dev/null || true
            npm ci && npm run build 2>/dev/null || true
            php artisan migrate --force 2>/dev/null || true
            sudo systemctl restart {app_name}-staging 2>/dev/null || sudo systemctl reload php8.5-fpm
"""
    
    staging_branch = "\n      - staging" if staging_env else ""

    return f"""name: Deploy {app_name}

on:
  push:
    branches:
      - main{staging_branch}

jobs:
  build:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
{build_steps}
{deploy_jobs}{staging_block}"""


@app.route("/settings")
@requires_auth
def settings():
    return render_template("settings.html",
        github_token_set=bool(GITHUB_TOKEN),
        cf_api_token_set=bool(CLOUDFLARE_API_TOKEN),
        cf_zone_id=CLOUDFLARE_ZONE_ID,
        cf_zone_name=CLOUDFLARE_ZONE_NAME,
        pg_host=PG_HOST,
        pg_port=PG_PORT,
        redis_host=REDIS_HOST,
        redis_port=REDIS_PORT,
        prometheus_url=PROMETHEUS_URL,
        grafana_url=GRAFANA_URL,
        app_servers=APP_SERVERS)


@app.route("/settings/github-token", methods=["POST"])
@requires_auth
def save_github_token():
    global GITHUB_TOKEN
    token = request.form.get("github_token", "").strip()
    if token and token != "****************":
        GITHUB_TOKEN = token
        
        env_path = "/opt/dashboard/config/.env"
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        
        env_content = f"GITHUB_TOKEN={token}\n"
        with open(env_path, "w") as f:
            f.write(env_content)
        
        flash("GitHub token saved successfully", "success")
    return redirect(url_for("settings"))


@app.route("/settings/cloudflare", methods=["POST"])
@requires_auth
def save_cloudflare_settings():
    global CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_ID, CLOUDFLARE_ZONE_NAME
    
    api_token = request.form.get("cf_api_token", "").strip()
    zone_id = request.form.get("cf_zone_id", "").strip()
    zone_name = request.form.get("cf_zone_name", "").strip()
    
    env_path = "/opt/dashboard/config/.env"
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    
    env_lines = []
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            env_lines = f.readlines()
    
    env_vars = {}
    for line in env_lines:
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            env_vars[key.strip()] = val.strip()
    
    if api_token and api_token != "****************":
        CLOUDFLARE_API_TOKEN = api_token
        env_vars["CLOUDFLARE_API_TOKEN"] = api_token
    
    if zone_id:
        CLOUDFLARE_ZONE_ID = zone_id
        env_vars["CLOUDFLARE_ZONE_ID"] = zone_id
    
    if zone_name:
        CLOUDFLARE_ZONE_NAME = zone_name
        env_vars["CLOUDFLARE_ZONE_NAME"] = zone_name
    
    with open(env_path, "w") as f:
        for key, val in env_vars.items():
            f.write(f"{key}={val}\n")
    
    flash("Cloudflare settings saved successfully", "success")
    return redirect(url_for("settings"))


@app.route("/apps/<app_name>/github-secrets")
@requires_auth
def app_github_secrets(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    git_repo = app.get("git_repo")
    owner, repo = parse_github_repo(git_repo) if git_repo else (None, None)
    
    github_secrets = []
    if owner and repo and GITHUB_TOKEN:
        github_secrets, error = list_github_secrets(owner, repo, GITHUB_TOKEN)
        if error:
            flash(f"Could not fetch GitHub secrets: {error}", "warning")
    
    return render_template("app_secrets.html",
        app_name=app_name,
        app=app,
        github_secrets=github_secrets or [],
        owner=owner,
        repo=repo,
        has_github_token=bool(GITHUB_TOKEN))


@app.route("/apps/<app_name>/github-secrets/add", methods=["POST"])
@requires_auth
def add_app_github_secret(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    git_repo = app.get("git_repo")
    owner, repo = parse_github_repo(git_repo) if git_repo else (None, None)
    
    if not owner or not repo:
        flash("No valid GitHub repository configured", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    if not GITHUB_TOKEN:
        flash("GitHub token not configured. Please add it in Settings.", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    secret_name = request.form.get("secret_name", "").strip().upper()
    secret_value = request.form.get("secret_value", "").strip()
    
    if not secret_name or not secret_value:
        flash("Secret name and value are required", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    if not re.match(r'^[A-Z_][A-Z0-9_]*$', secret_name):
        flash("Secret name must use uppercase letters, numbers, and underscores only", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    success, error = set_github_secret(owner, repo, GITHUB_TOKEN, secret_name, secret_value)
    if success:
        flash(f"Secret '{secret_name}' added successfully", "success")
    else:
        flash(f"Failed to add secret: {error}", "error")
    
    return redirect(url_for("app_github_secrets", app_name=app_name))


@app.route("/apps/<app_name>/github-secrets/<secret_name>/delete", methods=["POST"])
@requires_auth
def delete_app_github_secret(app_name, secret_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    git_repo = app.get("git_repo")
    owner, repo = parse_github_repo(git_repo) if git_repo else (None, None)
    
    if not owner or not repo:
        flash("No valid GitHub repository configured", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    if not GITHUB_TOKEN:
        flash("GitHub token not configured", "error")
        return redirect(url_for("app_github_secrets", app_name=app_name))
    
    success, error = delete_github_secret(owner, repo, GITHUB_TOKEN, secret_name)
    if success:
        flash(f"Secret '{secret_name}' deleted", "success")
    else:
        flash(f"Failed to delete secret: {error}", "error")
    
    return redirect(url_for("app_secrets", app_name=app_name))


@app.route("/docs")
@requires_auth
def docs_index():
    docs = []
    if os.path.exists(DOCS_PATH):
        for f in sorted(os.listdir(DOCS_PATH)):
            if f.endswith(".md"):
                docs.append({"name": f[:-3].replace("_", " ").title(), "file": f})
    return render_template("docs_index.html", docs=docs)


@app.route("/docs/<doc_name>")
@requires_auth
def docs_view(doc_name):
    doc_path = os.path.join(DOCS_PATH, f"{doc_name}.md")
    if not os.path.exists(doc_path):
        flash("Document not found", "error")
        return redirect(url_for("docs_index"))
    
    with open(doc_path, "r") as f:
        content = f.read()
    
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code", "toc"])
    return render_template("docs_view.html", content=html_content, doc_name=doc_name)


@app.route("/api/health")
def api_health():
    pg = get_pg_cluster_status()
    rd = get_redis_info()
    return jsonify({
        "postgresql": pg,
        "redis": rd,
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route("/api/apps")
def api_apps():
    applications = load_applications()
    return jsonify({"applications": list(applications.keys()), "apps": list(applications.keys())})


@app.route("/api/alerts")
def api_alerts():
    alerts = get_prometheus_alerts()
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/databases")
@requires_auth
def api_databases():
    return jsonify({"databases": load_databases(), "postgres_databases": get_pg_databases()})


@app.route("/databases/<db_name>")
@requires_auth
def database_detail(db_name):
    databases = load_databases()
    db_info = databases.get(db_name)
    return render_template("database_detail.html", 
        db_name=db_name, 
        db_info=db_info,
        pg_host=PG_HOST,
        pg_port=PG_PORT)


@app.route("/api/databases/<db_name>/metrics")
@requires_auth
def api_database_metrics(db_name):
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, database=db_name,
            user=PG_USER, password=PG_PASSWORD, connect_timeout=5
        )
        cur = conn.cursor()
        
        cur.execute("SELECT pg_database_size(%s)", (db_name,))
        size = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (db_name,))
        connections = cur.fetchone()[0]
        
        cur.execute("SELECT setting FROM pg_settings WHERE name = 'max_connections'")
        max_connections = int(cur.fetchone()[0])
        
        cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        table_count = cur.fetchone()[0]
        
        try:
            cur.execute("""
                SELECT count(*) FROM pg_stat_statements 
                WHERE mean_exec_time > 100 AND dbid = (SELECT oid FROM pg_database WHERE datname = %s)
            """, (db_name,))
            slow_queries = cur.fetchone()[0]
        except:
            slow_queries = 0
        
        cur.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "size": size,
            "connections": connections,
            "max_connections": max_connections,
            "table_count": table_count,
            "slow_queries": slow_queries
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/databases/<db_name>/tables")
@requires_auth
def api_database_tables(db_name):
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, database=db_name,
            user=PG_USER, password=PG_PASSWORD, connect_timeout=5
        )
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                schemaname, relname as name,
                n_live_tup as rows,
                pg_relation_size(schemaname || '.' || relname) as size,
                (SELECT count(*) FROM pg_indexes WHERE tablename = relname) as indexes,
                last_vacuum, last_analyze
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC
        """)
        
        tables = []
        for row in cur.fetchall():
            tables.append({
                "schema": row[0],
                "name": row[1],
                "rows": row[2] or 0,
                "size": row[3] or 0,
                "indexes": row[4] or 0,
                "last_vacuum": row[5].isoformat() if row[5] else None,
                "last_analyze": row[6].isoformat() if row[6] else None
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "tables": tables})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "tables": []})


@app.route("/api/databases/<db_name>/query-stats")
@requires_auth
def api_database_query_stats(db_name):
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, database=db_name,
            user=PG_USER, password=PG_PASSWORD, connect_timeout=5
        )
        cur = conn.cursor()
        
        cur.execute("""
            SELECT query, calls, total_exec_time, mean_exec_time, rows
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = %s)
            AND mean_exec_time > 100
            ORDER BY total_exec_time DESC
            LIMIT 20
        """, (db_name,))
        
        queries = []
        for row in cur.fetchall():
            queries.append({
                "query": row[0],
                "calls": row[1],
                "total_time": row[2],
                "avg_time": row[3],
                "rows": row[4]
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "queries": queries})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "queries": []})


@app.route("/api/databases/<db_name>/index-stats")
@requires_auth
def api_database_index_stats(db_name):
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, database=db_name,
            user=PG_USER, password=PG_PASSWORD, connect_timeout=5
        )
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                indexrelname as name,
                relname as table,
                pg_relation_size(indexrelid) as size,
                idx_scan as scans,
                idx_tup_read as tuples_read
            FROM pg_stat_user_indexes
            ORDER BY idx_scan DESC
            LIMIT 30
        """)
        
        indexes = []
        for row in cur.fetchall():
            indexes.append({
                "name": row[0],
                "table": row[1],
                "size": row[2] or 0,
                "scans": row[3] or 0,
                "tuples_read": row[4] or 0
            })
        
        cur.close()
        conn.close()
        
        return jsonify({"success": True, "indexes": indexes})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "indexes": []})


@app.route("/databases/<db_name>/backups")
@requires_auth
def database_backups(db_name):
    return render_template("database_backups.html", db_name=db_name)


@app.route("/api/databases/<db_name>/backups", methods=["GET", "POST"])
@requires_auth
def api_database_backups(db_name):
    if request.method == "POST":
        try:
            backup_dir = f"/var/backups/postgresql/{db_name}"
            result = subprocess.run([
                "ssh", f"root@{PG_HOST}",
                f"mkdir -p {backup_dir} && "
                f"pg_dump -U postgres {db_name} | gzip > {backup_dir}/$(date +%Y%m%d_%H%M%S).sql.gz"
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                return jsonify({"success": True, "message": "Backup created"})
            else:
                return jsonify({"success": False, "error": result.stderr})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    try:
        result = subprocess.run([
            "ssh", f"root@{PG_HOST}",
            f"ls -lh /var/backups/postgresql/{db_name}/ 2>/dev/null || echo ''"
        ], capture_output=True, text=True, timeout=30)
        
        backups = []
        if result.returncode == 0 and result.stdout.strip():
            for line in result.stdout.strip().split('\n')[1:]:
                if line:
                    parts = line.split()
                    if len(parts) >= 9:
                        backups.append({
                            "id": parts[-1],
                            "size": parts[4],
                            "created_at": " ".join(parts[5:8]),
                            "status": "completed",
                            "type": "full",
                            "location": "local"
                        })
        
        return jsonify({"success": True, "backups": list(reversed(backups))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "backups": []})


@app.route("/api/databases/<db_name>/backups/<backup_id>/restore", methods=["POST"])
@requires_auth
def api_restore_backup(db_name, backup_id):
    try:
        backup_path = f"/var/backups/postgresql/{db_name}/{backup_id}"
        
        result = subprocess.run([
            "ssh", f"root@{PG_HOST}",
            f"gunzip -c {backup_path} | psql -U postgres {db_name}"
        ], capture_output=True, text=True, timeout=600)
        
        if result.returncode == 0:
            return jsonify({"success": True, "message": "Database restored"})
        else:
            return jsonify({"success": False, "error": result.stderr})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/alerts")
@requires_auth
def alerts_page():
    return render_template("alerts.html", 
        prometheus_url=PROMETHEUS_URL,
        grafana_url=GRAFANA_URL)


@app.route("/api/alerts/rules")
def api_alert_rules():
    try:
        resp = requests.get(f"{PROMETHEUS_URL}/api/v1/rules", timeout=10)
        data = resp.json()
        
        rules = []
        if data.get("status") == "success":
            for group in data["data"]["groups"]:
                for rule in group.get("rules", []):
                    if rule.get("type") == "alerting":
                        rules.append({
                            "name": rule.get("name"),
                            "expr": rule.get("query"),
                            "severity": rule.get("labels", {}).get("severity", "info"),
                            "state": rule.get("state"),
                            "group": group.get("name")
                        })
        
        return jsonify({"success": True, "rules": rules})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "rules": []})


@app.route("/api/alerts/silences", methods=["GET", "POST", "DELETE"])
def api_alert_silences():
    alertmanager_url = os.environ.get("ALERTMANAGER_URL", "http://100.102.220.16:9093")
    
    if request.method == "GET":
        try:
            resp = requests.get(f"{alertmanager_url}/api/v2/silences", timeout=10)
            return jsonify({"success": True, "silences": resp.json()})
        except Exception as e:
            return jsonify({"success": False, "error": str(e), "silences": []})
    
    elif request.method == "POST":
        data = request.json
        
        if data.get("silence_id"):
            try:
                resp = requests.delete(f"{alertmanager_url}/api/v2/silence/{data['silence_id']}", timeout=10)
                return jsonify({"success": resp.status_code == 200})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        
        matchers = data.get("matchers", [])
        duration = data.get("duration", "1h")
        
        import re
        m = re.match(r"(\d+)([hmsd])", duration)
        if m:
            value = int(m.group(1))
            unit = m.group(2)
            seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit] * value
        else:
            seconds = 3600
        
        from datetime import timedelta
        ends_at = (datetime.utcnow() + timedelta(seconds=seconds)).isoformat() + "Z"
        
        silence_data = {
            "matchers": matchers,
            "startsAt": datetime.utcnow().isoformat() + "Z",
            "endsAt": ends_at,
            "createdBy": "dashboard",
            "comment": data.get("comment", "Silenced from dashboard")
        }
        
        try:
            resp = requests.post(
                f"{alertmanager_url}/api/v2/silences",
                json=silence_data,
                timeout=10
            )
            return jsonify({"success": resp.status_code == 200, "silence_id": resp.json().get("silenceID")})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    return jsonify({"success": False, "error": "Invalid method"})


@app.route("/api/servers")
def api_servers():
    return jsonify(check_servers_async(DB_SERVERS + APP_SERVERS + ROUTERS))


@app.route("/api/disk-space")
def api_disk_space():
    disk_info = {}
    
    server_ip_map = {}
    for s in DB_SERVERS + APP_SERVERS + ROUTERS:
        server_ip_map[s["ip"]] = s["name"]
    
    try:
        queries = [
            ("node_filesystem_size_bytes{mountpoint='/',fstype='ext4'}", "total"),
            ("node_filesystem_avail_bytes{mountpoint='/',fstype='ext4'}", "available")
        ]
        
        results = {}
        for query, metric_name in queries:
            resp = requests.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
                timeout=10
            )
            data = resp.json()
            if data.get("status") == "success":
                for r in data["data"]["result"]:
                    instance = r["metric"]["instance"].replace(":9100", "")
                    server_name = server_ip_map.get(instance, instance)
                    if server_name not in results:
                        results[server_name] = {}
                    results[server_name][metric_name] = float(r["value"][1])
        
        for server_name, metrics in results.items():
            total = metrics.get("total", 0)
            available = metrics.get("available", 0)
            used = total - available
            
            def format_bytes(b):
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if b < 1024:
                        return f"{b:.1f}{unit}"
                    b /= 1024
                return f"{b:.1f}PB"
            
            percent = f"{(used/total*100):.0f}%" if total > 0 else "0%"
            
            disk_info[server_name] = {
                "total": format_bytes(total),
                "used": format_bytes(used),
                "available": format_bytes(available),
                "percent": percent,
                "percent_raw": (used/total*100) if total > 0 else 0
            }
    except Exception as e:
        return jsonify({"error": str(e)})
    
    return jsonify(disk_info)


from secrets_module import (
    load_app_secrets, save_app_secrets, set_app_secret, delete_app_secret as delete_app_secret_module,
    get_app_secret, list_app_secrets, load_global_secrets, save_global_secrets,
    set_global_secret, get_global_secret, generate_env_file_content,
    export_secrets_for_deployment
)


def delete_app_secret(app_name, key, scope=None):
    return delete_app_secret_module(app_name, key, scope=scope)


@app.route("/secrets")
@requires_auth
def secrets_management():
    applications = load_applications()
    app_secrets_summary = {}
    for app_name in applications.keys():
        secrets = list_app_secrets(app_name)
        app_secrets_summary[app_name] = len(secrets)
    
    global_secrets = load_global_secrets()
    
    return render_template("secrets.html",
        applications=applications,
        app_secrets_summary=app_secrets_summary,
        global_secrets=global_secrets)


@app.route("/secrets/global")
@requires_auth
def global_secrets():
    secrets = load_global_secrets()
    secrets_list = [
        {"key": k, "description": v.get("description", ""), "updated_at": v.get("updated_at", "")}
        for k, v in secrets.items()
    ]
    return render_template("secrets_global.html", secrets=secrets_list)


@app.route("/secrets/global/add", methods=["GET", "POST"])
@requires_auth
def add_global_secret():
    if request.method == "POST":
        key = request.form.get("key", "").strip().upper()
        value = request.form.get("value", "")
        description = request.form.get("description", "").strip()
        
        if not key or not value:
            flash("Key and value are required", "error")
            return redirect(url_for("add_global_secret"))
        
        if not key.replace("_", "").isalnum():
            flash("Key must be alphanumeric with underscores only", "error")
            return redirect(url_for("add_global_secret"))
        
        result = set_global_secret(key, value, description)
        if result["success"]:
            flash(f"Secret '{key}' saved successfully", "success")
            return redirect(url_for("global_secrets"))
        else:
            flash(f"Failed to save secret: {result.get('error', 'Unknown error')}", "error")
    
    return render_template("secret_form.html", secret_type="global", app_name=None)


@app.route("/secrets/global/<key>/delete", methods=["POST"])
@requires_auth
def delete_global_secret(key):
    secrets = load_global_secrets()
    if key in secrets:
        del secrets[key]
        result = save_global_secrets(secrets)
        if result["success"]:
            flash(f"Secret '{key}' deleted", "success")
        else:
            flash(f"Failed to delete secret: {result.get('error', 'Unknown error')}", "error")
    else:
        flash("Secret not found", "error")
    return redirect(url_for("global_secrets"))


@app.route("/secrets/global/<key>/edit", methods=["GET", "POST"])
@requires_auth
def edit_global_secret(key):
    secrets = load_global_secrets()
    
    if key not in secrets:
        flash("Secret not found", "error")
        return redirect(url_for("global_secrets"))
    
    if request.method == "POST":
        value = request.form.get("value", "")
        description = request.form.get("description", "").strip()
        
        if not value:
            flash("Value is required", "error")
            return redirect(url_for("edit_global_secret", key=key))
        
        result = set_global_secret(key, value, description)
        if result["success"]:
            flash(f"Secret '{key}' updated successfully", "success")
            return redirect(url_for("global_secrets"))
        else:
            flash(f"Failed to update secret: {result.get('error', 'Unknown error')}", "error")
    
    secret = secrets[key]
    return render_template("secret_form.html", 
        secret_type="global", 
        app_name=None, 
        edit_mode=True,
        secret_key=key,
        secret_data=secret)


@app.route("/apps/<app_name>/secrets")
@requires_auth
def app_secrets(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    scope_filter = request.args.get("scope", "").strip().lower()
    if scope_filter not in ["", "shared", "production", "staging"]:
        scope_filter = ""
    secrets = list_app_secrets(app_name, scope=scope_filter or None)
    app = applications[app_name]
    
    return render_template("app_secrets.html",
        app_name=app_name,
        app=app,
        secrets=secrets,
        selected_scope=scope_filter or "all")


@app.route("/apps/<app_name>/secrets/add", methods=["GET", "POST"])
@requires_auth
def add_app_secret(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    if request.method == "POST":
        key = request.form.get("key", "").strip().upper()
        value = request.form.get("value", "")
        description = request.form.get("description", "").strip()
        scope = request.form.get("scope", "shared").strip().lower()
        if scope not in ["shared", "production", "staging"]:
            scope = "shared"
        
        if not key or not value:
            flash("Key and value are required", "error")
            return redirect(url_for("add_app_secret", app_name=app_name))
        
        if not key.replace("_", "").isalnum():
            flash("Key must be alphanumeric with underscores only", "error")
            return redirect(url_for("add_app_secret", app_name=app_name))
        
        result = set_app_secret(app_name, key, value, description, scope=scope)
        if result["success"]:
            sync_result = sync_runtime_env_for_app(app_name, applications[app_name])
            if sync_result.get("success"):
                flash(f"Secret '{key}' ({scope}) saved and runtime env synced", "success")
            else:
                flash(f"Secret '{key}' ({scope}) saved, but env sync had warnings: {'; '.join(sync_result.get('errors', []))}", "warning")
            return redirect(url_for("app_secrets", app_name=app_name))
        else:
            flash(f"Failed to save secret: {result.get('error', 'Unknown error')}", "error")

    default_scope = request.args.get("scope", "shared").strip().lower()
    if default_scope not in ["shared", "production", "staging"]:
        default_scope = "shared"
    return render_template("secret_form.html", secret_type="app", app_name=app_name, selected_scope=default_scope)


@app.route("/apps/<app_name>/secrets/<key>/delete", methods=["POST"])
@requires_auth
def delete_app_secret_route(app_name, key):
    applications = load_applications()
    app = applications.get(app_name)
    if not app:
        flash("Application not found", "error")
        return redirect(url_for("apps"))

    scope = request.form.get("scope", "").strip().lower()
    if scope not in ["", "shared", "production", "staging"]:
        scope = ""

    result = delete_app_secret(app_name, key, scope=scope or None)
    if result["success"]:
        sync_result = sync_runtime_env_for_app(app_name, app)
        if sync_result.get("success"):
            flash(f"Secret '{key}' deleted and runtime env synced", "success")
        else:
            flash(f"Secret '{key}' deleted, but env sync had warnings: {'; '.join(sync_result.get('errors', []))}", "warning")
    else:
        flash(f"Failed to delete secret: {result.get('error', 'Unknown error')}", "error")
    return redirect(url_for("app_secrets", app_name=app_name))


@app.route("/apps/<app_name>/secrets/<key>/edit", methods=["GET", "POST"])
@requires_auth
def edit_app_secret_route(app_name, key):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    scope = request.args.get("scope", "shared").strip().lower()
    if scope not in ["shared", "production", "staging"]:
        scope = "shared"

    secrets = load_app_secrets(app_name, scope=scope)

    if key not in secrets:
        flash("Secret not found", "error")
        return redirect(url_for("app_secrets", app_name=app_name))
    
    if request.method == "POST":
        value = request.form.get("value", "")
        description = request.form.get("description", "").strip()
        
        if not value:
            flash("Value is required", "error")
            return redirect(url_for("edit_app_secret_route", app_name=app_name, key=key))
        
        result = set_app_secret(app_name, key, value, description, scope=scope)
        if result["success"]:
            sync_result = sync_runtime_env_for_app(app_name, applications[app_name])
            if sync_result.get("success"):
                flash(f"Secret '{key}' ({scope}) updated and runtime env synced", "success")
            else:
                flash(f"Secret '{key}' ({scope}) updated, but env sync had warnings: {'; '.join(sync_result.get('errors', []))}", "warning")
            return redirect(url_for("app_secrets", app_name=app_name))
        else:
            flash(f"Failed to update secret: {result.get('error', 'Unknown error')}", "error")
    
    secret = secrets[key]
    return render_template("secret_form.html", 
        secret_type="app", 
        app_name=app_name, 
        edit_mode=True,
        secret_key=key,
        secret_data=secret,
        selected_scope=scope)


@app.route("/apps/<app_name>/secrets/<key>/reveal")
@requires_auth
def reveal_app_secret(app_name, key):
    scope = request.args.get("scope", "shared").strip().lower()
    if scope not in ["shared", "production", "staging"]:
        scope = "shared"
    value = get_app_secret(app_name, key, scope=scope)
    if value is not None:
        return jsonify({"success": True, "value": value})
    return jsonify({"success": False, "error": "Secret not found"})


@app.route("/apps/<app_name>/secrets/export")
@requires_auth
def export_app_secrets(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    framework = app.get("framework", "laravel")
    
    additional_vars = {}
    if framework == "laravel":
        db_name = app.get("database")
        if db_name:
            databases = load_databases()
            if db_name in databases:
                db = databases[db_name]
                db_admin = db.get("owner", f"{app_name}_admin")
                for user in db.get("users", []):
                    if user.get("name") == db_admin:
                        additional_vars.update({
                            "DB_HOST": PG_HOST,
                            "DB_PORT": str(PG_PORT),
                            "DB_DATABASE": db_name,
                            "DB_USERNAME": db_admin,
                            "DB_PASSWORD": user.get("password", ""),
                        })
                        break
        
        if app.get("redis_enabled"):
            additional_vars.update({
                "REDIS_HOST": REDIS_HOST,
                "REDIS_PORT": str(REDIS_PORT),
                "REDIS_PASSWORD": REDIS_PASSWORD,
            })
    
    env_content = generate_env_file_content(app_name, "production", additional_vars)
    
    return render_template("secrets_export.html",
        app_name=app_name,
        app=app,
        env_content=env_content)


@app.route("/api/secrets/<app_name>", methods=["GET"])
@requires_auth
def api_get_secrets(app_name):
    secrets = export_secrets_for_deployment(app_name)
    return jsonify({"success": True, "secrets": secrets})


@app.route("/api/secrets/<app_name>/env", methods=["GET"])
@requires_auth
def api_get_env_file(app_name):
    env_content = generate_env_file_content(app_name)
    return env_content, 200, {"Content-Type": "text/plain"}


@app.route("/api/secrets/<app_name>", methods=["POST"])
@requires_auth
def api_set_secret(app_name):
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No data provided"}), 400
    
    key = data.get("key", "").strip().upper()
    value = data.get("value", "")
    description = data.get("description", "")
    scope = str(data.get("scope", "shared")).strip().lower()
    if scope not in ["shared", "production", "staging"]:
        scope = "shared"
    
    if not key or not value:
        return jsonify({"success": False, "error": "Key and value required"}), 400
    
    result = set_app_secret(app_name, key, value, description, scope=scope)
    if result.get("success"):
        applications = load_applications()
        app = applications.get(app_name)
        if app:
            sync_result = sync_runtime_env_for_app(app_name, app)
            result["env_sync"] = sync_result
    return jsonify(result)


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
    server = find_server_by_name(server_name)
    
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
    
    all_servers = DB_SERVERS + APP_SERVERS + ROUTERS
    
    try:
        redis_client.setex(f"task:{task_id}", 3600, json.dumps({
            "status": "running",
            "progress": 0,
            "total": len(all_servers),
            "servers_completed": [],
            "started_at": datetime.utcnow().isoformat()
        }))
    except Exception:
        pass
    
    @run_in_thread
    def run_check():
        completed = []
        
        for i, server in enumerate(all_servers):
            get_server_updates(server["ip"], force_refresh=True)
            completed.append(server["name"])
            
            try:
                redis_client.setex(f"task:{task_id}", 3600, json.dumps({
                    "status": "running",
                    "progress": i + 1,
                    "total": len(all_servers),
                    "servers_completed": completed,
                    "started_at": datetime.utcnow().isoformat()
                }))
            except Exception:
                pass
        
        try:
            redis_client.setex(f"task:{task_id}", 3600, json.dumps({
                "status": "complete",
                "progress": len(all_servers),
                "total": len(all_servers),
                "servers_completed": completed,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat()
            }))
        except Exception:
            pass
    
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
    try:
        task_data = redis_client.get(f"task:{task_id}")
        if not task_data:
            return jsonify({"success": False, "error": "Task not found"}), 404
        
        return jsonify(json.loads(task_data))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/servers/<server_name>/updates", methods=["POST"])
@requires_auth
def api_update_server(server_name):
    """
    Update packages on a specific server.
    """
    server = find_server_by_name(server_name)
    
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
    
    try:
        redis_client.setex(f"task:{task_id}", 7200, json.dumps({
            "status": "running",
            "progress": 0,
            "total": len(all_servers),
            "servers_completed": [],
            "servers_failed": [],
            "started_at": datetime.utcnow().isoformat()
        }))
    except Exception:
        pass
    
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
            
            try:
                redis_client.setex(f"task:{task_id}", 7200, json.dumps({
                    "status": "running",
                    "progress": i + 1,
                    "total": len(all_servers),
                    "servers_completed": completed,
                    "servers_failed": failed,
                    "started_at": datetime.utcnow().isoformat()
                }))
            except Exception:
                pass
        
        try:
            redis_client.setex(f"task:{task_id}", 7200, json.dumps({
                "status": "complete",
                "progress": len(all_servers),
                "total": len(all_servers),
                "servers_completed": completed,
                "servers_failed": failed,
                "started_at": datetime.utcnow().isoformat(),
                "completed_at": datetime.utcnow().isoformat()
            }))
        except Exception:
            pass
    
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
    server = find_server_by_name(server_name)
    
    if not server:
        return jsonify({"success": False, "error": "Server not found"}), 404
    
    data = request.json or {}
    services = data.get("services", [])
    
    if not services:
        return jsonify({"success": False, "error": "No services specified"}), 400
    
    result = restart_services(server["ip"], services)
    return jsonify(result)


@app.route("/servers/<server_name>")
@requires_auth
def server_detail(server_name):
    """
    Server detail page with package updates.
    """
    server = find_server_by_name(server_name)
    
    if not server:
        flash("Server not found", "error")
        return redirect(url_for("servers"))
    
    server_status = check_servers_async([server])
    
    force_refresh = request.args.get("refresh", "false").lower() == "true"
    updates = get_server_updates(server["ip"], force_refresh=force_refresh)
    
    return render_template(
        "server_detail.html",
        server=server,
        server_status=server_status.get(server_name, {}),
        updates=updates
    )


@app.route("/api/settings/export")
@requires_auth
def api_settings_export():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    try:
        config = paas_db.export_configuration()
        return jsonify({"success": True, "config": config})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/import", methods=["POST"])
@requires_auth
def api_settings_import():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    data = request.json
    if not data or "config" not in data:
        return jsonify({"success": False, "error": "No configuration provided"})
    
    mode = data.get("mode", "merge")
    if mode not in ["merge", "replace"]:
        return jsonify({"success": False, "error": "Invalid mode. Use 'merge' or 'replace'"})
    
    try:
        result = paas_db.import_configuration(data["config"], mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/sync-status")
@requires_auth
def api_settings_sync_status():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"last_sync_status": "unavailable", "last_sync_at": None})
    
    try:
        status = paas_db.get_sync_status()
        return jsonify(status)
    except Exception:
        return jsonify({"last_sync_status": "error", "last_sync_at": None})


@app.route("/api/settings/sync-history")
@requires_auth
def api_settings_sync_history():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"history": []})
    
    try:
        history = paas_db.get_sync_history(limit=50)
        return jsonify({"history": history})
    except Exception:
        return jsonify({"history": []})


@app.route("/api/settings/gist", methods=["GET", "POST"])
@requires_auth
def api_settings_gist():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    if request.method == "GET":
        try:
            status = paas_db.get_sync_status()
            gist_id = status.get("gist_id") or paas_db.get_setting("gist_id", "")
            auto_sync = status.get("auto_sync_enabled", 1)
            return jsonify({
                "gist_id": gist_id,
                "auto_sync_enabled": bool(auto_sync)
            })
        except Exception as e:
            return jsonify({"gist_id": "", "auto_sync_enabled": True})
    
    data = request.json or {}
    
    if data.get("github_token"):
        global GITHUB_TOKEN
        GITHUB_TOKEN = data["github_token"]
        env_path = "/opt/dashboard/config/.env"
        os.makedirs(os.path.dirname(env_path), exist_ok=True)
        env_vars = {}
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        env_vars[key.strip()] = val.strip()
        env_vars["GITHUB_TOKEN"] = data["github_token"]
        with open(env_path, "w") as f:
            for key, val in env_vars.items():
                f.write(f"{key}={val}\n")
    
    if data.get("gist_id"):
        paas_db.set_setting("gist_id", data["gist_id"])
        paas_db.update_sync_status({"gist_id": data["gist_id"]})
    
    if "auto_sync_enabled" in data:
        paas_db.update_sync_status({"auto_sync_enabled": 1 if data["auto_sync_enabled"] else 0})
    
    return jsonify({"success": True})


@app.route("/api/settings/gist/sync", methods=["POST"])
@requires_auth
def api_settings_gist_sync():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    try:
        service = get_sync_service()
        result = service.sync()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/gist/create", methods=["POST"])
@requires_auth
def api_settings_gist_create():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    if not GITHUB_TOKEN:
        return jsonify({"success": False, "error": "GitHub token not configured"})
    
    try:
        service = GistSyncService(github_token=GITHUB_TOKEN)
        result = service.create_gist()
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/gist/versions")
@requires_auth
def api_settings_gist_versions():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"versions": []})
    
    try:
        service = get_sync_service()
        versions = service.get_gist_versions()
        return jsonify({"versions": versions})
    except Exception:
        return jsonify({"versions": []})


@app.route("/api/settings/gist/restore", methods=["POST"])
@requires_auth
def api_settings_gist_restore():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    data = request.json or {}
    version = data.get("version")
    mode = data.get("mode", "merge")
    
    try:
        service = get_sync_service()
        result = service.restore_from_gist(version=version, mode=mode)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/rotate-key", methods=["POST"])
@requires_auth
def api_settings_rotate_key():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    try:
        with paas_db.get_db() as conn:
            rows = conn.execute("SELECT id, key, value_encrypted, scope, description, app_id FROM secrets").fetchall()
            
            old_key = paas_db.get_encryption_key()
            
            new_key = paas_db.AESGCM.generate_key(bit_length=256)
            key_path = paas_db.ENCRYPTION_KEY_PATH
            with open(key_path + ".backup", "wb") as f:
                f.write(old_key)
            
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            import base64 as b64
            
            old_aesgcm = AESGCM(old_key)
            new_aesgcm = AESGCM(new_key)
            
            reencrypted = 0
            for row in rows:
                try:
                    encrypted = row["value_encrypted"]
                    if encrypted:
                        data = b64.b64decode(encrypted)
                        nonce = data[:12]
                        ciphertext = data[12:]
                        plaintext = old_aesgcm.decrypt(nonce, ciphertext, None)
                        
                        new_nonce = secrets.token_bytes(12)
                        new_ciphertext = new_aesgcm.encrypt(new_nonce, plaintext, None)
                        new_encrypted = b64.b64encode(new_nonce + new_ciphertext).decode()
                        
                        conn.execute(
                            "UPDATE secrets SET value_encrypted = ? WHERE id = ?",
                            (new_encrypted, row["id"])
                        )
                        reencrypted += 1
                except Exception:
                    pass
            
            with open(key_path, "wb") as f:
                f.write(new_key)
            os.chmod(key_path, 0o600)
            
            conn.commit()
        
        return jsonify({"success": True, "reencrypted_count": reencrypted})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/settings/reset", methods=["POST"])
@requires_auth
def api_settings_reset():
    if not PAAS_DB_AVAILABLE:
        return jsonify({"success": False, "error": "PaaS database module not available"})
    
    try:
        with paas_db.get_db() as conn:
            conn.execute("DELETE FROM domains")
            conn.execute("DELETE FROM secrets")
            conn.execute("DELETE FROM databases")
            conn.execute("DELETE FROM deployment_steps")
            conn.execute("DELETE FROM deployments")
            conn.execute("DELETE FROM applications")
            conn.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


SETUP_COMPLETE_FILE = "/data/.setup_complete"


def is_setup_complete():
    return os.path.exists(SETUP_COMPLETE_FILE)


@app.route("/setup")
def setup_wizard():
    if is_setup_complete():
        return redirect(url_for("index"))
    return render_template("setup.html")


@app.route("/api/setup/credentials", methods=["POST"])
def api_setup_credentials():
    data = request.json or {}
    
    env_path = "/opt/dashboard/config/.env"
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    
    env_vars = {}
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    env_vars[key.strip()] = val.strip()
    
    if data.get("github_token"):
        env_vars["GITHUB_TOKEN"] = data["github_token"]
        global GITHUB_TOKEN
        GITHUB_TOKEN = data["github_token"]
    
    if data.get("cloudflare_api_token"):
        env_vars["CLOUDFLARE_API_TOKEN"] = data["cloudflare_api_token"]
        global CLOUDFLARE_API_TOKEN
        CLOUDFLARE_API_TOKEN = data["cloudflare_api_token"]
    
    if data.get("cloudflare_zone_id"):
        env_vars["CLOUDFLARE_ZONE_ID"] = data["cloudflare_zone_id"]
        global CLOUDFLARE_ZONE_ID
        CLOUDFLARE_ZONE_ID = data["cloudflare_zone_id"]
    
    if data.get("cloudflare_zone_name"):
        env_vars["CLOUDFLARE_ZONE_NAME"] = data["cloudflare_zone_name"]
        global CLOUDFLARE_ZONE_NAME
        CLOUDFLARE_ZONE_NAME = data["cloudflare_zone_name"]
    
    with open(env_path, "w") as f:
        for key, val in env_vars.items():
            f.write(f"{key}={val}\n")
    
    return jsonify({"success": True})


@app.route("/api/setup/complete", methods=["POST"])
def api_setup_complete():
    os.makedirs(os.path.dirname(SETUP_COMPLETE_FILE), exist_ok=True)
    with open(SETUP_COMPLETE_FILE, "w") as f:
        f.write(datetime.utcnow().isoformat())
    return jsonify({"success": True})


# ============================================================================
# Phase 3: Add-on Services
# ============================================================================

@app.route("/apps/<app_name>/services")
@requires_auth
def app_services_page(app_name):
    """Services management page for an application."""
    if not PAAS_DB_AVAILABLE:
        flash("PaaS database module not available", "error")
        return redirect(url_for("apps"))
    
    app = paas_db.get_application(name=app_name)
    if not app:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    # Get services for this app
    try:
        from services import get_service_manager
        manager = get_service_manager()
        services = manager.get_services_for_app(app_name)
    except ImportError:
        services = []
    
    return render_template("app_services.html",
        app_name=app_name,
        app=app,
        services=services
    )


# Register Phase 3 Services API routes
try:
    from api.services_routes import register_services_routes
    register_services_routes(app)
except ImportError as e:
    print(f"Warning: Could not register services routes: {e}")


if __name__ == "__main__":
    if WEBSOCKET_AVAILABLE and socketio:
        socketio.run(app, host="0.0.0.0", port=8080, debug=True, allow_unsafe_werkzeug=True)
    else:
        app.run(host="0.0.0.0", port=8080, debug=True)
