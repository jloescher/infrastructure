#!/bin/bash
#
# Framework Setup Script for Quantyra PaaS
#
# This script sets up the runtime environment for various frameworks:
# - Laravel (Dokploy-managed Docker runtime)
# - Next.js (systemd + Node.js)
# - SvelteKit (systemd + Node.js)
# - Python (systemd + Gunicorn)
# - Go (systemd + binary)
#
# Usage:
#   setup-framework.sh --app-name NAME --framework FRAMEWORK [--port PORT] [--environment ENV]
#
# Options:
#   --app-name       Application name (required)
#   --framework      Framework type: laravel, nextjs, svelte, python, go (required)
#   --port           Application port (default: auto-assign based on framework)
#   --environment    Environment: production, staging (default: production)
#   --app-dir        Application directory (default: /opt/apps/APP_NAME)
#   --user           Runtime user (default: webapps)
#   --memory-limit   Memory limit for systemd service (default: framework-specific)
#   --workers        Number of workers for Python apps (default: 4)
#   --rebuild        Rebuild existing configuration
#   --dry-run        Show what would be done without making changes
#

set -euo pipefail

# Default values
APP_NAME=""
FRAMEWORK=""
PORT=""
ENVIRONMENT="production"
APP_DIR=""
RUNTIME_USER="webapps"
MEMORY_LIMIT=""
WORKERS="4"
REBUILD=false
DRY_RUN=false
TEMPLATES_DIR="/opt/dashboard/services/templates"

# Framework-specific defaults
declare -A FRAMEWORK_PORTS=(
    ["laravel"]="8100"
    ["nextjs"]="8200"
    ["svelte"]="8300"
    ["python"]="8400"
    ["go"]="8500"
)

declare -A FRAMEWORK_MEMORY=(
    ["laravel"]="512M"
    ["nextjs"]="512M"
    ["svelte"]="512M"
    ["python"]="512M"
    ["go"]="256M"
)

declare -A FRAMEWORK_RUNTIME=(
    ["laravel"]="dokploy+docker"
    ["nextjs"]="systemd+node"
    ["svelte"]="systemd+node"
    ["python"]="systemd+gunicorn"
    ["go"]="systemd+binary"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_help() {
    head -30 "$0" | tail -28 | sed 's/^#//' | sed 's/^ //'
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --app-name)
                APP_NAME="$2"
                shift 2
                ;;
            --framework)
                FRAMEWORK="$2"
                shift 2
                ;;
            --port)
                PORT="$2"
                shift 2
                ;;
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --app-dir)
                APP_DIR="$2"
                shift 2
                ;;
            --user)
                RUNTIME_USER="$2"
                shift 2
                ;;
            --memory-limit)
                MEMORY_LIMIT="$2"
                shift 2
                ;;
            --workers)
                WORKERS="$2"
                shift 2
                ;;
            --rebuild)
                REBUILD=true
                shift
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help|-h)
                show_help
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

validate_args() {
    if [[ -z "$APP_NAME" ]]; then
        log_error "Application name is required (--app-name)"
        exit 1
    fi

    if [[ -z "$FRAMEWORK" ]]; then
        log_error "Framework is required (--framework)"
        log_info "Supported frameworks: ${!FRAMEWORK_PORTS[*]}"
        exit 1
    fi

    if [[ ! -v FRAMEWORK_PORTS["$FRAMEWORK"] ]]; then
        log_error "Unsupported framework: $FRAMEWORK"
        log_info "Supported frameworks: ${!FRAMEWORK_PORTS[*]}"
        exit 1
    fi

    # Set defaults
    if [[ -z "$PORT" ]]; then
        PORT="${FRAMEWORK_PORTS[$FRAMEWORK]}"
        # Adjust for staging
        if [[ "$ENVIRONMENT" == "staging" ]]; then
            PORT=$((PORT + 1100))
        fi
    fi

    if [[ -z "$APP_DIR" ]]; then
        APP_DIR="/opt/apps/${APP_NAME}"
    fi

    if [[ -z "$MEMORY_LIMIT" ]]; then
        MEMORY_LIMIT="${FRAMEWORK_MEMORY[$FRAMEWORK]}"
    fi
}

