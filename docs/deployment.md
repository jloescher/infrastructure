# Deployment Guide

## Prerequisites

- Ansible 2.12+ installed
- SSH access to all servers
- Tailscale connected
- Vault or secrets manager configured

## Initial Setup

### 1. Install Ansible and Dependencies

```bash
pip install ansible
ansible-galaxy collection install community.general
```

### 2. Configure SSH

Add to `~/.ssh/config`:

```
Host re-node-01
    HostName 100.126.103.51
    User root

Host re-node-03
    HostName 100.114.117.46
    User root

Host re-node-04
    HostName 100.115.75.119
    User root

Host router-01
    HostName 100.102.220.16
    User root

Host router-02
    HostName 100.116.175.9
    User root

Host re-db
    HostName 100.92.26.38
    User root

Host re-node-02
    HostName 100.89.130.19
    User root
```

### 3. Test Connectivity

```bash
ansible all -m ping
```

### 4. Collect Current Configuration

Run the data collection script on each server:

```bash
# Copy script to servers
for host in re-node-01 re-node-03 re-node-04 router-01 router-02 re-db re-node-02; do
  scp scripts/collect_quantyra_infra_report.sh $host:/tmp/
done

# Run on each server
for host in re-node-01 re-node-03 re-node-04 router-01 router-02 re-db re-node-02; do
  ssh $host 'bash /tmp/collect_quantyra_infra_report.sh'
done

# Copy reports back
mkdir -p reports
for host in re-node-01 re-node-03 re-node-04 router-01 router-02 re-db re-node-02; do
  scp $host:/tmp/*_infra_report_*.md reports/
done
```

## Provisioning New Servers

### Full Provisioning

```bash
# Provision all servers
ansible-playbook playbooks/provision.yml

# Provision specific server group
ansible-playbook playbooks/provision.yml --limit db_servers
ansible-playbook playbooks/provision.yml --limit routers
ansible-playbook playbooks/provision.yml --limit app_servers

# Provision single server
ansible-playbook playbooks/provision.yml --limit re-node-01
```

### Provisioning Steps

The provisioning playbook will:

1. Update system packages
2. Install common utilities (curl, wget, htop, etc.)
3. Configure Tailscale
4. Set up firewall rules (UFW)
5. Harden SSH configuration
6. Install fail2ban
7. Configure timezone and NTP
8. Install Node Exporter for monitoring

## Deploying Applications

### Deploy via Ansible

```bash
# Deploy to all app servers
ansible-playbook playbooks/deploy.yml

# Deploy specific application
ansible-playbook playbooks/deploy.yml --tags web-app
ansible-playbook playbooks/deploy.yml --tags api

# Deploy to specific server
ansible-playbook playbooks/deploy.yml --limit re-db
```

### Deploy via CI/CD

1. Push to main/master branch
2. GitHub Actions will:
   - Build Docker image
   - Push to GitHub Container Registry
   - Deploy to app servers

### Manual Deployment

```bash
# On app server
cd /opt/apps/web-app
docker-compose pull
docker-compose up -d --remove-orphans

# Health check
curl http://localhost:3000/health
```

## Updating Infrastructure

### Update System Packages

```bash
# Update all servers
ansible-playbook playbooks/update.yml

# Update specific server group
ansible-playbook playbooks/update.yml --limit db_servers
```

### Update PostgreSQL

```bash
# Rolling update of PostgreSQL nodes
ansible-playbook playbooks/update.yml --limit postgres_cluster --tags postgresql
```

### Update Redis

```bash
# Update Redis (update replica first, then master)
ansible-playbook playbooks/update.yml --limit re-node-03 --tags redis
ansible-playbook playbooks/update.yml --limit re-node-01 --tags redis
```

### Update HAProxy

```bash
# Update HAProxy on both routers
ansible-playbook playbooks/update.yml --limit haproxy --tags haproxy
```

## Managing Backups

### Configure Backup Scripts

1. Copy backup scripts to servers:
   ```bash
   ansible-playbook playbooks/backup.yml --tags setup
   ```

2. Configure S3 credentials:
   ```bash
   # Create /etc/backup/s3.env
   AWS_ACCESS_KEY_ID=your-key
   AWS_SECRET_ACCESS_KEY=your-secret
   S3_BUCKET=your-backup-bucket
   ```

