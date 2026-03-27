"""
Framework Detection and Configuration Service.

This module provides framework detection, configuration management,
and port allocation for multi-framework PaaS deployments.

Supported Frameworks:
- Laravel (PHP)
- Next.js (Node.js)
- SvelteKit (Node.js)
- Python (Flask/Django)
- Go

Port Allocation:
- Laravel: 8100-8199 (production), 9200-9299 (staging)
- Next.js: 8200-8299 (production), 9300-9399 (staging)
- SvelteKit: 8300-8399 (production), 9400-9499 (staging)
- Python: 8400-8499 (production), 9500-9599 (staging)
- Go: 8500-8599 (production), 9600-9699 (staging)
"""

import os
import json
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field


class FrameworkDetectionError(Exception):
    """Raised when framework detection fails."""
    pass


@dataclass
class FrameworkConfig:
    """Configuration for a specific framework."""
    name: str
    display_name: str
    runtime: str
    detect_files: List[str]
    detect_packages: List[str] = field(default_factory=list)
    install_cmd: str = ""
    build_cmd: str = ""
    migrate_cmd: str = ""
    start_cmd: str = ""
    health_path: str = "/"
    health_port_offset: int = 0
    env_prefix: str = ""
    env_template: Dict[str, str] = field(default_factory=dict)
    requires_database: bool = True
    supports_redis: bool = True
    default_branch: str = "main"
    package_manager: str = "auto"


FRAMEWORK_CONFIGS: Dict[str, Dict[str, Any]] = {
    "laravel": {
        "display_name": "Laravel",
        "runtime": "nginx+php-fpm",
        "detect_files": ["composer.json", "artisan"],
        "detect_packages": ["laravel/framework"],
        "install_cmd": "composer install --no-interaction --optimize-autoloader --no-dev",
        "build_cmd": "npm ci && npm run build",
        "migrate_cmd": "php artisan migrate --force",
        "start_cmd": "php artisan config:cache && php artisan route:cache && php artisan view:cache",
        "health_path": "/",
        "health_port_offset": 0,
        "env_prefix": "",
        "env_template": {
            "APP_ENV": "{environment}",
            "APP_DEBUG": "{debug}",
            "APP_KEY": "",
            "APP_URL": "{app_url}",
            "DB_CONNECTION": "pgsql",
            "DB_HOST": "{db_host}",
            "DB_PORT": "{db_port}",
            "DB_DATABASE": "{db_name}",
            "DB_USERNAME": "{db_user}",
            "DB_PASSWORD": "{db_password}",
        },
        "requires_database": True,
        "supports_redis": True,
        "default_branch": "main",
        "package_manager": "composer",
    },
    "nextjs": {
        "display_name": "Next.js",
        "runtime": "systemd+node",
        "detect_files": ["package.json", "next.config.js", "next.config.mjs"],
        "detect_packages": ["next"],
        "install_cmd": "npm ci",
        "build_cmd": "npm run build",
        "migrate_cmd": "",
        "start_cmd": "npm start",
        "health_path": "/api/health",
        "health_port_offset": 0,
        "env_prefix": "NEXT_PUBLIC_",
        "env_template": {
            "NODE_ENV": "{environment}",
            "NEXT_PUBLIC_URL": "{app_url}",
            "DATABASE_URL": "{database_url}",
            "REDIS_URL": "{redis_url}",
        },
        "requires_database": False,
        "supports_redis": True,
        "default_branch": "main",
        "package_manager": "npm",
    },
    "svelte": {
        "display_name": "SvelteKit",
        "runtime": "systemd+node",
        "detect_files": ["package.json", "svelte.config.js"],
        "detect_packages": ["@sveltejs/kit"],
        "install_cmd": "npm ci",
        "build_cmd": "npm run build",
        "migrate_cmd": "",
        "start_cmd": "npm start",
        "health_path": "/",
        "health_port_offset": 0,
        "env_prefix": "PUBLIC_",
        "env_template": {
            "NODE_ENV": "{environment}",
            "PUBLIC_URL": "{app_url}",
            "DATABASE_URL": "{database_url}",
            "REDIS_URL": "{redis_url}",
        },
        "requires_database": False,
        "supports_redis": True,
        "default_branch": "main",
        "package_manager": "npm",
    },
    "python": {
        "display_name": "Python (Flask/Django)",
        "runtime": "systemd+gunicorn",
        "detect_files": ["requirements.txt", "pyproject.toml", "setup.py"],
        "detect_packages": ["flask", "django", "fastapi"],
        "install_cmd": "python3 -m venv venv && ./venv/bin/pip install -r requirements.txt",
        "build_cmd": "",
        "migrate_cmd": "./venv/bin/python manage.py migrate",
        "start_cmd": "./venv/bin/gunicorn --bind 0.0.0.0:{port} app:app",
        "health_path": "/health",
        "health_port_offset": 0,
        "env_prefix": "",
        "env_template": {
            "APP_ENV": "{environment}",
            "FLASK_ENV": "{flask_env}",
            "DJANGO_SETTINGS_MODULE": "{django_settings}",
            "DATABASE_URL": "{database_url}",
            "REDIS_URL": "{redis_url}",
        },
        "requires_database": True,
        "supports_redis": True,
        "default_branch": "main",
        "package_manager": "pip",
    },
    "go": {
        "display_name": "Go",
        "runtime": "systemd+binary",
        "detect_files": ["go.mod", "go.sum", "main.go"],
        "detect_packages": [],
        "install_cmd": "go mod download",
        "build_cmd": "go build -o bin/{app_name} .",
        "migrate_cmd": "",
        "start_cmd": "./bin/{app_name}",
        "health_path": "/health",
        "health_port_offset": 0,
        "env_prefix": "",
        "env_template": {
            "APP_ENV": "{environment}",
            "DATABASE_URL": "{database_url}",
            "REDIS_URL": "{redis_url}",
        },
        "requires_database": True,
        "supports_redis": True,
        "default_branch": "main",
        "package_manager": "go",
    },
}

