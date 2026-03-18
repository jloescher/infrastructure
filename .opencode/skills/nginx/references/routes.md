# Nginx Routes Reference

## Contents
- Laravel Routing Pattern
- Trust Proxy Configuration
- Static File Handling
- Security Headers

## Laravel Routing Pattern

Standard Laravel requires routing all requests to `index.php`:

```nginx
location / {
    try_files $uri $uri/ /index.php?$query_string;
}
```

### WARNING: Incorrect try_files

**The Problem:**

```nginx
# BAD - Missing query string breaks Laravel
try_files $uri $uri/ /index.php;

# BAD - Wrong fallback path
try_files $uri $uri/ =404;
```

**Why This Breaks:**
1. Laravel routes rely on `$_SERVER['QUERY_STRING']` for proper URL parsing
2. Without `?$query_string`, route parameters are lost
3. `=404` fallback prevents Laravel from handling 404s gracefully

**The Fix:**

```nginx
# GOOD - Complete Laravel routing
location / {
    try_files $uri $uri/ /index.php?$query_string;
}
```

## Trust Proxy Configuration

Since HAProxy sits in front of nginx, restore real client IPs:

```nginx
set_real_ip_from 100.92.26.38;    # re-db (app server self)
set_real_ip_from 100.89.130.19;   # re-node-02 (other app server)
set_real_ip_from 100.102.220.16;  # router-01 (HAProxy)
set_real_ip_from 100.116.175.9;   # router-02 (HAProxy)
real_ip_header X-Forwarded-For;
real_ip_recursive on;
```

### WARNING: Missing Trust Proxy

**The Problem:**

```nginx
# BAD - Missing real_ip configuration
# All requests appear to come from 100.102.220.16
```

**Why This Breaks:**
1. Laravel sees HAProxy IP as client IP
2. Rate limiting, logging, and security features break
3. `request()->ip()` returns wrong value in PHP

**Use `$realip_remote_addr` in fastcgi_params:**

```nginx
location ~ \.php$ {
    fastcgi_pass unix:/run/php/php8.5-fpm-app.sock;
    fastcgi_param REMOTE_ADDR $realip_remote_addr;
    # ...
}
```

## Static File Handling

Nginx handles static files before PHP:

```nginx
location ~* \.(jpg|jpeg|png|gif|ico|css|js|svg|woff|woff2)$ {
    expires 1M;
    add_header Cache-Control "public, immutable";
    access_log off;
}
```

Place static location blocks BEFORE the PHP location for priority matching.

## Security Headers

Always include security headers for production:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
```

### WARNING: Duplicate Headers

If HAProxy already sets these headers, nginx adds duplicates. Use `always` to ensure headers appear on all responses including errors.