ensure_runtime_user() {
    log_info "Ensuring runtime user '$RUNTIME_USER' exists..."
    
    if id -u "$RUNTIME_USER" >/dev/null 2>&1; then
        log_success "User '$RUNTIME_USER' already exists"
    else
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY RUN] Would create user '$RUNTIME_USER'"
        else
            useradd --system --create-home --home-dir "/home/$RUNTIME_USER" \
                --shell /usr/sbin/nologin "$RUNTIME_USER"
            log_success "Created user '$RUNTIME_USER'"
        fi
    fi
}

ensure_app_directory() {
    log_info "Ensuring application directory '$APP_DIR' exists..."
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would create/verify directory '$APP_DIR'"
    else
        mkdir -p "$APP_DIR"
        chown -R "$RUNTIME_USER:$RUNTIME_USER" "$APP_DIR"
        chmod 755 "$APP_DIR"
        log_success "Application directory ready"
    fi
}

setup_laravel() {
    log_warning "Laravel host runtime provisioning is deprecated."
    log_info "All Laravel/PHP apps must be deployed through Dokploy with Dockerized PHP runtimes."
    log_info "Use https://deploy.quantyralabs.cc to configure domains, env vars, and deployments."
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] No host web server/PHP runtime configuration will be created for Laravel apps"
    fi
}

setup_node() {
    log_info "Setting up Node.js runtime (systemd service)..."
    
    local service_file="/etc/systemd/system/${APP_NAME}.service"
    local node_env="production"
    
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        node_env="development"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would create systemd service: $service_file"
    else
        # Determine start command based on framework
        local start_cmd="npm start"
        local display_name="Node.js"
        
        if [[ "$FRAMEWORK" == "nextjs" ]]; then
            display_name="Next.js"
            start_cmd="npm start"
        elif [[ "$FRAMEWORK" == "svelte" ]]; then
            display_name="SvelteKit"
            start_cmd="npm start"
        fi
        
        cat > "$service_file" << EOF
[Unit]
Description=${APP_NAME} - ${display_name} Application
Documentation=https://github.com/quantyra/infrastructure
After=network.target

[Service]
Type=simple
User=${RUNTIME_USER}
Group=${RUNTIME_USER}
WorkingDirectory=${APP_DIR}

Environment="NODE_ENV=${node_env}"
Environment="PORT=${PORT}"

ExecStart=/usr/bin/${start_cmd}

Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

LimitNOFILE=65536
MemoryMax=${MEMORY_LIMIT}

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

TimeoutStartSec=60
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
        log_success "Created systemd service file"
        
        systemctl daemon-reload
        systemctl enable "${APP_NAME}"
        log_success "Enabled systemd service"
    fi
}

setup_python() {
    log_info "Setting up Python runtime (Gunicorn)..."
    
    local service_file="/etc/systemd/system/${APP_NAME}.service"
    local venv_path="${APP_DIR}/venv"
    local app_env="production"
    
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        app_env="development"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would create systemd service: $service_file"
        log_info "[DRY RUN] Would set up virtual environment: $venv_path"
    else
        # Create systemd service
        cat > "$service_file" << EOF
[Unit]
Description=${APP_NAME} - Python Application
Documentation=https://github.com/quantyra/infrastructure
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUNTIME_USER}
Group=${RUNTIME_USER}
WorkingDirectory=${APP_DIR}

Environment="PATH=${venv_path}/bin:/usr/local/bin:/usr/bin:/bin"
Environment="VIRTUAL_ENV=${venv_path}"
Environment="APP_ENV=${app_env}"

ExecStart=${venv_path}/bin/gunicorn \\
    --bind 0.0.0.0:${PORT} \\
    --workers ${WORKERS} \\
    --threads 2 \\
    --worker-class sync \\
    --timeout 30 \\
    --keep-alive 5 \\
    --access-logfile - \\
    --error-logfile - \\
    --log-level info \\
    app:app

Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

LimitNOFILE=65536
MemoryMax=${MEMORY_LIMIT}

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

TimeoutStartSec=60
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
        log_success "Created systemd service file"
        
        # Create virtual environment if it doesn't exist
        if [[ ! -d "$venv_path" ]]; then
            sudo -u "$RUNTIME_USER" python3 -m venv "$venv_path"
            log_success "Created virtual environment"
        fi
        
        systemctl daemon-reload
        systemctl enable "${APP_NAME}"
        log_success "Enabled systemd service"
    fi
}

