# Nginx Services Reference

## Contents
- PHP-FPM Socket Configuration
- systemd Service Management
- Worker Process Tuning
- Log Management

## PHP-FPM Socket Configuration

Per-application pools use Unix sockets for better performance:

```ini
[rentalfixer]
user = www-data
group = www-data
listen = /run/php/php8.5-fpm-rentalfixer.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
```

### WARNING: TCP vs Unix Sockets

**The Problem:**

```nginx
# BAD - TCP sockets add overhead and firewall complexity
fastcgi_pass 127.0.0.1:9000;
```

**Why This Breaks:**
1. TCP requires packet overhead vs direct kernel memory
2. Additional firewall rules needed
3. Port conflicts possible with app port ranges

**The Fix:**

```nginx
# GOOD - Unix domain socket
fastcgi_pass unix:/run/php/php8.5-fpm-rentalfixer.sock;
```

### WARNING: Socket Permission Errors

If nginx gets 502 errors, check socket permissions:

```bash
# Check socket ownership
ls -la /run/php/php8.5-fpm-*.sock

# Should show: www-data www-data
# Fix: Ensure listen.owner and listen.group match www-data
```

## systemd Service Management

Nginx and PHP-FPM run as systemd services on app servers.

### Service Files

- `/lib/systemd/system/nginx.service` - Main nginx service
- `/etc/systemd/system/nginx.service.d/override.conf` - Limits override:

```ini
[Service]
LimitNOFILE=65535
LimitNPROC=65535
```

### WARNING: Hard Reload vs Graceful Reload

**The Problem:**

```bash
# BAD - Hard restart drops active connections
sudo systemctl restart nginx
sudo systemctl restart php8.5-fpm
```

**Why This Breaks:**
1. `restart` terminates active connections immediately
2. Users see 502 errors during restart
3. PHP requests in progress are killed

**The Fix:**

```bash
# GOOD - Graceful reload preserves connections
sudo systemctl reload nginx
sudo systemctl reload php8.5-fpm
```

## Worker Process Tuning

Nginx configuration in `/etc/nginx/nginx.conf`:

```nginx
user www-data;
worker_processes auto;  # Match CPU cores
worker_connections 768; # Connections per worker
```

### WARNING: Static Worker Counts

**The Problem:**

```nginx
# BAD - Manual worker count
worker_processes 4;
```

**Why This Breaks:**
1. Must be updated when migrating to different server sizes
2. Underutilizes high-core-count servers
3. Overwhelms low-core servers

**Use `auto` for dynamic sizing:**

```nginx
# GOOD - Auto-detect CPU cores
worker_processes auto;
```

## Log Management

### Log Rotation

nginx logs should rotate via logrotate:

```bash
# Check logrotate config exists
cat /etc/logrotate.d/nginx
```

### WARNING: Missing Log Rotation

Unrotated logs fill disk space. Ensure logrotate is configured and cron is running.

### Access Log Format

Standard format includes real client IPs:

```nginx
log_format combined_realip '$realip_remote_addr - $remote_user [$time_local] '
                          '"$request" $status $body_bytes_sent '
                          '"$http_referer" "$http_user_agent"';
```

Use in server block:

```nginx
access_log /var/log/nginx/access.log combined_realip;