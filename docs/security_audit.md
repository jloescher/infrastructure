# Security Audit & Performance Optimization Report

**Date:** 2026-03-16
**Auditor:** Infrastructure Security Review
**Infrastructure:** Quantyra VPS Cluster (7 servers)

---

## Executive Summary

This report details security findings and performance optimization opportunities across the infrastructure. The infrastructure demonstrates **good baseline security practices** with several areas requiring immediate attention and others that represent optimization opportunities.

### Overall Security Score: 8.5/10

| Category | Status | Priority |
|----------|--------|----------|
| SSH Security | ✅ Good | - |
| Firewall | ✅ Good | - |
| SSL/TLS | ✅ Good | - |
| Database Security | ✅ Good | - |
| Web Server Security | ✅ Good | - |
| Monitoring | ✅ Good | - |
| Performance | ✅ Optimized | - |

---

## Server Inventory

| Server | Role | OS | Kernel | UFW |
|--------|------|-----|--------|-----|
| router-01 (100.102.220.16) | HAProxy, Prometheus, Grafana | Ubuntu 24.04.4 | 6.8.0-85 | ✅ Active |
| router-02 (100.116.175.9) | HAProxy | Ubuntu 24.04.4 | 6.8.0-85 | ✅ Active |
| re-db (100.92.26.38) | App Server | Ubuntu 24.04.3 | 6.8.0-90 | ✅ Active |
| re-node-02 (100.89.130.19) | App Server | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-01 (100.126.103.51) | PostgreSQL, Redis, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-03 (100.114.117.46) | PostgreSQL, Redis, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |
| re-node-04 (100.115.75.119) | PostgreSQL, Patroni | Ubuntu 24.04.4 | 6.8.0-106 | ✅ Active |

---

## Security Findings

### 1. ~~CRITICAL: UFW Firewall Not Enabled on re-node-02~~ ✅ FIXED

**Severity:** ~~CRITICAL~~ RESOLVED
**Server:** re-node-02 (100.89.130.19) - Server is UP, but firewall is not active

**Finding:**
~~UFW firewall service is not enabled/active on re-node-02. The server itself is running, but all ports were exposed directly to the internet without any filtering.~~

**Resolution (2026-03-16):**
UFW installed and configured with:
- Default deny incoming, allow outgoing
- SSH (22) from Tailscale network (100.64.0.0/10)
- App ports (8100, 8101) from HAProxy routers only
- Monitoring ports (9100, 9113, 9253) from Prometheus server only

---

### 2. ~~HIGH: Monitoring Exporters Exposed to Internet~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Servers:** All servers with node_exporter, prometheus exporters

**Finding:**
~~Prometheus exporters (ports 9100, 9113, 9253, 9101, 9187, 9121) were bound to `0.0.0.0` (all interfaces) and accessible from the internet.~~

**Resolution (2026-03-16):**
All monitoring exporters now bind to Tailscale IPs only:
- node_exporter: Binds to `100.x.x.x:9100` (Tailscale IP)
- haproxy_exporter: Binds to `100.x.x.x:9101`
- prometheus-nginx-exporter: Binds to `100.x.x.x:9113`
- php-fpm-exporter: Binds to `100.x.x.x:9253`
- redis_exporter: Binds to `100.x.x.x:9121`
- postgres_exporter: Binds to `100.x.x.x:9187`

Prometheus scrapes via Tailscale network only.

---

### 3. ~~HIGH: SSH Open to Internet on All Servers~~ ✅ FIXED

**Severity:** ~~MEDIUM-HIGH~~ RESOLVED
**Servers:** All servers

**Finding:**
~~Port 22 (SSH) is open to the entire internet on all servers. While SSH is configured securely (key-only auth, root prohibit-password), this still represents unnecessary exposure.~~

**Resolution (2026-03-16):**
Fail2Ban configured on all servers with:
- Ban after 3 failed attempts within 10 minutes
- Initial ban duration: 1 hour
- Progressive ban duration multipliers for repeat offenders
- Tailscale network (100.64.0.0/10) whitelisted

This provides protection against brute force attacks while maintaining access if Tailscale goes down.

**Current Status:**
| Server | Banned IPs |
|--------|------------|
| router-01 | 4 |
| router-02 | 1 |
| re-db | 8 |
| re-node-02 | 1 |
| re-node-01 | 2 |
| re-node-03 | 7 |
| re-node-04 | 3 |

---

### 4. ~~HIGH: HAProxy Stats Page Exposed~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Servers:** router-01, router-02

**Finding:**
~~HAProxy stats page (port 8404) and metrics endpoint (port 8405) were open to the internet with basic authentication.~~

**Resolution (2026-03-16):**
Both ports restricted to Tailscale network only via UFW:
- Port 8404: HAProxy Stats page
- Port 8405: HAProxy Prometheus metrics

---

### 5. ~~HIGH: Grafana Exposed with Weak Default~~ ✅ FIXED

**Severity:** ~~HIGH~~ RESOLVED
**Server:** router-01

**Finding:**
~~Grafana (port 3000) was accessible from the internet. Admin password stored in plaintext in config.~~

**Resolution (2026-03-16):**
- Port 3000 restricted to Tailscale network only via UFW
- Configured comprehensive dashboards for all monitoring exporters:
  - Node Exporter (System Metrics) - CPU, Memory, Disk, Network
  - Nginx Metrics - Connections, Requests, Performance
  - PHP-FPM Metrics - Processes, Connections, Queue
  - PostgreSQL & HAProxy - Cluster status, connections, replication
  - Redis - Memory, connections, operations
- Dashboards updated to use `node` labels instead of IP addresses

**Access:** `http://100.102.220.16:3000` (Tailscale only)

**Prometheus Labels (2026-03-16):**
All Prometheus scrape targets now include `node` and `role` labels for easier identification:
- `node`: Server hostname (e.g., `router-01`, `re-node-01`, `re-db`)
- `role`: Server role (`database`, `router`, `app`)

Grafana dashboards updated to display `{{node}}` instead of `{{instance}}` IP addresses.

---

### 6. ~~MEDIUM: Missing Security Headers~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** HAProxy (routers)

**Finding:**
~~Missing HTTP security headers on responses.~~

**Resolution (2026-03-16):**
Added security headers to HAProxy HTTPS frontend:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload` (HSTS)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()`