# Port allocation ranges per framework
FRAMEWORK_PORT_RANGES: Dict[str, Dict[str, Dict[str, int]]] = {
    "laravel": {
        "production": {"start": 8100, "end": 8199},
        "staging": {"start": 9200, "end": 9299},
    },
    "nextjs": {
        "production": {"start": 8200, "end": 8299},
        "staging": {"start": 9300, "end": 9399},
    },
    "svelte": {
        "production": {"start": 8300, "end": 8399},
        "staging": {"start": 9400, "end": 9499},
    },
    "python": {
        "production": {"start": 8400, "end": 8499},
        "staging": {"start": 9500, "end": 9599},
    },
    "go": {
        "production": {"start": 8500, "end": 8599},
        "staging": {"start": 9600, "end": 9699},
    },
}


def detect_framework_from_files(files: List[str]) -> Optional[str]:
    """
    Detect framework from a list of files present in the repository.
    
    Args:
        files: List of filenames present in the repository root
        
    Returns:
        Framework name or None if not detected
    """
    file_set = set(f.lower() for f in files)
    
    # Check for Laravel (highest priority for PHP apps)
    if "artisan" in file_set or "composer.json" in file_set:
        return "laravel"
    
    # Check for Next.js
    if "next.config.js" in file_set or "next.config.mjs" in file_set:
        return "nextjs"
    
    # Check for SvelteKit
    if "svelte.config.js" in file_set:
        return "svelte"
    
    # Check for Go
    if "go.mod" in file_set or "main.go" in file_set:
        return "go"
    
    # Check for Python
    python_files = {"requirements.txt", "pyproject.toml", "setup.py"}
    if file_set & python_files:
        return "python"
    
    # Check for package.json with framework detection
    if "package.json" in file_set:
        # This will need to be analyzed further
        return "nextjs"  # Default for Node.js apps
    
    return None


