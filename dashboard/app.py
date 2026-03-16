from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
import yaml
import os
import subprocess
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

try:
    from nacl import encoding, public
    PYNACL_AVAILABLE = True
except ImportError:
    PYNACL_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

AUTH_USER = os.environ.get("DASHBOARD_USER", "admin")
AUTH_PASS = os.environ.get("DASHBOARD_PASS", "DbAdmin2026!")

ENV_FILE = "/opt/dashboard/config/.env"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

CLOUDFLARE_API_TOKEN = ""
CLOUDFLARE_ZONE_ID = ""
CLOUDFLARE_ZONE_NAME = ""

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

BASE_DIR = "/opt/dashboard"
DB_CONFIG_PATH = os.path.join(BASE_DIR, "config", "databases.yml")
APPS_CONFIG_PATH = os.path.join(BASE_DIR, "config", "applications.yml")
DOCS_PATH = os.path.join(BASE_DIR, "docs")

PG_HOST = os.environ.get("PG_HOST", "100.102.220.16")
PG_PORT = int(os.environ.get("PG_PORT", 5000))
PG_USER = os.environ.get("PG_USER", "patroni_superuser")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "2e7vBpaaVK4vTJzrKebC")

REDIS_HOST = os.environ.get("REDIS_HOST", "100.102.220.16")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk")

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://100.102.220.16:9090")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://100.102.220.16:3000")

ROUTERS = [
    {"name": "router-01", "ip": "100.102.220.16", "public_ip": "172.93.54.112"},
    {"name": "router-02", "ip": "100.116.175.9", "public_ip": "23.29.118.6"}
]

APP_SERVERS = [
    {"name": "re-db", "ip": "100.92.26.38", "public_ip": "208.87.128.115", "role": "App Server"},
    {"name": "re-node-02", "ip": "100.101.39.22", "public_ip": "23.29.118.8", "role": "App Server (ATL)"}
]

APP_PORT_RANGE = {"start": 8100, "end": 8199}
allocated_ports = {}

def get_next_port(app_name):
    applications = load_applications()
    used_ports = set()
    for app_data in applications.values():
        if app_data.get("port"):
            used_ports.add(app_data["port"])
    
    for port in range(APP_PORT_RANGE["start"], APP_PORT_RANGE["end"]):
        if port not in used_ports:
            return port
    return APP_PORT_RANGE["start"]


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