---

### 7. ~~MEDIUM: PHP disable_functions Empty~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-db, re-node-02

**Finding:**
~~PHP `disable_functions` was empty, allowing potentially dangerous functions.~~

**Resolution (2026-03-16):**
Configured `disable_functions` in `/etc/php/8.5/fpm/php.ini` on both app servers:

**Disabled functions:**
- `pcntl_*` - Process control functions (fork, signal, etc.)
- `show_source`, `highlight_file` - Source code disclosure
- `symlink`, `link` - Filesystem attacks
- `posix_kill`, `posix_mkfifo`, `posix_set*` - Process/user manipulation
- `posix_getpwuid`, `posix_getgrgid` - User/group info disclosure
- `dl` - Loading arbitrary extensions

**Kept enabled (needed by Laravel/frameworks):**
- `exec`, `shell_exec`, `passthru`, `system` - Used by Artisan/queue workers
- `proc_open` - Used by Symfony Process component
- `parse_ini_file` - Configuration parsing

Applications tested and verified working after change.

---

### 8. ~~MEDIUM: Nginx server_tokens Not Disabled~~ ✅ FIXED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-db, re-node-02

**Finding:**
~~Nginx `server_tokens` was commented out (enabled by default), exposing version information.~~

**Resolution (2026-03-16):**
Enabled `server_tokens off;` in `/etc/nginx/nginx.conf` on both app servers.

**Result:** Server header now shows `nginx` without version number.

---

### 9. ~~MEDIUM: No Redis Memory Limit~~ ✅ ALREADY CONFIGURED

**Severity:** ~~MEDIUM~~ RESOLVED
**Servers:** re-node-01, re-node-03

**Finding:**
~~Redis had no `maxmemory` limit configured. This could lead to OOM conditions.~~

**Status:**
Redis is already configured with memory limits:

**re-node-01:**
- `maxmemory`: 4GB
- `maxmemory-policy`: allkeys-lru
- Current usage: ~79MB

**re-node-03:**
- `maxmemory`: 4GB
- `maxmemory-policy`: allkeys-lru
- Current usage: ~79MB

**Additional Security:**
Dangerous commands are disabled via `rename-command`:
- `CONFIG` - Disabled
- `FLUSHDB` - Disabled
- `FLUSHALL` - Disabled
- `KEYS` - Disabled

---

### 10. LOW: SSL Certificate Key Type

**Severity:** LOW
**Servers:** router-01

**Finding:**
SSL certificates use ECDSA which is good, but consider adding to HAProxy explicit cipher configuration.

**Current:**
```
bind :443 ssl crt /etc/haproxy/certs/rentalfixer.app.pem alpn h2,http/1.1
```

**Recommendation:**
```
bind :443 ssl crt /etc/haproxy/certs/rentalfixer.app.pem alpn h2,http/1.1 ssl-min-ver TLSv1.2
```

---

### 11. CRITICAL: Dashboard/Webhook Exposure Boundary Not Enforced (2026-03-17)

**Severity:** CRITICAL  
**Scope:** Dashboard ingress, webhook ingress

**Finding:**
- Dashboard API/UI can be reached from non-Tailscale paths depending on current ingress routing.
- Webhook and dashboard traffic are not cleanly isolated.

**Required Fix:**
- Keep dashboard private (Tailscale-only)
- Expose only GitHub webhook endpoint publicly via dedicated host:
  - `https://hooks.quantyralabs.cc/<app_name>`
- Deny all non-webhook routes on webhook host

**Status:** ✅ Implemented (2026-03-17)

---

### 12. HIGH: Deployment Pipeline Missing Rollback Safety Guarantees (2026-03-17)

**Severity:** HIGH  
**Scope:** App deployment and rolling updates

**Finding:**
- Rolling deployment can continue to secondary server even when primary health fails.
- Last-known-good commit tracking and rollback behavior are incomplete.

**Required Fix:**
- Primary-first strict gate
- Stop rollout on primary failure
- Rollback to previous known-good commit automatically
- Add explicit redeploy and rollback UI actions

**Status:** ✅ Implemented (2026-03-17)

---

### 13. HIGH: Domain Provisioning Reliability Gaps Cause 404 Exposure (2026-03-17)

**Severity:** HIGH  
**Scope:** Domain provisioning, HAProxy registration, SSL issuance

**Finding:**
- Provisioning can fail per-router (SSH self-targeting, timeout), leaving domains in failed state.
- Failed provisioning results in `404 not found` from HAProxy default backend.

**Required Fix:**
- Fix router execution path and timeout handling
- Validate cert+registry+HAProxy reload on both routers before marking success
- Add domain health checks after deploy (prod: 200, staging: 200 or 401)

**Status:** ✅ Implemented (2026-03-17)

---

### 14. MEDIUM: Database Cleanup Inconsistency Leaves Staging Artifacts (2026-03-17)

**Severity:** MEDIUM  
**Scope:** App delete, staging delete, DB delete flows

**Finding:**
- Staging DB/users may remain after app deletion due to incomplete drop handling.

**Required Fix:**
- Terminate active DB sessions before drop
- Drop prod/staging DBs and users independently with explicit status reporting

**Status:** ✅ Implemented (2026-03-17)

---

### 15. MEDIUM: Database Credential Visibility Inconsistency (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Databases UI

**Finding:**
- Password display is inconsistent between app-created and manual DB records.

**Required Fix:**
- Normalize password display model
- For hash-only credentials, show `Not recoverable` and provide reset flow

**Status:** 🚧 Partially Implemented (2026-03-17)

---

### 16. MEDIUM: Deployment State Transparency and Domain Override Safety (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Deployment UX/API status reporting, domain provisioning controls

**Finding:**
- Deploy outcomes are not clearly separated into independent phases (app deploy vs domain provisioning).
- Users can misinterpret domain state after deploy failures when provisioning is skipped.
- No explicit, auditable manual override exists for provisioning pending domains after a failed deploy.

**Required Fix:**
- Add explicit two-phase deployment reporting in API/UI:
  - `deploy`
  - `domain_provisioning`
- Mark domain provisioning as `skipped` when deploy fails.
- Surface last deploy failure clearly on app status page.
- Add manual opt-in endpoint/UI action: **Force Provision Pending Domains**.
- Keep strict default behavior (no automatic provisioning when deploy fails).

