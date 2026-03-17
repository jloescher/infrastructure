# Cloudflare Integration

This document covers the Cloudflare integration for DNS management, security, and performance optimization.

## Overview

The infrastructure integrates with Cloudflare for:

- **DNS Management**: Automatic A record creation for domains
- **Security**: WAF rules for bot blocking and attack prevention
- **SSL/TLS**: End-to-end encryption with Cloudflare SSL
- **Performance**: CDN caching and optimization
- **DDoS Protection**: Automatic DDoS mitigation

## Configuration

### API Credentials

Stored in `/opt/dashboard/config/.env` on router-01:

```bash
CLOUDFLARE_API_TOKEN=your_token_here
CLOUDFLARE_ZONE_ID=26470f68ef4dbbf7bf5a770630aa2a97
CLOUDFLARE_ZONE_NAME=xotec.io
```

### Zone Information

| Zone | ID | Nameservers |
|------|-----|-------------|
| xotec.io | 26470f68ef4dbbf7bf5a770630aa2a97 | andy.ns.cloudflare.com, ines.ns.cloudflare.com |

### API Token Permissions

Required permissions for the API token:

| Permission | Scope | Description |
|------------|-------|-------------|
| Zone - DNS - Edit | All zones | Create/update DNS records |
| Zone - Zone - Read | All zones | Read zone information |
| Zone - Firewall Services - Edit | All zones | Create firewall rules |

## DNS Configuration

### DNS Read-Only View

When configuring domains through the dashboard, existing DNS records are displayed in read-only mode:

**Features:**
- Automatic fetch of existing DNS records from Cloudflare API
- Conflict indicators showing which records will be affected
- Refresh button to update record list without page reload

**Conflict Indicators:**

| Icon | Meaning | Action |
|------|---------|--------|
| ⚠️ | Will be updated | Record will be overridden with app IP |
| 🔒 | Read-only | Record cannot be modified through dashboard |
| Block | Conflict | Provisioning blocked - requires manual deletion |

**Conflict Resolution Rules:**

| Record | If Exists | Action |
|--------|-----------|--------|
| `@` (root A) | Any | Override with router IPs |
| `www` | Any | Override with router IPs |
| `staging` | Any | Override with router IPs |
| Other CNAMEs | Exists | Block provisioning with error |

**Behavior:**
- `@`, `www`, and `staging` records are automatically updated
- Other existing CNAMEs will block provisioning
- User must manually delete conflicting CNAMEs in Cloudflare dashboard

### Domain Types

| Type | Pattern | Example | Access |
|------|---------|---------|--------|
| Production (root) | `domain.tld` | xotec.io | Public |
| WWW redirect | `www.domain.tld` | www.xotec.io | Redirect to root |
| Production (subdomain) | `appname.domain.tld` | rentalfixer.xotec.io | Public |
| Staging | `staging.domain.tld` | staging.xotec.io | Password protected |

### DNS Records

Each domain gets two A records for high availability:

**Root domain configuration:**
```
Type: A
Name: @
Content: 172.93.54.112 (router-01)
Proxy: Proxied

Type: A
Name: @
Content: 23.29.118.6 (router-02)
Proxy: Proxied

Type: A
Name: www
Content: 172.93.54.112 (router-01)
Proxy: Proxied

Type: A
Name: www
Content: 23.29.118.6 (router-02)
Proxy: Proxied
```

**Subdomain configuration:**
```
Type: A
Name: appname
Content: 172.93.54.112 (router-01)
Proxy: Proxied

Type: A
Name: appname
Content: 23.29.118.6 (router-02)
Proxy: Proxied
```

### Proxied vs DNS Only

| Setting | Use Case | SSL | DDoS Protection |
|---------|----------|-----|-----------------|
| Proxied (orange cloud) | All apps | Yes | Yes |
| DNS Only (gray cloud) | Direct access | No | No |

**Always use Proxied mode** for security and performance benefits.

### Cloudflare Scripts

The script `/opt/scripts/cloudflare/cloudflare-api.sh` provides CLI access:

```bash
# Set environment
export CLOUDFLARE_API_TOKEN=your_token
export CLOUDFLARE_ZONE_ID=zone_id

# List zones
/opt/scripts/cloudflare/cloudflare-api.sh list-zones

# Create DNS record
/opt/scripts/cloudflare/cloudflare-api.sh create-dns appname 172.93.54.112 true

# Delete DNS record
/opt/scripts/cloudflare/cloudflare-api.sh delete-dns appname

# Provision production + staging
/opt/scripts/cloudflare/cloudflare-api.sh provision-domains appname xotec.io staging

# Create security rules
/opt/scripts/cloudflare/cloudflare-api.sh security-rules zone_id appname.xotec.io
```

## Security Rules

### Rule Order

Rules are evaluated in priority order. Lower number = higher priority.

### Action Types

