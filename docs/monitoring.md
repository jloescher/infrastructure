# Monitoring

This document covers the complete monitoring stack for the Quantyra infrastructure.

## Overview

The monitoring stack includes:

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notifications
- **Node Exporter**: System metrics
- **Postgres Exporter**: PostgreSQL metrics
- **Redis Exporter**: Redis metrics
- **HAProxy Exporter**: Load balancer metrics
- **Nginx Exporter**: Web server metrics
- **PHP-FPM Exporter**: PHP process manager metrics

## Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://100.102.220.16:9090 | None |
| Grafana | http://100.102.220.16:3000 | admin / admin |
| Alertmanager | http://100.102.220.16:9093 | None |
| HAProxy Stats | http://100.102.220.16:8404 | admin / jFNeZ2bhfrTjTK7aKApD |

## Prometheus Configuration

### Scrape Targets

Located at `/etc/prometheus/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'quantyra'
    environment: 'production'

scrape_configs:
  # Prometheus self-monitoring
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Node Exporter - All servers
  - job_name: 'node_exporter'
    static_configs:
      - targets:
          - '100.126.103.51:9100'  # re-node-01
          - '100.114.117.46:9100'  # re-node-03
          - '100.115.75.119:9100'  # re-node-04
          - '100.102.220.16:9100'  # router-01
          - '100.116.175.9:9100'   # router-02
          - '100.92.26.38:9100'    # re-db
          - '100.89.130.19:9100'   # re-node-02

  # PostgreSQL Exporter
  - job_name: 'postgres_exporter'
    static_configs:
      - targets:
          - '100.126.103.51:9187'
          - '100.114.117.46:9187'
          - '100.115.75.119:9187'

  # Redis Exporter
  - job_name: 'redis_exporter'
    static_configs:
      - targets:
          - '100.126.103.51:9121'
          - '100.114.117.46:9121'

  # HAProxy Exporter
  - job_name: 'haproxy_exporter'
    static_configs:
      - targets:
          - '100.102.220.16:9101'
          - '100.116.175.9:9101'

  # Patroni
  - job_name: 'patroni'
    metrics_path: '/metrics'
    static_configs:
      - targets:
          - '100.126.103.51:8008'
          - '100.114.117.46:8008'
          - '100.115.75.119:8008'

  # etcd
  - job_name: 'etcd'
    static_configs:
      - targets:
          - "100.102.220.16:2379"
          - "100.116.175.9:2379"
          - "100.115.75.119:2379"

  # Nginx Exporter
  - job_name: 'nginx_exporter'
    static_configs:
      - targets:
          - '100.92.26.38:9113'
          - '100.89.130.19:9113'

  # PHP-FPM Exporter
  - job_name: 'php_fpm_exporter'
    static_configs:
      - targets:
          - '100.92.26.38:9253'
          - '100.89.130.19:9253'
```

## Exporter Configuration

### Node Exporter

Installed on all servers. Configured via systemd.

```bash
# Status
systemctl status node_exporter

# Logs
journalctl -u node_exporter -f
```

Key metrics:
- `node_cpu_seconds_total` - CPU usage
- `node_memory_MemAvailable_bytes` - Available memory
- `node_filesystem_avail_bytes` - Disk space
- `node_network_receive_bytes_total` - Network traffic

### Nginx Exporter

Installed on app servers. Monitors nginx stub_status.

```bash
# Status
systemctl status prometheus-nginx-exporter

# Manual test
curl http://localhost:9113/metrics
```

Key metrics:
- `nginx_connections_active` - Active connections
- `nginx_connections_reading` - Connections reading
- `nginx_connections_writing` - Connections writing
- `nginx_requests_total` - Total requests

### PHP-FPM Exporter

Installed on app servers. Monitors PHP-FPM pools.

```bash
# Status
systemctl status php-fpm-exporter

# Manual test
curl http://localhost:9253/metrics
```

Key metrics:
- `phpfpm_processes_total` - Total processes
- `phpfpm_processes_active` - Active processes
- `phpfpm_processes_idle` - Idle processes
- `phpfpm_requests_total` - Total requests

### PostgreSQL Exporter

Installed on database servers.

Key metrics:
- `pg_stat_database_numbackends` - Active connections
- `pg_stat_database_tup_fetched` - Rows fetched
- `pg_stat_database_tup_inserted` - Rows inserted
- `pg_replication_lag_seconds` - Replication lag

### Redis Exporter

Installed on Redis servers.

