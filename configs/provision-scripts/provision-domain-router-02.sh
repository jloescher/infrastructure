#!/bin/bash
set -e

# Handle --rebuild flag for rebuilding config without provisioning
if [ "$1" == "--rebuild" ]; then
    echo "Rebuilding HAProxy config..."
    
    APP_SERVER_1="100.92.26.38"
    APP_SERVER_2="100.101.39.22"
    
    http_cfg="/etc/haproxy/domains/web_http.cfg"
    https_cfg="/etc/haproxy/domains/web_https.cfg"
    backends_cfg="/etc/haproxy/domains/web_backends.cfg"
    registry_file="/etc/haproxy/domains/registry.conf"
    
    [ ! -f "$registry_file" ] && touch "$registry_file"
    
    # Collect all certificates
    certs=""
    for cert_file in /etc/haproxy/certs/*.pem; do
        [ -f "$cert_file" ] || continue
        cert_name=$(basename "$cert_file" .pem)
        certs="$certs crt /etc/haproxy/certs/${cert_name}.pem"
    done
    
    # Build HTTP frontend
    cat > "$http_cfg" << 'EOF'
# HTTP frontend - redirects to HTTPS
frontend web_http
    bind :80
    mode http

EOF

    # Build HTTPS frontend
    cat > "$https_cfg" << EOF
# HTTPS frontend with all certificates
frontend web_https
    bind :443 ssl${certs} alpn h2,http/1.1
    mode http

    http-request set-header X-Real-IP %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Real-IP %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-Proto https

EOF

    while IFS='=' read -r reg_domain reg_app reg_port; do
        [ -z "$reg_domain" ] && continue
        acl_name=$(echo "$reg_domain" | tr '.' '_')
        
        if [[ "$reg_domain" == www.* ]]; then
            main_domain="${reg_domain#www.}"
            cat >> "$https_cfg" << EOF
    acl is_${acl_name} hdr(host) -i ${reg_domain}
    http-request redirect location https://${main_domain} code 301 if is_${acl_name}

EOF
        else
            cat >> "$http_cfg" << EOF
    http-request redirect scheme https code 301 if { hdr(host) -i ${reg_domain} }

EOF
            cat >> "$https_cfg" << EOF
    acl is_${acl_name} hdr(host) -i ${reg_domain}
    http-request set-header X-Forwarded-Host ${reg_domain} if is_${acl_name}
    use_backend ${reg_app}_backend if is_${acl_name}

EOF
        fi
    done < "$registry_file"
    
    cat >> "$https_cfg" << EOF

    default_backend not_found_backend
EOF

    # Build backends
    cat > "$backends_cfg" << 'EOF'
# Backends for all applications
EOF

    added_backends=""
    while IFS='=' read -r reg_domain reg_app reg_port; do
        [ -z "$reg_domain" ] || [ -z "$reg_app" ] || [ -z "$reg_port" ] && continue
        [[ "$reg_domain" == www.* ]] && continue
        echo -e "$added_backends" | grep -q "^${reg_app}$" && continue
        added_backends="${added_backends}${reg_app}\n"
        
        cat >> "$backends_cfg" << EOF

backend ${reg_app}_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 ${APP_SERVER_1}:${reg_port} check
    server app2 ${APP_SERVER_2}:${reg_port} check
EOF
    done < "$registry_file"
    
    cat >> "$backends_cfg" << EOF

backend not_found_backend
    mode http
    http-request deny deny_status 404
EOF

    haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains 2>&1
    systemctl reload haproxy
    echo "Config rebuilt successfully"
    exit 0
fi

DOMAIN="$1"
APP_NAME="$2"
APP_PORT="$3"
WWW_DOMAIN=""
IS_STAGING=""
GIT_REPO=""
GIT_BRANCH="main"
EMAIL="jonathan@xotec.io"
CLOUDFLARE_CREDS="/root/.secrets/cloudflare.ini"

shift 3
while [[ $# -gt 0 ]]; do
    case $1 in
        --www)
            WWW_DOMAIN="$2"
            shift 2
            ;;
        --staging)
            IS_STAGING="true"
            GIT_BRANCH="staging"
            shift
            ;;
        --repo)
            GIT_REPO="$2"
            shift 2
            ;;
        --branch)
            GIT_BRANCH="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

if [ -z "$DOMAIN" ] || [ -z "$APP_NAME" ] || [ -z "$APP_PORT" ]; then
    echo "Usage: $0 <domain> <app_name> <app_port> [--www www.domain] [--staging] [--repo url] [--branch name]"
    exit 1
fi

APP_SERVER_1="100.92.26.38"
APP_SERVER_2="100.101.39.22"

echo "Provisioning domain: $DOMAIN for app: $APP_NAME on port: $APP_PORT"
[ -n "$WWW_DOMAIN" ] && echo "WWW redirect: $WWW_DOMAIN -> $DOMAIN"
[ -n "$IS_STAGING" ] && echo "Staging environment: branch=$GIT_BRANCH"

mkdir -p /etc/haproxy/certs /etc/haproxy/domains

get_ssl_cert() {
    local domain="$1"
    local extra_domains="${2:-}"
    
    if [ -f "/etc/haproxy/certs/${domain}.pem" ]; then
        echo "Certificate for $domain already exists"
        return 0
    fi
    
    echo "Obtaining SSL certificate for $domain using DNS-01 challenge..."
    
    local certbot_args="-d $domain"
    if [ -n "$extra_domains" ]; then
        certbot_args="$certbot_args $extra_domains"
    fi
    
    if [ -f "$CLOUDFLARE_CREDS" ]; then
        certbot certonly --dns-cloudflare \
            --dns-cloudflare-credentials "$CLOUDFLARE_CREDS" \
            $certbot_args \
            --non-interactive --agree-tos --email "$EMAIL" || {
            echo "Failed to obtain certificate for $domain"
            return 1
        }
    else
        echo "Cloudflare credentials not found at $CLOUDFLARE_CREDS"
        return 1
    fi
    
    cat /etc/letsencrypt/live/${domain}/fullchain.pem /etc/letsencrypt/live/${domain}/privkey.pem > /etc/haproxy/certs/${domain}.pem
    chmod 600 /etc/haproxy/certs/${domain}.pem
    
    echo "Certificate obtained for $domain"
}

if [ -n "$WWW_DOMAIN" ]; then
    get_ssl_cert "$DOMAIN" "-d $WWW_DOMAIN"
else
    get_ssl_cert "$DOMAIN"
fi

rebuild_haproxy_config() {
    echo "Rebuilding consolidated HAProxy config..."
    
    local http_cfg="/etc/haproxy/domains/web_http.cfg"
    local https_cfg="/etc/haproxy/domains/web_https.cfg"
    local backends_cfg="/etc/haproxy/domains/web_backends.cfg"
    local registry_file="/etc/haproxy/domains/registry.conf"
    
    # Collect all certificates
    local certs=""
    for cert_file in /etc/haproxy/certs/*.pem; do
        [ -f "$cert_file" ] || continue
        local cert_name=$(basename "$cert_file" .pem)
        certs="$certs crt /etc/haproxy/certs/${cert_name}.pem"
    done
    
    # Build HTTP frontend (redirects to HTTPS)
    cat > "$http_cfg" << 'EOF'
# HTTP frontend - redirects to HTTPS
frontend web_http
    bind :80
    mode http

EOF

    # Build HTTPS frontend
    cat > "$https_cfg" << EOF
# HTTPS frontend with all certificates
frontend web_https
    bind :443 ssl${certs} alpn h2,http/1.1
    mode http

    http-request set-header X-Real-IP %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Real-IP %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-Proto https

EOF

    # Add ACLs for each registered domain
    while IFS='=' read -r reg_domain reg_app reg_port; do
        [ -z "$reg_domain" ] && continue
        
        local acl_name=$(echo "$reg_domain" | tr '.' '_')
        
        # Check if this is a www redirect
        if [[ "$reg_domain" == www.* ]]; then
            local main_domain="${reg_domain#www.}"
            # Add HTTPS redirect for www
            cat >> "$https_cfg" << EOF
    acl is_${acl_name} hdr(host) -i ${reg_domain}
    http-request redirect location https://${main_domain} code 301 if is_${acl_name}

EOF
        else
            # Add HTTP redirect
            cat >> "$http_cfg" << EOF
    http-request redirect scheme https code 301 if { hdr(host) -i ${reg_domain} }

EOF
            # Add HTTPS ACL and routing
            cat >> "$https_cfg" << EOF
    acl is_${acl_name} hdr(host) -i ${reg_domain}
    http-request set-header X-Forwarded-Host ${reg_domain} if is_${acl_name}
    use_backend ${reg_app}_backend if is_${acl_name}

EOF
        fi
    done < "$registry_file"
    
    # Add default backend
    cat >> "$https_cfg" << EOF

    default_backend not_found_backend
EOF

    # Build backends
    cat > "$backends_cfg" << 'EOF'
# Backends for all applications
EOF

    # Track which backends we've added
    local added_backends=""
    
    while IFS='=' read -r reg_domain reg_app reg_port; do
        [ -z "$reg_domain" ] || [ -z "$reg_app" ] || [ -z "$reg_port" ] && continue
        
        # Skip www redirects (they don't need backends)
        [[ "$reg_domain" == www.* ]] && continue
        
        # Skip if we already added this backend
        echo -e "$added_backends" | grep -q "^${reg_app}$" && continue
        added_backends="${added_backends}${reg_app}\n"
        
        cat >> "$backends_cfg" << EOF

backend ${reg_app}_backend
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-499
    option forwardfor
    server app1 ${APP_SERVER_1}:${reg_port} check
    server app2 ${APP_SERVER_2}:${reg_port} check
EOF
    done < "$registry_file"
    
    # Add not_found backend
    cat >> "$backends_cfg" << EOF

backend not_found_backend
    mode http
    http-request deny deny_status 404
EOF
}

# Create registry if it doesn't exist
REGISTRY_FILE="/etc/haproxy/domains/registry.conf"
touch "$REGISTRY_FILE"

# Register this domain (update if exists)
if grep -q "^${DOMAIN}=" "$REGISTRY_FILE" 2>/dev/null; then
    sed -i "s|^${DOMAIN}=.*|${DOMAIN}=${APP_NAME}=${APP_PORT}|" "$REGISTRY_FILE"
else
    echo "${DOMAIN}=${APP_NAME}=${APP_PORT}" >> "$REGISTRY_FILE"
fi

# Register www domain if specified
if [ -n "$WWW_DOMAIN" ]; then
    if grep -q "^${WWW_DOMAIN}=" "$REGISTRY_FILE" 2>/dev/null; then
        sed -i "s|^${WWW_DOMAIN}=.*|${WWW_DOMAIN}=${APP_NAME}_www_redirect=${APP_PORT}|" "$REGISTRY_FILE"
    else
        echo "${WWW_DOMAIN}=${APP_NAME}_www_redirect=${APP_PORT}" >> "$REGISTRY_FILE"
    fi
fi

# Rebuild the consolidated config
rebuild_haproxy_config

# Validate and reload
echo "Validating HAProxy config..."
haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains 2>&1

echo "Reloading HAProxy..."
systemctl reload haproxy

echo "Domain provisioning complete: $DOMAIN"
