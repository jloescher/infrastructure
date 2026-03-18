---
name: cloudflare
description: Configures Cloudflare DNS, WAF rules, and DDoS protection for Quantyra infrastructure. Use when provisioning domains, configuring DNS records, setting up WAF rules, managing SSL certificates with DNS-01 challenges, or troubleshooting Cloudflare-proxied traffic.
---

# Cloudflare Skill

Cloudflare serves as the edge layer for Quantyra infrastructure, handling DNS, DDoS protection, WAF, and SSL termination. All domains use Cloudflare's proxied mode with DNS round-robin to two HAProxy routers. SSL certificates use DNS-01 challenges which work seamlessly with Cloudflare proxy enabled.

## Quick Start

### Create DNS A Record

```python
# From dashboard/app.py - Cloudflare DNS record creation
headers = {
    "Authorization": f"Bearer {cloudflare_api_token}",
    "Content-Type": "application/json"
}

data = {
    "type": "A",
    "name": domain,
    "content": router_ip,  # 172.93.54.112 or 23.29.118.6
    "ttl": 1,              # 1 = automatic
    "proxied": True        # REQUIRED for DDoS/WAF protection
}

response = requests.post(
    f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records",
    headers=headers,
    json=data
)
```

### DNS Round-Robin Setup

```python
# Both router IPs must be configured for HA
records = [
    {"name": "example.com", "content": "172.93.54.112"},  # router-01
    {"name": "example.com", "content": "23.29.118.6"}     # router-02
]
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Zone ID | Cloudflare zone identifier | `26470f68ef4dbbf7bf5a770630aa2a97` |
| Proxied mode | Traffic through Cloudflare edge | `"proxied": true` |
| DNS-01 challenge | SSL cert validation via DNS | `_acme-challenge.example.com` |
| Page Rule | URL forwarding/styling | `www` → root redirect |

## Common Patterns

### Domain Provisioning with SSL

**When:** Adding a new production domain with automatic SSL

```bash
# 1. Create DNS records (both routers)
# 2. Request SSL certificate via DNS-01
certbot certonly --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d example.com -d www.example.com

# 3. Update HAProxy registry
/opt/scripts/provision-domain.sh --rebuild
```

### WAF Rule Configuration

**When:** Setting up security rules for a zone

```yaml
# Security rules applied to all zones:
# 1. Allow legitimate bots
# 2. Challenge suspicious traffic (managed_challenge)
# 3. Challenge known attackers (managed_challenge)
# 4. Challenge rate-limited requests (managed_challenge)
# 5. Block SQL injection attempts
```

## See Also

- [patterns](references/patterns.md) - DNS and SSL patterns
- [workflows](references/workflows.md) - Domain provisioning workflows

## Related Skills

- **haproxy** - Load balancing configuration that works with Cloudflare DNS
- **nginx** - Origin server configuration behind Cloudflare proxy
- **ansible** - Infrastructure automation including Cloudflare API calls
- **python** - Flask dashboard uses Cloudflare API for DNS management