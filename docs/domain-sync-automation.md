# Domain Sync Automation - Coolify + HAProxy

> **Automated SSL certificate provisioning and HAProxy configuration for Coolify domains**

**Created:** 2026-04-02  
**Last Updated:** 2026-04-02  
**Status:** Active

---

## Overview

The `sync-coolify-domains.sh` script automates the synchronization of domains from Coolify to HAProxy, ensuring that:

1. All domains added in Coolify receive SSL certificates
2. HAProxy HTTPS frontend includes all certificates
3. Configuration is synced to both routers
4. HAProxy is reloaded with zero downtime

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DOMAIN PROVISIONING FLOW                               │
│                                                                           │
│  1. User adds domain in Coolify UI                                        │
│     • Application → Configuration → Domains                              │
│     • Enter domain (e.g., myapp.domain.tld)                              │
│     • Coolify stores in PostgreSQL database                              │
│                                                                           │
│  2. Automated sync detects new domain                                     │
│     • sync-coolify-domains.sh queries Coolify DB                         │
│     • Detects domains missing SSL certificates                           │
│     • Cron runs every 5 minutes OR webhook triggers immediately          │
│                                                                           │
│  3. SSL Certificate Provisioning                                          │
│     • Certbot DNS-01 challenge via Cloudflare API                        │
│     • Certificate stored in /etc/haproxy/certs/domain.tld.pem            │
│     • Works with Cloudflare proxy enabled (orange cloud)                 │
│                                                                           │
│  4. HAProxy Configuration Rebuild                                         │
│     • HTTPS frontend bind line includes all certs                        │
│     • Routes ALL domains to coolify_backend                              │
│     • HTTP frontend redirects all to HTTPS                               │
│                                                                           │
│  5. HAProxy Reload (Zero-Downtime)                                        │
│     • systemctl reload haproxy                                           │
│     • Existing connections maintained                                     │
│     • New domains immediately available                                   │
│                                                                           │
│  6. Coolify Traefik Routing                                               │
│     • Receives HTTP traffic from HAProxy                                 │
│     • Routes by Host header to Docker container                          │
│     • Domain mapping managed by Coolify                                  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Script Details

**Location:** `/opt/scripts/sync-coolify-domains.sh`

**Purpose:**  
Query Coolify's PostgreSQL database for active domains, provision missing SSL certificates via certbot DNS-01 challenge, rebuild HAProxy HTTPS frontend with all certificates, and reload HAProxy on both routers.

**Prerequisites:**
- Coolify installed and running (router-01)
- PostgreSQL database container: `coolify-db`
- Cloudflare API token configured: `/root/.cloudflare.ini`
- HAProxy installed on router-01 and router-02
- Certbot installed with DNS-01 plugin

---

## Usage

### Normal Execution

```bash
# Run from router-01
ssh root@100.102.220.16 "/opt/scripts/sync-coolify-domains.sh"

# Or locally via SSH
/opt/scripts/sync-coolify-domains.sh
```

### Dry-Run Mode

```bash
# Test without making changes
/opt/scripts/sync-coolify-domains.sh --dry-run
```

**Dry-run shows:**
- Domains found in Coolify
- Certificates that would be provisioned
- HAProxy config that would be written
- Syncs that would happen to router-02

### View Logs

```bash
# Tail logs in real-time
tail -f /var/log/sync-coolify-domains.log

# View recent logs
tail -100 /var/log/sync-coolify-domains.log

# Search logs for errors
grep ERROR /var/log/sync-coolify-domains.log
```

---

## Script Behavior

### Step-by-Step Process

1. **Query Coolify Database**
   - Connects to `coolify-db` PostgreSQL container
   - Queries `applications.fqdn WHERE deleted_at IS NULL`
   - Returns distinct list of active domains

2. **Check Existing Certificates**
   - Scans `/etc/haproxy/certs/*.pem`
   - Identifies domains missing certificates

