# Grafana Patterns Reference

## Contents
- Dashboard Patterns
- Panel Configuration
- Datasource Patterns
- Anti-Patterns

## Dashboard Patterns

### Provisioned Dashboard Structure

All dashboards MUST be provisioned via JSON files, not created in the UI:

```json
{
  "title": "Quantyra - Service Name",
  "uid": "service-unique-id",
  "tags": ["service", "quantyra"],
  "timezone": "browser",
  "schemaVersion": 16,
  "version": 0,
  "refresh": "30s",
  "panels": [...]
}
```

**WHY:** UI-created dashboards are lost on container restart. Provisioned dashboards are Git-tracked and survive redeployment.

### Tailscale IP References

Always use Tailscale IPs for cross-server datasources, never public IPs:

```yaml
# GOOD - Tailscale IP (encrypted, internal)
url: http://100.102.220.16:9090

# BAD - Public IP (exposes monitoring, no encryption)
url: http://172.93.54.112:9090
```

**WHY:** Tailscale provides encrypted mesh networking. Public IPs expose metrics endpoints and bypass encryption.

### Consistent Tagging

Every dashboard MUST include the `quantyra` tag plus service-specific tags:

```json
"tags": ["postgresql", "haproxy", "quantyra"]
```

**WHY:** Enables filtering and discovery in the Grafana UI. Standardizes the dashboard library.

## Panel Configuration

### Grid Position Standards

Use consistent panel heights and widths:

```json
// Stat panels - small, quick metrics
"gridPos": {"h": 4, "w": 6, "x": 0, "y": 0}

// Graphs - half width
"gridPos": {"h": 8, "w": 12, "x": 0, "y": 4}

// Full-width logs
"gridPos": {"h": 8, "w": 24, "x": 0, "y": 12}
```

### Threshold Configuration

Always configure thresholds for gauge/stat panels:

```json
"fieldConfig": {
  "defaults": {
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
```

### Derived Fields for Loki

Add trace ID extraction for distributed tracing correlation:

```yaml
# configs/grafana/provisioning/datasources/loki.yml
jsonData:
  derivedFields:
    - name: TraceID
      matcherRegex: '"traceId":"(\w+)"'
      url: '$${__value.raw}'
```

## Datasource Patterns

### Multi-Datasource Setup

Separate Prometheus (metrics) and Loki (logs) datasources:

```yaml
# configs/grafana/provisioning/datasources/datasources.yml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://100.102.220.16:9090
    isDefault: true
    
  - name: Loki
    type: loki
    url: http://100.102.220.16:3100
    isDefault: false
```

### Read-Only Datasources

Mark infrastructure datasources as non-editable:

```yaml
datasources:
  - name: Prometheus
    editable: false  # Prevent UI changes
```

**WHY:** Ensures all changes go through Git. Prevents drift between environments.

## Anti-Patterns

### WARNING: Storing Dashboards in Grafana DB

**The Problem:**
```bash
# Creating dashboards via UI and expecting them to persist
# Dashboards created in UI are stored in Grafana's SQLite database
```

**Why This Breaks:**
1. Container restart wipes the Grafana database (ephemeral storage)
2. No audit trail of dashboard changes
3. Cannot replicate across environments
4. Cannot version control or review changes

**The Fix:**
Always create dashboards as JSON files in `configs/grafana/dashboards/`, provisioned via `configs/grafana/provisioning/dashboards/dashboards.yml`.

**When You Might Be Tempted:**
When rapidly prototyping a new visualization. **AVOID:** Even for prototyping, create the JSON file directly or use the UI then export immediately.

### WARNING: Missing UID in Dashboards

**The Problem:**
```json
// BAD - No UID causes URL instability
{
  "title": "My Dashboard",
  // Missing "uid" field
}
```

**Why This Breaks:**
1. Grafana generates random UID on each provision
2. Dashboard URLs change on every redeploy
3. External links and bookmarks break
4. Alert rule references become invalid

**The Fix:**
```json
// GOOD - Stable UID
{
  "title": "My Dashboard",
  "uid": "my-dashboard-uid"
}
```

### WARNING: Hardcoded Variables in Queries

**The Problem:**
```json
// BAD - Hardcoded server IP
"expr": "up{instance=\"100.102.220.16:9100\"}"
```

**Why This Breaks:**
1. Server IPs can change (Tailscale reassignments)
2. Dashboards become stale when infrastructure changes
3. No multi-environment support

**The Fix:**
Use templating variables and job labels:

```json
// GOOD - Job-based selection
"expr": "up{job=\"node-exporter\"}"
```

Or use Grafana dashboard variables for interactive selection.