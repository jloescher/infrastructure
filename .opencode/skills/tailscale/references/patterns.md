# Tailscale Patterns Reference

## Contents
- Service Connection Patterns
- Firewall Configuration
- SSH Access Patterns
- Anti-Patterns

## Service Connection Patterns

### Database Connections via Tailscale

All database connections MUST use Tailscale IPs, never public IPs.

```python
# GOOD - Connect via Tailscale through HAProxy
conn = psycopg2.connect(
    host="100.102.220.16",  # router-01 Tailscale IP
    port="5000",            # HAProxy write port
    database="dashboard",
    user="patroni_superuser",
    password=os.getenv("PG_PASSWORD")
)
```

```python
# BAD - Never use public IPs for internal communication
conn = psycopg2.connect(
    host="172.93.54.112",   # router-01 public IP
    port="5000",
    ...
)
```

**Why:** Public IPs route through Cloudflare and expose traffic externally. Tailscale provides encrypted, zero-trust mesh networking between servers.

### Redis Connection Pattern

```python
# GOOD - Redis via Tailscale master
redis_client = redis.Redis(
    host="100.126.103.51",  # re-node-01 Tailscale IP
    port=6379,
    password=os.getenv("REDIS_PASSWORD"),
    decode_responses=True
)
```

### Monitoring Service Access

```python
# Prometheus API calls via Tailscale
PROMETHEUS_URL = "http://100.102.220.16:9090"
GRAFANA_URL = "http://100.102.220.16:3000"
ALERTMANAGER_URL = "http://100.102.220.16:9093"
LOKI_URL = "http://100.102.220.16:3100"
```

## Firewall Configuration

### UFW Rules for Tailscale

All servers trust the Tailscale CIDR block completely.

```yaml
# ansible/inventory/group_vars/all/ufw.yml
ufw_rules:
  - comment: "Tailscale mesh network"
    from: "100.64.0.0/10"
    port: "any"
    action: "allow"
    proto: "any"
```

### WARNING: Restricting Tailscale Traffic

**The Problem:**

```yaml
# BAD - Never restrict Tailscale to specific ports
ufw_rules:
  - comment: "Tailscale limited"
    from: "100.64.0.0/10"
    port: "22,80,443"  # WRONG - breaks mesh networking
    action: "allow"
```

**Why This Breaks:**
1. Tailscale requires UDP port 41641 for WireGuard tunneling
2. Internal service discovery uses various ports
3. Mesh networking needs unrestricted peer-to-peer connectivity

**The Fix:**

```yaml
# GOOD - Trust all Tailscale traffic
ufw_rules:
  - comment: "Tailscale full trust"
    from: "100.64.0.0/10"
    port: "any"
    action: "allow"
    proto: "any"
```

## SSH Access Patterns

### Standard SSH Over Tailscale

Tailscale SSH is disabled; use standard SSH with Tailscale IPs.

```bash
# GOOD - SSH to router via Tailscale IP
ssh -i ~/.ssh/id_vps root@100.102.220.16

# GOOD - Execute remote command
ssh root@100.116.175.9 'haproxy -c -f /etc/haproxy/haproxy.cfg'
```

### WARNING: Using Public IPs for SSH

**The Problem:**

```bash
# BAD - SSH to public IP bypasses Tailscale security
ssh -i ~/.ssh/id_vps root@172.93.54.112
```

**Why This Breaks:**
1. Exposes SSH to internet (though UFW should block)
2. Circumvents Tailscale's zero-trust model
3. Bypasses audit logging within Tailscale

**The Fix:**

```bash
# GOOD - Always use Tailscale IP
ssh -i ~/.ssh/id_vps root@100.102.220.16
```

### Ansible Inventory with Tailscale

```yaml
# ansible/inventory/hosts.yml
all:
  children:
    routers:
      hosts:
        router-01:
          ansible_host: 100.102.220.16  # Tailscale IP
          public_ip: 172.93.54.112      # For reference only
        router-02:
          ansible_host: 100.116.175.9
          public_ip: 23.29.118.6
```

## Docker Container Access

### Testing Connectivity from Containers

```bash
# GOOD - Test from dashboard container to Tailscale services
docker exec infrastructure-dashboard curl -s http://100.102.220.16:5000
docker exec infrastructure-dashboard redis-cli -h 100.126.103.51 -p 6379 ping
```

### WARNING: Hardcoded Tailscale IPs

**The Problem:**

```python
# BAD - Hardcoded IPs scattered in code
host = "100.102.220.16"  # Magic number, hard to maintain
```

**Why This Breaks:**
1. If server IPs change, must update everywhere
2. No central source of truth
3. Difficult to audit connections

**The Fix:**

```python
# GOOD - Use environment variables or config
PG_HOST = os.getenv("PG_HOST", "100.102.220.16")
REDIS_HOST = os.getenv("REDIS_HOST", "100.126.103.51")
```

Or use a configuration file:

```yaml
# dashboard/config/databases.yml
postgresql:
  host: "{{ env.PG_HOST | default('100.102.220.16') }}"
  port: 5000