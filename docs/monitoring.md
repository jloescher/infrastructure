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
- **HAProxy Exporter**: Load balancer metrics
- **Nginx Exporter**: Web server metrics

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

### PostgreSQL Exporter

Installed on database servers.

Key metrics:
- `pg_stat_database_numbackends` - Active connections
- `pg_stat_database_tup_fetched` - Rows fetched
- `pg_stat_database_tup_inserted` - Rows inserted
- `pg_replication_lag_seconds` - Replication lag

### Traefik Exporter

**NEW (2026-04-03)**: Traefik metrics are now collected for monitoring the Coolify deployment platform.

Traefik exposes metrics via its internal metrics endpoint. Configuration is handled automatically by Coolify.

**Location**: App servers (re-db, re-node-02)
**Port**: 8080 (internal API endpoint)

**Key Metrics**:
- `traefik_config_reloads_total` - Number of configuration reloads
- `traefik_entrypoint_requests_total` - Total requests per entrypoint
- `traefik_entrypoint_request_duration_seconds` - Request duration histograms
- `traefik_router_requests_total` - Requests per router
- `traefik_service_requests_total` - Requests per service
- `traefik_tls_certs_expiry_seconds` - Certificate expiration times

**Prometheus Scrape Configuration**:

```yaml
# Traefik metrics (via internal API)
- job_name: 'traefik'
  metrics_path: /metrics
  static_configs:
    - targets: ['100.92.26.38:8080']
      labels: {node: 're-db', role: 'app'}
    - targets: ['100.89.130.19:8080']
      labels: {node: 're-node-02', role: 'app'}
```

**Verify Metrics**:
```bash
# Test Traefik metrics endpoint
curl http://100.92.26.38:8080/metrics | grep traefik_config_reloads_total

# Check in Prometheus UI
# http://100.102.220.16:9090/targets
# Look for "traefik" job with status "UP"
```

### Docker Swarm Metrics

**NEW (2026-04-03)**: Docker daemon metrics are collected for monitoring container orchestration and Swarm health.

**Location**: App servers (re-db, re-node-02)
**Port**: 9323

**Enable Docker Metrics**:

Docker metrics are enabled via daemon configuration:

```json
# /etc/docker/daemon.json
{
  "metrics-addr": "0.0.0.0:9323",
  "experimental": true
}
```

Restart Docker after configuration changes:
```bash
systemctl restart docker
```

**Key Metrics**:
- `engine_daemon_container_actions_seconds` - Container action durations
- `engine_daemon_container_states_containers` - Containers by state (running, paused, stopped)
- `swarm_manager_node_count` - Number of nodes in Swarm
- `swarm_manager_node_health` - Node health status
- `swarm_manager_services_count` - Number of services
- `swarm_manager_tasks_count` - Number of tasks
- `engine_daemon_network_actions_seconds` - Network operation durations

**Prometheus Scrape Configuration**:

```yaml
# Docker daemon metrics
- job_name: 'docker'
  static_configs:
    - targets: ['100.92.26.38:9323']
      labels: {node: 're-db', role: 'app'}
    - targets: ['100.89.130.19:9323']
      labels: {node: 're-node-02', role: 'app'}
```

**Verify Metrics**:
```bash
# Test Docker metrics endpoint
curl http://100.92.26.38:9323/metrics | grep engine_daemon_container_states_containers

# Check in Prometheus UI
# http://100.102.220.16:9090/targets
# Look for "docker" job with status "UP"
```

**Useful Queries**:

```promql
# Total containers running across both app servers
sum(engine_daemon_container_states_containers{state="running"})

# Container actions rate (create, start, stop, destroy)
rate(engine_daemon_container_actions_seconds_count[5m])

# Swarm node health
swarm_manager_node_health

# Number of services in Swarm
swarm_manager_services_count

# Average container action duration
rate(engine_daemon_container_actions_seconds_sum[5m]) / rate(engine_daemon_container_actions_seconds_count[5m])
```

## Grafana Dashboards for Traefik and Docker

### Traefik Dashboard

**NEW (2026-04-03)**: Pre-configured dashboard for Traefik metrics.

**Dashboard Name**: Quantyra - Traefik
**UID**: traefik-quantyra

**Panels Include**:
- Configuration reloads count
- Request rate per entrypoint (web, websecure)
- Request rate per service
- Response time percentiles (p50, p95, p99)
- Active TLS certificates
- HTTP status codes distribution
- Open connections

**Access**: http://100.102.220.16:3000 → Dashboards → Quantyra - Traefik

### Docker Swarm Dashboard

**NEW (2026-04-03)**: Pre-configured dashboard for Docker Swarm metrics.

**Dashboard Name**: Quantyra - Docker Swarm
**UID**: docker-swarm-quantyra

**Panels Include**:
- Cluster overview (node count, service count, task count)
- Node health status
- Container states (running, paused, stopped) by node
- Container action rates (create, start, stop, destroy)
- Network actions
- Average container action duration
- Swarm manager metrics