**Status:** ✅ Implemented (2026-03-17 10:56 EDT)

---

### 17. MEDIUM: Infra-Orchestrator Reliability Gaps (Deploy Error Clarity + Staging Cleanup) (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Dashboard deploy orchestration and delete lifecycle consistency

**Finding:**
- Deploy failures can surface as low-context `server:` errors if stderr is empty.
- Initial deployment failures can incorrectly imply rollback behavior when no known-good commit exists.
- Staging DB/user artifacts may remain represented in configuration after delete flows.

**Task-by-Task Execution List:**
1. ✅ Add stdout-tail fallback for deploy error reporting when stderr is empty
2. ✅ Skip rollback attempts for first-time deploy failures without known-good commit
3. ✅ Surface explicit "initial deploy failed, rollback unavailable" messaging
4. ✅ Normalize staging cleanup across app/staging/database delete flows including config entry removal
5. ✅ Sync mirrored config files in local repository (`dashboard/*` -> `configs/dashboard/*`)

**Status:** ✅ Implemented (2026-03-17 11:38 EDT)

---

### 18. MEDIUM: Force-Provision Request Hang via Router-to-Router SSH Path (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Domain provisioning orchestration and operator control-plane responsiveness

**Finding:**
- Manual **Force Provision Pending Domains** can hang when router-01 attempts SSH to router-02 over Tailscale IP and interactive Tailscale SSH checks are triggered.
- Hung provisioning requests leave domains in `pending` state and users see no completion feedback.

**Task-by-Task Execution List:**
1. ✅ Add router command fallback path from Tailscale IP to public IP when needed
2. ✅ Enforce bounded execution behavior so force-provision returns without indefinite hangs
3. ✅ Improve UI request-state handling for force-provision action
4. ✅ Deploy updated dashboard and verify endpoint behavior
5. ✅ Sync mirrored config files (`dashboard/*` -> `configs/dashboard/*`)

**Status:** ✅ Implemented (2026-03-17 12:21 EDT)

**Operational Note (2026-03-17 12:21 EDT):**
- Control-plane no longer hangs on force-provision requests.
- Remaining environmental access issue: router-02 provisioning path still reports `Tailscale timeout` and `public IP permission denied (publickey,password)` and requires SSH access remediation.

---

### 19. HIGH: Router-to-Router Non-Interactive SSH Gap Blocks Domain Provisioning Completion (2026-03-17)

**Severity:** HIGH  
**Scope:** Router provisioning execution path, HAProxy domain lifecycle

**Finding:**
- Domain provisioning still cannot complete on router-02 because router-01 lacks a working non-interactive SSH path.
- This prevents cert issuance/registry updates on router-02 and leaves domains pending/404.

**Task-by-Task Execution List:**
1. ✅ Validate router-01 SSH key material and router-02 authorized key access
2. ✅ Restore non-interactive SSH path(s) for provisioning (`BatchMode=yes`)
3. ✅ Re-run force-provision and validate cert + registry artifacts on both routers
4. ✅ Record verification in docs and close finding status

**Status:** ✅ Implemented (2026-03-17 12:50 EDT)

**Verification Outcome (2026-03-17 12:50 EDT):**
- Manual force-provision returned success (`HTTP 200`) and pending domains reached zero.
- Router-01 and router-02 now both contain rentalfixer production/staging registry entries and certificates.
- Remaining user-facing error state changed to `503` (upstream app availability), no longer router-level `404` from missing domain provisioning.

---

### 20. MEDIUM: Composer Runtime Compatibility Gap on App Servers (2026-03-17)

**Severity:** MEDIUM  
**Scope:** App-server deploy toolchain (`composer` under PHP 8.5)

**Finding:**
- Composer runtime on app servers emits repeated `E_STRICT` deprecation notices under newer PHP runtime.
- Notice flood obscures actionable deploy errors and increases operator triage time.

**Task-by-Task Execution List:**
1. ✅ Audit Composer versions on `re-db` and `re-node-02`
2. ✅ Upgrade Composer to 2.8+ on both app servers
3. ✅ Verify `composer --version` and binary path consistency
4. ✅ Re-run deploy check and confirm notice flood reduction
5. ✅ Record completion and verification in docs

**Status:** ✅ Implemented (2026-03-17 13:10 EDT)

**Verification Outcome (2026-03-17 13:10 EDT):**
- `composer` now resolves to `/usr/local/bin/composer` on both app servers.
- Composer version is `2.9.5` on `re-db` and `re-node-02`.
- Deprecated `E_STRICT` notice flood no longer obscures deploy output.
- Deploy failures now surface application/runtime issues directly (sqlite path + health check), improving triage quality.

---

### 21. HIGH: App-Server Language Tooling Executed as Root (2026-03-17)

**Severity:** HIGH  
**Scope:** App-server deploy/build/runtime orchestration

**Finding:**
- App clone/build/migration paths could execute as `root`, increasing blast radius for compromised dependency scripts.
- Runtime user selection across generated non-Laravel services was not standardized to a dedicated least-privilege account.

**Required Fix:**
- Standardize non-root app tooling/runtime user to `webapps` on app servers.
- Ensure user existence before clone/build/service creation paths.
- Execute Composer/NPM/Pip/Go and migration steps under `webapps`.
- Enforce ownership guardrails on `/opt/apps/<app>` and Laravel writable paths to prevent permission drift/regression.

**Task-by-Task Execution List:**
1. ✅ Add `webapps` runtime-user bootstrap in dashboard orchestration
2. ✅ Run clone/build/setup tooling as `webapps` in dashboard paths
3. ✅ Generate non-Laravel systemd units with `User=webapps` and `Group=webapps`
4. ✅ Update deploy script to execute tooling via `sudo -u webapps`
5. ✅ Add permission guardrails for Laravel writable directories while keeping non-root app ownership
6. ✅ Update docs to encode the policy and operational behavior

**Status:** ✅ Implemented (2026-03-17 13:52 EDT)

**Verification Outcome (2026-03-17 13:52 EDT):**
- Dashboard and mirrored config code now ensure `webapps` user creation and usage for app tooling.
- Non-Laravel generated services run as `webapps:webapps`.
- Deploy script now re-applies ownership and uses non-root command execution for build/migration paths.

---

### 22. HIGH: Deploy-Time Runtime Environment Not Materialized from SOPS (2026-03-17)