Key metrics:
- `redis_connected_clients` - Connected clients
- `redis_memory_used_bytes` - Memory usage
- `redis_commands_processed_total` - Commands processed
- `redis_connected_slaves` - Connected slaves

## Alerting Rules

Located at `/etc/prometheus/rules/`:

### Infrastructure Alerts

```yaml
groups:
  - name: infrastructure
    rules:
      - alert: InstanceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Instance {{ $labels.instance }} down"
          description: "{{ $labels.instance }} has been down for more than 1 minute."

      - alert: DiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 20
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Low disk space on {{ $labels.instance }}"
          description: "Disk usage is above 80% on {{ $labels.instance }}."

      - alert: DiskSpaceCritical
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 10
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Critical disk space on {{ $labels.instance }}"
          description: "Disk usage is above 90% on {{ $labels.instance }}."

      - alert: MemoryUsageHigh
        expr: (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.instance }}"
          description: "Memory usage is above 90%."
```

### PostgreSQL Alerts

```yaml
  - name: postgresql
    rules:
      - alert: PostgreSQLReplicationLag
        expr: pg_replication_lag_seconds > 10
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL replication lag high"
          description: "Replication lag is {{ $value }} seconds."

      - alert: PostgreSQLDown
        expr: pg_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL instance down"
          description: "PostgreSQL on {{ $labels.instance }} is not responding."
```

### Redis Alerts

```yaml
  - name: redis
    rules:
      - alert: RedisDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Redis instance down"
          description: "Redis on {{ $labels.instance }} is not responding."

      - alert: RedisMemoryHigh
        expr: (redis_memory_used_bytes / redis_memory_max_bytes) * 100 > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory usage high"
          description: "Redis memory usage is above 90%."
```

## Alertmanager Configuration

Located at `/etc/alertmanager/alertmanager.yml`:

```yaml
global:
  resolve_timeout: 5m
  smtp_smarthost: 'smtp.example.com:587'
  smtp_from: 'alerts@xotec.io'
  smtp_auth_username: 'alerts@xotec.io'
  smtp_auth_password: 'password'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'email-notifications'
  routes:
    - match:
        severity: critical
      receiver: 'email-notifications'
      continue: true

receivers:
  - name: 'email-notifications'
    email_configs:
      - to: 'jonathan@xotec.io'
        send_resolved: true
```

## Grafana Dashboards

### Recommended Dashboards

Import by ID from grafana.com:

| Dashboard | ID | Description |
|-----------|-----|-------------|
| Node Exporter Full | 1860 | System metrics |
| PostgreSQL | 9628 | Database metrics |
| Redis | 11835 | Redis metrics |
| HAProxy | 367 | Load balancer metrics |
| Nginx | 12708 | Web server metrics |
| PHP-FPM | 9912 | PHP metrics |

### Custom Dashboards

Create dashboards for:
- Application-specific metrics
- Business KPIs
- Custom alerts

## Grafana Datasources

Pre-configured datasources:

```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://localhost:9090
    isDefault: true
```

## Maintenance

### Adding New Exporters

1. Install exporter on target server
2. Add scrape target to Prometheus config
3. Restart Prometheus

```bash
# Edit config
nano /etc/prometheus/prometheus.yml

# Validate
promtool check config /etc/prometheus/prometheus.yml

# Restart
systemctl restart prometheus
```

### Backup Prometheus Data

```bash
# Backup data directory
tar -czvf prometheus-backup-$(date +%Y%m%d).tar.gz /var/lib/prometheus/

# Backup config
tar -czvf prometheus-config-$(date +%Y%m%d).tar.gz /etc/prometheus/
```

### Retention Configuration

Prometheus is configured with:
- **Time retention**: 15 days
- **Size retention**: 20GB

```bash
# Check current retention
du -sh /var/lib/prometheus/

# Modify in systemd service
# /etc/systemd/system/prometheus.service
--storage.tsdb.retention.time=15d
--storage.tsdb.retention.size=20GB
```

## Troubleshooting

### Prometheus Not Scraping

```bash
# Check target status
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check logs
journalctl -u prometheus -f

# Test exporter directly
curl http://target:9100/metrics
```

### High Memory Usage

```bash
# Check Prometheus memory
ps aux | grep prometheus

# Reduce retention
--storage.tsdb.retention.time=7d
```

### Missing Metrics

1. Verify exporter is running
2. Check network connectivity
3. Verify Prometheus config syntax
4. Check exporter logs

```bash
# Test connectivity
curl -v http://target:port/metrics

# Check exporter logs
journalctl -u exporter-name -f
```