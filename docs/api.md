# API Documentation

## Authentication

All API endpoints require Basic Auth:

```bash
curl -u admin:DbAdmin2026! http://localhost:8080/api/apps
```

## Applications

### List Applications

```
GET /api/apps
```

Response:
```json
{
  "applications": ["myapp", "another-app"]
}
```

### Get Application Details

```
GET /api/apps/<app_name>
```

Response:
```json
{
  "success": true,
  "app": {
    "name": "my-app",
    "framework": "laravel",
    "git_repo": "https://github.com/user/my-app",
    "production_branch": "main",
    "staging_branch": "staging",
    "production_port": 8101,
    "staging_port": 9201,
    "created_at": "2026-03-27T10:00:00Z"
  }
}
```

### Create Application

```
POST /api/apps
Content-Type: application/json

{
  "name": "my-app",
  "framework": "laravel",
  "git_repo": "https://github.com/user/my-app",
  "production_branch": "main",
  "staging_branch": "staging"
}
```

Response:
```json
{
  "success": true,
  "message": "Application created successfully",
  "app": {
    "name": "my-app",
    "port": 8101
  }
}
```

### Update Application

```
PUT /api/apps/<app_name>
Content-Type: application/json

{
  "git_repo": "https://github.com/user/new-repo",
  "production_branch": "production"
}
```

### Delete Application

```
DELETE /api/apps/<app_name>?delete_data=true
```

Query Parameters:
- `delete_data` (boolean): Also delete database (default: false)

## Deployments

### Deploy Application

```
POST /api/apps/<app_name>/deploy
Content-Type: application/json

{
  "branch": "main",
  "rolling": true
}
```

Response:
```json
{
  "success": true,
  "message": "Deployment completed"
}
```

### Async Deploy

```
POST /api/apps/<app_name>/deploy-async
Content-Type: application/json

{
  "branch": "main",
  "environment": "production"
}
```

Response:
```json
{
  "success": true,
  "deployment_id": "abc123",
  "task_id": "def456",
  "websocket_room": "deployment:abc123"
}
```

### Get Deployment Status

```
GET /api/deployments/<deployment_id>
```

Response:
```json
{
  "success": true,
  "deployment": {
    "id": "abc123",
    "status": "running",
    "environment": "production",
    "branch": "main",
    "started_at": "2026-03-27T10:00:00Z"
  },
  "progress": {
    "percent": 45,
    "current_step": "install_deps",
    "servers": {
      "re-db": "completed",
      "re-node-02": "running"
    }
  }
}
```

### List Deployments

```
GET /api/apps/<app_name>/deployments
```

Response:
```json
{
  "success": true,
  "deployments": [
    {
      "id": "abc123",
      "branch": "main",
      "environment": "production",
      "status": "completed",
      "started_at": "2026-03-27T10:00:00Z",
      "completed_at": "2026-03-27T10:05:00Z"
    }
  ]
}
```

### Rollback Deployment

```
POST /api/deployments/<deployment_id>/rollback
```

Response:
```json
{
  "success": true,
  "message": "Rollback completed"
}
```

## Domains

### List Domains

```
GET /api/apps/<app_name>/domains
```

Response:
```json
{
  "success": true,
  "domains": [
    {
      "domain": "example.com",
      "environment": "production",
      "ssl_enabled": true,
      "ssl_status": "active",
      "created_at": "2026-03-27T10:00:00Z"
    }
  ]
}
```

### Provision Domain

```
POST /api/apps/<app_name>/domains
Content-Type: application/json

{
  "domain": "example.com",
  "environment": "production",
  "ssl_enabled": true
}
```

Response:
```json
{
  "success": true,
  "message": "Domain provisioned successfully",
  "domain": {
    "domain": "example.com",
    "dns_records": ["A", "AAAA", "CNAME"],
    "ssl_status": "pending"
  }
}
```

### Delete Domain

```
DELETE /api/apps/<app_name>/domains/<domain>
```

## Databases

### List Databases

```
GET /api/databases
```

Response:
```json
{
  "success": true,
  "databases": [
    {
      "name": "myapp_production",
      "owner": "myapp_user",
      "size": "256 MB",
      "tables": 42
    }
  ]
}
```

### Create Database

```
POST /api/databases
Content-Type: application/json

{
  "name": "myapp_production",
  "user": "myapp_user",
  "password": "secret123"
}
```

### Get Database Metrics

```
GET /api/databases/<db_name>/metrics
```

Response:
```json
{
  "success": true,
  "size": 1073741824,
  "connections": 15,
  "max_connections": 200,
  "table_count": 42,
  "slow_queries": 3,
  "cache_hit_ratio": 0.99
}
```

### Create Backup

```
POST /api/databases/<db_name>/backups
```

Response:
```json
{
  "success": true,
  "backup_id": "backup-20260327-100000",
  "size": "128 MB",
  "expires_at": "2026-04-27T00:00:00Z"
}
```

### List Backups

```
GET /api/databases/<db_name>/backups
```

### Restore Backup

```
POST /api/databases/<db_name>/backups/<backup_id>/restore
```

## Services

