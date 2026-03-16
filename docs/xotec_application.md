# XOTEC Data Layer - Application Documentation

## Overview

XOTEC Data Layer is a Go-based application running on `re-db` that processes MLS (Multiple Listing Service) real estate data.

**Location**: `/opt/quantyra-datalayer`  
**Binary**: Go executables in `bin/`  
**Secrets**: `/opt/quantyra-datalayer/secrets.env`  
**Deploy User**: `deploy`

---

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │            Caddy (Reverse Proxy)         │
                    │     Ports: 80, 443                       │
                    │     Domains: quantyra.io, lzrcdn.com        │
                    └──────────────┬──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
           ┌────────▼────────┐           ┌───────▼────────┐
           │  App (Blue)     │           │  App (Green)   │
           │  Port: 8001     │           │  Port: 8002    │
           │  (Active)       │           │  (Standby)     │
           └────────┬────────┘           └───────┬────────┘
                    │                             │
                    └──────────────┬──────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
┌────────▼────────┐    ┌──────────▼──────────┐    ┌────────▼────────┐
│   Scheduler     │    │      Redis          │    │   Asynqmon      │
│   (Cron Jobs)   │    │   (Job Queue)       │    │   Port: 9090    │
└────────┬────────┘    └──────────┬──────────┘    └─────────────────┘
         │                        │
         │             ┌──────────┴──────────┐
         │             │                     │
         │    ┌────────▼────────┐   ┌───────▼────────┐
         │    │ Worker (Ingest) │   │ Worker (Media) │
         │    │ Concurrency: 8  │   │ Concurrency: 6 │
         │    └─────────────────┘   └────────────────┘
         │             │
         │    ┌────────▼────────────┐
         │    │ Worker (MLS API)    │
         │    │ Concurrency: 1      │
         │    └─────────────────────┘
         │
┌────────▼────────────────┐
│ Worker (Maintenance)    │
│ Concurrency: 4          │
└─────────────────────────┘
```

---

## Services

### Main Application

| Service | Port | Description |
|---------|------|-------------|
| `quantyra-app-blue` | 8001 | HTTP server (blue instance) |
| `quantyra-app-green` | 8002 | HTTP server (green instance) - standby |

### Background Workers

| Service | Mode | Concurrency | Description |
|---------|------|-------------|-------------|
| `quantyra-worker-ingest` | ingest | 8 | MLS data processing, property batches |
| `quantyra-worker-maintenance` | maintenance | 4 | Background tasks, cleanup |
| `quantyra-worker-media` | media | 6 | Image processing, optimization |
| `quantyra-worker-mls-api` | mls-api | 1 | MLS Grid API requests (rate limited) |

### Supporting Services

| Service | Port | Description |
|---------|------|-------------|
| `quantyra-scheduler` | - | Job scheduler (cron) |
| `quantyra-asynqmon` | 9090 | Queue monitoring UI |
| `caddy` | 80, 443 | Reverse proxy with auto-HTTPS |

---

## Blue-Green Deployment

The application uses blue-green deployment for zero-downtime releases:

1. **Blue** (port 8001) - Currently active
2. **Green** (port 8002) - Standby for next release

### Deployment Process

1. Deploy new version to standby (green)
2. Health check passes on green
3. Caddy automatically routes to healthy instances
4. Drain connections from old (blue)
5. Blue becomes new standby for next release

### Health Checks

- **Endpoint**: `/health`
- **Interval**: 10 seconds
- **Timeout**: 5 seconds
- **Fail duration**: 30 seconds

---

## Domains

| Domain | Purpose |
|--------|---------|
| `quantyra.io` | Main application |
| `lzrcdn.com` | CDN/Media domain |
| `media.lzrcdn.com` | Media proxy |
| `asynq.quantyra.io` | Queue monitor (disabled) |

---

## Integration with Infrastructure

### PostgreSQL Connection

The application connects to PostgreSQL via HAProxy:

```
Write: 100.102.220.16:5000 (or 100.116.175.9:5000)
Read:  100.102.220.16:5001 (or 100.116.175.9:5001)
```

### Redis Connection

Job queues use Redis:

```
Master: 100.126.103.51:6379
Replica: 100.114.117.46:6379
```

---

## MLS Grid API Integration

The application integrates with MLS Grid API:

- **API URL**: `https://api.mlsgrid.com/v2`
- **Rate Limit**: 2 requests/second (enforced by worker)
- **Originating System**: `mfrmls` (Mid-Florida Regional MLS)
- **Data Source**: `live`

---

## Secrets Management

Secrets are stored in `/opt/quantyra-datalayer/secrets.env`:

- Database credentials
- Redis password
- MLS Grid API key
- Other sensitive configuration

**⚠️ Do not commit secrets to this repository**

---

## Common Operations

### Check Service Status

```bash
# All XOTEC services
systemctl status quantyra-*

# Individual service
systemctl status quantyra-app-blue
```

### View Logs

```bash
# Journal logs
journalctl -u quantyra-app-blue -f

# Caddy logs
tail -f /var/log/caddy/access.log
```

### Restart Services

```bash
# Restart app (blue)
sudo systemctl restart quantyra-app-blue

# Restart all workers
sudo systemctl restart quantyra-worker-*
```

### Deploy New Version

1. Upload new binary to `/opt/quantyra-datalayer/bin/`
2. Update environment if needed
3. Restart services:

```bash
sudo systemctl restart quantyra-app-blue
sudo systemctl restart quantyra-worker-*
sudo systemctl restart quantyra-scheduler
```

---

## Monitoring

### Metrics Endpoints

- **App Health**: `https://quantyra.io/health`
- **Asynqmon**: `https://quantyra.io/queue/` (internal: port 9090)

### Prometheus Scraping

Add to Prometheus config:

```yaml
- job_name: 'quantyra-app'
  static_configs:
    - targets: ['100.92.26.38:8001', '100.92.26.38:8002']
```

---

## Files in Repository

| File | Description |
|------|-------------|
| `configs/caddy/Caddyfile` | Caddy reverse proxy configuration |
| `configs/quantyra/systemd-services.conf` | Systemd service definitions |

---

## Troubleshooting

### App Not Responding

1. Check service status: `systemctl status quantyra-app-blue`
2. Check logs: `journalctl -u quantyra-app-blue -n 100`
3. Check health: `curl http://localhost:8001/health`

### Workers Not Processing Jobs

1. Check Redis connection
2. Check worker status: `systemctl status quantyra-worker-*`
3. Check Asynqmon at port 9090

### Database Connection Issues

1. Verify HAProxy is routing correctly
2. Check PostgreSQL cluster status: `patronictl list`
3. Verify network connectivity to router IPs

---

## Backup Notes

The application state includes:

- PostgreSQL database (backed up via pgBackRest)
- Redis queue data (RDB snapshots)
- Application files in `/opt/quantyra-datalayer/`

No additional backup configuration required beyond infrastructure backups.