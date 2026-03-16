# XOTEC Application Services

Systemd service definitions for the XOTEC Data Layer application.

## Services

### Application Servers
| Service | Port | Status |
|---------|------|--------|
| `quantyra-app-blue` | 8001 | Active |
| `quantyra-app-green` | 8002 | Standby |
| `quantyra-asynqmon` | 9090 | Queue Monitor |

### Workers
| Service | Concurrency | Purpose |
|---------|-------------|---------|
| `quantyra-worker-ingest` | 8 | MLS data processing |
| `quantyra-worker-maintenance` | 4 | Background tasks |
| `quantyra-worker-media` | 6 | Image processing |
| `quantyra-worker-mls-api` | 1 | MLS Grid API (rate limited) |

### Supporting
| Service | Purpose |
|---------|---------|
| `quantyra-scheduler` | Cron job scheduler |
| `caddy` | Reverse proxy (ports 80, 443) |

## Directory Structure

```
/opt/quantyra-datalayer/
├── bin/
│   ├── app
│   ├── asynqmon
│   ├── scheduler
│   └── worker
├── secrets.env
└── (application files)
```

## See Also

- [XOTEC Application Documentation](../docs/quantyra_application.md)
- [Caddy Configuration](../caddy/Caddyfile)