def configure_php_fpm_pool(app_name, server_ip):
    pool_config = f"""[{app_name}]
user = www-data
group = www-data
listen = /run/php/php8.5-fpm-{app_name}.sock
listen.owner = www-data
listen.group = www-data
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 5
pm.max_requests = 500
php_admin[value[disable_functions] = exec,passthru,shell_exec,system
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
    if os.path.exists(DB_CONFIG_PATH):
        with open(DB_CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f)
            return data.get("databases", {}) if data else {}
    return {}


def save_databases(databases):
    os.makedirs(os.path.dirname(DB_CONFIG_PATH), exist_ok=True)
    data = {"databases": databases}
    with open(DB_CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_applications():
    if os.path.exists(APPS_CONFIG_PATH):
        with open(APPS_CONFIG_PATH, "r") as f:
            data = yaml.safe_load(f)
            return data.get("applications", {}) if data else {}
    return {}


def save_applications(applications):
    os.makedirs(os.path.dirname(APPS_CONFIG_PATH), exist_ok=True)
    data = {"applications": applications}
    with open(APPS_CONFIG_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def ssh_command(server_ip, command, timeout=30):
    try:
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
             "-o", "BatchMode=yes", f"root@{server_ip}", command],
            capture_output=True, text=True, timeout=timeout
        )
        return {"success": result.returncode == 0, "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out"}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def clone_repo_to_servers(app_name, git_repo, servers, github_token=None):
    results = []
    
    clone_url = git_repo
    if github_token and "github.com" in git_repo:
        if git_repo.startswith("https://github.com/"):
            clone_url = git_repo.replace("https://github.com/", f"https://{github_token}@github.com/")
    
    for server in servers:
        app_dir = f"/opt/apps/{app_name}"
        
        check_result = ssh_command(server["ip"], f"test -d {app_dir} && echo exists")
        if "exists" in check_result.get("stdout", ""):
            results.append({"server": server["name"], "status": "exists", "message": f"Directory {app_dir} already exists"})
            continue
        
        mkdir_result = ssh_command(server["ip"], f"mkdir -p /opt/apps")
        if not mkdir_result["success"]:
            results.append({"server": server["name"], "status": "error", "message": f"Failed to create /opt/apps: {mkdir_result['stderr']}"})
            continue
        
        clone_result = ssh_command(server["ip"], f"cd /opt/apps && git clone {clone_url} {app_name}", timeout=120)
        if clone_result["success"]:
            results.append({"server": server["name"], "status": "cloned", "message": f"Cloned to {app_dir}"})
        else:
            results.append({"server": server["name"], "status": "error", "message": f"Clone failed: {clone_result['stderr']}"})
    
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
    clean_install = f"cd {app_dir} && rm -rf node_modules package-lock.json yarn.lock pnpm-lock.yaml && {install_cmd}"
    
    install_result = ssh_command(server_ip, clean_install, timeout=300)
    if not install_result["success"]:
        err = install_result.get('stderr') or install_result.get('stdout', 'Unknown error')[-500:]
        return {"success": False, "message": f"Install failed: {err}"}
    
    build_cmd = get_build_command(server_ip, app_dir, detected_tools)
    if not build_cmd:
        return {"success": True, "message": "No build script found, skipping build"}
    
    build_result = ssh_command(server_ip, f"cd {app_dir} && {build_cmd} 2>&1", timeout=300)
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
        
        if framework == "laravel":
            composer_cmd = f"cd {app_dir} && composer install --no-dev --optimize-autoloader 2>&1"
            composer_result = ssh_command(server["ip"], composer_cmd, timeout=300)
            
            if composer_result["success"]:
                build_result = run_frontend_build(server["ip"], app_dir)
                if not build_result["success"]:
                    results.append({"server": server["name"], "status": "error", "message": build_result["message"]})
                    continue
                
                env_result = ssh_command(server["ip"], f"cd {app_dir} && cp .env.example .env 2>/dev/null; php artisan key:generate 2>/dev/null")
                
                env_updates = [
                    f"sed -i 's/APP_ENV=.*/APP_ENV={environment}/' {app_dir}/.env",
                ]
                
                if environment == "staging":
                    env_updates.append(f"sed -i 's/APP_DEBUG=.*/APP_DEBUG=true/' {app_dir}/.env")
                else:
                    env_updates.append(f"sed -i 's/APP_DEBUG=.*/APP_DEBUG=false/' {app_dir}/.env")
                
                if db_config:
                    env_updates.extend([
                        f"sed -i 's/DB_HOST=.*/DB_HOST={db_config['host']}/' {app_dir}/.env",
                        f"sed -i 's/DB_PORT=.*/DB_PORT={db_config['port']}/' {app_dir}/.env",
                        f"sed -i 's/DB_DATABASE=.*/DB_DATABASE={db_config['database']}/' {app_dir}/.env",
                        f"sed -i 's/DB_USERNAME=.*/DB_USERNAME={db_config['username']}/' {app_dir}/.env",
                        f"sed -i 's/DB_PASSWORD=.*/DB_PASSWORD={db_config['password']}/' {app_dir}/.env",
                    ])
                if redis_config:
                    env_updates.extend([
                        f"sed -i 's/REDIS_HOST=.*/REDIS_HOST={redis_config['host']}/' {app_dir}/.env",
                        f"sed -i 's/REDIS_PASSWORD=.*/REDIS_PASSWORD={redis_config['password']}/' {app_dir}/.env",
                        f"sed -i 's/REDIS_PORT=.*/REDIS_PORT={redis_config['port']}/' {app_dir}/.env",
                    ])
                if app_url:
                    env_updates.extend([
                        f"sed -i 's|APP_URL=.*|APP_URL={app_url}|' {app_dir}/.env",
                        f"sed -i 's|ASSET_URL=.*|ASSET_URL={app_url}|' {app_dir}/.env 2>/dev/null || true",
                    ])
                ssh_command(server["ip"], " && ".join(env_updates))
                
                ssh_command(server["ip"], f"cd {app_dir} && php artisan storage:link 2>/dev/null; chown -R www-data:www-data {app_dir}")
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
            build_result = ssh_command(server["ip"], f"cd {app_dir} && go build -o bin/{app_name} . 2>&1", timeout=300)
            
            if build_result["success"]:
                results.append({"server": server["name"], "status": "built", "output": "Go binary built"})
            else:
                results.append({"server": server["name"], "status": "error", "message": build_result["stderr"][-500:] if build_result.get("stderr") else "Unknown error"})
    
        elif framework == "python":
            venv_path = f"{app_dir}/venv"
            venv_result = ssh_command(server["ip"], f"python3 -m venv {venv_path} 2>&1")
            
            if venv_result["success"]:
                requirements_check = ssh_command(server["ip"], f"test -f {app_dir}/requirements.txt && echo exists")
                pip_output = ""
                
                if "exists" in requirements_check.get("stdout", ""):
                    pip_result = ssh_command(server["ip"], f"{venv_path}/bin/pip install -r {app_dir}/requirements.txt 2>&1", timeout=300)
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
            env_vars["REDIS_URL"] = f"redis://:{redis_config['password']}@{redis_config['host']}:{redis_config['port']}/0"
    
    return {k: v for k, v in env_vars.items() if v is not None}


def create_systemd_service(app_name, framework, server_ip, db_url=None, redis_url=None, env_vars=None):
    if framework == "laravel":
        return {"success": True, "message": "Laravel uses nginx + PHP-FPM, not systemd service"}
    elif framework == "nextjs":
        service_content = f"""[Unit]
