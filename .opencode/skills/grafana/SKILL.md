---
name: grafana
description: Handles Grafana dashboard visualization and alert management for the Quantyra infrastructure monitoring stack. Use when creating or editing dashboards, provisioning datasources, configuring alerts, or troubleshooting visualization issues.
---

# Grafana Skill

Grafana 10.2.x provides visualization and alerting for the Quantyra infrastructure monitoring stack. Dashboards are provisioned via JSON files in `configs/grafana/dashboards/`, datasources via YAML in `configs/grafana/provisioning/datasources/`. The infrastructure uses provisioned dashboards (Git-tracked) rather than UI-created dashboards (ephemeral).

## Quick Start

### Add a New Dashboard

```yaml
# configs/grafana/provisioning/dashboards/dashboards.yml
providers:
  - name: default
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    options:
      path: /var/lib/grafana/dashboards
```

```json
// configs/grafana/dashboards/my_dashboard.json
{
  "title": "Quantyra - Service Name",
  "tags": ["service", "quantyra"],
  "timezone": "browser",
  "schemaVersion": 16,
  "refresh": "30s",
  "panels": [
    {
      "title": "Metric Name",
      "type": "stat",
      "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
      "targets": [
        {
          "expr": "up{job=\"my-job\"}",
          "legendFormat": "Status",
          "datasource": "Prometheus"
        }
      ]
    }
  ]
}
```

### Add a Datasource

```yaml
# configs/grafana/provisioning/datasources/datasources.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://100.102.220.16:9090
    isDefault: true
    editable: true
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Provisioning | Git-tracked dashboards/datasources | `configs/grafana/provisioning/` |
| Schema version | Dashboard JSON format version | `16` for Grafana 10.x |
| Grid position | Panel layout (`h`, `w`, `x`, `y`) | `{"h": 4, "w": 6, "x": 0, "y": 0}` |
| Expression | PromQL or LogQL query | `sum(rate(http_requests_total[5m]))` |
| Datasource | Backend data source reference | `"Prometheus"` or `"Loki"` |

## Common Patterns

### Stat Panel for Cluster Health

**When:** Displaying discrete values like replica counts or status

```json
{
  "title": "Patroni Cluster Status",
  "type": "stat",
  "gridPos": {"h": 4, "w": 6, "x": 0, "y": 0},
  "targets": [
    {
      "expr": "sum(patroni_primary{scope=\"quantyra_pg\"})",
      "legendFormat": "Leader",
      "refId": "A",
      "datasource": "Prometheus"
    }
  ]
}
```

### Gauge Panel with Thresholds

**When:** Visualizing percentages or ratios with warning levels

```json
{
  "title": "Connection Usage",
  "type": "gauge",
  "gridPos": {"h": 4, "w": 6, "x": 6, "y": 0},
  "targets": [
    {
      "expr": "(pg_stat_activity_count / pg_settings_max_connections) * 100",
      "legendFormat": "Connection %",
      "datasource": "Prometheus"
    }
  ],
  "fieldConfig": {
    "defaults": {
      "max": 100,
      "min": 0,
      "thresholds": {
        "mode": "absolute",
        "steps": [
          {"color": "green", "value": 0},
          {"color": "yellow", "value": 70},
          {"color": "red", "value": 85}
        ]
      }
    }
  }
}
```

## See Also

- [patterns](references/patterns.md) - Dashboard patterns and anti-patterns
- [workflows](references/workflows.md) - Deployment and troubleshooting workflows

## Related Skills

- **prometheus** - Metrics collection and PromQL queries
- **docker** - Container deployment for Grafana service
- **haproxy** - HAProxy metrics visualization
- **postgresql** - PostgreSQL monitoring dashboards
- **redis** - Redis monitoring dashboards
- **patroni** - Patroni cluster health monitoring
- **ansible** - Server provisioning and configuration