# Nginx Authentication Reference

## Contents
- Basic Authentication
- IP-Based Access Control
- Laravel Session Handling
- Staging Environment Protection

## Basic Authentication

nginx can provide basic auth for simple protection:

```nginx
location /admin {
    auth_basic "Admin Area";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    fastcgi_pass unix:/run/php/php8.5-fpm-app.sock;
    # ...
}
```

### WARNING: Basic Auth Limitations

**The Problem:**
Basic auth in nginx has drawbacks:
1. Credentials sent with every request (no session)
2. No logout mechanism
3. Cannot integrate with Laravel's auth system

**The Fix:**

Use Laravel's built-in authentication instead:

```nginx
# GOOD - Pass through to Laravel auth
location /admin {
    # Let Laravel handle authentication
    try_files $uri $uri/ /index.php?$query_string;
}
```

## IP-Based Access Control

Restrict admin areas by source IP:

```nginx
location /admin {
    allow 100.64.0.0/10;  # Tailscale only
    deny all;
    
    try_files $uri $uri/ /index.php?$query_string;
}
```

## Staging Environment Protection

In this infrastructure, staging password protection happens at HAProxy, not nginx:

```nginx
# nginx sees authenticated requests only
# HAProxy handles: http-request auth realm "Staging Area"
```

### WARNING: Duplicate Password Protection

**The Problem:**

```nginx
# BAD - Double auth is annoying
location / {
    auth_basic "Staging";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

Combined with HAProxy basic auth, users enter passwords twice.

**The Fix:**

Remove nginx-level auth when HAProxy handles it:

```nginx
# GOOD - No auth in nginx, handled by HAProxy
location / {
    try_files $uri $uri/ /index.php?$query_string;
}
```

## Laravel Session Configuration

Ensure sessions work correctly behind proxies:

```nginx
location ~ \.php$ {
    fastcgi_pass unix:/run/php/php8.5-fpm-app.sock;
    
    # Forward session cookies correctly
    fastcgi_param HTTPS "on";  # Tell Laravel HTTPS is used
    fastcgi_param HTTP_X_FORWARDED_PROTO "https";
}
```

### WARNING: Session Security

**The Problem:**

Laravel sessions may break or be insecure without proper proxy headers:
1. Session cookie not set as Secure
2. CSRF token mismatch errors
3. Session fixation vulnerabilities

**The Fix:**

Always forward HTTPS indicators:

```nginx
fastcgi_param HTTPS "on";
fastcgi_param HTTP_X_FORWARDED_PORT "443";
fastcgi_param HTTP_X_FORWARDED_PROTO "https";