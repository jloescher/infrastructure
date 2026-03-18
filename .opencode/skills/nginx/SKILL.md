---
name: nginx
description: Configures nginx web server and PHP-FPM for Laravel application backends. Use when setting up new application vhosts, configuring PHP-FPM pools, debugging 502 errors, optimizing worker processes, or reloading after deployments.
---

# Nginx Skill

Nginx serves Laravel applications on app servers behind HAProxy load balancers. SSL terminates at HAProxy; nginx handles plain HTTP on non-standard ports (8100-8199 production, 9200-9299 staging). PHP-FPM connects via Unix sockets with per-application pools.

## Quick Start

### Laravel Site Configuration

```nginx
server {
    listen 8100;
    server_name _;
    root /opt/apps/myapp/public;
    index index.php;

    # Trust HAProxy/Cloudflare IPs
    set_real_ip_from 100.92.26.38;
    set_real_ip_from 100.102.220.16;
    set_real_ip_from 100.116.175.9;
    real_ip_header X-Forwarded-For;
    real_ip_recursive on;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/run/php/php8.5-fpm-myapp.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
    }

    location ~ /\.ht {
        deny all;
    }
}
```

### PHP-FPM Pool Configuration

```ini
[myapp]
user = www-data
group = www-data
listen = /run/php/php8.5-fpm-myapp.sock
listen.owner = www-data
listen.group = www-data
listen.mode = 0660
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 5
pm.max_requests = 500
pm.status_path = /status
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Port Range | Production 8100-8199, Staging 9200-9299 | `listen 8100;` |
| Trust Proxy | Restore client IPs from HAProxy | `set_real_ip_from` |
| PHP-FPM Socket | Per-app Unix socket | `unix:/run/php/php8.5-fpm-{app}.sock` |
| try_files | Laravel routing | `try_files $uri $uri/ /index.php?$query_string;` |
| Stub Status | Metrics for nginx-exporter | `location /stub_status` |

## Common Patterns

### Production Laravel vhost

**When:** New production application deployment

```nginx
server {
    listen 8100;
    server_name _;
    root /opt/apps/rentalfixer/public;
    index index.php;

    set_real_ip_from 100.92.26.38;
    set_real_ip_from 100.89.130.19;
    set_real_ip_from 100.102.220.16;
    set_real_ip_from 100.116.175.9;
    real_ip_header X-Forwarded-For;
    real_ip_recursive on;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/run/php/php8.5-fpm-rentalfixer.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
        fastcgi_hide_header X-Powered-By;
        fastcgi_param REMOTE_ADDR $realip_remote_addr;
    }

    location ~ /\.ht {
        deny all;
    }
}
```

### Staging with Extended Timeouts

**When:** Staging environment with debugging enabled

```nginx
location ~ \.php$ {
    fastcgi_pass unix:/run/php/php8.5-fpm-rentalfixer-staging.sock;
    fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
    include fastcgi_params;
    fastcgi_hide_header X-Powered-By;
    
    # Extended timeouts for debugging
    fastcgi_param PHP_VALUE "max_execution_time=600\n memory_limit=256M";
    fastcgi_read_timeout 600;
}
```

## Operations

### Reload After Deployment

```bash
# Reload PHP-FPM after code deployment
sudo systemctl reload php8.5-fpm

# Test nginx configuration
sudo nginx -t

# Reload nginx gracefully
sudo systemctl reload nginx
```

### Check PHP-FPM Status

```bash
# View pool status
curl --unix-socket /run/php/php8.5-fpm-rentalfixer.sock http://localhost/status

# Check FPM error logs
sudo tail -f /var/log/php8.5-fpm/rentalfixer-error.log
```

## See Also

- [routes](references/routes.md) - Location block patterns and Laravel routing
- [services](references/services.md) - systemd integration and PHP-FPM management
- [errors](references/errors.md) - 502 debugging and common issues

## Related Skills

- **haproxy** - Load balancer that sits in front of nginx
- **ansible** - Server provisioning and configuration management
- **prometheus** - nginx-exporter metrics collection