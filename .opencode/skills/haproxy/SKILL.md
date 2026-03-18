---
name: haproxy
description: Configures HAProxy load balancing, SSL termination, and traffic routing for the Quantyra multi-region VPS infrastructure. Use when modifying HAProxy configurations, adding backends, provisioning domains, debugging routing issues, or updating SSL certificates across router-01 and router-02.
---

# HAProxy Skill

HAProxy provides consolidated SSL termination and layer 7 routing for all applications. Unlike per-domain frontends, this infrastructure uses a single HTTPS frontend on port 443 that routes by Host header ACLs. All configuration changes must propagate to both router-01 (100.102.220.16) and router-02 (100.116.175.9).

## Quick Start

### Add a New Application Backend

```haproxy
# /etc/haproxy/domains/web_backends.cfg
backend app_myapp_prod
    balance roundrobin
    option httpchk GET /health
    http-check expect status 200
    server re-db 100.92.26.38:8100 check inter 5s rise 2 fall 3
    server re-node-02 100.89.130.19:8100 check inter 5s rise 2 fall 3
```

### Route by Host Header

```haproxy
# /etc/haproxy/domains/web_https.cfg
frontend https_frontend
    bind *:443 ssl crt /etc/haproxy/certs/ alpn h2,http/1.1
    acl host_myapp hdr(host) -i myapp.com www.myapp.com
    use_backend app_myapp_prod if host_myapp
```

### Update Registry and Rebuild

```bash
# After modifying domain mappings
/opt/scripts/provision-domain.sh --rebuild

# Reload HAProxy without dropping connections
systemctl reload haproxy
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Frontend | Single entry point (port 443) | `frontend https_frontend` |
| Backend | App server pool | `backend app_<name>_<env>` |
| ACL | Host-based routing | `acl host_<name> hdr(host)` |
| Registry | Domain → port mapping | `/etc/haproxy/domains/registry.conf` |
| Health Check | Automatic failover | `option httpchk GET /health` |

## Common Patterns

### Port Allocation Convention

**When:** Provisioning new applications

| Range | Purpose |
|-------|---------|
| 8100-8199 | Production applications |
| 9200-9299 | Staging applications |
| 5000 | PostgreSQL writes (via HAProxy) |
| 5001 | PostgreSQL reads (load balanced) |
| 8404 | HAProxy stats page |

### SSL Certificate Management

**When:** Adding or renewing certificates

```bash
# Certificates stored in /etc/haproxy/certs/
# Concatenate: cert first, then intermediates
cat domain.crt intermediates.crt > /etc/haproxy/certs/domain.pem

# Rebuild config to pick up new certs
/opt/scripts/provision-domain.sh --rebuild
```

## See Also

- [patterns](references/patterns.md) - Configuration patterns and anti-patterns
- [workflows](references/workflows.md) - Domain provisioning and troubleshooting workflows

## Related Skills

- **nginx** - Web server configuration for application backends
- **cloudflare** - DNS management and CDN integration
- **ansible** - Server provisioning and configuration deployment
- **docker** - Container networking considerations
- **tailscale** - VPN network connectivity between routers