| Action | Use | User Experience |
|--------|-----|-----------------|
| Allow | Whitelist | Request passes immediately |
| Block | Deny | Request blocked, no recourse |
| Managed Challenge | Verify | CAPTCHA shown, can pass if human |

### Rule 1: Allow Legitimate Bots

**Priority: 1** | **Action: Allow**

```
(cf.client.bot) or 
(cf.verified_bot_category in {
  "Search Engine Crawler" 
  "Search Engine Optimization" 
  "Monitoring & Analytics" 
  "Advertising & Marketing" 
  "Page Preview" 
  "Academic Research" 
  "Security" 
  "Accessibility" 
  "Webhooks" 
  "Feed Fetcher"
}) or 
(http.user_agent contains "letsencrypt" and http.request.uri.path contains "acme-challenge")
```

Allows:
- Verified bots (Google, Bing, etc.)
- Monitoring services
- LetsEncrypt certificate validation

### Rule 2: Challenge Suspicious Requests

**Priority: 2** | **Action: Managed Challenge**

Challenges suspicious user agents and traffic patterns. Shows CAPTCHA to verify human visitors.

### Rule 3: Challenge Known Attackers

**Priority: 3** | **Action: Managed Challenge**

Challenges traffic from threat intelligence feeds and known malicious IPs.

### Rule 4: Challenge Rate Limit

**Priority: 4** | **Action: Managed Challenge**

Challenges high request rates and API abuse patterns.

### Rule 5: Block SQL Injection

**Priority: 5** | **Action: Block**

Blocks SQL injection patterns and malicious request payloads.

## Staging Password Protection

Staging domains are protected via Cloudflare Basic Auth.

### Configuration

When provisioning a staging domain, the dashboard:
1. Creates a firewall rule matching the staging domain
2. Configures basic auth with username/password
3. Stores credentials in applications.yml

### Accessing Staging

1. Navigate to staging URL (e.g., `staging.appname.xotec.io`)
2. Browser prompts for credentials
3. Enter username (default: `admin`) and password

### Password Management

- **View**: Check domain details in dashboard
- **Reset**: Delete and re-provision the domain
- **Remove**: Not supported (staging requires protection)

## SSL/TLS Configuration

### SSL Mode

Set to **Full (Strict)** in Cloudflare dashboard:
- Cloudflare validates origin certificate
- Origin must have valid Let's Encrypt certificate

### Certificate Chain

```
Client ←→ Cloudflare (Cloudflare cert) ←→ HAProxy (Let's Encrypt cert) ←→ App
```

### Edge Certificates

Cloudflare automatically provides:
- Universal SSL certificate
- HTTP/3 (QUIC) support
- 0-RTT Connection Resumption
- Automatic HTTP/2

### Origin Certificates

HAProxy uses Let's Encrypt certificates:
- Auto-renewed via certbot
- Stored in `/etc/haproxy/certs/`
- Combined format (fullchain + privkey)

## Performance Optimization

### Caching

Configure page rules for static assets:

```
Match: *appname.xotec.io/static/*
Settings:
  - Cache Level: Cache Everything
  - Edge Cache TTL: 1 month
  - Browser Cache TTL: 1 year
```

### Rocket Loader

Enable Rocket Loader for JavaScript optimization:
- Defers JavaScript loading
- Improves page load time

### Auto Minify

Enable for CSS, JS, and HTML:
- Removes whitespace and comments
- Reduces file sizes

## Monitoring

### Cloudflare Analytics

Access analytics at:
```
https://dash.cloudflare.com/{zone_id}/analytics
```

Key metrics:
- Requests per second
- Bandwidth
- Threats blocked
- Cache hit ratio

### Cloudflare Logs

For Enterprise plans, access raw logs via:
- Logpush to S3/R2
- Logpull API
- Instant Logs (real-time)

## Troubleshooting

### DNS Not Propagating

```bash
# Check Cloudflare DNS
dig @andy.ns.cloudflare.com appname.xotec.io

# Check public DNS
dig appname.xotec.io

# Clear Cloudflare cache
# Dashboard → Caching → Purge Everything
```

### SSL Errors

1. Verify origin certificate exists:
   ```bash
   ls -la /etc/haproxy/certs/appname.xotec.io.pem
   ```

2. Test origin directly:
   ```bash
   curl -k https://100.92.26.38:8100 -H "Host: appname.xotec.io"
   ```

3. Check SSL mode in Cloudflare dashboard

### Firewall Rules Not Working

1. Check rule priority order
2. Verify rule is not paused
3. Test rule expression in Cloudflare dashboard
4. Check activity log for blocked requests

### Real IP Not Showing

1. Verify Cloudflare is proxied (orange cloud)
2. Check HAProxy headers configuration
3. Verify nginx real_ip settings

```bash
# Test headers
curl -I https://appname.xotec.io

# Check nginx logs
tail -f /var/log/nginx/access.log
```