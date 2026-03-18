# HAProxy Workflows Reference

## Contents
- Domain Provisioning Workflow
- Config Rebuild Workflow
- Troubleshooting Workflow
- SSL Certificate Renewal

## Domain Provisioning Workflow

Provisioning a domain updates DNS, generates SSL certificates, and configures HAProxy routing.

### Copy this checklist and track progress:
- [ ] Step 1: Verify Cloudflare API credentials
- [ ] Step 2: Run provision-domain.sh with domain parameters
- [ ] Step 3: Validate DNS A records created
- [ ] Step 4: Confirm SSL certificates generated
- [ ] Step 5: Verify HAProxy config rebuilt on both routers
- [ ] Step 6: Test HTTPS endpoint responds correctly
- [ ] Step 7: Verify staging subdomain has basic auth

### Step-by-Step

```bash
# 1. Provision domain (runs on router-01)
/opt/scripts/provision-domain.sh \
    --domain myapp.com \
    --app myapp \
    --port 8100 \
    --staging-port 9200 \
    --servers "100.92.26.38,100.89.130.19"

# 2. Script executes:
#    - Creates Cloudflare DNS A records (proxied)
#    - Generates SSL via certbot DNS-01 challenge
#    - Updates registry.conf with domain → port mapping
#    - Rebuilds HAProxy configs
#    - Reloads HAProxy on both routers
```

### Validation

```bash
# Test from outside infrastructure
curl -I https://myapp.com
curl -I https://staging.myapp.com  # Should prompt for auth

# Check HAProxy stats
curl http://100.102.220.16:8404/stats
```

## Config Rebuild Workflow

Use this when manually editing registry.conf or backend definitions.

### Copy this checklist and track progress:
- [ ] Step 1: Edit configuration fragment
- [ ] Step 2: Validate syntax on one router
- [ ] Step 3: Copy changes to second router
- [ ] Step 4: Validate syntax on second router
- [ ] Step 5: Reload HAProxy on both routers
- [ ] Step 6: Verify health checks passing

### Step-by-Step

```bash
# 1. Edit backend configuration
ssh root@100.102.220.16
vim /etc/haproxy/domains/web_backends.cfg

# 2. Validate syntax
haproxy -c -f /etc/haproxy/haproxy.cfg

# 3. If valid, run rebuild to sync to router-02
/opt/scripts/provision-domain.sh --rebuild

# 4. Reload both routers
ssh root@100.102.220.16 'systemctl reload haproxy'
ssh root@100.116.175.9 'systemctl reload haproxy'
```

### Feedback Loop

1. Make changes to `/etc/haproxy/domains/`
2. Validate: `haproxy -c -f /etc/haproxy/haproxy.cfg`
3. If validation fails, fix errors and repeat step 2
4. Only proceed when validation passes with "Configuration file is valid"

## Troubleshooting Workflow

### Copy this checklist and track progress:
- [ ] Step 1: Check HAProxy service status
- [ ] Step 2: Verify configuration syntax
- [ ] Step 3: Review recent logs
- [ ] Step 4: Check backend health in stats
- [ ] Step 5: Verify network connectivity
- [ ] Step 6: Validate certificate expiration

### Common Issues

#### Config Test Fails

```bash
# Check syntax with detailed error
haproxy -c -f /etc/haproxy/haproxy.cfg

# Common causes:
# - Missing certificate file
# - Backend server IP unreachable
# - Syntax error in ACL definition
```

#### Backend Shows DOWN

```bash
# Check from HAProxy router
curl -I http://100.92.26.38:8100/health

# Verify app server is listening
ssh root@100.92.26.38 'ss -tlnp | grep 8100'

# Check firewall rules
ssh root@100.92.26.38 'ufw status numbered'
```

#### SSL Certificate Errors

```bash
# Check certificate expiration
echo | openssl s_client -servername myapp.com \
    -connect 100.102.220.16:443 2>/dev/null | openssl x509 -noout -dates

# Verify cert file exists and is readable
ls -la /etc/haproxy/certs/myapp.com.pem
openssl x509 -in /etc/haproxy/certs/myapp.com.pem -text -noout
```

## SSL Certificate Renewal

### Copy this checklist and track progress:
- [ ] Step 1: Check current certificate expiration
- [ ] Step 2: Run certbot renewal
- [ ] Step 3: Verify new certificates generated
- [ ] Step 4: Update HAProxy certificate files
- [ ] Step 5: Reload HAProxy gracefully
- [ ] Step 6: Verify new certificate served

### Automated Renewal

```bash
# Certbot runs daily via systemd timer
systemctl list-timers | grep certbot

# Manual renewal test (doesn't actually renew)
certbot renew --dry-run
```

### Manual Renewal

```bash
# Force renewal for specific domain
certbot certonly --force-renew \
    -d myapp.com -d www.myapp.com \
    --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini

# Rebuild HAProxy certs
/opt/scripts/provision-domain.sh --rebuild

# Reload HAProxy
systemctl reload haproxy
```

### WARNING: Certificate Chain Issues

**The Problem:**
Browser shows certificate invalid even though file exists.

**Why This Happens:**
1. Missing intermediate certificates in the chain
2. Certificate file has wrong order (key must be first)
3. Certificate permissions prevent HAProxy from reading

**The Fix:**

```bash
# Verify chain order
cat /etc/haproxy/certs/myapp.com.pem | grep -E 'BEGIN|END'

# Expected order:
# -----BEGIN PRIVATE KEY-----
# -----END PRIVATE KEY-----
# -----BEGIN CERTIFICATE----- (domain cert)
# -----END CERTIFICATE-----
# -----BEGIN CERTIFICATE----- (intermediate)
# -----END CERTIFICATE-----

# Fix permissions
chmod 644 /etc/haproxy/certs/*.pem
```

## Failover Testing

Test high availability by simulating router failure.

```bash
# 1. Verify both IPs in DNS
dig myapp.com +short

# 2. Stop HAProxy on primary router
ssh root@100.102.220.16 'systemctl stop haproxy'

# 3. Test requests still succeed (via router-02)
curl -I https://myapp.com

# 4. Restart HAProxy
ssh root@100.102.220.16 'systemctl start haproxy'
```

See the **cloudflare** skill for DNS-level failover configuration.
```

The files are ready. They include:
- **SKILL.md** (72 lines): Quick reference with consolidated frontend pattern, backend examples, and port allocation conventions
- **patterns.md** (149 lines): Configuration structure, 3 documented anti-patterns with WARNING headers, backend patterns, SSL management, and monitoring setup
- **workflows.md** (192 lines): 4 checklisted workflows (domain provisioning, config rebuild, troubleshooting, SSL renewal) with feedback loops and real server IPs from your infrastructure