def detect_framework_from_package_json(package_json_content: str) -> Optional[str]:
    """
    Detect framework from package.json content.
    
    Args:
        package_json_content: JSON content of package.json
        
    Returns:
        Framework name or None if not detected
    """
    try:
        pkg = json.loads(package_json_content)
        dependencies = pkg.get("dependencies", {})
        dev_dependencies = pkg.get("devDependencies", {})
        all_deps = {**dependencies, **dev_dependencies}
        
        # Check for Next.js
        if "next" in all_deps:
            return "nextjs"
        
        # Check for SvelteKit
        if "@sveltejs/kit" in all_deps:
            return "svelte"
        
        # Check for Nuxt (Vue.js)
        if "nuxt" in all_deps:
            return "svelte"  # Treat Nuxt similar to Svelte for now
        
        # Check for Vite + React/Vue (SPA)
        if "vite" in all_deps:
            return "nextjs"  # Treat SPAs similar to Next.js
        
        # Default for Node.js apps
        if dependencies or dev_dependencies:
            return "nextjs"
            
    except json.JSONDecodeError:
        pass
    
    return None


def detect_framework(app_path: str, ssh_command_func=None) -> str:
    """
    Detect framework from an application directory.
    
    This function checks for characteristic files and package dependencies
    to determine the framework type.
    
    Args:
        app_path: Path to the application directory on the server
        ssh_command_func: Function to execute SSH commands (server_ip, command) -> result
        
    Returns:
        Framework name string
        
    Raises:
        FrameworkDetectionError: If framework cannot be detected
    """
    if not ssh_command_func:
        raise FrameworkDetectionError("SSH command function required for detection")
    
    # List of files to check for detection
    detection_files = [
        "artisan",
        "composer.json", 
        "package.json",
        "next.config.js",
        "next.config.mjs",
        "svelte.config.js",
        "go.mod",
        "main.go",
        "requirements.txt",
        "pyproject.toml",
        "setup.py",
    ]
    
    # Check which files exist
    existing_files = []
    for filename in detection_files:
        check_cmd = f"test -f {app_path}/{filename} && echo exists"
        # Note: ssh_command_func should be called with server_ip
        # For this function, we assume the caller handles the server context
        result = ssh_command_func(f"test -f {app_path}/{filename} 2>/dev/null && echo {filename}")
        if result.get("success") and filename in result.get("stdout", ""):
            existing_files.append(filename)
    
    if not existing_files:
        raise FrameworkDetectionError(
            f"Could not detect framework: no recognized files found in {app_path}"
        )
    
    # Detect from files
    detected = detect_framework_from_files(existing_files)
    
    # If we have package.json but no specific framework detected, analyze it
    if detected in ["nextjs", None] and "package.json" in existing_files:
        pkg_result = ssh_command_func(f"cat {app_path}/package.json 2>/dev/null")
        if pkg_result.get("success"):
            pkg_detected = detect_framework_from_package_json(pkg_result.get("stdout", "{}"))
            if pkg_detected:
                detected = pkg_detected
    
    if not detected:
        # Default to nextjs for Node.js apps, python for others
        if "package.json" in existing_files:
            detected = "nextjs"
        else:
            raise FrameworkDetectionError(
                f"Could not determine framework from files: {existing_files}"
            )
    
    return detected


def get_framework_config(framework: str) -> Dict[str, Any]:
    """
    Get configuration for a specific framework.
    
    Args:
        framework: Framework name
        
    Returns:
        Dictionary with framework configuration
        
    Raises:
        ValueError: If framework is not supported
    """
    if framework not in FRAMEWORK_CONFIGS:
        raise ValueError(f"Unsupported framework: {framework}. "
                        f"Supported: {', '.join(FRAMEWORK_CONFIGS.keys())}")
    
    return FRAMEWORK_CONFIGS[framework].copy()


