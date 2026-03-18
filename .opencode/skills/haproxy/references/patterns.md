# HAProxy Patterns Reference

## Contents
- Configuration Structure
- Backend Definition Patterns
- Anti-Patterns

## Configuration Structure

The Quantyra infrastructure uses a consolidated configuration model. All domain-specific configuration fragments live in `/etc/haproxy/domains/` and are assembled into the main config.

```
/etc/haproxy/
├── haproxy.cfg              # Main config (includes domain fragments)
└── domains/
    ├── web_http.cfg         # Single HTTP frontend (redirects to HTTPS)
    ├── web_https.cfg        # Single HTTPS frontend (all certificates)
    ├── web_backends.cfg     # All application backends
    └── registry.conf        # Domain → App → Port mapping (generated)
```

### WARNING: Per-Domain Frontends

**The Problem:**

```haproxy
# BAD - Creates separate frontend per domain
frontend myapp_frontend
    bind *:443 ssl crt /etc/haproxy/certs/myapp.pem
    default_backend app_myapp

frontend other_frontend
    bind *:443 ssl crt /etc/haproxy/certs/other.pem
    default_backend app_other
```

**Why This Breaks:**
1. Only the first frontend binding to port 443 will work; subsequent binds fail
2. Exhausts available ports with many domains
3. Impossible to share SSL session cache across domains
4. Complicates certificate management (must restart to reload certs)

**The Fix:**

```haproxy
# GOOD - Single consolidated frontend with Host ACL routing
frontend https_frontend
    bind *:443 ssl crt /etc/haproxy/certs/ alpn h2,http/1.1

    acl host_myapp hdr(host) -i myapp.com www.myapp.com
    acl host_other hdr(host) -i other.com www.other.com

    use_backend app_myapp_prod if host_myapp
    use_backend app_other_prod if host_other
```

**When You Might Be Tempted:**
When you need different SSL settings per domain. Instead, use `ssl-default-bind-options` in global config and apply domain-specific rules via ACLs.

## Backend Definition Patterns

### Production Application Backend

```haproxy
backend app_example_prod
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200
    default-server inter 5s rise 2 fall 3 maxconn 500
    server re-db 100.92.26.38:8100 check
    server re-node-02 100.89.130.19:8100 check backup
```

### Staging Backend with Basic Auth

```haproxy
backend app_example_staging
    balance roundrobin
    option httpchk GET /health
    http-request auth unless { http_auth(staging_users) }
    server re-db 100.92.26.38:9200 check
```

### Database Backend (TCP Mode)

```haproxy
backend postgres_write
    mode tcp
    option tcp-check
    tcp-check connect port 5432
    server re-node-03 100.114.117.46:5432 check
```

### WARNING: Missing Health Checks

**The Problem:**

```haproxy
# BAD - No health checks, failed servers stay in pool
backend app_bad
    server re-db 100.92.26.38:8100
    server re-node-02 100.89.130.19:8100
```

**Why This Breaks:**
1. Failed servers continue receiving traffic, causing 5xx errors
2. No automatic failover when app servers restart
3. Deployments cause downtime as backends removed without draining

**The Fix:**

```haproxy
# GOOD - Health checks with proper intervals
backend app_good
    option httpchk GET /health
    http-check expect status 200
    default-server inter 5s rise 2 fall 3
    server re-db 100.92.26.38:8100 check
    server re-node-02 100.89.130.19:8100 check
```

## SSL Certificate Patterns

### Multi-Certificate Directory

HAProxy loads all `.pem` files from the certs directory:

```haproxy
# In web_https.cfg
frontend https_frontend
    bind *:443 ssl crt /etc/haproxy/certs/ alpn h2,http/1.1
```

### Certificate File Format

```bash
# Concatenate: private key + certificate + intermediates
cat \
    /etc/letsencrypt/live/myapp.com/privkey.pem \
    /etc/letsencrypt/live/myapp.com/cert.pem \
    /etc/letsencrypt/live/myapp.com/chain.pem \
    > /etc/haproxy/certs/myapp.com.pem
```

### WARNING: Hardcoded Certificate Paths

**The Problem:**

```haproxy
# BAD - Single cert per domain, requires restart to update
bind *:443 ssl crt /etc/haproxy/certs/specific-domain.pem
```

**Why This Breaks:**
1. Cannot reload config without dropping connections
2. Must enumerate every certificate in bind directive
3. Certificate rotation requires full restart

**The Fix:**
Use directory loading and `crt-list` for advanced SNI routing if needed:

```haproxy
# GOOD - Directory loads all certs, reloadable
bind *:443 ssl crt /etc/haproxy/certs/ alpn h2,http/1.1
```

## Stats and Monitoring

### Enable Stats Page

```haproxy
# In haproxy.cfg global section
listen stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s
    stats admin if TRUE
```

Access at: http://100.102.220.16:8404/stats

### Prometheus Metrics

```haproxy
frontend prometheus
    bind *:8405
    http-request use-service prometheus-exporter if { path /metrics }
```

See the **prometheus** skill for scraping configuration.