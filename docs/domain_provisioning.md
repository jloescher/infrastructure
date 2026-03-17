# Domain Provisioning

This document covers the complete domain provisioning system for applications deployed on the Quantyra infrastructure.

## Overview

The infrastructure supports automated domain provisioning with:

- **Production domains**: `domain.tld` (root domain, not subdomain)
- **WWW redirect**: `www.domain.tld` → `domain.tld`
- **Staging domains**: `staging.domain.tld` (password-protected)
- **SSL certificates**: Automatic Let's Encrypt via Certbot (DNS-01 challenge)
- **DNS**: Automatic Cloudflare DNS configuration with multi-zone support
- **Security**: 5 Cloudflare WAF rules with managed_challenge support

## Domain Lifecycle

- Domains are stored in a single `domains` list per app.
- Wizard-selected domains are saved as `pending` and provisioned during deployment.
- Domains page is used for adding/removing additional domains after deployment.
- Each domain tracks status: `pending`, `provisioned`, or `failed` with error details.
- A Cloudflare zone selected by one app is locked and not selectable by other apps.

## Deployment Validation

Domain provisioning is validated as part of deployment:

- **Production domain check:** must return `200` (redirect chain to `200` is accepted)
- **Staging domain check:** `200` or `401` is accepted (staging auth enabled)

If validation fails, deployment is marked failed and domain status remains `failed` with router-level error details.

### Deploy Failure Handling

Implemented 2026-03-17 10:56 EDT. UX/API flow now makes deploy/provision behavior explicit:

- Deployment progress is split into two phases:
  - `deploy`
  - `domain_provisioning`
- When deploy fails, `domain_provisioning` is marked `skipped` (not attempted by default).
- A manual app-level action (**Force Provision Pending Domains**) is provided for explicit operator override after failed deploy.

### Force-Provision Operational Note (Updated 2026-03-17 12:21 EDT)

- Manual force-provision now uses bounded request behavior with in-progress guard rails.
- Router execution path now tolerates router-to-router SSH path issues via fallback connectivity strategy.
- Operational remediation completed (2026-03-17 12:50 EDT): restored non-interactive SSH from router-01 to router-02 and validated successful force-provision on both routers.

## Architecture