def get_framework_port(framework: str, environment: str = "production", 
                       existing_ports: set = None) -> int:
    """
    Get the next available port for a framework and environment.
    
    Args:
        framework: Framework name
        environment: "production" or "staging"
        existing_ports: Set of already allocated ports
        
    Returns:
        Next available port number
    """
    if framework not in FRAMEWORK_PORT_RANGES:
        # Fall back to default Laravel range
        framework = "laravel"
    
    port_range = FRAMEWORK_PORT_RANGES[framework].get(
        environment, 
        FRAMEWORK_PORT_RANGES[framework]["production"]
    )
    
    start_port = port_range["start"]
    end_port = port_range["end"]
    
    if existing_ports:
        for port in range(start_port, end_port + 1):
            if port not in existing_ports:
                return port
    
    return start_port


def get_all_frameworks() -> List[str]:
    """
    Get list of all supported frameworks.
    
    Returns:
        List of framework names
    """
    return list(FRAMEWORK_CONFIGS.keys())


def validate_framework(framework: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a framework is supported.
    
    Args:
        framework: Framework name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not framework:
        return False, "Framework name is required"
    
    if framework not in FRAMEWORK_CONFIGS:
        return False, f"Unsupported framework '{framework}'. Supported: {', '.join(FRAMEWORK_CONFIGS.keys())}"
    
    return True, None


def get_runtime_type(framework: str) -> str:
    """
    Get the runtime type for a framework.
    
    Args:
        framework: Framework name
        
    Returns:
        Runtime type string (e.g., "nginx+php-fpm", "systemd+node")
    """
    config = get_framework_config(framework)
    return config.get("runtime", "systemd+node")


def get_health_check_config(framework: str, port: int) -> Dict[str, Any]:
    """
    Get health check configuration for a framework.
    
    Args:
        framework: Framework name
        port: Application port
        
    Returns:
        Dictionary with health check configuration
    """
    config = get_framework_config(framework)
    health_port = port + config.get("health_port_offset", 0)
    
    return {
        "path": config.get("health_path", "/"),
        "port": health_port,
        "expected_status": 200,
        "timeout": 10,
    }


def format_install_command(framework: str, app_name: str, environment: str = "production") -> str:
    """
    Get the formatted install command for a framework.
    
    Args:
        framework: Framework name
        app_name: Application name
        environment: Environment name
        
    Returns:
        Formatted install command
    """
    config = get_framework_config(framework)
    cmd = config.get("install_cmd", "")
    
    # Replace placeholders
    cmd = cmd.replace("{app_name}", app_name)
    cmd = cmd.replace("{environment}", environment)
    
    return cmd


def format_build_command(framework: str, app_name: str, port: int = 8100) -> str:
    """
    Get the formatted build command for a framework.
    
    Args:
        framework: Framework name
        app_name: Application name
        port: Application port
        
    Returns:
        Formatted build command
    """
    config = get_framework_config(framework)
    cmd = config.get("build_cmd", "")
    
    # Replace placeholders
    cmd = cmd.replace("{app_name}", app_name)
    cmd = cmd.replace("{port}", str(port))
    
    return cmd


def format_start_command(framework: str, app_name: str, port: int = 8100) -> str:
    """
    Get the formatted start command for a framework.
    
    Args:
        framework: Framework name
        app_name: Application name
        port: Application port
        
    Returns:
        Formatted start command
    """
    config = get_framework_config(framework)
    cmd = config.get("start_cmd", "")
    
    # Replace placeholders
    cmd = cmd.replace("{app_name}", app_name)
    cmd = cmd.replace("{port}", str(port))
    
    return cmd


def format_migrate_command(framework: str, app_name: str, environment: str = "production") -> str:
    """
    Get the formatted migration command for a framework.
    
    Args:
        framework: Framework name
        app_name: Application name
        environment: Environment name
        
    Returns:
        Formatted migration command
    """
    config = get_framework_config(framework)
    cmd = config.get("migrate_cmd", "")
    
    # Replace placeholders
    cmd = cmd.replace("{app_name}", app_name)
    cmd = cmd.replace("{environment}", environment)
    
    return cmd


def get_package_manager(framework: str) -> str:
    """
    Get the package manager for a framework.
    
    Args:
        framework: Framework name
        
    Returns:
        Package manager name (npm, yarn, pnpm, pip, composer, go)
    """
    config = get_framework_config(framework)
    return config.get("package_manager", "npm")


def needs_systemd_service(framework: str) -> bool:
    """
    Check if the framework requires a systemd service.
    
    Args:
        framework: Framework name
        
    Returns:
        True if systemd service is needed
    """
    config = get_framework_config(framework)
    runtime = config.get("runtime", "")
    return "systemd" in runtime


def get_service_template_name(framework: str) -> str:
    """
    Get the systemd service template name for a framework.
    
    Args:
        framework: Framework name
        
    Returns:
        Template filename
    """
    config = get_framework_config(framework)
    runtime = config.get("runtime", "systemd+node")
    
    if "php-fpm" in runtime:
        return "laravel.service.j2"
    elif "node" in runtime:
        return "node.service.j2"
    elif "gunicorn" in runtime:
        return "python.service.j2"
    elif "binary" in runtime:
        return "go.service.j2"
    else:
        return "node.service.j2"


def build_env_vars_for_framework(
    framework: str,
    environment: str = "production",
    app_url: str = "",
    db_config: Dict[str, str] = None,
    redis_config: Dict[str, str] = None,
    additional_vars: Dict[str, str] = None,
) -> Dict[str, str]:
    """
    Build environment variables dictionary for a framework.
    
    Args:
        framework: Framework name
        environment: Environment name
        app_url: Application URL
        db_config: Database configuration dict
        redis_config: Redis configuration dict
        additional_vars: Additional environment variables
        
    Returns:
        Dictionary of environment variables
    """
    config = get_framework_config(framework)
    env_template = config.get("env_template", {})
    env_vars = {}
    
    # Build common values
    debug = "true" if environment == "staging" else "false"
    flask_env = "development" if environment == "staging" else "production"
    django_settings = f"config.settings.{environment}"
    
    # Build database URL if config provided
    database_url = ""
    if db_config:
        database_url = f"postgresql://{db_config.get('username', '')}:{db_config.get('password', '')}@{db_config.get('host', '')}:{db_config.get('port', '5432')}/{db_config.get('database', '')}"
    
    # Build Redis URL if config provided
    redis_url = ""
    if redis_config:
        redis_db = redis_config.get('db', 0)
        redis_url = f"redis://:{redis_config.get('password', '')}@{redis_config.get('host', '')}:{redis_config.get('port', '6379')}/{redis_db}"
    
    # Process template
    for key, value_template in env_template.items():
        value = value_template
        value = value.replace("{environment}", environment)
        value = value.replace("{debug}", debug)
        value = value.replace("{flask_env}", flask_env)
        value = value.replace("{django_settings}", django_settings)
        value = value.replace("{app_url}", app_url)
        value = value.replace("{database_url}", database_url)
        value = value.replace("{redis_url}", redis_url)
        
        if db_config:
            value = value.replace("{db_host}", db_config.get('host', ''))
            value = value.replace("{db_port}", str(db_config.get('port', 5432)))
            value = value.replace("{db_name}", db_config.get('database', ''))
            value = value.replace("{db_user}", db_config.get('username', ''))
            value = value.replace("{db_password}", db_config.get('password', ''))
        
        if redis_config:
            value = value.replace("{redis_host}", redis_config.get('host', ''))
            value = value.replace("{redis_port}", str(redis_config.get('port', 6379)))
            value = value.replace("{redis_password}", redis_config.get('password', ''))
        
        # Only include non-empty values
        if value and not value.startswith("{") and not value.endswith("}"):
            env_vars[key] = value
    
    # Merge additional variables
    if additional_vars:
        env_vars.update(additional_vars)
    
    return env_vars