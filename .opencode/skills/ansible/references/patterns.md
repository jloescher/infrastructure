# Ansible Patterns Reference

## Contents
- Inventory Structure
- Variable Precedence
- Task Organization
- Common Anti-Patterns

## Inventory Structure

This project uses YAML inventory with Tailscale IPs:

```yaml
# ansible/inventory/hosts.yml
all:
  children:
    db_servers:
      hosts:
        re-node-01:
          ansible_host: 100.126.103.51
          ansible_user: root
          ansible_ssh_private_key_file: ~/.ssh/id_vps
    app_servers:
      hosts:
        re-db:
          ansible_host: 100.92.26.38
    router_servers:
      hosts:
        router-01:
          ansible_host: 100.102.220.16
        router-02:
          ansible_host: 100.116.175.9
```

Group variables in `ansible/inventory/group_vars/`:

```yaml
# group_vars/db_servers.yml
postgres_max_connections: 200
postgres_shared_buffers: "8GB"
patroni_etcd_hosts: "100.115.75.119:2379"
```

### WARNING: Hardcoding Variables in Playbooks

**The Problem:**

```yaml
# BAD - Variables embedded in playbook
- name: Configure PostgreSQL
  postgresql_set:
    name: max_connections
    value: 200  # Magic number, no context
```

**Why This Breaks:**
1. No reuse across playbooks—copy-paste errors proliferate
2. Environment differences (staging vs production) require playbook edits
3. Secrets visible in version control if not careful

**The Fix:**

```yaml
# GOOD - Variables in group_vars/
- name: Configure PostgreSQL
  postgresql_set:
    name: max_connections
    value: "{{ postgres_max_connections }}"
```

## Variable Precedence

Use this hierarchy (highest wins):

1. Extra vars (`-e` CLI)
2. Host variables
3. Group variables (child groups override parent)
4. Role defaults

```bash
# Override for emergency fix
ansible-playbook deploy.yml -e "app_version=hotfix-123"
```

### WARNING: Overriding Role Defaults Incorrectly

**The Problem:**

```yaml
# BAD - Duplicate variable in every host entry
hosts:
  re-node-01:
    ansible_host: 100.126.103.51
    postgres_port: 5432  # Repeated per host
```

**Why This Breaks:**
1. Updates require editing every host entry
2. Inconsistency across hosts causes cluster failures
3. Patroni etcd coordination fails if ports mismatch

**The Fix:**

```yaml
# GOOD - Common variables in group_vars/all.yml
# group_vars/all.yml
postgres_port: 5432
patroni_port: 8008
```

## Task Organization

Structure playbooks with clear sections:

```yaml
# ansible/playbooks/provision.yml
---
- name: Provision Infrastructure Servers
  hosts: all
  become: yes
  
  pre_tasks:
    - name: Update apt cache
      apt:
        update_cache: yes
        cache_valid_time: 3600
  
  roles:
    - common
    - docker
    - monitoring_agent
  
  tasks:
    - name: Configure Tailscale
      include_role:
        name: tailscale
        
    - name: Verify connectivity
      wait_for:
        host: "{{ item }}"
        port: 22
        timeout: 30
      loop: "{{ groups['db_servers'] }}"
```

### WARNING: Monolithic Playbooks

**The Problem:**

```yaml
# BAD - Single playbook doing everything
- name: Do Everything
  hosts: all
  tasks:
    - name: Install PostgreSQL
      # 50 tasks for PostgreSQL
    - name: Install HAProxy
      # 50 tasks for HAProxy
    - name: Install Redis
      # 50 tasks for Redis
```

**Why This Breaks:**
1. 10+ minute runs, no way to retry just failed components
2. Changes to one role require testing the entire playbook
3. Impossible to run just database updates without touching routers

**The Fix:**

Split into focused playbooks:
- `provision.yml` - Initial server setup
- `deploy.yml` - Application deployment
- `update.yml` - System package updates
- `monitoring.yml` - Monitoring stack only

## Handler Patterns

Handlers run only when notified, at the end:

```yaml
- name: Update HAProxy config
  template:
    src: haproxy.cfg.j2
    dest: /etc/haproxy/haproxy.cfg
  notify: reload haproxy

handlers:
  - name: reload haproxy
    service:
      name: haproxy
      state: reloaded
```

### WARNING: Not Restarting Services After Config Changes

**The Problem:**

```yaml
# BAD - Config updated but service not restarted
- name: Update Patroni config
  template:
    src: patroni.yml.j2
    dest: /etc/patroni/patroni.yml
  # Missing notify or service restart
```

**Why This Breaks:**
1. Config drift—file changed but runtime unchanged
2. Failures during failover because new config never loaded
3. Silent misconfiguration that bites during incidents

**The Fix:**

Always notify handlers for config changes:

```yaml
- name: Update Patroni config
  template:
    src: patroni.yml.j2
    dest: /etc/patroni/patroni.yml
  notify: restart patroni

handlers:
  - name: restart patroni
    service:
      name: patroni
      state: restarted