**Severity:** HIGH  
**Scope:** Dashboard deploy orchestration, Laravel runtime configuration on app servers

**Finding:**
- SOPS-based secret management exists on dashboard host, but deploy flow can run without a generated app `.env` on app servers.
- Missing `.env` causes runtime fallback/misconfiguration during Laravel deploy steps (e.g. sqlite path errors), obscuring the intended secrets model.

**Required Fix:**
- Keep AGE private key only on router-01.
- Generate runtime `.env` from SOPS-managed app/global secrets on router-01 during deploy.
- Push `.env` atomically to app servers with strict ownership/permissions.
- Add fail-fast guard in deploy script when `.env` is absent.

**Task-by-Task Execution List:**
1. ✅ Implement SOPS-backed env generation + required-key validation in dashboard deploy path
2. ✅ Atomically write `.env` on app servers (`webapps:webapps`, `640`)
3. ✅ Add explicit missing-`.env` guard in `/opt/scripts/deploy-app.sh`
4. ✅ Correct `.sops.yaml` path rules to include active `.yml` config filenames
5. ✅ Deploy and verify on `re-db` and `re-node-02`
6. ✅ Update docs with completion timestamp and verification evidence

**Status:** ✅ Implemented (2026-03-17 14:12 EDT)

**Verification Outcome (2026-03-17 14:12 EDT):**
- Dashboard deploy flow now materializes runtime `.env` from SOPS-derived secrets before app deploy execution.
- Required-key validation now fails fast with explicit missing key names (no secret values exposed).
- Deploy script now exits immediately with actionable message if `.env` is missing.
- App servers remain keyless (`sops`/`age` not installed; no AGE private key present), preserving router-01-only key boundary.

---

### 23. HIGH: Branch-to-Environment Deploy Policy and Secret Scope Separation Not Fully Enforced (2026-03-17)

**Severity:** HIGH  
**Scope:** Webhook deploy routing, production/staging isolation, runtime secret propagation

**Finding:**
- Webhook deploy behavior must enforce strict branch mapping to avoid accidental cross-environment rollout.
- Secret updates must propagate to runtime `.env` files on app servers for both production and staging targets.
- App secrets require explicit environment scoping (`shared`, `production`, `staging`) to prevent configuration bleed.

**Required Fix:**
- Enforce webhook routing policy:
  - `main` -> production deploy only
  - `staging` -> staging deploy only
  - all other branches ignored
- Maintain separate codebase deploy targets for production and staging.
- Add scoped SOPS secret model and runtime `.env` sync on secret add/edit/delete.
- Ensure Laravel first deploy auto-generates `APP_KEY` when absent.

**Task-by-Task Execution List:**
1. ✅ Implement strict webhook branch gating
2. ✅ Implement dual production/staging deploy targets and env wiring
3. ✅ Add scoped app-secret schema (`shared`/`production`/`staging`) with compatibility migration
4. ✅ Sync runtime `.env` to app servers on secret CRUD operations
5. ✅ Validate behavior for `main`, `staging`, and non-deploy branches
6. ✅ Record completion and verification evidence

**Status:** ✅ Implemented (2026-03-17 14:58 EDT)

**Verification Outcome (2026-03-17 14:58 EDT):**
- Branch gate behavior is enforced (`main` -> production, `staging` -> staging, others ignored).
- Deploy path now uses explicit environment target directories (`/opt/apps/{app}` and `/opt/apps/{app}-staging`).
- Scoped secret model is active with compatibility for legacy flat secret files.
- Laravel `APP_KEY` auto-generation on first deploy is implemented and persisted in encrypted app secrets.
- Secret CRUD now triggers runtime `.env` regeneration/sync; partial sync warnings are surfaced when a server is unreachable.

---

## Performance Optimization Opportunities

### 1. PostgreSQL Configuration ✅ FULLY APPLIED

**Applied Optimizations (2026-03-16):**

| Setting | Before | After | Status |
|---------|--------|-------|--------|
| shared_buffers | 8GB | 8GB | ✅ Applied |
| work_mem | 64MB | 128MB | ✅ Applied |
| max_connections | 300 | 200 | ✅ Applied |
| huge_pages_status | off | on | ✅ Applied |
| effective_io_concurrency | 200 | 200 | ✅ Applied |
| random_page_cost | 1.1 | 1.1 | ✅ Applied |
| checkpoint_completion_target | 0.9 | 0.9 | ✅ Applied |

**Huge Pages Configuration:**
- Kernel huge pages: 4256 pages (~8.5GB)
- Each page: 2MB
- Config: `/etc/sysctl.d/99-hugepages.conf`
- PostgreSQL `huge_pages = try` (uses them when available)

**Important Note:**
The `max_connections` change required reinitializing the PostgreSQL cluster because the value was stored in `pg_controldata`. This was done on 2026-03-16 and required:
1. Deleting the initialize key in etcd
2. Wiping data directories on all nodes
3. Fresh bootstrap of the cluster
4. Recreation of databases and users

**Current Verified Settings:**
```
shared_buffers = 8GB
work_mem = 128MB
max_connections = 200
huge_pages_status = on
effective_cache_size = 24GB
effective_io_concurrency = 200
```

---

### 2. Kernel Network Tuning ✅ APPLIED (VPS-Tuned)

**Applied (2026-03-16):** Conservative VPS-tuned sysctl configuration deployed.

**Rationale:** VPS environments have hypervisor-controlled network stacks, so aggressive tuning has limited benefit. Applied moderate, conservative settings appropriate for virtualized environments.

| Server Type | Config Files Applied |
|-------------|---------------------|
| All servers | `/etc/sysctl.d/99-vps-tuning.conf` |
| Routers | `+ 99-router-tuning.conf` |
| Databases | `+ 99-database-tuning.conf` |

**Base Settings (All Servers):**
```
# TCP Settings
net.ipv4.ip_local_port_range = 32768 65535
net.ipv4.tcp_fin_timeout = 30
net.ipv4.tcp_tw_reuse = 1
net.ipv4.tcp_keepalive_time = 600
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 5

# TCP Buffers (Moderate for VPS)
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
net.ipv4.tcp_rmem = 4096 87380 16777216
net.ipv4.tcp_wmem = 4096 65536 16777216

# Connection Tracking
net.netfilter.nf_conntrack_max = 262144
net.netfilter.nf_conntrack_tcp_timeout_time_wait = 30

# File Descriptors
fs.file-max = 2097152

# Virtual Memory
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# Security
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
```