Description={app_name} Next.js Application
After=network.target

[Service]
Type=simple
User=node
Group=node
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
User=node
Group=node
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
User=www-data
Group=www-data
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
User=app
Group=app
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
    result = ssh_command(server_ip, f"echo '{escaped_content}' > {env_file} && chmod 600 {env_file}")
    
    return result


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
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
             "-o", "BatchMode=yes", f"root@{server['ip']}", "uptime -p 2>/dev/null || echo 'unreachable'"],
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
        
        if not db_name.replace("_", "").isalnum():
            flash("Database name must be alphanumeric (underscores allowed)", "error")
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
    return render_template("servers.html", servers=server_status, db_servers=DB_SERVERS, app_servers=APP_SERVERS, routers=ROUTERS)


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
        staging_env = "staging_env" in request.form
        create_db = "create_db" in request.form
        db_name = request.form.get("db_name", app_name).strip().lower()
        pool_size = int(request.form.get("db_pool_size", 20))
        create_redis = "create_redis" in request.form
        deploy_now = "deploy_now" in request.form
        
        if not app_name or not framework:
            flash("Application name and framework are required", "error")
            return redirect(url_for("create_app"))
        
        results = {"app_name": app_name, "framework": framework, "errors": [], "created": []}
        target_servers = [s["name"] for s in APP_SERVERS]
        
        applications = load_applications()
        if app_name in applications:
            flash(f"Application '{app_name}' already exists", "error")
            return redirect(url_for("create_app"))
        
        if create_db:
            try:
                db_admin = f"{app_name}_admin"
                db_password = secrets.token_urlsafe(16)
                
                conn = psycopg2.connect(
                    host=PG_HOST, port=PG_PORT, user=PG_USER,
                    password=PG_PASSWORD, database="postgres"
                )
                conn.autocommit = True
                cur = conn.cursor()
                
                cur.execute("CREATE USER {} WITH PASSWORD %s CREATEDB;".format(db_admin), (db_password,))
                
                cur.execute("SELECT rolpassword FROM pg_authid WHERE rolname = %s;", (db_admin,))
                admin_hash = cur.fetchone()[0]
                
                cur.execute("CREATE DATABASE {} OWNER {};".format(db_name, db_admin))
                
                if staging_env:
                    staging_db_name = f"{db_name}_staging"
                    cur.execute("CREATE DATABASE {} OWNER {};".format(staging_db_name, db_admin))
                
                cur.close()
                conn.close()
                
                databases = load_databases()
                databases[db_name] = {
                    "name": db_name,
                    "description": app_description or f"{app_name} database",
                    "owner": db_admin,
                    "password": db_password,
                    "users": [{"name": db_admin, "password": db_password, "password_hash": admin_hash, "roles": ["CREATEDB"]}],
                    "pgbouncer_pool_size": pool_size,
                    "pgbouncer_max_clients": pool_size * 10,
                    "app": app_name
                }
                save_databases(databases)
                
                results["created"].append(f"Database: {db_name}")
                if staging_env:
                    results["created"].append(f"Staging database: {db_name}_staging")
                results["db_admin"] = db_admin
                results["db_password"] = db_password
                
            except Exception as e:
                results["errors"].append(f"Database creation failed: {str(e)}")
        
        port = get_next_port(app_name)
        
        if git_repo and deploy_now:
            results["clone_results"] = clone_repo_to_servers(app_name, git_repo, APP_SERVERS, GITHUB_TOKEN)
            for r in results["clone_results"]:
                if r["status"] == "cloned":
                    results["created"].append(f"Cloned repo to {r['server']}")
                elif r["status"] == "exists":
                    results["created"].append(f"Repo directory exists on {r['server']}")
                else:
                    results["errors"].append(f"{r['server']}: {r['message']}")
            
            db_config = None
            redis_config = None
            if create_db and results.get("db_password"):
                db_config = {
                    "host": PG_HOST,
                    "port": str(PG_PORT),
                    "database": db_name,
                    "username": f"{app_name}_admin",
                    "password": results["db_password"]
                }
            if create_redis:
                redis_config = {
                    "host": REDIS_HOST,
                    "port": str(REDIS_PORT),
                    "password": REDIS_PASSWORD
                }
            
            results["setup_results"] = run_framework_setup(app_name, framework, APP_SERVERS, db_config, redis_config, app_url=f"https://{app_name}.xotec.io")
            for r in results["setup_results"]:
                if r["status"] in ["composer_installed", "npm_installed", "built", "venv_created"]:
                    results["created"].append(f"Setup on {r['server']}: {r.get('output', r['status'])}")
                else:
                    results["errors"].append(f"Setup on {r['server']}: {r.get('message', 'Unknown error')}")
            
            results["server_results"] = []
            for server in APP_SERVERS:
                if framework == "laravel":
                    app_result = setup_laravel_app(app_name, server["ip"], port)
                    if app_result["success"]:
                        results["server_results"].append({"server": server["name"], "status": "configured", "port": port})
                        results["created"].append(f"nginx + PHP-FPM on {server['name']}:{port}")
                    else:
                        results["server_results"].append({"server": server["name"], "status": "error", "message": app_result.get("error", "Unknown error")})
                        results["errors"].append(f"App setup on {server['name']}: {app_result.get('error', 'Unknown error')}")
                else:
                    db_url = None
                    redis_url = None
                    if create_db and results.get("db_password"):
                        db_url = f"postgres://{results['db_admin']}:{results['db_password']}@{PG_HOST}:6432/{db_name}"
                    if create_redis:
                        redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0"
                    
                    env_vars = {
                        "APP_NAME": app_name,
                        "APP_ENV": "production",
                        "NODE_ENV": "production"
                    }
                    if db_url:
                        env_vars["DATABASE_URL"] = db_url
                    if redis_url:
                        env_vars["REDIS_URL"] = redis_url
                    
                    svc_result = create_systemd_service(app_name, framework, server["ip"], db_url, redis_url, env_vars)
                    if svc_result["success"]:
                        results["server_results"].append({"server": server["name"], "status": "created"})
                        results["created"].append(f"Systemd service on {server['name']}")
                    else:
                        results["server_results"].append({"server": server["name"], "status": "error", "message": svc_result.get("stderr", "Unknown error")})
                        results["errors"].append(f"Systemd service on {server['name']}: {svc_result.get('stderr', 'Unknown error')}")
        
        applications[app_name] = {
            "name": app_name,
            "description": app_description,
            "framework": framework,
            "git_repo": git_repo,
            "target_servers": target_servers,
            "staging_env": staging_env,
            "database": db_name if create_db else None,
            "db_user": f"{app_name}_admin" if create_db else None,
            "db_password": results.get("db_password") if create_db else None,
            "redis_enabled": create_redis,
            "port": port if framework == "laravel" else None,
            "domains": [],
            "created_at": datetime.utcnow().isoformat()
        }
        save_applications(applications)
        results["created"].append(f"Application: {app_name}")
        
        workflow = generate_github_workflow(framework, app_name, target_servers, staging_env, create_db, db_name)
        applications[app_name]["deploy_workflow"] = workflow
        save_applications(applications)
        
        if git_repo and deploy_now and GITHUB_TOKEN:
            db_pwd = results.get("db_password") if create_db else None
            redis_url = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/0" if create_redis else None
            secrets_result = push_app_secrets_to_github(app_name, applications[app_name], db_pwd, redis_url)
            results["secrets_result"] = secrets_result
            if secrets_result["success"]:
                results["created"].append(f"GitHub secrets: {', '.join(secrets_result['pushed'])}")
            else:
                results["errors"].append(f"GitHub secrets: {secrets_result.get('error', 'Unknown error')}")
        
        workflow = generate_github_workflow(framework, app_name, target_servers, staging_env, create_db, db_name)
        
        return render_template("create_app_result.html", results=results, 
            app_name=app_name, framework=framework, git_repo=git_repo,
            target_servers=target_servers, staging_env=staging_env,
            create_db=create_db, db_name=db_name, create_redis=create_redis,
            workflow=workflow, app_servers=APP_SERVERS)
    
    return render_template("create_app.html", app_servers=APP_SERVERS)