3. Set up cron jobs:
   ```bash
   # Add to /etc/cron.d/backups
   0 2 * * * root /usr/local/bin/postgres_backup.sh full >> /var/log/backup.log 2>&1
   0 3 * * * root /usr/local/bin/redis_backup.sh >> /var/log/backup.log 2>&1
   0 4 * * * root /usr/local/bin/sync_to_s3.sh /backup >> /var/log/backup.log 2>&1
   ```

### Manual Backup

```bash
# PostgreSQL backup
ansible all -m shell -a "/usr/local/bin/postgres_backup.sh full" --limit db_servers

# Redis backup
ansible all -m shell -a "/usr/local/bin/redis_backup.sh" --limit redis_cluster

# Sync to S3
ansible all -m shell -a "/usr/local/bin/sync_to_s3.sh /backup" --limit db_servers
```

## Monitoring Setup

### Deploy Monitoring Stack

```bash
# Deploy Prometheus, Grafana, Alertmanager
ansible-playbook playbooks/monitoring.yml

# Deploy only Prometheus
ansible-playbook playbooks/monitoring.yml --tags prometheus

# Deploy only Grafana
ansible-playbook playbooks/monitoring.yml --tags grafana
```

### Configure Alerts

1. Edit alert rules:
   ```bash
   vim monitoring/prometheus/rules/alerts.yml
   ```

2. Reload Prometheus:
   ```bash
   curl -X POST http://100.102.220.16:9090/-/reload
   ```

### Import Grafana Dashboards

1. Access Grafana: https://grafana.quantyra.com
2. Go to Dashboards → Import
3. Upload JSON files from `monitoring/grafana/dashboards/`

## Security

### Update Firewall Rules

```bash
# Apply UFW rules
ansible-playbook playbooks/security.yml --tags firewall

# Check firewall status
ansible all -m shell -a "ufw status verbose"
```

### Rotate SSH Keys

```bash
# Generate new SSH key
ssh-keygen -t ed25519 -C "deploy@$(date +%Y%m%d)"

# Distribute to servers
ansible all -m authorized_key -a "user=root key='$(cat ~/.ssh/id_ed25519.pub)'"

# Test connection
ansible all -m ping
```

### Update Fail2ban

```bash
# Update fail2ban configuration
ansible-playbook playbooks/security.yml --tags fail2ban

# Check fail2ban status
ansible all -m shell -a "fail2ban-client status"
```

## Troubleshooting

### Ansible Issues

```bash
# Verbose output
ansible-playbook playbooks/provision.yml -vvv

# Check syntax
ansible-playbook playbooks/provision.yml --syntax-check

# Dry run
ansible-playbook playbooks/provision.yml --check
```

### Connectivity Issues

```bash
# Test SSH connection
ansible all -m ping

# Check Tailscale
ansible all -m shell -a "tailscale status"

# Check firewall
ansible all -m shell -a "ufw status"
```

### Service Issues

```bash
# Check service status
ansible all -m shell -a "systemctl status patroni" --limit db_servers

# Restart service
ansible all -m shell -a "systemctl restart patroni" --limit db_servers

# Check logs
ansible all -m shell -a "journalctl -u patroni -n 50" --limit db_servers
```

## Maintenance Windows

### Planned Maintenance

1. Notify stakeholders 24 hours in advance
2. Disable alerts during maintenance:
   ```bash
   curl -X POST http://100.102.220.16:9093/api/v1/silences -d '{"matchers":[{"name":"alertname","value":".*","isRegex":true}],"startsAt":"2024-01-15T10:00:00Z","endsAt":"2024-01-15T12:00:00Z","createdBy":"admin","comment":"Planned maintenance"}'
   ```

3. Perform maintenance tasks
4. Re-enable alerts
5. Verify all services are healthy

### Emergency Maintenance

1. Notify stakeholders immediately
2. Follow runbook procedures
3. Document all actions taken
4. Conduct post-mortem after resolution

## Rollback Procedures

### Application Rollback

```bash
# SSH to app server
ssh re-db

# Find previous image
docker images | grep web-app

# Rollback
docker tag web-app:previous web-app:latest
docker-compose -f /opt/apps/web-app/docker-compose.yml up -d
```

### Database Rollback

See disaster recovery guide for PostgreSQL/Redis rollback procedures.