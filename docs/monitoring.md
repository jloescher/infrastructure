# Monitoring

This document covers the complete monitoring stack for the Quantyra infrastructure.

## Overview

The monitoring stack includes:

- **Prometheus**: Metrics collection and alerting
- **Grafana**: Visualization and dashboards
- **Alertmanager**: Alert routing and notifications
- **Loki**: Centralized log aggregation
- **Promtail**: Log collection agent
- **Node Exporter**: System metrics
- **Postgres Exporter**: PostgreSQL metrics
- **Redis Exporter**: Redis metrics
- **HAProxy Exporter**: Load balancer metrics
- **Nginx Exporter**: Web server metrics
- **PHP-FPM Exporter**: PHP process manager metrics

## Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://100.102.220.16:9090 | None (Tailscale only) |
| Grafana | http://100.102.220.16:3000 | admin / nyb4faf3hye6zwn_UQT |
| Alertmanager | http://100.102.220.16:9093 | None (Tailscale only) |
| Loki | http://100.102.220.16:3100 | None (Tailscale only) |
| HAProxy Stats | http://100.102.220.16:8404 | admin / jFNeZ2bhfrTjTK7aKApD |

## Prometheus Configuration

### Scrape Targets

Located at `/etc/prometheus/prometheus.yml`:

**Note:** All scrape targets include `node` and `role` labels for easier identification.

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'quantyra'
    environment: 'production'

scrape_configs:
  # Node Exporter - All servers (with node labels)
  - job_name: 'node_exporter'
    static_configs:
      - targets: ['100.126.103.51:9100']
        labels: {node: 're-node-01', role: 'database'}
      - targets: ['100.114.117.46:9100']
        labels: {node: 're-node-03', role: 'database'}
      - targets: ['100.115.75.119:9100']
        labels: {node: 're-node-04', role: 'database'}
      - targets: ['100.102.220.16:9100']
        labels: {node: 'router-01', role: 'router'}
      - targets: ['100.116.175.9:9100']
        labels: {node: 'router-02', role: 'router'}
      - targets: ['100.92.26.38:9100']
        labels: {node: 're-db', role: 'app'}
      - targets: ['100.89.130.19:9100']
        labels: {node: 're-node-02', role: 'app'}

  # PostgreSQL Exporter (with node labels)
  - job_name: 'postgres_exporter'
    static_configs:
      - targets: ['100.126.103.51:9187']
        labels: {node: 're-node-01'}
      - targets: ['100.114.117.46:9187']
        labels: {node: 're-node-03'}
      - targets: ['100.115.75.119:9187']
        labels: {node: 're-node-04'}

  # Redis Exporter (with node labels)
  - job_name: 'redis_exporter'
    static_configs:
      - targets: ['100.126.103.51:9121']
        labels: {node: 're-node-01'}
      - targets: ['100.114.117.46:9121']
        labels: {node: 're-node-03'}

  # HAProxy Exporter (with node labels)
  - job_name: 'haproxy_exporter'
    static_configs:
      - targets: ['100.102.220.16:9101']
        labels: {node: 'router-01'}
      - targets: ['100.116.175.9:9101']
        labels: {node: 'router-02'}

  # Patroni (with node labels)
  - job_name: 'patroni'
    metrics_path: '/metrics'
    static_configs:
      - targets: ['100.126.103.51:8008']
        labels: {node: 're-node-01'}
      - targets: ['100.114.117.46:8008']
        labels: {node: 're-node-03'}
      - targets: ['100.115.75.119:8008']
        labels: {node: 're-node-04'}

  # etcd (with node labels)
  - job_name: 'etcd'
    static_configs:
      - targets: ['100.102.220.16:2379']
        labels: {node: 'router-01'}
      - targets: ['100.116.175.9:2379']
        labels: {node: 'router-02'}
      - targets: ['100.115.75.119:2379']
        labels: {node: 're-node-04'}

  # Nginx Exporter (with node labels)
  - job_name: 'nginx_exporter'
    static_configs:
      - targets: ['100.92.26.38:9113']
        labels: {node: 're-db'}
      - targets: ['100.89.130.19:9113']
        labels: {node: 're-node-02'}

  # PHP-FPM Exporter (with node labels)
  - job_name: 'php_fpm_exporter'
    static_configs:
      - targets: ['100.92.26.38:9253']
        labels: {node: 're-db'}
      - targets: ['100.89.130.19:9253']
        labels: {node: 're-node-02'}
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

## Centralized Logging (Loki)

### Architecture

```
All Servers → Promtail → Loki (router-01) → Grafana
```

Loki is a log aggregation system designed to store and query logs from all servers.

### Components

| Component | Location | Port | Purpose |
|-----------|----------|------|---------|
| Loki | router-01 | 3100 | Log storage and query |
| Promtail | All servers | 9080 | Log collection agent |

### Configuration

**Loki config:** `/etc/loki/loki-config.yaml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /var/lib/loki
  storage:
    filesystem:
      chunks_directory: /var/lib/loki/chunks
      rules_directory: /var/lib/loki/rules
  replication_factor: 1

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 744h  # 31 days
```

**Promtail config:** `/etc/promtail/promtail-config.yaml`

Each server has a customized Promtail config collecting relevant logs:

| Server | Logs Collected |
|--------|----------------|
| router-01/02 | syslog, auth, haproxy |
| re-db, re-node-02 | syslog, auth, nginx, php-fpm |
| re-node-01/03/04 | syslog, auth, postgresql, patroni, redis |

### Querying Logs in Grafana

1. Navigate to **Explore** in Grafana
2. Select **Loki** datasource
3. Use LogQL queries:

```logql
# All syslog logs
{job="syslog"}

# Logs from specific host
{host="re-db"}

# Nginx logs
{job="nginx"}

# Search for errors
{job="syslog"} |= "error"

# Filter by pattern
{job="auth"} |= "Failed"
```

### Retention

- **Log retention**: 31 days (744h)
- **Storage**: `/var/lib/loki/` on router-01

## Grafana Dashboards

### Custom Dashboards

Pre-configured dashboards for the infrastructure:

| Dashboard | UID | Description |
|-----------|-----|-------------|
| Node Exporter | node-exporter-quantyra | System metrics (CPU, Memory, Disk, Network) |
| PostgreSQL & HAProxy | postgres-haproxy-quantyra | Database cluster status and connections |
| Redis | redis-quantyra | Redis memory, connections, operations |
| Nginx | nginx-quantyra | Web server connections and requests |
| PHP-FPM | phpfpm-quantyra | PHP process pool metrics |
| Loki Logs | loki-logs-quantyra | Centralized log viewing and analysis |

### Grafana Datasources

Pre-configured datasources:

```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://localhost:9090
    isDefault: true
  - name: Loki
    type: loki
    url: http://localhost:3100
```

### Using Labels

All dashboards use `node` labels instead of IP addresses for cleaner display:
- Query example: `sum by (node) (node_cpu_seconds_total)`

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