---
name: ansible
description: Configures Ansible playbooks, roles, and infrastructure automation for Quantyra's multi-region VPS infrastructure. Use when writing playbooks, modifying inventory, provisioning servers, deploying applications, or syncing configurations across the Patroni/HAProxy/Redis cluster.
---

# Ansible Skill

Ansible 2.12+ manages the Quantyra infrastructure—provisioning servers, deploying applications, and maintaining the Patroni PostgreSQL cluster, HAProxy routers, and monitoring stack. All server communication uses Tailscale IPs (100.64.0.0/10).

## Quick Start

### Test Connectivity

```bash
ansible all -m ping
```

### Provision All Servers

```bash
ansible-playbook ansible/playbooks/provision.yml
```

### Deploy to Specific Group

```bash
ansible-playbook ansible/playbooks/deploy.yml --limit app_servers
```

## Key Concepts

| Concept | Purpose | Example |
|---------|---------|---------|
| Inventory | Server definitions | `ansible/inventory/hosts.yml` |
| Group Vars | Shared configuration | `ansible/inventory/group_vars/db_servers.yml` |
| Playbooks | Orchestration scripts | `ansible/playbooks/provision.yml` |
| Roles | Reusable task bundles | `ansible/roles/postgresql/` |

## Common Patterns

### Target Specific Environment

**When:** Testing changes before full deployment.

```bash
# Dry run first
ansible-playbook ansible/playbooks/update.yml --check --limit router-01

# Then execute
ansible-playbook ansible/playbooks/update.yml --limit router-01
```

### Install Required Collections

**When:** Fresh checkout or new dependencies.

```bash
ansible-galaxy collection install community.general
```

## See Also

- [patterns](references/patterns.md) - Ansible patterns and anti-patterns
- [workflows](references/workflows.md) - Common operational workflows

## Related Skills

- **python** - For Ansible modules and custom plugins
- **docker** - For the monitoring stack deployment
- **postgresql** - Patroni cluster managed via Ansible
- **redis** - Sentinel failover configuration
- **haproxy** - Load balancer configuration
- **prometheus** - Monitoring deployment
- **grafana** - Dashboard provisioning
- **nginx** - Web server configuration