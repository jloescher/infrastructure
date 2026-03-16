# Security Audit Report
**Date**: 2026-03-15

## Summary

| Category | Status | Action Taken |
|----------|--------|--------------|
| SSH Hardening | ✅ Fixed | PermitRootLogin set to prohibit-password on all servers |
| Password Auth | ✅ Fixed | PasswordAuthentication disabled on all servers |
| fail2ban | ✅ Installed | Running on all 7 servers |
| Exposed Services | ⚠️ Review | Some exporters publicly exposed |

## SSH Configuration

### Before
- router-01: `PermitRootLogin yes` (vulnerable)
- router-02: `PermitRootLogin yes` (fixed earlier)
- All servers: `PasswordAuthentication` commented (defaults to yes)

### After
- All servers: `PermitRootLogin prohibit-password`
- All servers: `PasswordAuthentication no`

### Verified Servers
| Server | PermitRootLogin | PasswordAuthentication |
|--------|-----------------|------------------------|
| re-node-01 | prohibit-password | no |
| re-node-03 | prohibit-password | no |
| re-node-04 | prohibit-password | no |
| router-01 | prohibit-password | no |
| router-02 | prohibit-password | no |
| re-db | prohibit-password | no |
| re-node-02 | prohibit-password | no |

## fail2ban Status

All servers now have fail2ban running with sshd jail active:

| Server | Status | Jails |
|--------|--------|-------|
| re-node-01 | active | sshd |
| re-node-03 | active | sshd |
| re-node-04 | active | sshd |
| router-01 | active | sshd |
| router-02 | active | sshd |
| re-db | active | sshd |
| re-node-02 | active | sshd |

## Exposed Services Review

### Publicly Exposed (Requires Review)

| Server | Port | Service | Risk | Recommendation |
|--------|------|---------|------|----------------|
| router-02 | 9100 | node_exporter | Medium | Bind to Tailscale IP only |
| router-02 | 9101 | haproxy_exporter | Medium | Bind to Tailscale IP only |
| re-db | 9100 | node_exporter | Medium | Bind to Tailscale IP only |
| re-db | 9090 | asynqmon | High | Add auth or restrict access |
| re-node-02 | 9100 | node_exporter | Medium | Bind to Tailscale IP only |
| router-01 | 8405 | HAProxy stats | Medium | Add auth or restrict |
| router-02 | 8405 | HAProxy stats | Medium | Add auth or restrict |
| router-01 | 26379 | Redis Sentinel | Medium | Bind to Tailscale IP only |
| router-02 | 26379 | Redis Sentinel | Medium | Bind to Tailscale IP only |

### Firewall (UFW) Status

All servers have UFW active. Key observations:

- **DB servers**: PostgreSQL restricted to Tailscale network (100.64.0.0/10)
- **Routers**: HTTP/80, HTTPS/443, HAProxy ports (5000, 5001, 8405) open to public
- **App servers**: HTTP/80, HTTPS/443 open to public, some Dragonfly ports blocked

### Internal Services (Tailscale Bound)

| Server | Port | Service | Binding |
|--------|------|---------|---------|
| router-01 | 9090 | Prometheus | 100.102.220.16 |
| router-01 | 2379/2380 | etcd | 100.102.220.16 |
| router-01 | 5000/5001 | HAProxy PG | 100.102.220.16 |
| router-02 | 5000/5001 | HAProxy PG | 100.116.175.9 |

## Recommendations

### High Priority
1. **Add authentication to HAProxy stats page** (port 8405)
2. **Add authentication to asynqmon** (re-db:9090)
3. **Bind exporters to Tailscale IPs only**

### Medium Priority
1. Add additional fail2ban jails for:
   - HAProxy (if logging enabled)
   - PostgreSQL auth failures
2. Enable PostgreSQL SSL for connections
3. Set up log aggregation (Loki or similar)

### Low Priority
1. Rotate SSH keys (current keys working)
2. Audit PostgreSQL user permissions
3. Enable Redis TLS

## Redis Sentinel Security

Redis Sentinel is now running on both routers:
- **router-01**: 100.102.220.16:26379
- **router-02**: 100.116.175.9:26379

Protected-mode is disabled for Tailscale connectivity. Consider:
- Binding to Tailscale interface only
- Adding firewall rules to restrict 26379 to DB servers

## Alerting

Alertmanager is configured and running at:
- **URL**: http://100.102.220.16:9093
- **Channels**: Slack (#alerts), Email (jonathan@quantyra.co)
- **26 alert rules** active for:
  - Node health (CPU, memory, disk)
  - PostgreSQL (connections, replication, deadlocks)
  - Redis (memory, connections, replication)
  - HAProxy (backend health, connection rates)
  - etcd (health, fsync, DB size)
  - Backups (status checks)