### Traffic Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  DNS (Proxied)          │  WAF Rules (5 total)          │   │
│  │  A record → router-01   │  1. Allow legitimate bots     │   │
│  │  A record → router-02   │  2. Challenge suspicious *    │   │
│  │  WWW A → router-01/02   │  3. Challenge known attackers*│   │
│  │  Staging A → routers    │  4. Challenge rate limit *    │   │
│  │                         │  5. Block SQL injection       │   │
│  │  * = managed_challenge (captcha)                         │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ CF-Connecting-IP
┌─────────────────────────────────────────────────────────────────┐
│                    HAProxy (Routers)                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Consolidated Frontend Architecture                     │   │
│  │                                                         │   │
│  │  web_http.cfg  → Single HTTP frontend (redirects)       │   │
│  │  web_https.cfg → Single HTTPS frontend (all certs)      │   │
│  │  web_backends.cfg → All backends                        │   │
│  │  registry.conf → Domain → App → Port mapping            │   │
│  │                                                         │   │
│  │  • SSL Termination (Let's Encrypt)                      │   │
│  │  • Routes by Host header                                │   │
│  │  • Round-robin to app servers                           │   │
│  │  • Health checks                                        │   │
│  │  • X-Forwarded-For headers                              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ X-Real-IP
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx (App Servers)                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  • Reverse Proxy (PHP-FPM for Laravel)                  │   │
│  │  • Static files                                         │   │
│  │  • real_ip_header X-Forwarded-For                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ REMOTE_ADDR
┌─────────────────────────────────────────────────────────────────┐
│                    Application                                  │
│  Laravel: $request->ip() returns real client IP                │
└─────────────────────────────────────────────────────────────────┘
```

### Consolidated Frontend Architecture

All domains share a single HAProxy frontend instead of having separate frontends:

**Why Consolidated?**
- Multiple frontends on port 443 cause SNI routing issues
- Single frontend with multiple certificates works reliably
- HAProxy uses Host header for routing after SSL termination
- Simpler to manage and debug

**Configuration Files:**

```
/etc/haproxy/domains/
├── web_http.cfg       # Single HTTP frontend
├── web_https.cfg      # Single HTTPS frontend
├── web_backends.cfg   # All application backends
└── registry.conf      # Domain registry
```

## Domain Provisioning

### Via Dashboard

Navigate to **Applications → [App Name] → Domains**

#### Multi-Domain Provisioning (Recommended)

1. **Select Zones**: Search and select multiple Cloudflare zones from the list
   - Zones are fetched automatically via API
   - Use search to filter zones by name
   - Selected zones appear as chips/tags

2. **Configure Per Domain**: Each selected domain has configuration options:
   - **Production Root**: Use root domain (`domain.tld`) instead of subdomain
   - **Staging**: Enable staging environment (`staging.domain.tld`)
   - **Additional CNAMEs**: Add subdomains (api, dashboard, etc.)

3. **Preview**: See live preview of what will be created:
   - Production domain with WWW redirect
   - Staging subdomain (if enabled)
   - Additional CNAMEs (if specified)

4. **Provision**: Click **Provision Selected Domains**

#### What Gets Created

For each domain configured with production root + staging:

| Type | Domain | Purpose |
|------|--------|---------|
| A | `domain.tld` | Production site |
| A | `www.domain.tld` | Redirect to production |
| A | `staging.domain.tld` | Password-protected staging |
| CNAME | `api.domain.tld` | API subdomain (if added) |

All domains get:
- SSL certificate via Let's Encrypt (DNS-01 challenge)
- 5 Cloudflare security rules
- HAProxy configuration on both routers
- Nginx configuration on both app servers (staging only)

### Via Command Line

The `provision-domain.sh` script handles domain provisioning:

```bash
# Basic usage
/opt/scripts/provision-domain.sh <domain> <app_name> <port>

# Production domain with www redirect
/opt/scripts/provision-domain.sh rentalfixer.app rentalfixer 8100 --www www.rentalfixer.app

# Staging domain
/opt/scripts/provision-domain.sh staging.rentalfixer.app rentalfixer_staging 8101 --staging

# Rebuild all configs from registry
/opt/scripts/provision-domain.sh --rebuild
```

### How It Works

1. **SSL Certificate Generation**
   - Uses DNS-01 challenge with Cloudflare
   - Reads credentials from `/root/.secrets/cloudflare.ini`
   - Certificate stored in `/etc/haproxy/certs/{domain}.pem`

2. **Registry Update**
   - Domain added to `/etc/haproxy/domains/registry.conf`
   - Format: `domain=app_name=port`

3. **Config Rebuild**
   - Reads all domains from registry
   - Generates consolidated frontend configs
   - Generates all backends

4. **HAProxy Reload**
   - Validates configuration
   - Reloads HAProxy service

## SSL Certificate Management

### DNS-01 Challenge (Primary Method)

**Why DNS-01?**
- Works with Cloudflare proxy enabled
- No need to stop HAProxy
- No exposed HTTP challenge endpoints

**How it works:**

```
provision-domain.sh
        ↓
certbot certonly --dns-cloudflare
        ↓
Certbot creates TXT record in Cloudflare DNS
        ↓
Let's Encrypt validates via DNS
        ↓
Certificate saved to /etc/letsencrypt/live/domain/
        ↓
Combined to /etc/haproxy/certs/domain.pem
        ↓
HAProxy config updated
        ↓
HAProxy reloaded
```

**Prerequisites:**
- Cloudflare API token with DNS edit permissions
- Credentials stored at `/root/.secrets/cloudflare.ini` on both routers

```ini
# /root/.secrets/cloudflare.ini
dns_cloudflare_api_token = your_token_here
```

### Certificate Storage

| Location | Purpose |
|----------|---------|
| `/etc/letsencrypt/live/{domain}/` | Let's Encrypt certificates |
| `/etc/haproxy/certs/{domain}.pem` | Combined cert + key for HAProxy |

### Auto-Renewal

Certbot sets up automatic renewal via systemd timer:
- Checks twice daily
- Renews certificates 30 days before expiry
- Uses same DNS-01 challenge for renewal

**Important**: After renewal, HAProxy must be reloaded to pick up new certificates:

```bash
# Check renewal status
certbot renew --dry-run

# Manual renewal
certbot renew && systemctl reload haproxy
```

**Recommended**: Add a deploy hook for automatic HAProxy reload:

```bash
# /etc/letsencrypt/renewal-hooks/deploy/haproxy-reload.sh
#!/bin/bash
systemctl reload haproxy
```

### Manual Certificate Management

```bash
# List certificates
certbot certificates

# Renew specific certificate
certbot renew --cert-name domain.tld

# Revoke a certificate
certbot revoke --cert-path /etc/letsencrypt/live/domain.tld/cert.pem

# Check certificate details
openssl x509 -in /etc/haproxy/certs/domain.tld.pem -noout -text
```

## Domain Registry

The `registry.conf` file tracks all registered domains:

```
# Format: domain=app_name=port
rentalfixer.app=rentalfixer=8100
staging.rentalfixer.app=rentalfixer_staging=8101
www.rentalfixer.app=rentalfixer_www_redirect=8100
```

**WWW Redirects**:
- Domains starting with `www.` are treated as redirects
- The registry tracks them with `_www_redirect` suffix
- Config generated redirects to the non-www domain

### Managing the Registry

```bash
# View all registered domains
cat /etc/haproxy/domains/registry.conf

# Add a domain manually
echo "newdomain.tld=appname=8102" >> /etc/haproxy/domains/registry.conf
/opt/scripts/provision-domain.sh --rebuild

# Remove a domain
sed -i '/^domain.tld=/d' /etc/haproxy/domains/registry.conf
rm /etc/haproxy/certs/domain.tld.pem
/opt/scripts/provision-domain.sh --rebuild
```

## DNS Configuration

### DNS Read-Only View

When configuring domains through the dashboard, existing DNS records are displayed in read-only mode:

- **Automatic Fetch**: DNS records are fetched from Cloudflare API
- **Conflict Indicators**: Records that will be updated are highlighted
- **Lock Icons**: Indicates records cannot be modified through the dashboard

### Conflict Resolution Rules

| Record Type | If Exists | Action |
|-------------|-----------|--------|
| `@` (root A) | Any value | Override with router IPs |
| `www` | Any value | Override with router IPs |
| `staging` | Any value | Override with router IPs |
| Other CNAMEs | Exists | Block provisioning, show error |

**Behavior:**
- `@`, `www`, and `staging` records are automatically updated with the correct router IPs
- Other existing CNAMEs will block provisioning with an error message
- User must manually delete conflicting CNAMEs in Cloudflare dashboard before provisioning

### DNS Refresh

Refresh DNS records at any time:
- **Domains Page**: Click refresh button to reload records
- **App Creation Wizard**: Click refresh icon in Step 5 (Domain Configuration)
- Records are re-fetched from Cloudflare without page reload

### For Cloudflare-Managed Domains (Auto-Configured)

| Type | Name | Content | Proxy | Purpose |
|------|------|---------|-------|---------|
| A | @ | 172.93.54.112 | Proxied | Production (router-01) |
| A | @ | 23.29.118.6 | Proxied | Production (router-02) |
| A | www | 172.93.54.112 | Proxied | WWW redirect |
| A | www | 23.29.118.6 | Proxied | WWW redirect |
| A | staging | 172.93.54.112 | Proxied | Staging (router-01) |
| A | staging | 23.29.118.6 | Proxied | Staging (router-02) |

### For Manual DNS

| Type | Name | Content | TTL |
|------|------|---------|-----|
| A | @ | 172.93.54.112 | 300 |
| A | @ | 23.29.118.6 | 300 |

## Security Rules

### Rule Priority Order

| Priority | Rule | Action | Description |
|----------|------|--------|-------------|
| 1 | Allow legitimate bots | Allow | Google, Bing, LetsEncrypt, monitoring tools |
| 2 | Challenge suspicious | Managed Challenge | Suspicious user agents, crawlers |
| 3 | Challenge known attackers | Managed Challenge | IPs from threat intelligence feeds |
| 4 | Challenge rate limit | Managed Challenge | High request rates, API abuse |
| 5 | Block SQL injection | Block | SQL injection patterns in requests |

### Managed Challenge vs Block

- **Managed Challenge** (Rules 2, 3, 4): Shows CAPTCHA to user
  - Legitimate users can pass
  - Bots and attackers are blocked
  - Reduces false positives
  
- **Block** (Rules 1, 5): Immediate action
  - Rule 1: Allow whitelisted bots (no challenge)
  - Rule 5: Block malicious requests (no chance to pass)

## Staging Password Protection

Staging domains are protected by Cloudflare Basic Auth.

### Default Behavior

- Auto-generated password (16 characters)
- Username: `admin`
- Password stored in application config

### Accessing Staging

1. Navigate to `staging.domain.tld`
2. Enter credentials when prompted
3. Password viewable in dashboard domain list

## Client IP Forwarding

### How It Works

```
Client IP: 1.2.3.4

Cloudflare receives request
    ↓ Adds CF-Connecting-IP: 1.2.3.4
    
HAProxy receives request
    ↓ Reads CF-Connecting-IP
    ↓ Sets X-Forwarded-For: 1.2.3.4
    ↓ Sets X-Real-IP: 1.2.3.4
    
Nginx receives request
    ↓ real_ip_header X-Forwarded-For
    ↓ real_ip_recursive on
    ↓ REMOTE_ADDR = 1.2.3.4
    
Application receives real client IP
```

### Laravel Configuration

```php
// app/Http/Middleware/TrustProxies.php
protected $proxies = '*';
protected $headers = Request::HEADER_X_FORWARDED_ALL;

// Usage
$ip = $request->ip();
```

### Next.js Configuration

```javascript
// next.config.js
module.exports = {
  experimental: {
    trustHostHeader: true,
  },
}

// Usage
const ip = req.headers['x-forwarded-for']?.split(',')[0] || req.socket.remoteAddress;
```

## Deleting Domains

### Delete Staging Environment

Via Dashboard: **Applications → [App Name] → Delete → Delete Staging**

This removes:
- Staging nginx config from both app servers
- Staging PHP-FPM pool from both app servers
- Staging SSL certificate from both routers
- Staging entry from registry.conf
- Staging database users (`{app}_staging_user`, `{app}_staging_admin`)
- Staging database
- Rebuilds HAProxy configs

Keeps:
- DNS records
- Cloudflare WAF rules
- Production environment

### Delete Entire Application

Via Dashboard: **Applications → [App Name] → Delete → Delete Application**

This removes:
- All server configurations (app servers + routers)
- All SSL certificates from both routers
- All HAProxy registry entries and rebuilds config
- PM2 processes (for Node.js apps)
- All database users (`{app}_user`, `{app}_admin`, `{app}_staging_user`, `{app}_staging_admin`)
- Databases (after confirmation)
- Secrets file (`/opt/dashboard/secrets/{app}.yaml`)
- Application from applications.yml

**Note**: DNS records and WAF rules are NOT deleted automatically to allow easy redeployment or manual cleanup in Cloudflare dashboard.

## Troubleshooting

### 503 Errors

1. Check HAProxy status: `systemctl status haproxy`
2. Check backend servers: `echo 'show stat' | socat stdio /run/haproxy/admin.sock`
3. Check certificate exists: `ls -la /etc/haproxy/certs/`
4. Validate config: `haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains`
5. Check domain is in registry: `cat /etc/haproxy/domains/registry.conf`

### SSL Certificate Issues

```bash
# Check certificate status
certbot certificates

# Force renewal
certbot renew --force-renewal

# Check HAProxy cert file
openssl x509 -in /etc/haproxy/certs/domain.tld.pem -noout -text

# Verify DNS-01 credentials
cat /root/.secrets/cloudflare.ini
```

### Domain Not Routing

1. Check domain in registry: `grep "domain.tld" /etc/haproxy/domains/registry.conf`
2. Rebuild configs: `/opt/scripts/provision-domain.sh --rebuild`
3. Check HAProxy logs: `journalctl -u haproxy -f`

### DNS Propagation

```bash
# Check DNS resolution
dig domain.tld

# Check from specific DNS server
dig @1.1.1.1 domain.tld

# Check both routers are returned
dig +short domain.tld A
```

## Files Reference

| File | Purpose |
|------|---------|
| `/opt/scripts/provision-domain.sh` | Domain provisioning script |
| `/etc/haproxy/domains/registry.conf` | Domain registry |
| `/etc/haproxy/domains/web_http.cfg` | HTTP frontend config |
| `/etc/haproxy/domains/web_https.cfg` | HTTPS frontend config |
| `/etc/haproxy/domains/web_backends.cfg` | Backend configs |
| `/etc/haproxy/certs/*.pem` | SSL certificates |
| `/root/.secrets/cloudflare.ini` | Cloudflare API credentials |
| `/opt/dashboard/config/.env` | Dashboard API credentials |
| `/opt/dashboard/config/applications.yml` | Application configs with domains |
