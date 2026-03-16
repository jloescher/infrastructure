# Infrastructure Review Overview

Generated from repository inspection on 2026-03-15.

## Executive Summary

This repository describes a 7-node VPS environment connected over Tailscale, with clear separation between database, routing, monitoring, and application responsibilities. The overall design is strong: PostgreSQL is deployed as a 3-node Patroni-managed cluster behind HAProxy read/write endpoints, Redis is deployed as a master/replica pair, and the XOTEC application runs on a dedicated app server with blue/green service layout behind Caddy.

The repo is most reliable today as a captured-state inventory and operational knowledge base. It contains strong host metadata, service configs, runbooks, and intended recovery procedures. The main gap is that parts of the automation layer do not yet match the live operating model, especially for application deployment, monitoring deployment, and backup implementation.

## Current Infrastructure Shape

### Network and Topology

- All nodes are connected through the Tailscale network `100.64.0.0/10`.
- Public ingress appears to flow through Cloudflare DNS to two router nodes.
- Internal service-to-service traffic is primarily over Tailscale addresses.
- `router-01` serves as the primary routing and monitoring node.
- `router-02` serves as the secondary router and web entrypoint.

### Server Roles

| Server | Primary Role | Notes |
|--------|--------------|-------|
| `re-node-01` | PostgreSQL + Patroni + Redis master + PgBouncer | Core DB node |
| `re-node-03` | PostgreSQL + Patroni + Redis replica | Replica DB node |
| `re-node-04` | PostgreSQL + Patroni | Third DB node |
| `router-01` | HAProxy + etcd + Prometheus + Grafana + Alertmanager | Primary infra edge/monitoring |
| `router-02` | HAProxy | Secondary router |
| `re-db` | XOTEC application server | Active app host |
| `re-node-02` | Idle app-capable node | Reserved capacity |

## Database Layer

### PostgreSQL / Patroni

The database tier is the strongest and most mature part of the environment.

- PostgreSQL version: `18.3`
- Patroni cluster name: `quantyra_pg`
- Nodes: `re-node-01`, `re-node-03`, `re-node-04`
- HAProxy write endpoints:
  - `100.102.220.16:5000`
  - `100.116.175.9:5000`
- HAProxy read endpoints:
  - `100.102.220.16:5001`
  - `100.116.175.9:5001`

Configuration suggests a practical HA design:

- Patroni handles leader election and node health.
- HAProxy uses Patroni health endpoints for routing.
- Reads are load-balanced across replicas.
- `re-node-01` is allowed as backup read target.
- PgBouncer is present on `re-node-01`.

Current PostgreSQL tuning is production-oriented:

- `max_connections = 300`
- `shared_buffers = 8GB`
- `effective_cache_size = 24GB`
- `maintenance_work_mem = 2GB`
- `work_mem = 64MB`
- `wal_keep_size = 8GB`
- `synchronous_commit = off`

### Redis

Redis is simpler and functional, but currently less resilient than PostgreSQL.

- Master: `re-node-01:6379`
- Replica: `re-node-03:6379`
- Max memory: `4GB`
- Eviction policy: `allkeys-lru`
- Persistence: both snapshotting and AOF are enabled
- Access model: Tailscale network

Operationally:

- This is a standard master/replica deployment.
- Redis Sentinel is not yet configured.
- Failover would currently require manual intervention.
- Dangerous commands are renamed or disabled.

## Routing and Edge Layer

HAProxy is the shared routing plane for database and web traffic.

### `router-01`

- Routes PostgreSQL read/write traffic
- Hosts etcd for Patroni DCS
- Hosts Prometheus, Grafana, and Alertmanager

### `router-02`

- Routes PostgreSQL read/write traffic
- Routes HTTP/HTTPS traffic to app servers

The captured HAProxy configs show:

- Patroni-aware health checks for PostgreSQL
- HTTP load balancing for app HTTP traffic
- TCP passthrough for HTTPS traffic
- Metrics endpoint exposed on port `8405`

One notable architectural quirk: the checked-in `router-01` HAProxy config also contains web frontends, which blurs the documented separation a bit. That may be intentional redundancy, or it may reflect configuration drift between documentation and live deployment.

## Application Layer

The live application model is centered on `re-db`, not Docker.

### XOTEC on `re-db`

The XOTEC data layer appears to run as native systemd services:

- `quantyra-app-blue` on `:8001`
- `quantyra-app-green` on `:8002`
- `quantyra-scheduler`
- `quantyra-asynqmon` on `:9090`
- Worker services:
  - ingest
  - maintenance
  - media
  - mls-api

Caddy sits in front of the services and provides:

- TLS termination
- blue/green upstream selection
- health checking
- sticky routing for setup flows
- routing for:
  - `quantyra.io`
  - `lzrcdn.com`
  - `media.lzrcdn.com`

