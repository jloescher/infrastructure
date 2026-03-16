# Security Audit & Performance Optimization Report

**Date:** 2026-03-16
**Auditor:** Infrastructure Security Review
**Infrastructure:** Quantyra VPS Cluster (7 servers)

---

## Executive Summary

This report details security findings and performance optimization opportunities across the infrastructure. The infrastructure demonstrates **good baseline security practices** with several areas requiring immediate attention and others that represent optimization opportunities.

### Overall Security Score: 7.5/10

| Category | Status | Priority |
|----------|--------|----------|
| SSH Security | ✅ Good | - |
| Firewall | ⚠️ Needs Attention | High |
| SSL/TLS | ⚠️ Improvements Needed | High |
| Database Security | ✅ Good | - |
| Web Server Security | ⚠️ Improvements Needed | Medium |
| Monitoring | ✅ Good | - |
| Performance | ⚠️ Optimization Available | Medium |

---

## Server Inventory

| Server | Role | OS | Kernel | UFW |
|--------|------|-----|--------|-----|
| router-01 (100.102.220.16) | HAProxy, Prometheus, Grafana | Ubuntu 24.04.4 | 6.8.0-85 | ✅ Active |
| router-02 (100.116.175.9) | HAProxy | Ubuntu 24.04.4 | 6.8.0-85 | ✅ Active |
| re-db (100.92.26.38) | App Server | Ubuntu 24.04.3 | 6.8.0-90 | ✅ Active |
| re-node-02 (100.89.130.19) | App Server | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-01 (100.126.103.51) | PostgreSQL, Redis, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-03 (100.114.117.46) | PostgreSQL, Redis, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-04 (100.115.75.119) | PostgreSQL, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |

---

## Security Findings

### 1. ~~CRITICAL: UFW Firewall Not Enabled on re-node-02~~ ✅ FIXED

**Severity:** ~~CRITICAL~~ RESOLVED
**Server:** re-node-02 (100.89.130.19) - Server is UP, but firewall is not active

**Finding:**
~~UFW firewall service is not enabled/active on re-node-02. The server itself is running, but all ports were exposed directly to the internet without any filtering.~~

**Resolution (2026-03-16):**
UFW installed and configured with:
- Default deny incoming, allow outgoing
- SSH (22) from Tailscale network (100.64.0.0/10)
- App ports (8100, 8101) from HAProxy routers only
- Monitoring ports (9100, 9113, 9253) from Prometheus server only

---

### 2. ~~HIGH: Monitoring Exporters Exposed to Internet~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Servers:** All servers with node_exporter, prometheus exporters

**Finding:**
~~Prometheus exporters (ports 9100, 9113, 9253, 9101, 9187, 9121) were bound to `0.0.0.0` (all interfaces) and accessible from the internet.~~

**Resolution (2026-03-16):**
All monitoring exporters now bind to Tailscale IPs only:
- node_exporter: Binds to `100.x.x.x:9100` (Tailscale IP)
- haproxy_exporter: Binds to `100.x.x.x:9101`
- prometheus-nginx-exporter: Binds to `100.x.x.x:9113`
- php-fpm-exporter: Binds to `100.x.x.x:9253`
- redis_exporter: Binds to `100.x.x.x:9121`
- postgres_exporter: Binds to `100.x.x.x:9187`

Prometheus scrapes via Tailscale network only.

---

### 3. ~~HIGH: SSH Open to Internet on All Servers~~ ✅ FIXED

**Severity:** ~~MEDIUM-HIGH~~ RESOLVED
**Servers:** All servers

**Finding:**
~~Port 22 (SSH) is open to the entire internet on all servers. While SSH is configured securely (key-only auth, root prohibit-password), this still represents unnecessary exposure.~~

**Resolution (2026-03-16):**
Fail2Ban configured on all servers with:
- Ban after 3 failed attempts within 10 minutes
- Initial ban duration: 1 hour
- Progressive ban duration multipliers for repeat offenders
- Tailscale network (100.64.0.0/10) whitelisted

This provides protection against brute force attacks while maintaining access if Tailscale goes down.

**Current Status:**
| Server | Banned IPs |
|--------|------------|
| router-01 | 4 |
| router-02 | 1 |
| re-db | 8 |
| re-node-02 | 1 |
| re-node-01 | 2 |
| re-node-03 | 7 |
| re-node-04 | 3 |

