# Grafana Workflows Reference

## Contents
- Deploy Grafana Changes
- Add a New Dashboard
- Troubleshoot Missing Data
- Backup and Restore

## Deploy Grafana Changes

**When:** Modifying dashboards, datasources, or provisioning config

```markdown
Copy this checklist and track progress:
- [ ] Edit JSON/YAML files in configs/grafana/
- [ ] Validate JSON syntax
- [ ] Restart Grafana container
- [ ] Verify dashboards appear in UI
- [ ] Verify datasource connectivity
```

### Step-by-Step

1. **Make changes** to `configs/grafana/dashboards/` or `configs/grafana/provisioning/`

2. **Validate JSON:**
   ```bash
   python3 -m json.tool configs/grafana/dashboards/my_dashboard.json > /dev/null
   ```

3. **Restart container:**
   ```bash
   cd docker && ./scripts/deploy.sh restart grafana
   ```

4. **Verify provisioning:**
   ```bash
   docker logs infrastructure-grafana 2>&1 | grep -i "provisioning"
   ```

5. **Check UI:** Visit http://localhost:3000 and confirm changes

## Add a New Dashboard

**When:** Adding monitoring for a new service or metric

### Create Dashboard JSON

```bash
# Copy an existing dashboard as template
cp configs/grafana/dashboards/redis_dashboard.json \
   configs/grafana/dashboards/new_service_dashboard.json
```

### Required Fields

Edit the JSON to include:

```json
{
  "title": "Quantyra - New Service",
  "uid": "new-service-uid",
  "tags": ["new-service", "quantyra"],
  "timezone": "browser",
  "schemaVersion": 16,
  "refresh": "30s"
}
```

### Add Prometheus Queries

See the **prometheus** skill for PromQL patterns:

```json
{
  "targets": [
    {
      "expr": "rate(http_requests_total{job=\"new-service\"}[5m])",
      "legendFormat": "{{method}} {{status}}",
      "datasource": "Prometheus"
    }
  ]
}
```

### Deploy and Verify

```bash
# Restart to pick up new dashboard
cd docker && ./scripts/deploy.sh restart grafana

# Validate dashboard loads
curl -s http://localhost:3000/api/dashboards/uid/new-service-uid | jq .dashboard.title
```

## Troubleshoot Missing Data

**When:** Dashboard panels show "No data" or errors

### Step 1: Check Datasource Connectivity

```bash
# From Grafana container
docker exec infrastructure-grafana wget -qO- \
  http://100.102.220.16:9090/api/v1/status/targets
```

### Step 2: Verify PromQL Query

```bash
# Test query directly against Prometheus
curl -s "http://localhost:9090/api/v1/query?query=up" | jq .
```

### Step 3: Check Panel Datasource Reference

```json
// Verify datasource name matches provisioning
"datasource": "Prometheus"  // Must match datasources.yml name field
```

### Step 4: Validate Dashboard JSON

```bash
# Check for JSON syntax errors
python3 -m json.tool configs/grafana/dashboards/my_dashboard.json > /dev/null
```

### Step 5: Review Grafana Logs

```bash
docker logs infrastructure-grafana --tail 100 | grep -i error
```

## Backup and Restore

### Export Dashboard (Manual)

```bash
# Export via API
curl -s http://admin:admin@localhost:3000/api/dashboards/uid/my-dashboard \
  | jq '.dashboard' > backup_dashboard.json
```

### Backup Provisioning Files

Dashboards are already in Git, but ensure changes are committed:

```bash
git add configs/grafana/
git commit -m "infra: update Grafana dashboards"
```

### Restore from Git

```bash
# Restore dashboards from repository
git checkout configs/grafana/dashboards/
cd docker && ./scripts/deploy.sh restart grafana
```

## Feedback Loops

When deploying dashboard changes:

1. **Make changes** to JSON/YAML files
2. **Validate:** `python3 -m json.tool <file> > /dev/null`
3. **If validation fails**, fix JSON and repeat step 2
4. **Deploy:** `./scripts/deploy.sh restart grafana`
5. **Verify:** Check UI at http://localhost:3000
6. **If dashboards don't appear**, check logs and fix provisioning config
7. **Only proceed** when dashboards load correctly