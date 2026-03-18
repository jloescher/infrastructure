# Tailscale Workflows Reference

## Contents
- Troubleshooting Connectivity
- Adding a New Server to Tailscale
- Rotating Tailscale IPs
- Network Debugging

## Troubleshooting Connectivity

### Quick Diagnostic Checklist

Copy this checklist and track progress:
- [ ] Step 1: Verify local Tailscale is running
- [ ] Step 2: Check Tailscale status
- [ ] Step 3: Test ping to target server
- [ ] Step 4: Verify target service is listening
- [ ] Step 5: Check firewall rules on target
- [ ] Step 6: Test from Docker container if applicable

### Step 1: Verify Tailscale Status

```bash
# Check if Tailscale is connected
tailscale status

# Expected output:
# 100.x.x.x       infrastructure      jonathans-macbook-pro  ...
# 100.102.220.16  router-01           linux                  ...
# 100.116.175.9   router-02           linux                  ...
```

### Step 2: Test Basic Connectivity

```bash
# Ping a server
ping -c 3 100.102.220.16

# If ping fails, check Tailscale on target server
ssh root@<public-ip> 'tailscale status'
```

### Step 3: Service-Specific Testing

```bash
# Test PostgreSQL via HAProxy
psql -h 100.102.220.16 -p 5000 -U patroni_superuser -c "SELECT 1"

# Test Redis
redis-cli -h 100.126.103.51 -p 6379 -a $REDIS_PASSWORD ping

# Test HAProxy stats
curl http://100.102.220.16:8404/stats
```

### Step 4: Docker Container Testing

```bash
# Enter dashboard container
docker exec -it infrastructure-dashboard /bin/sh

# Test from inside container
curl -s http://100.102.220.16:5000
```

### Step 5: Validate Firewall Rules

```bash
# On target server, check UFW status
ssh root@100.102.220.16 'ufw status verbose | grep 100.64'

# Expected: "Anywhere on Anywhere ALLOW IN   100.64.0.0/10"
```

## Adding a New Server to Tailscale

### Pre-Provisioning Checklist

Copy this checklist and track progress:
- [ ] Step 1: Generate Tailscale auth key
- [ ] Step 2: Add server to Ansible inventory
- [ ] Step 3: Include tailscale role in playbook
- [ ] Step 4: Run provisioning
- [ ] Step 5: Verify connectivity
- [ ] Step 6: Update documentation

### Step 1: Generate Auth Key

```bash
# From Tailscale admin console or CLI
tailscale login --advertise-exit-node=false
```

### Step 2: Ansible Integration

```yaml
# ansible/playbooks/provision.yml
- name: Provision server
  hosts: new_server
  roles:
    - common
    - tailscale
    - docker
```

```yaml
# ansible/inventory/hosts.yml
new_server:
  hosts:
    re-node-05:
      ansible_host: <public-ip>  # Initial connection
      tailscale_ip: "100.x.x.x"   # Assigned after join
```

### Step 3: Verify New Server

```bash
# From your machine
tailscale status | grep re-node-05

# Test connectivity
ping <new-tailscale-ip>
ssh root@<new-tailscale-ip> 'hostname'
```

## Rotating Tailscale IPs

### WARNING: IP Changes Require Updates

If a server's Tailscale IP changes, you MUST update:

1. **Ansible inventory** - `ansible/inventory/hosts.yml`
2. **Environment variables** - `.env` files
3. **Configuration files** - `dashboard/config/*.yml`
4. **Firewall rules** - If any use specific IPs (should use CIDR)
5. **Documentation** - `AGENTS.md`, runbooks

### Automated IP Verification

```bash
# Check for hardcoded IPs in codebase
grep -r "100\.102\.220\." --include="*.py" --include="*.yml" --include="*.env*"

# Check for outdated inventory
ansible-inventory --graph | grep -E "100\.[0-9]+\.[0-9]+\.[0-9]+"
```

## Network Debugging

### Capturing Tailscale Traffic

```bash
# On any server, capture WireGuard traffic
tcpdump -i tailscale0 -n host 100.102.220.16

# Capture specific port
tcpdump -i tailscale0 -n port 5000
```

### Checking Tailscale Routes

```bash
# View routing table
ip route show table all | grep 100.64

# Check Tailscale interfaces
ip addr show tailscale0
```

### Connection Logging

```bash
# Monitor Tailscale daemon logs
journalctl -u tailscaled -f

# Check for dropped packets
journalctl -u tailscaled | grep -i "drop\|reject"
```

### Iterative Debugging Pattern

When connectivity fails:

1. Make changes (firewall rules, service config)
2. Validate: `ping -c 3 <tailscale-ip>`
3. If validation fails, check `journalctl -u tailscaled -n 50`
4. Fix issues and repeat step 2
5. Only proceed when validation passes
6. Test actual service: `curl http://<tailscale-ip>:<port>/health`

## Related Skills

- **ansible** - See the **ansible** skill for server provisioning workflows
- **haproxy** - See the **haproxy** skill for load balancer configuration over Tailscale
- **postgresql** - See the **postgresql** skill for database connectivity patterns
- **docker** - See the **docker** skill for container networking