@app.route("/apps/<app_name>/delete", methods=["POST"])
@requires_auth
def delete_app(app_name):
    applications = load_applications()
    
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    app = applications[app_name]
    delete_db = request.form.get("delete_database") == "true"
    
    # Delete from app servers
    for server in APP_SERVERS:
        server_ip = server["ip"]
        
        # Remove app directory
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}")
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}-staging")
        
        # Remove nginx configs
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}-staging")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}-staging")
        
        # Remove PHP-FPM pool
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}.conf")
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}-staging.conf")
        
        # Reload services
        ssh_command(server_ip, "systemctl reload nginx || true")
        ssh_command(server_ip, "systemctl reload php8.5-fpm || true")
    
    # Delete domains from routers (keep DNS and WAF rules)
    for domain in app.get("domains", []):
        domain_name = domain.get("name")
        
        # Remove from HAProxy
        for router in ROUTERS:
            ssh_command(router["ip"], f"rm -f /etc/haproxy/domains/{domain_name}.cfg")
            ssh_command(router["ip"], f"rm -f /etc/haproxy/certs/{domain_name}.pem")
    
    # Reload HAProxy on all routers
    for router in ROUTERS:
        ssh_command(router["ip"], "systemctl reload haproxy || true")
    
    # Delete databases
    if delete_db and app.get("database"):
        db_name = app["database"]
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, database="postgres"
            )
            conn.autocommit = True
            cur = conn.cursor()
            
            cur.execute("DROP DATABASE IF EXISTS {};".format(db_name))
            
            staging_db = f"{db_name}_staging"
            cur.execute("DROP DATABASE IF EXISTS {};".format(staging_db))
            
            for user in [f"{app_name}_admin", f"{app_name}_app"]:
                cur.execute("DROP USER IF EXISTS {};".format(user))
            
            cur.close()
            conn.close()
            
            databases = load_databases()
            if db_name in databases:
                del databases[db_name]
                save_databases(databases)
            
            flash(f"Database '{db_name}' deleted", "success")
        except Exception as e:
            flash(f"Failed to delete database: {str(e)}", "error")
    
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
    
    # Remove staging from app servers
    for server in APP_SERVERS:
        server_ip = server["ip"]
        
        # Remove staging directory
        ssh_command(server_ip, f"rm -rf /opt/apps/{app_name}-staging")
        
        # Remove staging nginx config
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-available/{app_name}-staging")
        ssh_command(server_ip, f"rm -f /etc/nginx/sites-enabled/{app_name}-staging")
        
        # Remove staging PHP-FPM pool
        ssh_command(server_ip, f"rm -f /etc/php/8.5/fpm/pool.d/{app_name}-staging.conf")
        
        ssh_command(server_ip, "systemctl reload nginx || true")
        ssh_command(server_ip, "systemctl reload php8.5-fpm || true")
    
    # Remove staging domains from HAProxy (keep DNS and WAF rules)
    staging_domains = [d for d in app.get("domains", []) if d.get("type") == "staging"]
    for domain in staging_domains:
        domain_name = domain.get("name")
        
        # Remove from HAProxy
        for router in ROUTERS:
            ssh_command(router["ip"], f"rm -f /etc/haproxy/domains/{domain_name}.cfg")
            ssh_command(router["ip"], f"rm -f /etc/haproxy/certs/{domain_name}.pem")
    
    # Reload HAProxy
    for router in ROUTERS:
        ssh_command(router["ip"], "systemctl reload haproxy || true")
    
    # Drop staging database
    if app.get("database"):
        staging_db = f"{app['database']}_staging"
        try:
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT, user=PG_USER,
                password=PG_PASSWORD, database="postgres"
            )
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("DROP DATABASE IF EXISTS {};".format(staging_db))
            cur.close()
            conn.close()
        except Exception as e:
            flash(f"Failed to drop staging database: {str(e)}", "warning")
    
    # Remove staging domains from app config
    app["domains"] = [d for d in app.get("domains", []) if d.get("type") != "staging"]
    applications[app_name] = app
    save_applications(applications)
    
    flash(f"Staging environment for '{app_name}' deleted", "success")
    return redirect(url_for("app_status", app_name=app_name))


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
                    "password": REDIS_PASSWORD
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


