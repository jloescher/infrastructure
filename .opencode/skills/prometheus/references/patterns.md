# Prometheus Patterns Reference

## Contents
- Alerting Rules Structure
- Recording Rules
- Service Discovery Patterns
- PromQL Anti-Patterns
- HAProxy Integration

## Alerting Rules Structure

Rules live in `monitoring/prometheus/rules/*.yml`. Each file contains groups with rules.

```yaml
groups:
  - name: postgresql
    interval: 30s
    rules:
      - alert: PostgreSQLReplicationLag
        expr: pg_stat_replication_pg_wal_lsn_diff / 1000000000 > 30
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "PostgreSQL replication lag > 30s on {{ $labels.instance }}"
          description: "Replication lag is {{ $value }} seconds"
```

### WARNING: Missing `for` Duration

**The Problem:**
```yaml
# BAD - fires immediately on blip
expr: up == 0
```

**Why This Breaks:**
1. Network hiccups cause false positives
2. Rolling restarts trigger pages unnecessarily
3. Alert fatigue desensitizes on-call engineers

**The Fix:**
```yaml
# GOOD - must be down for 2 minutes
expr: up == 0
for: 2m
```

## Recording Rules

Pre-compute expensive queries for dashboards.

```yaml
groups:
  - name: haproxy_rules
    rules:
      - record: job:haproxy_backend_http_requests_per_second:rate5m
        expr: rate(haproxy_backend_http_requests_total[5m])
      
      - record: job:haproxy_backend_response_time_seconds:p99
        expr: histogram_quantile(0.99, 
          sum(rate(haproxy_backend_response_time_seconds_bucket[5m])) by (le, backend))
```

## Service Discovery Patterns

### Static Targets (Infrastructure Servers)

```yaml
scrape_configs:
  - job_name: 'node'
    static_configs:
      - targets:
        - '100.126.103.51:9100'  # re-node-01
        - '100.114.117.46:9100'  # re-node-03
        - '100.115.75.119:9100'  # re-node-04
        - '100.102.220.16:9100'  # router-01
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
```

### HAProxy Stats Endpoint

```yaml
  - job_name: 'haproxy'
    static_configs:
      - targets: ['100.102.220.16:8404']
    metrics_path: '/metrics'
```

## PromQL Anti-Patterns

### WARNING: Using `irate()` for Alerting

**The Problem:**
```promql
# BAD - irate only looks at last 2 samples, too sensitive
irate(node_cpu_seconds_total{mode="idle"}[5m]) < 0.1
```

**Why This Breaks:**
1. Misses spikes between scrape intervals
2. Produces erratic results under load
3. Hard to reason about in incident response

**The Fix:**
```promql
# GOOD - rate() averages over full window
rate(node_cpu_seconds_total{mode="idle"}[5m]) < 0.1
```

**When You Might Be Tempted:**
Using `irate()` seems "more accurate" for fast-changing counters. It is not. Use `irate()` only for dashboards where you want instant volatility, never for alerts.

## HAProxy Integration

Enable metrics endpoint in HAProxy config:

```haproxy
frontend stats
  bind *:8404
  stats enable
  stats uri /stats
  stats refresh 10s
  http-request use-service prometheus-exporter if { path /metrics }
```

Query key metrics:

```promql
# Backend health (1 = up, 0 = down)
haproxy_backend_up{backend="app_servers"}

# Current sessions
haproxy_backend_current_sessions

# HTTP 5xx rate
rate(haproxy_backend_http_5xx[5m])