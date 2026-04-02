#!/bin/bash
# sync-coolify-domains.sh - Synchronize Coolify domains with HAProxy SSL certificates
# 
# Purpose:
#   Query Coolify's PostgreSQL database for active domains, provision missing SSL
#   certificates, rebuild HAProxy HTTPS frontend, and reload HAProxy.
#
# Architecture:
#   Cloudflare → HAProxy (TLS termination) → Coolify Traefik (HTTP) → Docker containers
#
# Usage:
#   /opt/scripts/sync-coolify-domains.sh [--dry-run]
#
# Created: 2026-04-02
# Author: Senior DevOps Architect - Quantyra Infrastructure

set -euo pipefail

# Configuration
SCRIPT_NAME="sync-coolify-domains.sh"
LOG_FILE="/var/log/sync-coolify-domains.log"
HAProxy_CERTS_DIR="/etc/haproxy/certs"
HAProxy_HTTPS_CFG="/etc/haproxy/domains/web_https.cfg"
HAProxy_HTTP_CFG="/etc/haproxy/domains/web_http.cfg"
HAProxy_BACKENDS_CFG="/etc/haproxy/domains/web_backends.cfg"
HAProxy_REGISTRY="/etc/haproxy/domains/registry.conf"
COOLIFY_DB_CONTAINER="coolify-db"
COOLIFY_DB_USER="coolify"
COOLIFY_DB_NAME="coolify"
CERTBOT_CONFIG_DIR="/etc/letsencrypt"
CLOUDFLARE_CREDENTIALS="/root/.cloudflare.ini"
DRY_RUN=false
ROUTER_02_IP="100.116.175.9"

# Logging functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S UTC')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S UTC')] ERROR: $1" | tee -a "$LOG_FILE"
}

log_info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S UTC')] INFO: $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S UTC')] WARN: $1" | tee -a "$LOG_FILE"
}

# Parse arguments
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    log_info "Dry-run mode enabled - no changes will be made"
fi

# Ensure log file exists
touch "$LOG_FILE"

log_info "=== Starting Coolify domain sync ==="

# Step 1: Query Coolify database for active domains
log_info "Querying Coolify database for active domains..."

COOLIFY_DOMAINS=$(docker exec "$COOLIFY_DB_CONTAINER" \
    psql -U "$COOLIFY_DB_USER" -d "$COOLIFY_DB_NAME" -t -A -c \
    "SELECT DISTINCT fqdn FROM applications WHERE deleted_at IS NULL AND fqdn IS NOT NULL AND fqdn != '' ORDER BY fqdn;" \
    2>&1)

if [[ $? -ne 0 ]]; then
    log_error "Failed to query Coolify database: $COOLIFY_DOMAINS"
    exit 1
fi

# Parse domains into array
DOMAIN_ARRAY=()
while IFS= read -r domain; do
    [[ -n "$domain" ]] && DOMAIN_ARRAY+=("$domain")
done <<< "$COOLIFY_DOMAINS"