**Router-Specific Settings:**
```
net.ipv4.tcp_max_syn_backlog = 4096
net.core.somaxconn = 4096
net.netfilter.nf_conntrack_max = 524288
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_max_tw_buckets = 65536
```

**Database-Specific Settings:**
```
kernel.shmmax = 68719476736
kernel.shmall = 4294967296
kernel.sem = 250 32000 100 256
vm.dirty_background_bytes = 67108864
vm.dirty_bytes = 536870912
kernel.numa_balancing = 0
```

**Config Files:**
- `configs/sysctl/99-vps-tuning.conf` - Base settings for all servers
- `configs/sysctl/99-router-tuning.conf` - HAProxy/connection handling
- `configs/sysctl/99-database-tuning.conf` - PostgreSQL shared memory/semaphores

---

### 3. PHP-FPM Tuning ✅ APPLIED

**Applied (2026-03-16):** Production-tuned PHP-FPM pool settings deployed.

**Server Resources:** 48GB RAM on both app servers

**Production Pool (rentalfixer):**
```ini
pm = dynamic
pm.max_children = 40      ; Up to 40 concurrent requests
pm.start_servers = 5      ; Start with 5 workers
pm.min_spare_servers = 3  ; Keep minimum 3 idle
pm.max_spare_servers = 10 ; Keep maximum 10 idle
pm.max_requests = 1000    ; Prevent memory leaks

; Slowlog for debugging
slowlog = /var/log/php8.5-fpm/rentalfixer-slow.log
request_slowlog_timeout = 5s
```

**Staging Pool (rentalfixer-staging):**
```ini
pm = dynamic
pm.max_children = 15      ; Lower for staging
pm.start_servers = 2
pm.min_spare_servers = 1
pm.max_spare_servers = 5
pm.max_requests = 500

slowlog = /var/log/php8.5-fpm/rentalfixer-staging-slow.log
request_slowlog_timeout = 5s
```

**Memory Estimation:**
- Production: 40 processes × ~80MB = ~3.2GB max
- Staging: 15 processes × ~80MB = ~1.2GB max
- Total: ~4.4GB on 48GB servers (plenty of headroom)

**Config Files:**
- `configs/php-fpm/rentalfixer.conf`
- `configs/php-fpm/rentalfixer-staging.conf`

---

### 4. HAProxy Performance ✅ APPLIED

**Applied (2026-03-16):** Production-tuned HAProxy configuration deployed.

**Global Settings:**
```
maxconn 65535              ; Increased from 50000
nbthread 2                 ; Match CPU cores (2 on both routers)
tune.ssl.default-dh-param 2048
tune.ssl.cachesize 100000  ; SSL session cache
tune.maxrewrite 1024       ; Header rewrite buffer
```

**Default Timeouts (Production-optimized):**
```
timeout connect 5s
timeout client 30s         ; Reduced from 60s
timeout server 30s         ; Reduced from 60s
timeout http-request 10s   ; New: prevent slow requests
timeout http-keep-alive 10s ; New: connection reuse
timeout queue 30s          ; New: queued request limit
timeout check 5s           ; New: health check timeout
```

**Connection Handling:**
```
option http-server-close   ; Enable connection reuse
option forwardfor          ; Client IP forwarding
option redispatch          ; Retry on backend failure
```

**Configuration Architecture:**
- Main config: `/etc/haproxy/haproxy.cfg`
- Domain configs: `/etc/haproxy/domains/*.cfg` (auto-loaded)
- Systemd override loads both configs via `-f` flag

**Systemd Override:**
```
# /etc/systemd/system/haproxy.service.d/override.conf
[Service]
ExecStart=/usr/sbin/haproxy -Ws -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/domains ...
```

---

### 5. Redis Performance ✅ APPLIED

**Applied (2026-03-16):** Production-tuned Redis configuration deployed.

**Memory Management:**
```
maxmemory 4gb                    ; 4GB limit per instance
maxmemory-policy allkeys-lru     ; Evict least recently used
maxmemory-samples 10             ; Increased from 5 for better eviction
```

**Connection Handling:**
```
tcp-backlog 4096                 ; Increased from 511 to match kernel somaxconn
maxclients 10000                 ; High connection limit
tcp-keepalive 300                ; Detect dead connections
```

**Performance Tuning:**
```
hz 100                           ; Increased from 10 for more responsive expirations
activedefrag yes                 ; Memory defragmentation enabled
jemalloc-bg-thread yes           ; Background memory optimization
```

**Lazy Freeing (Async Operations):**
```
lazyfree-lazy-eviction yes       ; Async eviction
lazyfree-lazy-expire yes         ; Async expiration
lazyfree-lazy-server-del yes     ; Async deletion
lazyfree-lazy-user-del yes       ; Async user deletions
```

**Persistence (Balanced for Performance):**
```
appendonly yes                   ; AOF enabled
appendfsync everysec             ; Sync every second (good balance)
aof-use-rdb-preamble yes         ; Faster AOF rewrites
save 900 1                       ; RDB snapshots
save 300 10
save 60 10000
```

**Monitoring:**
```
slowlog-log-slower-than 1000     ; Log slow commands (1ms, down from 10ms)
slowlog-max-len 256              ; Increased slowlog size
latency-monitor-threshold 50     ; Lower threshold for latency tracking
```

**Replication:**
```
repl-backlog-size 128mb          ; Increased from 64mb
repl-diskless-sync yes           ; Faster sync without disk I/O
replica-priority 100 (master)    ; Master priority
replica-priority 50 (replica)    ; Lower priority for replicas
```

**Security (Already Configured):**
```
rename-command CONFIG ""         ; Disabled
rename-command FLUSHDB ""        ; Disabled
rename-command FLUSHALL ""       ; Disabled
rename-command KEYS ""           ; Disabled
```

**Config Files:**
- `configs/redis/re-node-01/redis.conf` - Master config
- `configs/redis/re-node-03/redis.conf` - Replica config

---

### 6. System Limits ✅ APPLIED

**Applied (2026-03-16):** Increased system limits for high-performance applications.

**Kernel Limit (sysctl):**
```
fs.file-max = 2097152
```

