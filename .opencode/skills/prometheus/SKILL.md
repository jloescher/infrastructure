---
name: prometheus
description: Manages Prometheus metrics collection, alerting rules, and monitoring stack integration. Use when writing PromQL queries, creating alerting rules, configuring service discovery, debugging metric collection, or integrating with Grafana/Alertmanager.
---

# Prometheus Skill

Prometheus 2.48.x collects metrics from HAProxy, PostgreSQL (via Patroni), Redis, Node Exporter, and application exporters. Runs on router-01 with Grafana for visualization and Alertmanager for routing.

## Quick Start

### Check Metric Endpoint

```bash
# Query Prometheus API directly
curl -s "http://100.102.220.16:9090/api/v1/query?query=up" | jq

# Check specific target
curl -s "http://100.102.220.16:9090/api/v1/targets" | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

### Basic PromQL Query

```promql
# HAProxy backend health
haproxy_backend_http_requests_total{backend="app_servers"}

# PostgreSQL replication lag (seconds)
pg_stat_replication_pg_wal_lsn_diff / 1000000000

# Node CPU usage
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Target | Scrape endpoint | `100.102.220.16:8404` (HAProxy stats) |
| Job | Group of targets | `haproxy`, `postgres`, `node` |
| Metric types | Counter, Gauge, Histogram, Summary | `haproxy_backend_up` (gauge) |
| Labels | Key-value metadata | `{instance="100.102.220.16:9090", job="prometheus"}` |
| Recording rule | Pre-computed query | `job:pg_replication_lag:seconds` |
| Alerting rule | Trigger condition | `expr: pg_replication_lag > 30` |

## Common Patterns

### Rate Calculation for Counters

**When:** Calculating requests/second from cumulative counters.

```promql
# WRONG - raw counter increases forever
haproxy_backend_http_requests_total

# CORRECT - per-second rate over 5m window
rate(haproxy_backend_http_requests_total[5m])
```

### Vector Matching with Labels

**When:** Combining metrics from different sources.

```promql
# Join node CPU with custom app metrics by instance
app_request_duration_seconds_sum / on(instance) group_left node_cpu_seconds_total
```

## See Also

- [patterns](references/patterns.md)
- [workflows](references/workflows.md)

## Related Skills

- **grafana** - Dashboard provisioning and visualization
- **docker** - Local monitoring stack deployment
- **haproxy** - Metrics export via stats page
- **postgresql** - Patroni/PostgreSQL metrics