**Access**: http://100.102.220.16:3000 → Dashboards → Quantyra - Docker Swarm

### Dashboard JSON Files

Dashboard JSON files are provisioned automatically from:

```
/var/lib/grafana/dashboards/
├── traefik_dashboard.json
├── docker_swarm_dashboard.json
├── node_exporter_dashboard.json
└── postgres_haproxy_dashboard.json
```

**Reload Dashboards**:
```bash
# Restart Grafana to reload dashboards
systemctl restart grafana-server

# Or via API (if configured)
curl -X POST http://admin:password@localhost:3000/api/admin/reload
```

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

### Traefik Alerts

**NEW (2026-04-03)**: Alerts for Coolify/Traefik load balancer.

```yaml
  - name: traefik
    rules:
      - alert: TraefikDown
        expr: up{job="traefik"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Traefik instance down on {{ $labels.node }}"
          description: "Traefik is not responding on {{ $labels.node }}. Applications may be inaccessible."

      - alert: TraefikConfigReloadFailure
        expr: increase(traefik_config_reloads_total{success="false"}[5m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Traefik configuration reload failed on {{ $labels.node }}"
          description: "Traefik failed to reload configuration. Check Traefik logs for errors."

      - alert: TraefikHighErrorRate
        expr: sum(rate(traefik_entrypoint_requests_total{code=~"5.."}[5m])) / sum(rate(traefik_entrypoint_requests_total[5m])) * 100 > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate in Traefik"
          description: "More than 10% of requests are returning 5xx errors."

      - alert: TraefikCertificateExpiringSoon
        expr: (traefik_tls_certs_expiry_seconds - time()) / 86400 < 14
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "TLS certificate expiring soon"
          description: "TLS certificate will expire in less than 14 days. Auto-renewal should handle this, but verify."

      - alert: TraefikCertificateExpired
        expr: (traefik_tls_certs_expiry_seconds - time()) / 86400 < 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "TLS certificate has expired"
          description: "TLS certificate has expired. HTTPS will fail for affected domains."
```

### Docker Swarm Alerts

**NEW (2026-04-03)**: Alerts for Docker Swarm cluster health.

```yaml
  - name: docker_swarm
    rules:
      - alert: DockerSwarmNodeDown
        expr: swarm_manager_node_health == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Docker Swarm node unhealthy"
          description: "Docker Swarm node is unhealthy or unreachable."

      - alert: DockerSwarmManagerDown
        expr: count(up{job="docker"} == 1) < 2
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Docker Swarm manager unreachable"
          description: "Docker Swarm manager (re-db) is unreachable. Cannot deploy or manage services."

      - alert: DockerSwarmServiceReplicasUnhealthy
        expr: count by (service_name) (engine_daemon_container_states_containers{state="running"} < 1)
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Service has no running replicas"
          description: "Service {{ $labels.service_name }} has no running replicas."

      - alert: DockerHighContainerRestarts
        expr: rate(engine_daemon_container_actions_seconds_count{action="start"}[10m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High container restart rate on {{ $labels.node }}"
          description: "Containers are being restarted frequently. Check application logs for crashes."

      - alert: DockerSwarmServiceCountChanged
        expr: delta(swarm_manager_services_count[10m]) != 0
        for: 1m
        labels:
          severity: info
        annotations:
          summary: "Docker Swarm service count changed"
          description: "Number of services in Swarm changed from {{ $labels.value }}. This may be expected if deploying or removing services."
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
| router-01/02 | syslog, auth, haproxy, prometheus, alertmanager, dashboard |
| re-db, re-node-02 | syslog, auth, docker-related syslog |
| re-node-01/03/04 | syslog, auth, postgresql, patroni |

### HAProxy Log Collection

HAProxy logs require special configuration:

1. **rsyslog config** (`/etc/rsyslog.d/49-haproxy.conf`):
```bash
# Create socket for chroot'ed HAProxy
$AddUnixListenSocket /var/lib/haproxy/dev/log

# Route HAProxy logs to dedicated file
:programname, startswith, "haproxy" {
  /var/log/haproxy.log
  stop
}
local0.* /var/log/haproxy.log
& stop
local1.* /var/log/haproxy.log
& stop
```

2. **Log file permissions**:
```bash
touch /var/log/haproxy.log
chown syslog:adm /var/log/haproxy.log
chmod 644 /var/log/haproxy.log
systemctl restart rsyslog
```

3. **Logrotate** (`/etc/logrotate.d/haproxy`):
```bash
/var/log/haproxy.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 644 syslog adm
    postrotate
        /usr/bin/systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}
```

### Querying Logs in Grafana

1. Navigate to **Explore** in Grafana
2. Select **Loki** datasource
3. Use LogQL queries:

```logql
# All syslog logs
{job="syslog"}

# Logs from specific host
{host="re-db"}

# Docker-related syslog lines
{job="syslog"} |= "docker"

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