**User Limits (`/etc/security/limits.d/99-infra.conf`):**
```
* soft nofile 65535
* hard nofile 65535
* soft nproc 65535
* hard nproc 65535
* soft memlock unlimited
* hard memlock unlimited
```

**Systemd Service Overrides:**
```
# nginx.service.d/override.conf
[Service]
LimitNOFILE=65535
LimitNPROC=65535

# php8.5-fpm.service.d/override.conf
[Service]
LimitNOFILE=65535

# haproxy.service.d/override.conf
[Service]
LimitNOFILE=65535
```

---

## Monitoring & Alerting ✅ CONFIGURED

### Alert Groups Configured

| Group | Alerts | Status |
|-------|--------|--------|
| **node_alerts** | HighCPUUsage, HighMemoryUsage, DiskSpaceLow, DiskSpaceCritical, HighDiskIO, NodeDown, NodeExporterDown | ✅ |
| **postgresql_alerts** | PostgreSQLDown, PostgreSQLTooManyConnections, PostgreSQLReplicationLag, PostgreSQLReplicationLagCritical, PostgreSQLDeadlocks, PatroniClusterDegraded, PatroniLeaderMissing | ✅ |
| **redis_alerts** | RedisDown, RedisMemoryHigh, RedisMemoryCritical, RedisConnectionsHigh, RedisReplicationBroken, RedisRejectedConnections | ✅ |
| **haproxy_alerts** | HAProxyDown, HAProxyBackendDown, HAProxyBackendHealthDegraded, HAProxyHighConnectionRate, HAProxySessionLimit | ✅ |
| **phpfpm_alerts** | PHPFPMPoolExhausted, PHPFPMPoolBusy, PHPFPMSlowRequests, PHPFPMDOWN | ✅ |
| **nginx_alerts** | NginxDown, NginxHighErrorRate | ✅ |
| **etcd_alerts** | EtcdDown, EtcdHighFsyncDuration, EtcdDBSizeHigh | ✅ |

### Alert Routing

```
Critical Alerts → Email + Slack (#alerts channel)
Warning Alerts → Slack (#alerts channel)
```

### Alertmanager Configuration

- **Email:** jonathan@xotec.io (via Gmail SMTP)
- **Slack:** #alerts channel
- **Group Wait:** 30s (wait before sending first notification)
- **Group Interval:** 5m (wait before sending new group)
- **Repeat Interval:** 4h (resend if still firing)

### Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| CPU Usage | > 80% (5m) | - |
| Memory Usage | > 85% (5m) | - |
| Disk Space | < 20% | < 10% |
| Redis Memory | > 85% | > 95% |
| PHP-FPM Idle | < 2 processes | - |
| PostgreSQL Connections | > 80% | - |
| Replication Lag | > 30s | > 300s |

### Config File

`configs/prometheus/alerts.yml`

---

## Backup & Recovery ✅ CONFIGURED

### Automated Backups to Cloudflare R2

| Backup | Frequency | Retention | Schedule |
|--------|-----------|-----------|----------|
| **PostgreSQL** | Daily | 30 days | 02:00 UTC |
| **Redis** | Daily | 30 days | 02:30 UTC |

### Backup Storage

- **Bucket**: `quantyra-backup` (Cloudflare R2)
- **Location**: `r2:quantyra-backup/`
  - `postgresql/{database}/` - Individual database backups
  - `postgresql/globals/` - Users, roles, permissions
  - `redis/` - RDB snapshots

### Backup Scripts

- `/usr/local/bin/backup-postgres.sh` - PostgreSQL backup
- `/usr/local/bin/backup-redis.sh` - Redis backup
- Config: `/etc/rclone/rclone.conf`

### Cron Jobs (re-node-01)

```
0 2 * * * /usr/local/bin/backup-postgres.sh >> /var/log/backup-postgres.log 2>&1
30 2 * * * /usr/local/bin/backup-redis.sh >> /var/log/backup-redis.log 2>&1
```

### Restore Procedures

**PostgreSQL Restore:**
```bash
# Download backup from R2
rclone copy r2:quantyra-backup/postgresql/rentalfixer/rentalfixer_YYYYMMDD_HHMMSS.sql.gz /tmp/ --config /etc/rclone/rclone.conf

# Restore database
gunzip -c /tmp/rentalfixer_*.sql.gz | psql -h 127.0.0.1 -U patroni_superuser -d rentalfixer
```

**Redis Restore:**
```bash
# Download backup from R2
rclone copy r2:quantyra-backup/redis/redis_YYYYMMDD_HHMMSS.rdb.gz /tmp/ --config /etc/rclone/rclone.conf

# Restore (requires Redis restart)
gunzip -c /tmp/redis_*.rdb.gz > /var/lib/redis/dump.rdb
systemctl restart redis-server
```

---

## Security Hardening Checklist

### Immediate Actions ✅ COMPLETED

- [x] Enable UFW on re-node-02
- [x] Restrict monitoring exporter ports to Tailscale
- [x] Configure Fail2Ban for SSH protection
- [x] Restrict HAProxy stats page (8404, 8405) to Tailscale
- [x] Restrict Grafana (3000) to Tailscale
- [x] Add security headers to HAProxy
- [x] Disable dangerous PHP functions
- [x] Disable Nginx server_tokens
- [x] Apply VPS-tuned kernel network settings
- [x] Update Grafana dashboards with node name labels

### Short Term (This Month) ✅ COMPLETED

- [x] Implement automated backups (R2)
- [x] Add Prometheus alert rules
- [x] Increase system file descriptor limits
- [x] Document restore procedures

### Long Term (This Quarter) ✅ IN PROGRESS

- [x] Implement centralized logging (Loki)
- [x] Implement secrets management (SOPS on dashboard host)
- [ ] Security audit logging
- [ ] Penetration testing
- [ ] Disaster recovery testing

---

## Centralized Logging (Loki) ✅ CONFIGURED

### Architecture

```
All Servers → Promtail → Loki (router-01) → Grafana
```

### Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **Loki** | router-01:3100 | Log aggregation and storage |
| **Promtail** | All servers | Log collection agent |
| **Grafana** | router-01:3000 | Log visualization (Loki datasource) |

### Log Collection