This is a thoughtful app layout:

- Blue/green deployment reduces downtime risk.
- Worker roles are separated by function and concurrency.
- Queue visibility exists through `asynqmon`.
- The app consumes PostgreSQL via HAProxy and Redis directly.

### `re-node-02`

`re-node-02` is documented as idle and ready for future deployment. It is currently best understood as spare capacity rather than part of the active app path.

## Monitoring and Operations

Monitoring is conceptually well-designed, but only partially implemented in repo automation.

### Intended Stack

- Prometheus
- Grafana
- Alertmanager
- node_exporter
- postgres_exporter
- planned Redis and HAProxy exporters
- planned blackbox probing

### Monitoring Strengths

- Prometheus targets are defined for DB nodes, routers, app servers, Patroni, etcd, and HAProxy.
- Alert rules cover CPU, memory, disk, PostgreSQL, Redis, HAProxy, etcd, and backups.
- Grafana dashboards for PostgreSQL/HAProxy and Redis are present.
- Alertmanager routing is defined for severity and team destination.

### Monitoring Reality Check

The monitoring design is ahead of implementation in a few places:

- Redis exporter is referenced before being fully established.
- HAProxy exporter expectations do not line up cleanly with the checked-in configs.
- Blackbox exporter config is referenced, but the config file is missing from the repo.
- App metrics and Docker metrics are listed, but the live app model is not Docker-based.

## Security Posture

There are good foundations in place:

- UFW is enabled broadly.
- SSH hardening is documented.
- fail2ban is deployed on DB nodes.
- Redis protected mode is enabled.
- destructive Redis commands are renamed or disabled.
- XOTEC services include systemd hardening directives such as `NoNewPrivileges=true` and `ProtectSystem=strict`.

However, the biggest security issue in the repository is immediate:

### Critical Security Issue

Redis credentials are committed in plaintext in the checked-in Redis configs. This should be treated as an active secret exposure and rotated.

## Backups and Disaster Recovery

This is the largest operational gap.

The repo contains:

- backup scripts
- a pgBackRest config
- disaster recovery documentation
- action items for enabling backups
- Ansible playbooks intended to deploy backup scripts and cron jobs

But the captured state and group vars consistently describe backups as not yet deployed:

- `pgbackrest_enabled: false`
- `redis_backup_enabled: false`
- `monitoring_backup_enabled: false`

That means your DR documentation is directionally useful, but not yet fully backed by implemented backup infrastructure.

## What Is Working Well

- The infrastructure topology is coherent and easy to reason about.
- PostgreSQL HA design is solid and production-oriented.
- The XOTEC service model on `re-db` is more mature than the generic app automation in the repo.
- The documentation is unusually strong for an infra repo: inventory, runbook, DR guide, action plan, and service configs all reinforce each other.
- The repo already captures enough real-world detail to become a strong source of truth.

## Key Risks and Mismatches

### 1. Secrets in Repository

Redis passwords are checked into version control. This is the most urgent issue.

### 2. Automation Does Not Match Live App Platform

The repo documents a systemd/Caddy/Go deployment for XOTEC, but the Ansible deployment path is Docker Compose with placeholder services and placeholder credentials. As written, the automation for app servers does not appear safe to run against the live app environment.

### 3. Monitoring Deployment Is Incomplete

The monitoring stack references files and paths that are not all present, especially around blackbox exporter and some compose mount paths. The intent is solid, but the deployment artifacts are incomplete.

### 4. Backup State Is Weaker Than Some Docs Suggest

Some top-level docs read as if backups are already operational, while the detailed inventory and action plan say they are not. The latter appears to be the more accurate description.

### 5. Health Checks and Update Logic Need Alignment

Some update playbooks validate services using ports or endpoints that do not match the checked-in configs. That increases the chance of false failures or risky maintenance runs.

## Overall Assessment

This is a strong infrastructure design with a good real-world operating model, especially around PostgreSQL, routing, and the XOTEC app stack. The repo already functions well as documentation and environment capture.

The next maturity step is not redesign. It is alignment:

1. remove secrets from the repo and rotate exposed credentials
2. decide whether this repo is primarily documentation or executable infrastructure-as-code
3. bring Ansible automation in line with the real XOTEC deployment model
4. finish backup implementation
5. complete or simplify monitoring so declared components match deployed ones

## Recommended Next Priorities

1. Rotate the exposed Redis credentials and scrub them from version control history if appropriate.
2. Freeze or label the current Docker-based app automation as non-production until it matches the live systemd/Caddy deployment.
3. Implement and verify backups for PostgreSQL and Redis before expanding DR claims.
4. Reconcile monitoring definitions with what is actually installed and scraped.
5. Use `re-node-02` deliberately as either standby app capacity, staging, or a future HA role.
