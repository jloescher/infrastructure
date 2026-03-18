# Nginx Errors Reference

## Contents
- 502 Bad Gateway Debugging
- 504 Gateway Timeout
- Permission Denied
- Configuration Test Failures

## 502 Bad Gateway Debugging

502 errors indicate PHP-FPM is unreachable or failing.

### Diagnostic Checklist

```bash
# 1. Check PHP-FPM is running
sudo systemctl status php8.5-fpm

# 2. Verify socket exists and permissions
ls -la /run/php/php8.5-fpm-*.sock

# 3. Check PHP-FPM error logs
sudo tail -f /var/log/php8.5-fpm/error.log

# 4. Test nginx configuration
sudo nginx -t

# 5. Check nginx error log
sudo tail -f /var/log/nginx/error.log
```

### Common Causes

| Cause | Symptom | Fix |
|-------|---------|-----|
| FPM not running | Socket missing | `systemctl start php8.5-fpm` |
| Wrong socket path | `No such file or directory` | Update nginx fastcgi_pass |
| Permission denied | `Permission denied` in logs | Check `listen.owner/group` |
| Worker exhaustion | `server reached pm.max_children` | Increase `pm.max_children` |

### WARNING: Socket Path Mismatches

**The Problem:**

```nginx
# nginx config
fastcgi_pass unix:/run/php/php8.5-fpm-app.sock;

# But FPM pool config
listen = /run/php/php8.5-fpm-rentalfixer.sock
```

**Why This Breaks:**
nginx cannot connect to FPM, resulting in 502 for all PHP requests.

**The Fix:**

Ensure socket paths match exactly:

```bash
# Check FPM pool socket
grep "^listen" /etc/php/8.5/fpm/pool.d/*.conf

# Update nginx to match
fastcgi_pass unix:/run/php/php8.5-fpm-rentalfixer.sock;
```

## 504 Gateway Timeout

Request took longer than nginx allows.

```nginx
# Increase timeout for specific locations
location /api/long-running {
    fastcgi_read_timeout 300;
    fastcgi_send_timeout 300;
}
```

### WARNING: Blind Timeout Increases

**The Problem:**

```nginx
# BAD - Global timeout increase masks performance issues
fastcgi_read_timeout 300;
```

**Why This Breaks:**
1. Slow endpoints block FPM workers
2. Worker pool exhaustion
3. Cascading failures under load

**The Fix:**

Profile the slow endpoint first:

```bash
# Check PHP slow log
tail /var/log/php8.5-fpm/slow.log

# Optimize query or add caching before increasing timeout
```

## Permission Denied

### nginx Cannot Read Files

```bash
# Check file ownership
ls -la /opt/apps/myapp/public

# Should be readable by www-data
sudo chown -R webapps:www-data /opt/apps/myapp
sudo chmod -R 755 /opt/apps/myapp/public
```

### Socket Permission Denied

```bash
# Check socket permissions
ls -la /run/php/php8.5-fpm-app.sock

# Fix in FPM pool config
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
```

Then reload PHP-FPM.

## Configuration Test Failures

Always test before reloading:

```bash
sudo nginx -t
```

### WARNING: Skipping Validation

**The Problem:**

```bash
# BAD - Reload without testing
sudo systemctl reload nginx
```

A broken config takes nginx offline until fixed.

**The Fix:**

```bash
# GOOD - Test first, reload only if valid
sudo nginx -t && sudo systemctl reload nginx
```

## Deployment Rollback

If deployment causes 502 errors:

```bash
# 1. Check logs
sudo journalctl -u php8.5-fpm -n 50

# 2. Rollback code via deploy script
/opt/scripts/deploy-app.sh rentalfixer main production

# 3. Force FPM restart if needed
sudo systemctl restart php8.5-fpm
```

See **ansible** skill for automated health checks and rollback procedures.