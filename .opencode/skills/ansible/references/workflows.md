# Ansible Workflows Reference

## Contents
- Initial Server Provisioning
- Application Deployment
- Emergency Procedures
- Testing and Validation

## Initial Server Provisioning

Complete workflow for adding a new server to the infrastructure.

Copy this checklist and track progress:
- [ ] Step 1: Add server to inventory
- [ ] Step 2: Test connectivity with ping
- [ ] Step 3: Run provision playbook with limit
- [ ] Step 4: Verify services are healthy
- [ ] Step 5: Join to Patroni/etcd/Redis as appropriate

```bash
# Step 1: Edit ansible/inventory/hosts.yml
# Add host under appropriate group with Tailscale IP

# Step 2: Test connectivity
ansible new-server -m ping

# Step 3: Provision with limit (NEVER run full provision on single server)
ansible-playbook ansible/playbooks/provision.yml --limit new-server

# Step 4: Verify services
ssh root@new-server 'systemctl status patroni'
ssh root@new-server 'patronictl list'
```

### WARNING: Running Full Provision on Production

**The Problem:**
Running `ansible-playbook provision.yml` without `--limit` on a working cluster can:
1. Restart all PostgreSQL nodes simultaneously
2. Trigger Patroni leader elections across the cluster
3. Cause brief outages during HAProxy config reloads

**The Fix:**
Always use `--limit` when targeting specific servers:

```bash
# GOOD - Explicit limit
ansible-playbook provision.yml --limit re-node-04

# GOOD - Limit to group
ansible-playbook provision.yml --limit db_servers
```

## Application Deployment

Deploy Laravel/Node.js applications to app servers.

```bash
# Deploy to staging first
ansible-playbook ansible/playbooks/deploy.yml \
  --limit re-node-02 \
  -e "app_name=myapp" \
  -e "environment=staging"

# Verify staging health
curl -s https://staging.myapp.com/health

# Deploy to production
ansible-playbook ansible/playbooks/deploy.yml \
  --limit app_servers \
  -e "app_name=myapp" \
  -e "environment=production"
```

### WARNING: Deploying Without Health Checks

**The Problem:**

```yaml
# BAD - No verification deployment succeeded
- name: Deploy app
  git:
    repo: https://github.com/org/app.git
    dest: /opt/apps/myapp
- name: Restart service
  service:
    name: myapp
    state: restarted
  # Done—no verification
```

**Why This Breaks:**
1. Failed deployments go unnoticed until users report issues
2. Bad configs restart into broken state
3. Database migrations may fail but deployment reports success

**The Fix:**
Add health verification tasks:

```yaml
- name: Deploy app
  git:
    repo: https://github.com/org/app.git
    dest: /opt/apps/myapp
    version: "{{ app_version | default('main') }}"

- name: Install dependencies
  composer:
    command: install
    working_dir: /opt/apps/myapp

- name: Run migrations
  command: php artisan migrate --force
  args:
    chdir: /opt/apps/myapp

- name: Restart PHP-FPM
  service:
    name: php8.2-fpm
    state: reloaded

- name: Verify health endpoint
  uri:
    url: "https://{{ domain }}/health"
    status_code: 200
  retries: 5
  delay: 3
```

## Emergency Procedures

### Patroni Failover

When the PostgreSQL leader needs manual intervention:

```bash
# Check current status
ansible router-01 -m shell -a 'patronictl list'

# Initiate switchover (run from any node)
ansible re-node-01 -m shell -a 'patronictl switchover'
# Follow prompts to select new leader

# Verify new leader
ansible router-01 -m shell -a 'patronictl list'
```

### HAProxy Config Emergency Rebuild

If HAProxy configs are corrupted:

```bash
# Rebuild from registry on both routers
ansible router_servers -m shell \
  -a '/opt/scripts/provision-domain.sh --rebuild'

# Validate config before reloading
ansible router_servers -m shell \
  -a 'haproxy -c -f /etc/haproxy/haproxy.cfg'

# Reload if valid
ansible router_servers -m service \
  -a 'name=haproxy state=reloaded'
```

## Testing and Validation

Always validate before applying changes:

```bash
# Syntax check
ansible-playbook --syntax-check ansible/playbooks/provision.yml

# Dry run (check mode)
ansible-playbook --check ansible/playbooks/update.yml --limit re-node-02

# Diff mode (show what would change)
ansible-playbook --diff --check ansible/playbooks/provision.yml --limit router-01
```

### Feedback Loop for Config Changes

1. Make changes to playbook/role
2. Validate: `ansible-playbook --syntax-check playbook.yml`
3. Dry run: `ansible-playbook --check --limit test-server playbook.yml`
4. If dry run fails, fix issues and repeat step 3
5. Only proceed when dry run passes
6. Execute: `ansible-playbook --limit test-server playbook.yml`
7. Verify: Check service status and logs
8. Roll out to remaining servers: `ansible-playbook playbook.yml`

### WARNING: Skipping Syntax Checks

**The Problem:**
Running playbooks without `--syntax-check` first can:
1. Fail mid-playbook leaving infrastructure in partial state
2. Waste time on SSH connections before failing on YAML error
3. Cause unnecessary service restarts if the playbook has logic errors

**The Fix:**
Make syntax check a mandatory pre-step:

```bash
# GOOD - Always syntax check first
ansible-playbook --syntax-check playbook.yml && \
ansible-playbook --check playbook.yml --limit test-server && \
ansible-playbook playbook.yml --limit test-server