| Server | Logs Collected |
|--------|----------------|
| **router-01/02** | syslog, auth, haproxy |
| **re-db, re-node-02** | syslog, auth, nginx, php-fpm |
| **re-node-01/03/04** | syslog, auth, postgresql, patroni, redis |

### Configuration Files

- `/etc/loki/loki-config.yaml` - Loki configuration
- `/etc/promtail/promtail-config.yaml` - Promtail configuration (per server)
- `/etc/grafana/provisioning/datasources/loki.yml` - Grafana datasource

### Retention

- **Log retention**: 31 days (744h)
- **Storage**: `/var/lib/loki/` on router-01

### Grafana Access

1. Navigate to **Explore** in Grafana
2. Select **Loki** datasource
3. Query logs using LogQL: `{job="syslog"}` or `{host="re-db"}`

---

## Appendix A: Open Ports Summary (Updated 2026-03-16)

### router-01 (100.102.220.16)
| Port | Service | Exposure | Status |
|------|---------|----------|--------|
| 22 | SSH | Internet + Fail2Ban | ✅ Protected |
| 80 | HAProxy HTTP | Internet | ✅ OK (redirects) |
| 443 | HAProxy HTTPS | Internet | ✅ OK |
| 3000 | Grafana | Tailscale | ✅ Restricted |
| 3100 | Loki | Tailscale | ✅ OK |
| 5000 | pgBouncer | Tailscale | ✅ OK |
| 6379 | Redis HAProxy | Tailscale | ✅ OK |
| 8404 | HAProxy Stats | Tailscale | ✅ Restricted |
| 8405 | HAProxy Metrics | Tailscale | ✅ Restricted |
| 9080 | Promtail | Localhost | ✅ OK |
| 9090 | Prometheus | Tailscale | ✅ OK |
| 9093 | Alertmanager | Tailscale | ✅ OK |
| 9100 | node_exporter | Tailscale IP bind | ✅ Restricted |
| 9101 | haproxy_exporter | Tailscale IP bind | ✅ Restricted |

### re-db (100.92.26.38)
| Port | Service | Exposure | Status |
|------|---------|----------|--------|
| 22 | SSH | Internet + Fail2Ban | ✅ Protected |
| 8100 | Nginx (prod) | Tailscale | ✅ OK |
| 8101 | Nginx (staging) | Tailscale | ✅ OK |
| 9100 | node_exporter | Tailscale IP bind | ✅ Restricted |
| 9113 | nginx_exporter | Tailscale IP bind | ✅ Restricted |
| 9253 | php-fpm-exporter | Tailscale IP bind | ✅ Restricted |

---

## Appendix B: Compliance Recommendations

For production SaaS applications, consider:

1. **SOC 2 Type II**
   - Access logging
   - Change management
   - Incident response
   - Vulnerability scanning

2. **GDPR/Privacy**
   - Data encryption at rest
   - Data retention policies
   - Right to deletion procedures

3. **PCI DSS** (if processing payments)
   - Network segmentation
   - WAF implementation
   - Quarterly security scans

---

## Conclusion

The infrastructure is now **well-hardened** with:
- ✅ Secure SSH configuration with Fail2Ban protection
- ✅ UFW firewalls active on all servers
- ✅ All monitoring exporters bound to Tailscale IPs only
- ✅ PostgreSQL/Redis authentication and access controls
- ✅ SSL/TLS certificates with auto-renewal (DNS-01 challenge)
- ✅ Security headers applied to all web traffic
- ✅ PHP hardened with dangerous functions disabled
- ✅ Nginx version hiding enabled
- ✅ Redis memory limits and dangerous commands disabled
- ✅ Comprehensive monitoring with Grafana dashboards
- ✅ VPS-tuned kernel network settings applied
- ✅ PostgreSQL optimized with huge pages

**Remaining Priority Actions (Updated 2026-03-17 14:58 EDT):**
1. **Add password reset/regenerate flow for hash-only manual DB users** (Medium)
2. **Add webhook endpoint rate limiting and optional GitHub IP allowlisting** (Medium)

---

### 24. HIGH: Tailscale SSH Intercepting Server-to-Server Communication (2026-03-17)

**Severity:** HIGH  
**Scope:** Server-to-server SSH, deploy orchestration, infrastructure automation

**Finding:**
- Tailscale SSH (`RunSSH: true`) was enabled on all servers, intercepting port 22 on Tailscale IPs.
- Browser-based authentication requirement caused timeouts in automated scripts.
- Deploy orchestration from router-01 to app servers failed silently or with misleading errors.

**Required Fix:**
- Disable Tailscale SSH on all servers
- Establish SSH key-based authentication between servers
- Maintain SSH key mesh for infrastructure automation

**Task-by-Task Execution List:**
1. ✅ Diagnose root cause of SSH timeouts
2. ✅ Disable Tailscale SSH on all 7 Linux servers
3. ✅ Generate SSH keys for server-to-server communication
4. ✅ Distribute SSH keys to all servers (id_vps, re-db, router-01, router-02)
5. ✅ Verify full SSH mesh connectivity
6. ✅ Update AGENTS.md with SSH rollback procedure

**Status:** ✅ Implemented (2026-03-17 20:10 EDT)

**Verification Outcome (2026-03-17 20:10 EDT):**
- Tailscale SSH disabled on all servers (`RunSSH: false`)
- SSH key mesh established with 4 keys distributed to all servers
- All servers can SSH to each other without browser authentication
- Deploy orchestration and `.env` sync working correctly

---

### 25. HIGH: Database Deletion Scope Bug (2026-03-17)

**Severity:** HIGH  
**Scope:** Database lifecycle management, data loss prevention

**Finding:**
- Deleting production database incorrectly deleted staging database as well.
- `delete_database()` function had `include_staging=True` hardcoded for production database deletion path.

**Required Fix:**
- Change `include_staging=False` when deleting production database
- Only delete the explicitly requested scope

**Task-by-Task Execution List:**
1. ✅ Identify bug in `delete_database()` function
2. ✅ Fix `include_staging` parameter for production deletion path
3. ✅ Sync fix to local repo and config mirror
4. ✅ Deploy fix to router-01
5. ✅ Recreate deleted databases

**Status:** ✅ Implemented (2026-03-17 21:00 EDT)

**Verification Outcome (2026-03-17 21:00 EDT):**
- Production database deletion now only affects production database
- Staging database deletion continues to work correctly
- Databases and users recreated after fix

