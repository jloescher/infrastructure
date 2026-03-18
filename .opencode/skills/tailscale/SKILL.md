---
name: tailscale
description: Handles Tailscale VPN networking and secure server communication for the Quantyra infrastructure. Use when configuring Tailscale connectivity, troubleshooting network issues between servers, setting up firewall rules for Tailscale, or verifying Tailscale status on infrastructure components.
---

# Tailscale Skill

The Quantyra infrastructure uses Tailscale as the secure mesh VPN for all server-to-server communication. All infrastructure components communicate exclusively over Tailscale IPs (100.64.0.0/10), with public IPs only exposed to Cloudflare for inbound traffic. Tailscale SSH is disabled in favor of standard SSH key authentication over the Tailscale network.

## Quick Start

### Verify Tailscale Connectivity

```bash
# Check local Tailscale status
tailscale status

# Test connectivity to a server
ping 100.102.220.16

# Test from within Docker container
docker exec infrastructure-dashboard curl -s http://100.102.220.16:5000
```

### SSH Over Tailscale

```bash
# All SSH uses Tailscale IPs, not public IPs
ssh -i ~/.ssh/id_vps root@100.102.220.16

# Run remote commands via Tailscale
ssh root@100.102.220.16 'patronictl list'
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Tailnet IP | Server addressing | `100.102.220.16` (router-01) |
| Tailscale CIDR | Firewall trust zone | `100.64.0.0/10` |
| MagicDNS | Optional hostname resolution | `router-01` → `100.102.220.16` |
| Exit Node | Not used in this infra | N/A |

## Common Patterns

### Connecting Services via Tailscale

**When:** Dashboard or applications need to reach PostgreSQL, Redis, or other services.

```python
# Dashboard database connection via Tailscale
PG_HOST = "100.102.220.16"  # router-01 Tailscale IP
PG_PORT = "5000"            # HAProxy PostgreSQL write port

# Redis connection via Tailscale
REDIS_HOST = "100.126.103.51"  # re-node-01 Tailscale IP
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
```

### Firewall Rules for Tailscale

**When:** Configuring UFW on any infrastructure server.

```yaml
# security/firewall/ufw_rules.yml
tailscale_trusted:
  - comment: "Allow all Tailscale traffic"
    from: "100.64.0.0/10"
    port: "any"
    action: "allow"
```

## Server Inventory

| Server | Tailscale IP | Public IP | Role |
|--------|--------------|-----------|------|
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd |
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy, Monitoring |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy (Secondary) |
| re-db | 100.92.26.38 | 208.87.128.115 | App Server (Primary) |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) |

## See Also

- [patterns](references/patterns.md) - Common Tailscale patterns
- [workflows](references/workflows.md) - Troubleshooting and setup workflows

## Related Skills

- **ansible** - Server provisioning including Tailscale setup
- **haproxy** - Load balancing over Tailscale network
- **postgresql** - Database connections via Tailscale
- **redis** - Redis connections via Tailscale
- **docker** - Container networking with Tailscale