DOMAIN_COUNT=${#DOMAIN_ARRAY[@]}
log_info "Found $DOMAIN_COUNT active domains in Coolify"

if [[ $DOMAIN_COUNT -eq 0 ]]; then
    log_warn "No active domains found in Coolify - skipping sync"
    log_info "=== Sync complete (no domains) ==="
    exit 0
fi

# Step 2: List existing HAProxy certificates
log_info "Checking existing HAProxy SSL certificates..."

EXISTING_CERTS=()
for cert_file in "$HAProxy_CERTS_DIR"/*.pem; do
    [[ -f "$cert_file" ]] || continue
    cert_name=$(basename "$cert_file" .pem)
    EXISTING_CERTS+=("$cert_name")
done

EXISTING_CERT_COUNT=${#EXISTING_CERTS[@]}
log_info "Found $EXISTING_CERT_COUNT existing certificates in $HAProxy_CERTS_DIR"

# Step 3: Identify domains missing SSL certificates
log_info "Identifying domains requiring SSL certificate provisioning..."

MISSING_CERTS=()
for domain in "${DOMAIN_ARRAY[@]}"; do
    # Check if cert exists (exact match)
    if [[ -f "$HAProxy_CERTS_DIR/${domain}.pem" ]]; then
        log_info "Certificate exists for $domain"
    else
        MISSING_CERTS+=("$domain")
        log_warn "Missing certificate for $domain"
    fi
done

MISSING_CERT_COUNT=${#MISSING_CERTS[@]}
log_info "Found $MISSING_CERT_COUNT domains requiring new certificates"

# Step 4: Provision missing SSL certificates (certbot DNS-01)
if [[ $MISSING_CERT_COUNT -gt 0 ]]; then
    log_info "Provisioning missing SSL certificates..."
    
    for domain in "${MISSING_CERTS[@]}"; do
        log_info "Provisioning certificate for $domain..."
        
        if [[ "$DRY_RUN" == true ]]; then
            log_info "[DRY-RUN] Would run: certbot certonly --dns-cloudflare -d $domain"
            continue
        fi
        
        # Run certbot with DNS-01 challenge (Cloudflare)
        certbot certonly \
            --dns-cloudflare \
            --dns-cloudflare-credentials "$CLOUDFLARE_CREDENTIALS" \
            --dns-cloudflare-propagation-seconds 30 \
            --non-interactive \
            --agree-tos \
            --email admin@quantyra.internal \
            --no-eff-email \
            -d "$domain" \
            2>&1 | tee -a "$LOG_FILE"
        
        if [[ $? -ne 0 ]]; then
            log_error "Failed to provision certificate for $domain"
            continue
        fi
        
        # Combine cert and key into PEM format for HAProxy
        CERT_PATH="$CERTBOT_CONFIG_DIR/live/$domain/fullchain.pem"
        KEY_PATH="$CERTBOT_CONFIG_DIR/live/$domain/privkey.pem"
        HAProxy_CERT_PATH="$HAProxy_CERTS_DIR/${domain}.pem"
        
        if [[ -f "$CERT_PATH" && -f "$KEY_PATH" ]]; then
            cat "$CERT_PATH" "$KEY_PATH" > "$HAProxy_CERT_PATH"
            chmod 600 "$HAProxy_CERT_PATH"
            log_info "Created HAProxy certificate: $HAProxy_CERT_PATH"
        else
            log_error "Certificate files not found for $domain"
        fi
    done
fi

# Step 5: Rebuild HAProxy HTTPS frontend with ALL certificates
log_info "Rebuilding HAProxy HTTPS frontend configuration..."

# Collect all certificates
ALL_CERTS=()
for cert_file in "$HAProxy_CERTS_DIR"/*.pem; do
    [[ -f "$cert_file" ]] || continue
    cert_name=$(basename "$cert_file" .pem)
    ALL_CERTS+=("crt /etc/haproxy/certs/${cert_name}.pem")
done

# Sort certs to ensure consistent ordering
SORTED_CERTS=$(printf '%s\n' "${ALL_CERTS[@]}" | sort | tr '\n' ' ')

CERT_BIND_LINE="bind :443 ssl ${SORTED_CERTS} alpn h2,http/1.1"

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would write to $HAProxy_HTTPS_CFG:"
    log_info "[DRY-RUN]   $CERT_BIND_LINE"
else
    # Build HTTPS frontend configuration
    cat > "$HAProxy_HTTPS_CFG" << 'HTTPS_EOF'
# HTTPS frontend - routes all domains to Coolify backend
# Generated by sync-coolify-domains.sh
# Architecture: HAProxy (TLS termination) → Coolify Traefik (HTTP)

frontend web_https
HTTPS_EOF

    # Add bind line with all certificates
    echo "    $CERT_BIND_LINE" >> "$HAProxy_HTTPS_CFG"
    
    # Add remainder of frontend configuration
    cat >> "$HAProxy_HTTPS_CFG" << 'HTTPS_EOF2'
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

    # Route ALL domains to Coolify backend
    # Domain routing is handled by Coolify Traefik internally
    default_backend coolify_backend
HTTPS_EOF2

    log_info "Updated $HAProxy_HTTPS_CFG with $(echo "${SORTED_CERTS}" | wc -w) certificates"
fi

# Step 6: Ensure HTTP frontend redirects all to HTTPS
log_info "Ensuring HTTP frontend redirects all traffic to HTTPS..."

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would verify $HAProxy_HTTP_CFG"
else
    cat > "$HAProxy_HTTP_CFG" << 'HTTP_EOF'
# HTTP frontend - redirects all traffic to HTTPS
# Generated by sync-coolify-domains.sh

frontend web_http
    bind :80
    mode http

    # Redirect ALL HTTP traffic to HTTPS
    http-request redirect scheme https code 301
HTTP_EOF

    log_info "Updated $HAProxy_HTTP_CFG"
fi

# Step 7: Ensure backend configuration is correct
log_info "Ensuring backend configuration..."

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would verify $HAProxy_BACKENDS_CFG"
else
    cat > "$HAProxy_BACKENDS_CFG" << 'BACKEND_EOF'
# Backends for Coolify integration
# Generated by sync-coolify-domains.sh
# Architecture: HAProxy routes to Coolify Traefik on port 80 (HTTP)

backend coolify_backend
    mode http
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200-499
    option forwardfor
    
    # Coolify Traefik instances (receive HTTP after HAProxy SSL termination)
    server re-db-coolify 100.92.26.38:80 check
    server re-node-02-coolify 100.89.130.19:80 check

backend not_found_backend
    mode http
    http-request deny deny_status 404
BACKEND_EOF

    log_info "Updated $HAProxy_BACKENDS_CFG"
fi

# Step 8: Clear registry.conf (Coolify manages domains internally)
log_info "Clearing registry.conf (Coolify manages domain routing)..."

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would clear $HAProxy_REGISTRY"
else
    > "$HAProxy_REGISTRY"
    log_info "Cleared $HAProxy_REGISTRY"
fi

# Step 9: Validate HAProxy configuration
log_info "Validating HAProxy configuration..."

VALIDATION_OUTPUT=$(haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains 2>&1)

if echo "$VALIDATION_OUTPUT" | grep -q "Configuration file is valid"; then
    log_info "HAProxy configuration validated successfully"
else
    log_error "HAProxy configuration validation failed:"
    log_error "$VALIDATION_OUTPUT"
    exit 1
fi

# Step 10: Reload HAProxy
log_info "Reloading HAProxy..."

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would reload HAProxy"
else
    systemctl reload haproxy 2>&1 | tee -a "$LOG_FILE"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to reload HAProxy"
        exit 1
    fi
    
    log_info "HAProxy reload complete"
fi

# Step 11: Sync to router-02
log_info "Syncing configuration to router-02..."

if [[ "$DRY_RUN" == true ]]; then
    log_info "[DRY-RUN] Would sync configs to router-02 ($ROUTER_02_IP)"
else
    # Sync domain config files
    scp "$HAProxy_HTTP_CFG" "$HAProxy_HTTPS_CFG" "$HAProxy_BACKENDS_CFG" "$HAProxy_REGISTRY" \
        root@"$ROUTER_02_IP":/etc/haproxy/domains/ 2>&1 | tee -a "$LOG_FILE" || log_error "Failed to sync config files"
    
    # Sync certificate files
    scp "$HAProxy_CERTS_DIR"/*.pem root@"$ROUTER_02_IP":"$HAProxy_CERTS_DIR/" 2>&1 | tee -a "$LOG_FILE" || log_error "Failed to sync certs"
    
    # Reload HAProxy on router-02
    ssh root@"$ROUTER_02_IP" "systemctl reload haproxy" 2>&1 | tee -a "$LOG_FILE" || log_error "Failed to reload HAProxy on router-02"
    
    log_info "Router-02 sync complete"
fi

# Summary
log_info "=== Sync Summary ==="
log_info "Coolify domains processed: $DOMAIN_COUNT"
log_info "New certificates provisioned: $MISSING_CERT_COUNT"
log_info "Total certificates in HAProxy: $(ls -1 "$HAProxy_CERTS_DIR"/*.pem 2>/dev/null | wc -l)"
log_info "HAProxy status: $(systemctl is-active haproxy)"
log_info "=== Sync complete ==="

exit 0