def provision_domain_on_routers(domain, app_name, app_port, www_domain=None, is_staging=False, git_repo=None, git_branch="main"):
    results = []
    
    for router in ROUTERS:
        cmd = f"/opt/scripts/provision-domain.sh {domain} {app_name} {app_port}"
        if www_domain:
            cmd += f" --www {www_domain}"
        if is_staging:
            cmd += " --staging"
        if git_repo:
            cmd += f" --repo {git_repo}"
        if git_branch:
            cmd += f" --branch {git_branch}"
        
        result = ssh_command(router["ip"], cmd)
        results.append({
            "router": router["name"],
            "success": result.get("returncode", 1) == 0,
            "output": result.get("stdout", ""),
            "error": result.get("stderr", "")
        })
    
    return results


def remove_domain_from_routers(domain):
    results = []
    
    for router in ROUTERS:
        rm_cert = ssh_command(router["ip"], f"rm -f /etc/haproxy/certs/{domain}.pem")
        rm_registry = ssh_command(router["ip"], f"sed -i '/^{domain}=/d' /etc/haproxy/domains/registry.conf")
        rebuild = ssh_command(router["ip"], "/opt/scripts/provision-domain.sh --rebuild 2>/dev/null || systemctl reload haproxy")
        results.append({
            "router": router["name"],
            "success": rm_cert.get("returncode", 1) == 0
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
            
            app_port = app.get("port", 8100)
            domains = app.get("domains", [])
            provisioned_domains = []
            
            for config in domain_configs:
                base_domain = config.get("domain")
                if not base_domain:
                    continue
                
                zone_id = None
                for z in cf_zones:
                    if z["name"] == base_domain:
                        zone_id = z["id"]
                        break
                
                # Production
                prod_config = config.get("production", {})
                prod_type = prod_config.get("type", "root")
                prod_prefix = prod_config.get("prefix", "").strip().lower()
                
                if prod_type == "root":
                    prod_domain = base_domain
                    www_domain = f"www.{base_domain}"
                else:
                    prod_domain = f"{prod_prefix or 'www'}.{base_domain}"
                    www_domain = None
                
                if not any(d.get("name") == prod_domain for d in domains):
                    # Create DNS records
                    dns_success = False
                    if zone_id and CLOUDFLARE_API_TOKEN:
                        if prod_type == "root":
                            # Root domain
                            cf_create_dns_record("@", ROUTERS[0]["public_ip"], zone_id=zone_id)
                            cf_create_dns_record("@", ROUTERS[1]["public_ip"], zone_id=zone_id)
                            # www subdomain (redirects to root)
                            cf_create_dns_record("www", ROUTERS[0]["public_ip"], zone_id=zone_id)
                            cf_create_dns_record("www", ROUTERS[1]["public_ip"], zone_id=zone_id)
                        else:
                            cf_create_dns_record(prod_prefix, ROUTERS[0]["public_ip"], zone_id=zone_id)
                            cf_create_dns_record(prod_prefix, ROUTERS[1]["public_ip"], zone_id=zone_id)
                        dns_success = True
                    
                    # SSL for production domain
                    ssl_results = provision_domain_on_routers(prod_domain, app_name, app_port, www_domain=www_domain)
                    ssl_success = all(r["success"] for r in ssl_results)
                    
                    # Update APP_URL for Laravel apps
                    if ssl_success and prod_type == "root":
                        update_app_url(app_name, f"https://{prod_domain}")
                    
                    # Security
                    if enable_security and zone_id:
                        cf_create_security_rules(prod_domain, zone_id)
                    
                    domains.append({
                        "name": prod_domain,
                        "type": "production",
                        "base_domain": base_domain,
                        "ssl_enabled": True,
                        "provisioned": ssl_success,
                        "dns_provisioned": dns_success,
                        "security_enabled": enable_security,
                        "www_redirect": prod_type == "root",
                        "created_at": datetime.utcnow().isoformat()
                    })
                    provisioned_domains.append(prod_domain)
                    
                    # Add www domain entry for tracking
                    if www_domain:
                        domains.append({
                            "name": www_domain,
                            "type": "www_redirect",
                            "base_domain": base_domain,
                            "redirect_to": prod_domain,
                            "ssl_enabled": True,
                            "provisioned": ssl_success,
                            "dns_provisioned": dns_success,
                            "created_at": datetime.utcnow().isoformat()
                        })
                        provisioned_domains.append(www_domain)
                
                # Staging
                staging_config = config.get("staging", {})
                staging_type = staging_config.get("type", "subdomain")
                staging_prefix = staging_config.get("prefix", "staging").strip().lower()
                staging_password = staging_config.get("password", "") or secrets.token_urlsafe(12)
                
                if staging_type == "subdomain":
                    staging_domain = f"{staging_prefix}.{base_domain}"
                    staging_app_name = f"{app_name}-staging"
                    staging_port = app_port + 1 if app_port else 8101
                    git_repo = app.get("git_repo")
                    
                    if not any(d.get("name") == staging_domain for d in domains):
                        # DNS
                        dns_success = False
                        if zone_id and CLOUDFLARE_API_TOKEN:
                            cf_create_dns_record(f"{staging_prefix}", ROUTERS[0]["public_ip"], zone_id=zone_id)
                            cf_create_dns_record(f"{staging_prefix}", ROUTERS[1]["public_ip"], zone_id=zone_id)
                            dns_success = True
                        
                        # SSL with staging app name and repo setup
                        ssl_results = provision_domain_on_routers(
                            staging_domain, staging_app_name, staging_port,
                            is_staging=True, git_repo=git_repo, git_branch="staging"
                        )
                        ssl_success = all(r["success"] for r in ssl_results)
                        
                        # Security
                        if enable_security and zone_id:
                            cf_create_security_rules(staging_domain, zone_id)
                        
                        domains.append({
                            "name": staging_domain,
                            "type": "staging",
                            "base_domain": base_domain,
                            "app_name": staging_app_name,
                            "port": staging_port,
                            "ssl_enabled": True,
                            "provisioned": ssl_success,
                            "dns_provisioned": dns_success,
                            "password": staging_password,
                            "security_enabled": enable_security,
                            "database": f"{app.get('database', app_name)}_staging" if app.get('database') else None,
                            "git_branch": "staging",
                            "git_repo": git_repo,
                            "created_at": datetime.utcnow().isoformat()
                        })
                        provisioned_domains.append(staging_domain)
                
                # Additional CNAMEs
                cnames = config.get("cnames", [])
                for cname in cnames:
                    cname = cname.strip().lower()
                    if not cname:
                        continue
                    
                    cname_domain = f"{cname}.{base_domain}"
                    
                    if not any(d.get("name") == cname_domain for d in domains):
                        # DNS
                        dns_success = False
                        if zone_id and CLOUDFLARE_API_TOKEN:
                            cf_create_dns_record(cname, ROUTERS[0]["public_ip"], zone_id=zone_id)
                            cf_create_dns_record(cname, ROUTERS[1]["public_ip"], zone_id=zone_id)
                            dns_success = True
                        
                        # SSL
                        ssl_results = provision_domain_on_routers(cname_domain, f"{app_name}-{cname}", app_port)
                        ssl_success = all(r["success"] for r in ssl_results)
                        
                        domains.append({
                            "name": cname_domain,
                            "type": "cname",
                            "base_domain": base_domain,
                            "ssl_enabled": True,
                            "provisioned": ssl_success,
                            "dns_provisioned": dns_success,
                            "security_enabled": enable_security,
                            "created_at": datetime.utcnow().isoformat()
                        })
                        provisioned_domains.append(cname_domain)
            
            if provisioned_domains:
                app["domains"] = domains
                applications[app_name] = app
                save_applications(applications)
                flash(f"Provisioned: {', '.join(provisioned_domains)}", "success")
            else:
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
            
            app_port = app.get("port", 8100)
            
            domain_data = {
                "name": domain,
                "type": domain_type,
                "ssl_enabled": ssl_enabled,
                "created_at": datetime.utcnow().isoformat()
            }
            
            if domain_type == "staging":
                domain_data["password"] = staging_password
            
            if ssl_enabled:
                provision_results = provision_domain_on_routers(domain, app_name, app_port)
                all_success = all(r["success"] for r in provision_results)
                domain_data["provisioned"] = all_success
                
                if all_success:
                    flash(f"Domain {domain} provisioned with SSL", "success")
                else:
                    errors = [f"{r['router']}: {r.get('error', 'Unknown error')}" for r in provision_results if not r["success"]]
                    flash(f"Domain added but SSL failed: {'; '.join(errors)}", "warning")
            else:
                domain_data["provisioned"] = False
                flash(f"Domain {domain} added (SSL not enabled)", "success")
            
            domains.append(domain_data)
            app["domains"] = domains
            applications[app_name] = app
            save_applications(applications)
            
            return redirect(url_for("app_domains", app_name=app_name))
    
    return render_template("app_domains.html",
        app_name=app_name,
        app=app,
        app_servers=APP_SERVERS,
        routers=ROUTERS,
        cf_configured=bool(CLOUDFLARE_API_TOKEN),
        cf_zones=cf_zones,
        cf_zone_name=CLOUDFLARE_ZONE_NAME)


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
    
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER,
            password=PG_PASSWORD, database="postgres"
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("DROP DATABASE IF EXISTS {};".format(db_name))
        
        staging_db = f"{db_name}_staging"
        cur.execute("DROP DATABASE IF EXISTS {};".format(staging_db))
        
        db_info = databases[db_name]
        for user in db_info.get("users", []):
            cur.execute("DROP USER IF EXISTS {};".format(user["name"]))
        
        cur.close()
        conn.close()
        
        del databases[db_name]
        save_databases(databases)
        
        flash(f"Database '{db_name}' deleted", "success")
    except Exception as e:
        flash(f"Failed to delete database: {str(e)}", "error")
    
    return redirect(url_for("databases"))


def generate_github_workflow(framework, app_name, target_servers, staging_env, create_db, db_name):
    deploy_servers = [
        {"name": "re-db", "ip": "100.92.26.38"},
        {"name": "re-node-02", "ip": "100.101.39.22"}
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
    
    return f"""name: Deploy {app_name}

on:
  push:
    branches:
      - main{'\n      - staging' if staging_env else ''}

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


@app.route("/api/alerts")
def api_alerts():
    alerts = get_prometheus_alerts()
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/databases")
def api_databases():
    return jsonify({"databases": load_databases(), "postgres_databases": get_pg_databases()})


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


def delete_app_secret(app_name, key):
    return delete_app_secret_module(app_name, key)


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


@app.route("/apps/<app_name>/secrets")
@requires_auth
def app_secrets(app_name):
    applications = load_applications()
    if app_name not in applications:
        flash("Application not found", "error")
        return redirect(url_for("apps"))
    
    secrets = list_app_secrets(app_name)
    app = applications[app_name]
    
    return render_template("app_secrets.html",
        app_name=app_name,
        app=app,
        secrets=secrets)


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
        
        if not key or not value:
            flash("Key and value are required", "error")
            return redirect(url_for("add_app_secret", app_name=app_name))
        
        if not key.replace("_", "").isalnum():
            flash("Key must be alphanumeric with underscores only", "error")
            return redirect(url_for("add_app_secret", app_name=app_name))
        
        result = set_app_secret(app_name, key, value, description)
        if result["success"]:
            flash(f"Secret '{key}' saved for {app_name}", "success")
            return redirect(url_for("app_secrets", app_name=app_name))
        else:
            flash(f"Failed to save secret: {result.get('error', 'Unknown error')}", "error")
    
    return render_template("secret_form.html", secret_type="app", app_name=app_name)


@app.route("/apps/<app_name>/secrets/<key>/delete", methods=["POST"])
@requires_auth
def delete_app_secret_route(app_name, key):
    result = delete_app_secret(app_name, key)
    if result["success"]:
        flash(f"Secret '{key}' deleted", "success")
    else:
        flash(f"Failed to delete secret: {result.get('error', 'Unknown error')}", "error")
    return redirect(url_for("app_secrets", app_name=app_name))


@app.route("/apps/<app_name>/secrets/<key>/reveal")
@requires_auth
def reveal_app_secret(app_name, key):
    value = get_app_secret(app_name, key)
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
    
    if not key or not value:
        return jsonify({"success": False, "error": "Key and value required"}), 400
    
    result = set_app_secret(app_name, key, value, description)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)