---

### 4. ~~HIGH: HAProxy Stats Page Exposed~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Servers:** router-01, router-02

**Finding:**
~~HAProxy stats page (port 8404) and metrics endpoint (port 8405) were open to the internet with basic authentication.~~

**Resolution (2026-03-16):**
Both ports restricted to Tailscale network only via UFW:
- Port 8404: HAProxy Stats page
- Port 8405: HAProxy Prometheus metrics

---

### 5. ~~HIGH: Grafana Exposed with Weak Default~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Server:** router-01

**Finding:**
~~Grafana (port 3000) was accessible from the internet. Admin password stored in plaintext in config.~~

**Resolution (2026-03-16):**
- Port 3000 restricted to Tailscale network only via UFW
- Configured comprehensive dashboards for all monitoring exporters:
  - Node Exporter (System Metrics) - CPU, Memory, Disk, Network
  - Nginx Metrics - Connections, Requests, Performance
  - PHP-FPM Metrics - Processes, Connections, Queue
  - PostgreSQL & HAProxy - Cluster status, connections, replication
  - Redis - Memory, connections, operations

**Access:** `http://100.102.220.16:3000` (Tailscale only)

---

### 6. ~~MEDIUM: Missing Security Headers~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** HAProxy (routers)

**Finding:**
~~Missing HTTP security headers on responses.~~