3. **Provision Missing Certificates**
   - Runs certbot with DNS-01 challenge:
     ```bash
     certbot certonly --dns-cloudflare \
         --dns-cloudflare-credentials /root/.cloudflare.ini \
         -d domain.tld
     ```
   - Combines cert + key into PEM format for HAProxy
   - Stores in `/etc/haproxy/certs/domain.tld.pem`

4. **Rebuild HAProxy HTTPS Frontend**
   - Collects ALL certificates from `/etc/haproxy/certs/`
   - Builds bind line:
     ```haproxy
     bind :443 ssl crt /etc/haproxy/certs/default.pem \
                       crt /etc/haproxy/certs/domain1.tld.pem \
                       crt /etc/haproxy/certs/domain2.tld.pem \
                       alpn h2,http/1.1
     ```
   - Writes `/etc/haproxy/domains/web_https.cfg`

5. **Ensure HTTP Redirects**
   - Writes `/etc/haproxy/domains/web_http.cfg`
   - Redirects ALL HTTP traffic to HTTPS

6. **Ensure Backend Configuration**
   - Writes `/etc/haproxy/domains/web_backends.cfg`
   - Routes to `coolify_backend` (re-db:80, re-node-02:80)

7. **Clear Registry**
   - Clears `/etc/haproxy/domains/registry.conf`
   - Coolify Traefik manages routing internally

8. **Validate HAProxy Config**
   - Runs: `haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains`
   - Exits if validation fails

9. **Reload HAProxy**
   - Runs: `systemctl reload haproxy`
   - Zero-downtime reload (existing connections maintained)

10. **Sync to router-02**
    - SCPs config files and certificates
    - Reloads HAProxy on router-02

### Idempotency & Safety