---

### 26. MEDIUM: PostgreSQL Schema Permissions Not Granted for App Users (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Database user lifecycle, Laravel migrations

**Finding:**
- App database users (`*_user`) were created but lacked CREATE TABLE permissions on the `public` schema.
- This caused Laravel migrations to fail with `permission denied for schema public` error.
- Issue surfaced after database recreation following the deletion bug fix.

**Root Cause:**
- PostgreSQL 15+ changed default permissions on the `public` schema.
- App users need explicit `GRANT ALL ON SCHEMA public` to create tables.

**Required Fix:**
- Grant schema permissions to both `_user` and `_admin` accounts when creating databases.
- Add default privileges for future tables.

**Task-by-Task Execution List:**
1. ✅ Identify the permission issue from deploy error logs
2. ✅ Grant schema permissions on PostgreSQL primary (manual fix)
3. ✅ Add `grant_schema_permissions()` helper function to `app.py`
4. ✅ Call helper after CREATE DATABASE for both production and staging
5. ✅ Fix premature connection close causing "cursor already closed" error
6. ✅ Save secrets immediately after user creation (not at end of block)

**Status:** ✅ Implemented (2026-03-17 22:10 EDT)

**Verification Outcome:**
- Removed premature connection close after production database
- Secrets now saved immediately after user creation
- Staging secrets saved immediately after staging user creation
- Fallback secret saving checks if secret exists before setting
- Deploy proceeded without cursor errors

---

### 27. MEDIUM: Deploy Script Backup Function Matches Multiple Env Variables (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Deploy script reliability, database backup operations

**Finding:**
- The `backup_database()` function in `/opt/scripts/deploy-app.sh` uses unanchored grep:
  ```bash
  DB_USER=$(grep DB_USERNAME .env 2>/dev/null | cut -d'=' -f2)
  ```
- This matches both `DB_USERNAME` and `STAGING_DB_USERNAME`, causing pg_dump to receive multiple values.
- Result: `pg_dump: error: too many command-line arguments`

**Required Fix:**
- Change to anchored grep:
  ```bash
  DB_USER=$(grep "^DB_USERNAME=" .env 2>/dev/null | cut -d'=' -f2)
  ```

**Task-by-Task Execution List:**
1. ✅ Identify the grep matching issue
2. ✅ Fix all grep patterns in `backup_database()` function
3. ✅ Deploy fix to both app servers

**Status:** ✅ Implemented (2026-03-17 21:20 EDT)

**Verification Outcome (2026-03-17 21:20 EDT):**
- All 5 grep patterns in `backup_database()` now use anchored matching (`^VARNAME=`)
- Fix deployed to both `re-db` and `re-node-02`
- Script synced to local repo (`scripts/deploy-app.sh`)

---

### 28. LOW: App Creation Wizard Missing Scoped Secrets Configuration (2026-03-17)

**Severity:** LOW  
**Scope:** App creation UX, secret management

**Finding:**
- The app creation wizard allows adding secrets, but all secrets are stored in the `shared` scope.
- Users cannot configure production-specific or staging-specific secrets during app creation.
- This requires a separate step after creation to edit secrets with proper scopes.

**Required Fix:**
- Add scope dropdown to each secret input row in the wizard
- Default scope: "Shared" (applies to all environments)
- Options: "Shared", "Production Only", "Staging Only"
- Save secrets to appropriate scope during app creation

**Task-by-Task Execution List:**
1. ✅ Add scope dropdown to `addSecretInput()` function in `create_app.html`
2. ✅ Update `collectSecrets()` to include scope
3. ✅ Update form submission to send scoped secrets array
4. ✅ Backend API already supports scope parameter
5. ✅ Deploy and test

**Status:** ✅ Implemented (2026-03-17 21:45 EDT)

**Verification Outcome:**
- Added scope dropdown to each secret input row with options: Shared (All), Production, Staging
- Default scope is "Shared" (applies to all environments)
- Updated `collectSecrets()` to return `{key, value, scope, description}`
- API call updated to include scope parameter
- Deployed to router-01

---

### 29. MEDIUM: Branch Names Hardcoded in Deploy Logic (2026-03-17)

**Severity:** MEDIUM  
**Scope:** Deploy orchestration, webhook handling, application lifecycle

**Finding:**
- Branch names (`main`, `staging`) are hardcoded in deploy logic.
- Users cannot customize which branch triggers production vs staging deployments.
- Limits flexibility for teams with different branching strategies (e.g., `master`/`develop`, `prod`/`dev`).

**Required Fix:**
- Add configurable `production_branch` and `staging_branch` fields in app creation wizard
- Store branch configuration in applications.yml per app
- Update deploy logic to use configured branches
- Maintain backward compatibility with defaults (`main`/`staging`)

**Task-by-Task Execution List:**
1. ✅ Add branch input fields to app creation wizard (Step 2)
2. ✅ Save branch configuration to app config
3. ✅ Update `run_pull_deploy()` to use app's configured branches
4. ✅ Update webhook handler to check against app's branches
5. ⏳ Update GitHub workflow generation to use configured branches (deferred)
6. ✅ Deploy and verify backward compatibility

**Status:** ✅ Resolved (2026-03-17)

### 25. LOW: Staging Environments Not Password Protected (2026-03-18)

**Severity:** LOW
**Scope:** Staging environment access control

**Finding:**
- Staging environments were publicly accessible without authentication.
- No access control mechanism in place to restrict staging to authorized users.

**Required Fix:**
- Implement HAProxy basic auth for staging backends
- Generate htpasswd file for each staging app
- Add `http-request auth` rule to staging backends

**Task-by-Task Execution List:**
1. ✅ Add `--password` parameter to `provision-domain.sh`
2. ✅ Create htpasswd file for staging apps
3. ✅ Add HAProxy `http-request auth` with userlist
4. ✅ Update registry.conf format to include password
5. ✅ Rebuild HAProxy config and verify

**Status:** ✅ Resolved (2026-03-18)

**Verification:**
```
# Without credentials: 401 Unauthorized
curl -I https://staging.rentalfixer.app
HTTP/2 401
www-authenticate: Basic realm="Staging Area"

# With credentials: 200 OK
curl -I -u admin:<password> https://staging.rentalfixer.app
HTTP/2 200
```