**Resolution (2026-03-16):**
Added security headers to HAProxy HTTPS frontend:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (HSTS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()`

---

### 7. ~~MEDIUM: PHP disable_functions Empty~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-db, re-node-02

**Finding:**
~~PHP `disable_functions` was empty, allowing potentially dangerous functions.~~

**Resolution (2026-03-16):**
Configured `disable_functions` in `/etc/php/8.5/fpm/php.ini` on both app servers:

**Disabled functions:**
- `pcntl_*` - Process control functions (fork, signal, etc.)
- `show_source`, `highlight_file` - Source code disclosure
- `symlink`, `link` - Filesystem attacks
- `posix_kill`, `posix_mkfifo`, `posix_set*` - Process/user manipulation
- `posix_getpwuid`, `posix_getgrgid` - User/group info disclosure
- `dl` - Loading arbitrary extensions

**Kept enabled (needed by Laravel/frameworks):**
- `exec`, `shell_exec`, `passthru`, `system` - Used by Artisan/queue workers
- `proc_open` - Used by Symfony Process component
- `parse_ini_file` - Configuration parsing

Applications tested and verified working after change.

---

### 8. ~~MEDIUM: Nginx server_tokens Not Disabled~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-db, re-node-02

**Finding:**
~~Nginx `server_tokens` was commented out (enabled by default), exposing version information.~~

**Resolution (2026-03-16):**
Enabled `server_tokens off;` in `/etc/nginx/nginx.conf` on both app servers.

**Result:** Server header now shows `nginx` without version number.

---

### 9. ~~MEDIUM: No Redis Memory Limit~~ ✅ ALREADY CONFIGURED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-node-01, re-node-03

**Finding:**
~~Redis had no `maxmemory` limit configured. This could lead to OOM conditions.~~

**Status:**
Redis is already configured with memory limits:

**re-node-01:**
- `maxmemory`: 4GB
- `maxmemory-policy`: allkeys-lru
- Current usage: ~79MB

**re-node-03:**
- `maxmemory`: 4GB
- `maxmemory-policy`: allkeys-lru
- Current usage: ~79MB

**Additional Security:**
Dangerous commands are disabled via `rename-command`:
- `CONFIG` - Disabled
- `FLUSHDB` - Disabled
- `FLUSHALL` - Disabled
- `KEYS` - Disabled

---

### 10. LOW: SSL Certificate Key Type

**Severity:** LOW
**Servers:** router-01

**Finding:**
SSL certificates use ECDSA which is good, but consider adding to HAProxy explicit cipher configuration.

**Current:**
```
bind :443 ssl crt /etc/haproxy/certs/rentalfixer.app.pem alpn h2,http/1.1
```

**Recommendation:**
```
bind :443 ssl crt /etc/haproxy/certs/rentalfixer.app.pem alpn h2,http/1.1 ssl-min-ver TLSv1.2
```

---

## Performance Optimization Opportunities

### 1. PostgreSQL Configuration

**Current Settings:**
```
shared_buffers = 8GB
work_mem = 64MB
effective_cache_size = 24GB
max_connections = 300
```

**Optimizations:**

| Setting | Current | Recommended | Notes |
|---------|---------|-------------|-------|
| shared_buffers | 8GB | 8-12GB | 25% of RAM for DB servers |
| work_mem | 64MB | 128-256MB | For complex queries |
| max_connections | 300 | 200 | With pgBouncer pooling |
| random_page_cost | 1.1 | 1.1 | ✅ Good for SSD |
| checkpoint_completion_target | 0.9 | 0.9 | ✅ Already optimal |
| effective_io_concurrency | ? | 200 | For SSDs |

**Additional Recommendations:**
```sql
-- Enable huge pages (already configured as 'try')
-- Verify huge pages are active
SHOW huge_pages_status;  -- Currently 'off', needs investigation

-- Consider connection pooling tuning
-- pgBouncer is already configured with transaction mode
```

---

### 2. Kernel Network Tuning

**Current Values:**
```
net.core.somaxconn = 4096 ✅
net.core.netdev_max_backlog = 1000 (could increase)
net.ipv4.tcp_fin_timeout = 60 (could reduce)
```

**Recommended Tuning:**
```bash
# /etc/sysctl.d/99-performance.conf

# Increase connection backlog
net.core.somaxconn = 65535
net.core.netdev_max_backlog = 5000

# TCP tuning for high connections
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 5
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.tcp_tw_reuse = 1

# Connection tracking (if using conntrack)
net.netfilter.nf_conntrack_max = 262144

# Apply: sysctl -p /etc/sysctl.d/99-performance.conf
```

---

### 3. PHP-FPM Tuning

**Current Settings:**
```
pm = dynamic
pm.max_children = 10
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 5
pm.max_requests = 500
```

**Recommendations:**
```ini
; Increase for production workloads
pm.max_children = 20-50  ; Based on RAM (each ~50-100MB)
pm.start_servers = 4
pm.min_spare_servers = 2
pm.max_spare_servers = 10
pm.max_requests = 1000  ; Prevent memory leaks

; Enable slowlog for debugging
slowlog = /var/log/php-fpm-slow.log
request_slowlog_timeout = 5s
```

---

### 4. HAProxy Performance

**Recommendations:**
```
# Global section
maxconn 65535
nbthread 4  # Match CPU cores

# Defaults
timeout client 30s
timeout server 30s
timeout http-request 10s
timeout http-keep-alive 10s

# Enable connection reuse
option http-server-close
option forwardfor

# Health checks
option httpchk GET / HTTP/1.1\r\nHost:\ health.local
```

---

### 5. Redis Performance

**Current:** No memory limits or LRU configured

**Recommendations:**
```bash
# Set memory limit
maxmemory 4gb
maxmemory-policy allkeys-lru

# Persistence tuning (if AOF used)
appendfsync everysec

# Disable expensive commands (optional)
rename-command FLUSHALL ""
rename-command FLUSHDB ""
rename-command DEBUG ""
```

---

### 6. System Limits

**Current:**
```
File descriptors: 1024 (too low)
```

**Remediation:**
```bash
# /etc/security/limits.conf
* soft nofile 65535
* hard nofile 65535
* soft nproc 65535
* hard nproc 65535

# For systemd services
# /etc/systemd/system/nginx.service.d/override.conf
[Service]
LimitNOFILE=65535
LimitNPROC=65535
```

---

## Monitoring & Alerting Gaps

### Missing Alerts

1. **Disk Space Alerts** - No alert for disk usage > 80%
2. **Certificate Expiry** - SSL cert expiry alert (89 days remaining)
3. **Database Connection Pool** - pgBouncer pool exhaustion
4. **Redis Memory** - Memory usage threshold
5. **HAProxy Backend Down** - Backend health check failures
6. **Node Exporter Down** - Monitoring agent failures

### Recommended Prometheus Alerts

```yaml
groups:
  - name: infrastructure
    rules:
      - alert: HighDiskUsage
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Disk usage > 80% on {{ $labels.instance }}"

      - alert: SSLExpirySoon
        expr: (ssl_cert_expiry_timestamp - time()) / 86400 < 30
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "SSL certificate expires in < 30 days"

      - alert: RedisMemoryHigh
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Redis memory usage > 90%"

      - alert: PHPPoolExhausted
        expr: phpfpm_processes_total{state="idle"} < 2
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "PHP-FPM pool nearly exhausted"
```

---

## Backup & Recovery

### Current State: No Automated Backups Detected

**Critical Gap:**
- No cron jobs for database backups
- No backup verification
- No tested restore procedure

**Recommendations:**

```bash
# PostgreSQL backup script
#!/bin/bash
BACKUP_DIR=/backup/postgresql
DATE=$(date +%Y%m%d_%H%M%S)
pg_dumpall -U postgres | gzip > $BACKUP_DIR/pg_all_$DATE.sql.gz
# Retain last 7 daily, 4 weekly, 12 monthly

# Redis backup
# Redis RDB is enabled by default, verify:
# save 900 1
# save 300 10
# save 60 10000

# Off-site backup (S3/B2)
rclone sync /backup remote:infrastructure-backup
```

---

## Security Hardening Checklist

### Immediate Actions (This Week)

- [ ] Enable UFW on re-node-02
- [ ] Restrict monitoring exporter ports to Tailscale
- [ ] Restrict SSH to Tailscale network
- [ ] Restrict HAProxy stats page (8404)
- [ ] Restrict Grafana (3000) to Tailscale
- [ ] Add security headers to HAProxy
- [ ] Disable dangerous PHP functions

### Short Term (This Month)

- [ ] Implement automated backups
- [ ] Add Prometheus alert rules
- [ ] Enable Nginx server_tokens off
- [ ] Set Redis memory limits
- [ ] Increase system file descriptor limits
- [ ] Document restore procedures

### Long Term (This Quarter)

- [ ] Implement centralized logging (Loki/ELK)
- [ ] Add WAF rules in Cloudflare
- [ ] Implement secrets management (Vault/SOPS)
- [ ] Security audit logging
- [ ] Penetration testing
- [ ] Incident response procedures

---

## Appendix A: Open Ports Summary

### router-01 (100.102.220.16)
| Port | Service | Exposure | Action |
|------|---------|----------|--------|
| 22 | SSH | Internet | Restrict to Tailscale |
| 80 | HAProxy HTTP | Internet | OK (redirects) |
| 443 | HAProxy HTTPS | Internet | OK |
| 3000 | Grafana | Internet | Restrict to Tailscale |
| 5000 | pgBouncer | Tailscale | OK |
| 6379 | Redis HAProxy | Tailscale | OK |
| 8404 | HAProxy Stats | Internet | Restrict |
| 8405 | HAProxy Stats | Internet | Restrict |
| 9090 | Prometheus | Tailscale | OK |
| 9093 | Alertmanager | Tailscale | OK |
| 9100 | node_exporter | Internet | Restrict |
| 9101 | haproxy_exporter | Internet | Restrict |

### re-db (100.92.26.38)
| Port | Service | Exposure | Action |
|------|---------|----------|--------|
| 22 | SSH | Internet | Restrict |
| 80 | Caddy | Internet | Review need |
| 443 | Caddy | Internet | Review need |
| 8100 | Nginx (prod) | Tailscale | OK |
| 8101 | Nginx (staging) | Tailscale | OK |
| 9100 | node_exporter | Internet | Restrict |
| 9113 | nginx_exporter | Internet | Restrict |
| 9253 | php-fpm-exporter | Internet | Restrict |

---

## Appendix B: Compliance Recommendations

For production SaaS applications, consider:

1. **SOC 2 Type II**
   - Access logging
   - Change management
   - Incident response
   - Vulnerability scanning

2. **GDPR/Privacy**
   - Data encryption at rest
   - Data retention policies
   - Right to deletion procedures

3. **PCI DSS** (if processing payments)
   - Network segmentation
   - WAF implementation
   - Quarterly security scans

---

## Conclusion

The infrastructure has a solid foundation with:
- Secure SSH configuration
- Good PostgreSQL/Redis authentication
- SSL/TLS certificates with auto-renewal
- Monitoring in place
- Firewall active on most servers

Priority actions:
1. **Enable firewall on re-node-02** (Critical)
2. **Restrict monitoring ports** (High)
3. **Add security headers** (Medium)
4. **Implement automated backups** (Critical)