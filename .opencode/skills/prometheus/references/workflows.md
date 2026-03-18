# Prometheus Workflows Reference

## Contents
- Adding a New Alert
- Debugging Missing Metrics
- Testing Alert Expressions
- Rolling Out Rule Changes

## Adding a New Alert

Copy this checklist and track progress:
- [ ] Identify metric and threshold from Grafana or exploration
- [ ] Write alert rule in appropriate `monitoring/prometheus/rules/*.yml` file
- [ ] Add `for` duration to prevent flapping (minimum 2m)
- [ ] Include summary and description annotations
- [ ] Set severity label (critical, warning, info)
- [ ] Validate syntax with `promtool`
- [ ] Reload Prometheus config
- [ ] Test by triggering condition in staging

### Alert Rule Template

```yaml
groups:
  - name: custom_app
    rules:
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on {{ $labels.job }}"
          description: "Error rate is {{ $value | humanizePercentage }}"
```

## Debugging Missing Metrics

### Step 1: Verify Target is Up

```bash
# Check targets page
curl -s http://100.102.220.16:9090/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.job=="haproxy") | {health: .health, lastError}'
```

### Step 2: Check Exporter Endpoint

```bash
# Direct scrape test
curl -s http://100.102.220.16:8404/metrics | head -20

# Look for expected metric
curl -s http://100.102.220.16:8404/metrics | grep haproxy_backend_up
```

### Step 3: Validate PromQL

```promql
# Start broad, then narrow
{__name__=~".*haproxy.*"}  # All HAProxy metrics
haproxy_backend_up          # Specific metric
haproxy_backend_up{backend="app_servers"}  # With label filter
```

## Testing Alert Expressions

Use Prometheus UI or API to test before deploying:

```bash
# Test alert expression
curl -s "http://100.102.220.16:9090/api/v1/query?query=up==0" | jq

# Test with time range
curl -s "http://100.102.220.16:9090/api/v1/query_range?query=up&start=$(date -d '10 min ago' +%s)&end=$(date +%s)&step=15s" | jq
```

## Rolling Out Rule Changes

### WARNING: Direct File Edit Without Validation

**The Problem:**
Editing rule files and restarting Prometheus without syntax check.

**Why This Breaks:**
1. YAML indentation errors break entire rule group
2. Invalid PromQL fails silently or crashes Prometheus
3. No rollback if rules are malformed

**The Fix:**

```bash
# Step 1: Validate syntax
docker run --rm -v $(pwd)/monitoring/prometheus:/prom prom/prometheus:v2.48.0 \
  promtool check rules /prom/rules/*.yml

# Step 2: Check config
docker run --rm -v $(pwd)/monitoring/prometheus:/prom prom/prometheus:v2.48.0 \
  promtool check config /prom/prometheus.yml

# Step 3: Reload (no restart needed)
curl -X POST http://100.102.220.16:9090/-/reload
```

### Iteration Workflow

1. Make changes to rule file
2. Validate: Run promtool check commands above
3. If validation fails, fix syntax errors and repeat step 2
4. Only proceed when validation passes
5. Deploy to router-01 and reload Prometheus
6. Verify alert appears in Prometheus UI Status > Rules

## Silencing Alerts (Incident Response)

```bash
# Create silence via Alertmanager API
curl -X POST http://100.102.220.16:9093/api/v1/silences \
  -d '{
    "matchers": [{"name": "alertname", "value": "PostgreSQLReplicationLag", "isRegex": false}],
    "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%S)'",
    "endsAt": "'$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%S)'",
    "createdBy": "oncall",
    "comment": "Planned maintenance"
  }'