#!/bin/bash
set -e

APP_SERVER_1="100.92.26.38"
APP_SERVER_2="100.89.130.19"

# Handle --rebuild flag for rebuilding config without provisioning
if [ "$1" == "--rebuild" ]; then
    echo "Rebuilding HAProxy config..."
    
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

    # Build HTTPS frontend with security headers
    cat > "$https_cfg" << EOF
# HTTPS frontend with all certificates
frontend web_https
    bind :443 ssl${certs} alpn h2,http/1.1
    mode http

    # Client IP forwarding from Cloudflare
    http-request set-header X-Real-IP %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Real-IP %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[req.hdr(CF-Connecting-IP)] if { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-For %[src] unless { req.hdr(CF-Connecting-IP) -m found }
    http-request set-header X-Forwarded-Proto https

    # Security headers
    http-response set-header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    http-response set-header X-Content-Type-Options "nosniff"
    http-response set-header X-Frame-Options "SAMEORIGIN"
    http-response set-header X-XSS-Protection "1; mode=block"
    http-response set-header Referrer-Policy "strict-origin-when-cross-origin"
    http-response set-header Permissions-Policy "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()"

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

echo "Usage: $0 --rebuild"
exit 1