setup_go() {
    log_info "Setting up Go runtime (systemd service)..."
    
    local service_file="/etc/systemd/system/${APP_NAME}.service"
    local binary_path="${APP_DIR}/bin/${APP_NAME}"
    local app_env="production"
    
    if [[ "$ENVIRONMENT" == "staging" ]]; then
        app_env="development"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[DRY RUN] Would create systemd service: $service_file"
    else
        cat > "$service_file" << EOF
[Unit]
Description=${APP_NAME} - Go Application
Documentation=https://github.com/quantyra/infrastructure
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${RUNTIME_USER}
Group=${RUNTIME_USER}
WorkingDirectory=${APP_DIR}

Environment="APP_ENV=${app_env}"
Environment="PORT=${PORT}"

ExecStart=${binary_path}

Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3

LimitNOFILE=65536
MemoryMax=${MEMORY_LIMIT}

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${APP_NAME}

TimeoutStartSec=30
TimeoutStopSec=15

[Install]
WantedBy=multi-user.target
EOF
        log_success "Created systemd service file"
        
        # Ensure bin directory exists
        mkdir -p "${APP_DIR}/bin"
        chown -R "$RUNTIME_USER:$RUNTIME_USER" "${APP_DIR}/bin"
        
        systemctl daemon-reload
        systemctl enable "${APP_NAME}"
        log_success "Enabled systemd service"
    fi
}

detect_framework() {
    log_info "Attempting to auto-detect framework..."
    
    if [[ -f "${APP_DIR}/artisan" ]]; then
        echo "laravel"
    elif [[ -f "${APP_DIR}/next.config.js" ]] || [[ -f "${APP_DIR}/next.config.mjs" ]]; then
        echo "nextjs"
    elif [[ -f "${APP_DIR}/svelte.config.js" ]]; then
        echo "svelte"
    elif [[ -f "${APP_DIR}/go.mod" ]] || [[ -f "${APP_DIR}/main.go" ]]; then
        echo "go"
    elif [[ -f "${APP_DIR}/requirements.txt" ]] || [[ -f "${APP_DIR}/pyproject.toml" ]]; then
        echo "python"
    elif [[ -f "${APP_DIR}/package.json" ]]; then
        echo "nextjs"  # Default for Node.js apps
    else
        echo ""
    fi
}

cleanup_existing() {
    if [[ "$REBUILD" == true ]]; then
        log_warning "Rebuild mode - cleaning up existing configuration..."
        
        # Stop service if running
        systemctl stop "${APP_NAME}" 2>/dev/null || true
        systemctl disable "${APP_NAME}" 2>/dev/null || true
        
        # Remove old configs
        rm -f "/etc/systemd/system/${APP_NAME}.service"
        
        systemctl daemon-reload
        log_success "Cleaned up existing configuration"
    fi
}

main() {
    parse_args "$@"
    validate_args
    
    log_info "========================================="
    log_info "Framework Setup for ${APP_NAME}"
    log_info "========================================="
    log_info "Framework:    ${FRAMEWORK}"
    log_info "Environment:  ${ENVIRONMENT}"
    log_info "Port:         ${PORT}"
    log_info "App Dir:      ${APP_DIR}"
    log_info "Runtime User: ${RUNTIME_USER}"
    log_info "Memory Limit: ${MEMORY_LIMIT}"
    log_info "Dry Run:      ${DRY_RUN}"
    log_info "========================================="
    
    if [[ "$DRY_RUN" == true ]]; then
        log_warning "DRY RUN MODE - No changes will be made"
    fi
    
    cleanup_existing
    ensure_runtime_user
    ensure_app_directory
    
    case "$FRAMEWORK" in
        laravel)
            setup_laravel
            ;;
        nextjs|svelte)
            setup_node
            ;;
        python)
            setup_python
            ;;
        go)
            setup_go
            ;;
        *)
            log_error "Unknown framework: $FRAMEWORK"
            exit 1
            ;;
    esac
    
    log_success "========================================="
    log_success "Framework setup completed!"
    log_success "========================================="
    
    if [[ "$FRAMEWORK" != "laravel" ]]; then
        log_info "To start the service:"
        log_info "  systemctl start ${APP_NAME}"
        log_info "To view logs:"
        log_info "  journalctl -u ${APP_NAME} -f"
    fi
}

# Run main function
main "$@"
