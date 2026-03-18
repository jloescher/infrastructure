# Nginx Database Reference

Nginx does not directly connect to databases. However, proper nginx/PHP-FPM configuration affects database connectivity in Laravel applications.

## Contents
- PHP Database Connection Timeouts
- Long-Running Request Handling
- Connection Pooling Indirect Effects

## PHP Database Connection Timeouts

When nginx or PHP-FPM timeouts are shorter than database query timeouts:

```nginx
# BAD - PHP-FPM kills worker before DB query completes
request_terminate_timeout = 30s

# Database query takes 60s
# Result: 502 error, but query continues running on DB
```

### WARNING: Timeout Mismatch

**The Problem:**
nginx/FPM timeouts shorter than database query timeouts cause:
1. Client sees 502 Gateway Timeout
2. Database query continues executing (wasted resources)
3. Potential for duplicate operations on retry

**The Fix:**

Align timeouts through the stack:

```nginx
# nginx location block
fastcgi_read_timeout 300;
fastcgi_send_timeout 300;

# PHP-FPM pool config
request_terminate_timeout = 300s
request_slowlog_timeout = 30s

# Laravel .env
DB_WAIT_TIMEOUT=300
```

## Long-Running Request Handling

For admin imports or batch operations:

```nginx
location /admin/import {
    fastcgi_read_timeout 600;
    fastcgi_send_timeout 600;
    fastcgi_connect_timeout 600;
    
    # Increase PHP limits for this location
    fastcgi_param PHP_VALUE "max_execution_time=600\nmemory_limit=512M";
}
```

### WARNING: Global Timeout Increases

**The Problem:**

```nginx
# BAD - Global high timeout affects all requests
fastcgi_read_timeout 600;
```

**Why This Breaks:**
1. Slow clients occupy PHP-FPM workers longer
2. Worker exhaustion under load
3. Legitimate 502 errors delayed, masking real problems

**The Fix:**

Apply extended timeouts only to specific locations:

```nginx
# GOOD - Scoped to specific routes
location ~ ^/admin/(import|export|batch) {
    fastcgi_read_timeout 600;
    # ...
}
```

## Monitoring Slow Queries

PHP-FPM slow log configuration:

```ini
; pool config
slowlog = /var/log/php8.5-fpm/slow.log
request_slowlog_timeout = 10s
```

Correlate with nginx access logs:

```bash
# Find slow requests
awk '$11 > 10 {print}' /var/log/nginx/access.log

# Check corresponding slow PHP logs
grep "script_filename" /var/log/php8.5-fpm/slow.log
```

## Related Skills

- **postgresql** - Database connection pooling and query optimization
- **php** - PHP-FPM configuration and Laravel database connections