- ✅ **Idempotent**: Safe to run multiple times
- ✅ **Only adds domains with `deleted_at IS NULL`**
- ✅ **Preserves existing certificates** (doesn't delete or overwrite)
- ✅ **Validates HAProxy config before reload**
- ✅ **Dry-run mode for safe testing**
- ✅ **No changes if Coolify has no active domains**
- ✅ **No changes if all certs already exist**

---

## Cron Configuration

### Recommended Schedule

**Every 5 minutes** (recommended):

```bash
# Edit crontab
crontab -e

# Add this line:
*/5 * * * * /opt/scripts/sync-coolify-domains.sh >> /var/log/sync-coolify-domains.log 2>&1

# Verify
crontab -l | grep sync-coolify-domains
```

### Why 5-Minute Interval?

- **Near real-time**: Domains available within 5 minutes of adding in Coolify
- **Balanced load**: Not too frequent to cause unnecessary queries
- **Caching**: Certbot caches operations, no redundant provisioning
- **Quick enough**: Production apps don't need immediate availability

### Alternative Schedules

```bash
# Every 10 minutes (less frequent)
*/10 * * * * /opt/scripts/sync-coolify-domains.sh >> /var/log/sync-coolify-domains.log 2>&1

# Every 15 minutes (even less frequent)
*/15 * * * * /opt/scripts/sync-coolify-domains.sh >> /var/log/sync-coolify-domains.log 2>&1

# Hourly (not recommended - too slow)
0 * * * * /opt/scripts/sync-coolify-domains.sh >> /var/log/sync-coolify-domains.log 2>&1
```

---

## Coolify Webhook Integration (Optional)

For immediate domain sync (bypass 5-minute wait), you can set up a webhook handler:

### Webhook Endpoint (Future Enhancement)

**Note:** This is optional. The 5-minute cron sync is sufficient for most use cases.

```bash
# Create webhook endpoint on router-01 (port 8080)
# Example: Using Python Flask or Node.js Express

# Endpoint: POST /webhook/sync-domains
# Triggers: /opt/scripts/sync-coolify-domains.sh

# In Coolify UI:
# Settings → Webhooks → Add Webhook
# URL: http://100.102.220.16:8080/webhook/sync-domains
# Trigger: "Domain Added" event
```

### Current Recommendation

Use cron-based sync (5-minute interval). Webhook integration can be added later if immediate sync is critical for your use case.

---

## SSL Certificate Renewal

### Certbot Handles Renewal Automatically

Certbot's built-in renewal system handles certificate renewal:

```bash
# Check certbot renewal status
certbot certificates

# Certbot renewal runs twice daily via systemd timer
systemctl list-timers | grep certbot

# Manual renewal test (dry-run)
certbot renew --dry-run

# Force renewal (not recommended - let certbot handle it)
certbot renew --force-renewal
```

### Renewal Flow

1. **Certbot systemd timer** runs twice daily
2. **Checks all certificates** for expiration (< 30 days)
3. **Renews certificates** via DNS-01 challenge
4. **Renewed certs stored** in `/etc/letsencrypt/live/domain.tld/`
5. **Next sync script run** combines renewed certs into PEM for HAProxy
6. **HAProxy reloads** with renewed certificates

### Important Notes

- **The sync script does NOT handle renewal** - certbot handles this
- **The sync script only provisions NEW certificates** for domains added in Coolify
- **Renewed certificates are picked up automatically** on next sync script run
- **No manual intervention required** for certificate renewal

---

## Log Format

### Example Log Output

```
[2026-04-02 01:45:00 UTC] INFO: === Starting Coolify domain sync ===
[2026-04-02 01:45:01 UTC] INFO: Querying Coolify database for active domains...
[2026-04-02 01:45:01 UTC] INFO: Found 3 active domains in Coolify
[2026-04-02 01:45:02 UTC] INFO: Checking existing HAProxy SSL certificates...
[2026-04-02 01:45:02 UTC] INFO: Found 5 existing certificates in /etc/haproxy/certs
[2026-04-02 01:45:03 UTC] INFO: Identifying domains requiring SSL certificate provisioning...
[2026-04-02 01:45:03 UTC] INFO: Certificate exists for jonathanloescher.com
[2026-04-02 01:45:03 UTC] INFO: Certificate exists for rentalfixer.app
[2026-04-02 01:45:03 UTC] WARN: Missing certificate for myapp.domain.tld
[2026-04-02 01:45:03 UTC] INFO: Found 1 domains requiring new certificates
[2026-04-02 01:45:04 UTC] INFO: Provisioning missing SSL certificates...
[2026-04-02 01:45:04 UTC] INFO: Provisioning certificate for myapp.domain.tld...
[2026-04-02 01:45:35 UTC] INFO: Created HAProxy certificate: /etc/haproxy/certs/myapp.domain.tld.pem
[2026-04-02 01:45:36 UTC] INFO: Rebuilding HAProxy HTTPS frontend configuration...
[2026-04-02 01:45:36 UTC] INFO: Updated /etc/haproxy/domains/web_https.cfg with 6 certificates
[2026-04-02 01:45:37 UTC] INFO: Ensuring HTTP frontend redirects all traffic to HTTPS...
[2026-04-02 01:45:37 UTC] INFO: Updated /etc/haproxy/domains/web_http.cfg
[2026-04-02 01:45:38 UTC] INFO: Ensuring backend configuration...
[2026-04-02 01:45:38 UTC] INFO: Updated /etc/haproxy/domains/web_backends.cfg
[2026-04-02 01:45:39 UTC] INFO: Clearing registry.conf (Coolify manages domain routing)...
[2026-04-02 01:45:39 UTC] INFO: Cleared /etc/haproxy/domains/registry.conf
[2026-04-02 01:45:40 UTC] INFO: Validating HAProxy configuration...
[2026-04-02 01:45:40 UTC] INFO: HAProxy configuration validated successfully
[2026-04-02 01:45:41 UTC] INFO: Reloading HAProxy...
[2026-04-02 01:45:41 UTC] INFO: HAProxy reload complete
[2026-04-02 01:45:42 UTC] INFO: Syncing configuration to router-02...
[2026-04-02 01:45:45 UTC] INFO: Router-02 sync complete
[2026-04-02 01:45:46 UTC] INFO: === Sync Summary ===
[2026-04-02 01:45:46 UTC] INFO: Coolify domains processed: 3
[2026-04-02 01:45:46 UTC] INFO: New certificates provisioned: 1
[2026-04-02 01:45:46 UTC] INFO: Total certificates in HAProxy: 6
[2026-04-02 01:45:46 UTC] INFO: HAProxy status: active
[2026-04-02 01:45:47 UTC] INFO: === Sync complete ===
```

### Log Analysis

```bash
# Find all errors
grep ERROR /var/log/sync-coolify-domains.log

# Find all warnings
grep WARN /var/log/sync-coolify-domains.log

# Find all successful syncs
grep "Sync complete" /var/log/sync-coolify-domains.log

# Find certificates provisioned
grep "Created HAProxy certificate" /var/log/sync-coolify-domains.log

# Count syncs per day
grep "Sync complete" /var/log/sync-coolify-domains.log | \
    awk '{print $1}' | sort | uniq -c
```

---

## Troubleshooting

### Script Fails to Query Database

**Symptom:** `Failed to query Coolify database`

**Possible Causes:**
1. Coolify DB container not running
2. Database credentials incorrect
3. PostgreSQL not accepting connections

**Solutions:**
```bash
# Check if Coolify DB container is running
docker ps | grep coolify-db

# Restart Coolify DB if needed
docker restart coolify-db

# Test database connection manually
docker exec coolify-db psql -U coolify -d coolify -c "SELECT 1;"

# Check database logs
docker logs coolify-db --tail 100
```

### Certbot Fails to Provision Certificate

**Symptom:** `Failed to provision certificate for domain.tld`

**Possible Causes:**
1. Cloudflare API token invalid
2. DNS record doesn't exist
3. Cloudflare proxy not enabled (orange cloud)
4. Rate limit exceeded

**Solutions:**
```bash
# Test Cloudflare API token
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
     -H "Authorization: Bearer YOUR_TOKEN"

# Check certbot logs
certbot certificates

# Manual certificate provisioning
certbot certonly --dns-cloudflare \
    --dns-cloudflare-credentials /root/.cloudflare.ini \
    -d domain.tld --test-cert

# Check Cloudflare DNS record exists
dig domain.tld @1.1.1.1
```

### HAProxy Config Validation Fails

**Symptom:** `HAProxy configuration validation failed`

**Possible Causes:**
1. Syntax error in generated config
2. Missing certificate file
3. Port conflict

**Solutions:**
```bash
# Manual config validation
haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains

# Check for syntax errors
cat /etc/haproxy/domains/web_https.cfg

# Verify all certificates exist
ls -la /etc/haproxy/certs/*.pem

# Check HAProxy logs
journalctl -u haproxy -f
```

### HAProxy Fails to Reload

**Symptom:** `Failed to reload HAProxy`

**Possible Causes:**
1. HAProxy service not running
2. Config validation failed
3. System resource constraints

**Solutions:**
```bash
# Check HAProxy status
systemctl status haproxy

# Restart HAProxy if needed
systemctl restart haproxy

# Check HAProxy logs
journalctl -u haproxy -f

# Check system resources
free -h && df -h
```

### Sync to router-02 Fails

**Symptom:** `Failed to sync config files` or `Failed to reload HAProxy on router-02`

**Possible Causes:**
1. SSH key not authorized
2. Network connectivity issue
3. HAProxy not running on router-02

**Solutions:**
```bash
# Test SSH connectivity
ssh root@100.116.175.9 "hostname"

# Manual file sync
scp /etc/haproxy/domains/*.cfg root@100.116.175.9:/etc/haproxy/domains/
scp /etc/haproxy/certs/*.pem root@100.116.175.9:/etc/haproxy/certs/

# Check HAProxy on router-02
ssh root@100.116.175.9 "systemctl status haproxy"

# Reload HAProxy on router-02
ssh root@100.116.175.9 "systemctl reload haproxy"
```

---

## Verification & Runbooks

### Add New Domain to Coolify

**Prerequisites:**
- Coolify application deployed
- Domain ready to add

**Steps:**
1. **Add domain in Coolify UI:**
   ```
   Application → Configuration → Domains → Add Domain
   Enter: myapp.domain.tld
   Save
   ```

2. **Wait for sync (5 minutes max) or trigger manually:**
   ```bash
   ssh root@100.102.220.16 "/opt/scripts/sync-coolify-domains.sh"
   ```

3. **Verify SSL certificate:**
   ```bash
   # Check certificate exists
   ssh root@100.102.220.16 "ls -la /etc/haproxy/certs/myapp.domain.tld.pem"
   
   # Check certificate details
   openssl x509 -in /etc/haproxy/certs/myapp.domain.tld.pem -noout -text
   ```

4. **Verify HAProxy config:**
   ```bash
   # Check HTTPS frontend includes cert
   ssh root@100.102.220.16 "grep myapp.domain.tld /etc/haproxy/domains/web_https.cfg"
   
   # Check HAProxy status
   ssh root@100.102.220.16 "systemctl status haproxy"
   ```

5. **Add DNS record in Cloudflare:**
   ```
   Type: A
   Name: myapp
   Content: 172.93.54.112 (router-01)
   Proxy: Enabled (Orange Cloud)
   
   Type: A
   Name: myapp
   Content: 23.29.118.6 (router-02)
   Proxy: Enabled (Orange Cloud)
   ```

6. **Test domain:**
   ```bash
   # Test HTTPS
   curl -I https://myapp.domain.tld
   
   # Test in browser
   open https://myapp.domain.tld
   ```

7. **Check logs:**
   ```bash
   tail -50 /var/log/sync-coolify-domains.log
   ```

### Verify Sync Script is Running

```bash
# Check cron job
crontab -l | grep sync-coolify-domains

# Check recent logs
tail -20 /var/log/sync-coolify-domains.log

# Check last sync time
grep "Sync complete" /var/log/sync-coolify-domains.log | tail -1

# Count syncs today
grep "Sync complete" /var/log/sync-coolify-domains.log | \
    grep "$(date '+%Y-%m-%d')" | wc -l
```

### Manual Domain Sync (Immediate)

```bash
# Run sync immediately
ssh root@100.102.220.16 "/opt/scripts/sync-coolify-domains.sh"

# Check results
tail -30 /var/log/sync-coolify-domains.log
```

### Remove Domain from Coolify

**Note:** The sync script only ADDS domains, doesn't remove them.

**To remove a domain:**
1. Delete domain in Coolify UI
2. Domain remains in HAProxy (with cert)
3. HAProxy routes to Coolify → Coolify returns 404
4. Manual cleanup (optional):
   ```bash
   # Remove certificate
   rm /etc/haproxy/certs/domain.tld.pem
   
   # Remove from certbot
   certbot delete --cert-name domain.tld
   
   # Rebuild HAProxy config (run sync script)
   /opt/scripts/sync-coolify-domains.sh
   ```

---

## Related Documentation

- [Infrastructure Complete Overview](./infrastructure-complete-overview.md)
- [HAProxy Configuration](./haproxy_ha_dns.md)
- [Coolify Setup](./coolify-setup.md) (if exists)
- [Cloudflare Integration](./cloudflare.md)

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2026-04-02 | Created domain sync automation script and documentation | Senior DevOps Architect |

---

**Document Status:** Active  
**Next Review:** 2026-05-02