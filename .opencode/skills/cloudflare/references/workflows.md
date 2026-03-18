# Cloudflare Workflows Reference

## Contents
- Domain Provisioning Workflow
- SSL Certificate Renewal
- WAF Rule Updates
- Troubleshooting Guide

## Domain Provisioning Workflow

Complete workflow for adding a new domain to the infrastructure.

Copy this checklist and track progress:
- [ ] Step 1: Validate domain ownership in Cloudflare
- [ ] Step 2: Create DNS A records (both routers, proxied)
- [ ] Step 3: Request SSL certificate via DNS-01
- [ ] Step 4: Configure HAProxy backend
- [ ] Step 5: Verify end-to-end connectivity

### Step 1: Create DNS Records

```python
def provision_domain_cloudflare(domain, zone_id, api_token):
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    router_ips = ["172.93.54.112", "23.29.118.6"]
    
    for ip in router_ips:
        data = {
            "type": "A",
            "name": domain,
            "content": ip,
            "ttl": 1,
            "proxied": True
        }
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
            headers=headers,
            json=data
        )
        response.raise_for_status()
```

### Step 2: Request SSL Certificate

```bash
#!/bin/bash
DOMAIN=$1

certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}" \
  -d "staging.${DOMAIN}" \
  --preferred-challenges dns-01 \
  --deploy-hook "systemctl reload haproxy"
```

### Step 3: Validation Loop

1. Make changes (DNS + SSL)
2. Validate: `dig +short example.com` should return Cloudflare IPs (not origin)
3. Validate: `curl -I https://example.com` returns 200 with `CF-RAY` header
4. If validation fails, check:
   - DNS propagation: `dig @1.1.1.1 example.com`
   - SSL certificate: `openssl s_client -connect example.com:443`
   - HAProxy config: `haproxy -c -f /etc/haproxy/haproxy.cfg`

Only proceed when all validations pass.

## SSL Certificate Renewal

All certificates auto-renew via certbot timer. Manual renewal workflow:

```bash
# Test renewal (dry run)
certbot renew --dns-cloudflare --dry-run

# Force renewal if needed
certbot renew --dns-cloudflare --force-renewal

# Reload HAProxy after renewal
systemctl reload haproxy
```

### WARNING: Renewal Failures

If DNS-01 renewal fails:
1. Check Cloudflare API token hasn't expired
2. Verify token has `Zone:Read` and `DNS:Edit` permissions
3. Test manually: `certbot certonly --dns-cloudflare -d example.com`

## WAF Rule Updates

Deploying new WAF rules across all zones:

```python
def update_waf_rules(zone_id, api_token):
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }
    
    # Get existing rules
    response = requests.get(
        f"https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/rules",
        headers=headers
    )
    rules = response.json()["result"]
    
    # Update or create rules
    for rule in waf_rule_definitions:
        existing = find_rule(rules, rule["description"])
        if existing:
            # Update
            requests.put(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/rules/{existing['id']}",
                headers=headers,
                json=rule
            )
        else:
            # Create
            requests.post(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/firewall/rules",
                headers=headers,
                json=rule
            )
```

## Troubleshooting Guide

### Issue: 525/526 SSL Handshake Errors

**Cause:** Origin certificate invalid or Full (strict) mode enabled without valid cert

**Fix:**
```bash
# Check origin certificate
openssl s_client -connect router-01:443 -servername example.com

# Verify certbot certificate exists
ls -la /etc/letsencrypt/live/example.com/

# If missing, reissue
certbot certonly --dns-cloudflare -d example.com --force-renewal
```

### Issue: DNS Not Resolving

**Validation:**
```bash
# Check Cloudflare nameservers
dig NS example.com

# Verify A records exist
dig A example.com @1.1.1.1

# Check if proxied (returns Cloudflare IPs)
dig A example.com +short
# Should return: 104.21.x.x or 172.67.x.x (Cloudflare anycast)
# NOT: 172.93.54.112 (origin IP)
```

### Issue: WAF Blocking Legitimate Traffic

**Quick fix:**
```bash
# Find blocking rule in Cloudflare logs
# Dashboard: Security > Events

# Create bypass rule for specific IP/path if needed
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/firewall/rules" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "filter": {"expression": "ip.src eq 1.2.3.4"},
    "action": "allow",
    "description": "Emergency bypass for monitoring"
  }'