# Cloudflare Patterns Reference

## Contents
- DNS Record Management
- SSL Certificate Patterns
- WAF Configuration
- Anti-Patterns

## DNS Record Management

### REQUIRED: Always Use Proxied Mode

```python
# GOOD - Proxied mode enables DDoS protection and WAF
data = {
    "type": "A",
    "name": "example.com",
    "content": router_ip,
    "proxied": True  # REQUIRED
}

# BAD - DNS-only loses all Cloudflare protections
data = {
    "type": "A", 
    "name": "example.com",
    "content": router_ip,
    "proxied": False  # NEVER do this for web traffic
}
```

### DNS Round-Robin for HA

Both router IPs must be registered for the same domain:

```python
# Create two A records for the same domain
router_ips = ["172.93.54.112", "23.29.118.6"]  # router-01, router-02

for ip in router_ips:
    requests.post(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
        headers=headers,
        json={
            "type": "A",
            "name": domain,
            "content": ip,
            "proxied": True
        }
    )
```

## SSL Certificate Patterns

### DNS-01 Challenge (Required with Proxy)

When `proxied: true`, HTTP-01 challenges fail. Use DNS-01:

```bash
# certbot with Cloudflare DNS plugin
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d example.com \
  -d www.example.com \
  --preferred-challenges dns-01
```

Credentials file format:
```ini
# /etc/letsencrypt/cloudflare.ini
dns_cloudflare_api_token = YOUR_CLOUDFLARE_API_TOKEN
```

### WARNING: Never Disable Proxy for SSL Validation

```python
# BAD - Disabling proxy to validate HTTP-01
# This exposes origin IP and bypasses DDoS protection
# Attackers can cache the origin IP before re-enabling proxy

# GOOD - Use DNS-01 challenge instead
# Stays proxied throughout certificate lifecycle
```

## WAF Configuration

### Standard Security Rules

Apply these 5 rules to all zones:

| Order | Action | Description |
|-------|--------|-------------|
| 1 | skip | Allow legitimate bots (Google, Bing, etc.) |
| 2 | managed_challenge | Challenge suspicious traffic |
| 3 | managed_challenge | Challenge known attackers |
| 4 | managed_challenge | Challenge rate-limited requests |
| 5 | block | Block SQL injection attempts |

### Staging Domain Protection

Use basic auth at HAProxy level for staging subdomains:

```bash
# /etc/haproxy/domains/web_https.cfg
# Staging domains get password protection
acl is_staging hdr(host) -i staging.example.com
http-request auth realm "Staging" if is_staging !{ http_auth_check(staging_users) }
```

## Anti-Patterns

### WARNING: Hardcoding Origin IPs in Applications

**The Problem:**
```python
# BAD - Application connects directly to origin IP
DB_HOST = "172.93.54.112"  # Breaks if server fails
```

**Why This Breaks:**
1. Bypasses Cloudflare's DDoS protection for API calls
2. No failover if that specific server goes down
3. Origin IP exposure in code repositories

**The Fix:**
```python
# GOOD - Use domain names that resolve via Cloudflare
DB_HOST = "api.internal.example.com"  # Tailscale or internal DNS
```

### WARNING: Caching Dynamic Content

**The Problem:**
```python
# BAD - Page Rules caching API endpoints
# Cloudflare caches POST responses or authenticated content
```

**The Fix:**
```python
# GOOD - Use Cache-Control headers from origin
# Or configure Page Rules to bypass cache for /api/*
```

### WARNING: Wrong SSL/TLS Mode

**The Problem:**
Setting SSL/TLS encryption mode to "Flexible" instead of "Full (strict)":

```yaml
# BAD - Flexible mode: Cloudflare → Origin is HTTP
# Origin expects HTTPS but gets HTTP, or certificate validation is skipped
```

**The Fix:**
```yaml
# GOOD - Full (strict) mode
# Encrypts end-to-end with valid origin certificates
# Required for Quantyra infrastructure compliance