### List Service Templates

```
GET /api/services/templates
```

Response:
```json
{
  "success": true,
  "templates": [
    {
      "type": "redis",
      "name": "Redis",
      "description": "In-memory data store",
      "default_memory": "256M",
      "env_vars": ["REDIS_URL"]
    },
    {
      "type": "meilisearch",
      "name": "Meilisearch",
      "description": "Search engine",
      "default_memory": "512M",
      "env_vars": ["MEILI_API_KEY"]
    }
  ]
}
```

### List Application Services

```
GET /api/apps/<app_name>/services
```

### Create Service

```
POST /api/apps/<app_name>/services
Content-Type: application/json

{
  "type": "redis",
  "environment": "production",
  "config": {
    "memory_limit": "512M"
  }
}
```

Response:
```json
{
  "success": true,
  "service": {
    "type": "redis",
    "connection_url": "redis://:password@localhost:6379/0",
    "env_var": "REDIS_URL"
  }
}
```

### Delete Service

```
DELETE /api/apps/<app_name>/services/<service_type>
```

## Secrets

### List Secrets

```
GET /api/secrets/<app_name>
```

Response:
```json
{
  "success": true,
  "secrets": [
    {
      "key": "APP_KEY",
      "scope": "production",
      "created_at": "2026-03-27T10:00:00Z",
      "updated_at": "2026-03-27T10:00:00Z"
    }
  ]
}
```

**Note:** Secret values are never returned in API responses.

### Add Secret

```
POST /api/secrets/<app_name>
Content-Type: application/json

{
  "key": "APP_KEY",
  "value": "base64:...",
  "scope": "production"
}
```

### Update Secret

```
PUT /api/secrets/<app_name>/<key>
Content-Type: application/json

{
  "value": "new-value",
  "scope": "production"
}
```

### Delete Secret

```
DELETE /api/secrets/<app_name>/<key>
```

## Drift Detection

### Check Drift

```
POST /api/drift/check
```

Response:
```json
{
  "success": true,
  "message": "Drift check started",
  "check_id": "drift-123"
}
```

### Get Drift Results

```
GET /api/drift/results
```

Response:
```json
{
  "success": true,
  "drift_detected": true,
  "items": [
    {
      "type": "domain",
      "name": "example.com",
      "expected": {
        "ssl_enabled": true
      },
      "actual": {
        "ssl_enabled": false
      }
    }
  ]
}
```

## Webhooks

### GitHub Webhook

```
POST /api/webhooks/github/<app_name>
X-GitHub-Event: push

{
  "ref": "refs/heads/main",
  "after": "abc123...",
  "repository": {
    "full_name": "user/repo"
  }
}
```

Response:
```json
{
  "success": true,
  "deployment_id": "deploy-456"
}
```

### Configure Webhooks

```
POST /api/apps/<app_name>/webhooks
Content-Type: application/json

{
  "url": "https://example.com/webhook",
  "events": ["deployment.completed", "deployment.failed"],
  "secret": "webhook-secret"
}
```

## WebSocket Events

Connect to `ws://localhost:8080/socket.io`

### Events

| Event | Description | Payload |
|-------|-------------|---------|
| `deployment_started` | Deployment started | `{deployment_id, branch, environment}` |
| `step_progress` | Step progress update | `{server, step, status, output}` |
| `deployment_complete` | Deployment finished | `{deployment_id, success, duration}` |
| `deployment_failed` | Deployment failed | `{deployment_id, error, logs}` |
| `rollback_started` | Rollback initiated | `{deployment_id, target}` |
| `drift_detected` | Configuration drift | `{items}` |

### Example

```javascript
const socket = io('http://localhost:8080');

socket.emit('join', {room: 'deployment:abc123'});

socket.on('step_progress', (data) => {
  console.log(`${data.server}: ${data.step} - ${data.status}`);
  if (data.output) {
    console.log(data.output);
  }
});

socket.on('deployment_complete', (data) => {
  console.log(`Deployment ${data.deployment_id} completed in ${data.duration}s`);
});
```

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "error": "Application not found",
  "code": "APP_NOT_FOUND"
}
```

### Common Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `APP_NOT_FOUND` | 404 | Application does not exist |
| `DOMAIN_EXISTS` | 400 | Domain already provisioned |
| `DEPLOYMENT_FAILED` | 500 | Deployment encountered an error |
| `INVALID_FRAMEWORK` | 400 | Unsupported framework |
| `PORT_IN_USE` | 400 | Port already allocated |
| `DB_CONNECTION_ERROR` | 500 | Cannot connect to database |
| `UNAUTHORIZED` | 401 | Invalid credentials |
| `RATE_LIMITED` | 429 | Too many requests |

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/apps/*/deploy` | 10 requests | 1 minute |
| `/api/webhooks/*` | 100 requests | 1 minute |
| All others | 60 requests | 1 minute |

## Pagination

List endpoints support pagination:

```
GET /api/apps/<app_name>/deployments?page=1&per_page=20
```

Response includes pagination metadata:

```json
{
  "success": true,
  "deployments": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 45,
    "total_pages": 3
  }
}
```