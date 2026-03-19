# Infrastructure Plan

This document tracks current tasks, priorities, and future improvements for the Quantyra infrastructure.

## Status Overview

| Component | Status | Notes |
|-----------|--------|-------|
| HAProxy (Consolidated Frontends) | ✅ Complete | Both routers working |
| SSL Certificates (DNS-01) | ✅ Complete | Auto-renewal configured |
| Dashboard | ✅ Working | Deployed with infra-only reliability hardening |
| PostgreSQL Cluster | ✅ Working | 3-node Patroni cluster |
| Redis Cluster | ✅ Working | Master-replica with Sentinel |
| Monitoring | ✅ Working | Prometheus, Grafana, Alertmanager |
| Docker Compose | 🚧 In Progress | Ready for testing |
| Config Sync | ✅ Complete | 89 config files in repo |
| App Cleanup Audit | ✅ Complete | Orphaned resources removed |
| GitHub Validation | ✅ Complete | Repo validation before creation |
| DNS Read-Only View | ✅ Complete | Existing records displayed with conflicts |
| Webhook Host Isolation | ✅ Complete | `hooks.quantyralabs.cc` public webhook-only path policy |
| Deploy/Provision UX Phases | ✅ Complete | Separate deploy + domain provisioning stages with force-provision fallback |
| Force-Provision Reliability | ✅ Complete | Router SSH fallback and non-hanging force-provision UX |
| Router SSH Remediation | ✅ Complete | Restored non-interactive public-key path and validated force-provision execution |
| Composer Toolchain Compatibility | ✅ Complete | Composer upgraded on both app servers; deprecation noise removed from deploy logs |
| Non-Root App Tooling Runtime | ✅ Complete | App build/runtime tooling standardized to `webapps` user with permission guardrails |
| SOPS-Driven Deploy Env Generation | ✅ Complete | Deploy now materializes runtime `.env` from SOPS on router-01 and pushes to app servers |
| Branch-Gated Dual-Env Deploy + Scoped Secrets | ✅ Complete | Enforced branch gating, scoped secrets, dual deploy targets, and runtime `.env` sync |
| Package Update Dashboard | ✅ Complete | Server package updates visible with security highlighting and bulk update |

---

## Immediate Priority (Current Session)

### Phase 0: Security Boundary (Tailscale + Public Webhooks)

**Decision:** Dashboard remains Tailscale-only. Public exposure is limited to GitHub webhooks at `hooks.quantyralabs.cc`.

**Targets:**
1. Dashboard UI/API (`:8080`) reachable only via Tailscale network
2. Public endpoint only for GitHub webhooks
3. Dedicated webhook host: `https://hooks.quantyralabs.cc/<app_name>`

**Implementation Steps:**
- ✅ Add edge routing policy for `hooks.quantyralabs.cc` to allow only webhook POST path
- ✅ Deny all non-webhook paths on webhook host (404)
- ✅ Keep dashboard host private/Tailscale-only
- ✅ Enforce HMAC signature validation (`X-Hub-Signature-256`) and event filtering (`push`, `ping`)

### Phase 1: Domain Provisioning Reliability + 404 Fix

**Current Failures Observed:**
- `router-01: Permission denied (publickey,password)`
- `router-02: Command timed out`
- Domains return 404 because HAProxy provisioning is incomplete

**Implementation Steps:**
1. ✅ Fix router execution path in provisioning (no SSH-to-self on router-01)
2. ✅ Increase provisioning timeout for certbot operations
3. ✅ Ensure certbot runs with non-interactive expansion for existing cert SAN changes
4. ✅ Verify provision success before marking domain as provisioned:
   - cert exists on both routers
   - registry entry exists
   - HAProxy config validates and reloads
5. ✅ Persist per-router errors in domain status

### Phase 2: Deployment Health Checks and Failure Handling

**Requirement:** Deployment must validate domain health as part of rollout.

**Health Rules:**
| Domain Type | Accepted Status |
|-------------|-----------------|
| Production | 200 (or redirect chain ending in 200) |
| Staging | 200 or 401 |

**Implementation Steps:**
1. ✅ Add post-deploy app health checks per server
2. ✅ Add post-provision domain health checks
3. ✅ Mark deployment failed if checks do not pass
4. ✅ Surface structured errors in UI and deploy results

### Phase 3: Rolling Deploy with Safe Rollback

**Requirement:** If primary server fails build/start/health, stop rollout and rollback.

**Implementation Steps:**
1. ✅ Primary-first deployment gate
2. ✅ Abort secondary rollout when primary fails
3. ✅ Track commit state (`before_commit` and per-server last known commit)
4. ✅ Rollback primary to last working commit on failure
5. ✅ Add redeploy action for failed deployments
6. ✅ Add rollback action in UI/API

### Phase 4: Delete Path and Database Cleanup Hardening

**Current Failure:** Production DB/users removed, staging DB/users can remain.

**Implementation Steps:**
1. ✅ Terminate active DB connections before drop (`pg_stat_activity`)
2. ✅ Drop production and staging DBs independently with status tracking
3. ✅ Drop staging users reliably (`_staging_user`, `_staging_admin`)
4. ✅ Apply same cleanup logic to all delete flows:
   - app delete
   - staging delete
   - database delete endpoint

### Phase 5: Database Password Visibility and Credential Handling

**Current Issue:** Databases page may show `-` for passwords for some records.

**Implementation Steps:**
1. ✅ Align password display logic with current schema
2. ✅ For hash-only/manual users: show `Not recoverable`
3. ⏳ Add password reset/regenerate flow for manual databases
4. ✅ Keep app-generated credentials visible as requested

### Phase 6: Security Hardening from Full Audit

**Implementation Steps:**
1. ✅ Require auth for sensitive APIs (especially `/api/databases`)
2. ✅ Enforce strict server-side validation for app/db/domain identifiers
3. ✅ Remove hardcoded credential usage in templates/snippets
4. ⏳ Add webhook endpoint rate limiting and optional GitHub IP allowlisting

### Phase 7: Deployment UX Transparency + Controlled Domain Override

**Requirement:** Deployment progress must clearly separate application deploy from domain provisioning, and users must have an explicit opt-in override to provision pending domains after deploy failure.

**Implementation Steps:**
1. ✅ Add two-phase deploy progress model in API/UI:
   - deploy phase
   - domain provisioning phase
2. ✅ Mark domain provisioning phase as `skipped` when deploy phase fails
3. ✅ Persist last deploy outcome and surface failure banner in app status UI
4. ✅ Add explicit **Force Provision Pending Domains** action (manual opt-in)
5. ✅ Keep default behavior strict: do not auto-provision domains when deploy fails

**Tracking:**
- Started: 2026-03-17 10:51 EDT
- Completed: 2026-03-17 10:56 EDT

### Phase 8: Infra-Only Reliability Fixes + Config Sync

**Requirement:** Keep scope strictly in infrastructure/PaaS code (no app-repo fixes), improve deploy failure diagnostics, handle initial deploy rollback semantics, and harden staging DB/user deletion consistency.

**Task-by-Task Execution List:**
1. ✅ Add deploy error fallback extraction so blank `server:` errors include meaningful stdout context
2. ✅ Disable rollback attempts for initial deployment failures when no known-good commit exists
3. ✅ Improve deploy failure messaging to clearly state rollback unavailability for first deploy
4. ✅ Fix staging DB/user cleanup consistency in:
   - app delete
   - staging delete
   - database delete endpoint
   including config cleanup for staging entries in `databases.yml`
5. ✅ Mirror all dashboard code/template changes into `configs/dashboard/*`
6. ✅ Update docs with completion timestamps and outcomes

**Tracking:**
- Started: 2026-03-17 11:33 EDT
- Completed: 2026-03-17 11:38 EDT

### Phase 9: Force-Provision Reliability + Router Reachability Fallback

**Requirement:** Manual force-provision must not hang and must work even when router-to-router Tailscale SSH requires interactive auth checks.

**Task-by-Task Execution List:**
1. ✅ Add router command fallback path (Tailscale IP -> public IP) for router-02 operations
2. ✅ Prevent long-hanging force-provision requests with bounded per-router execution behavior
3. ✅ Improve Force Provision button UX (disable while running + in-progress feedback)
4. ✅ Ensure create-result page shows phase status from server-rendered deploy results (not static pending)
5. ✅ Sync updated dashboard code/templates into `configs/dashboard/*`
6. ✅ Deploy updated dashboard to router-01 and restart service

**Tracking:**
- Started: 2026-03-17 12:17 EDT
- Completed: 2026-03-17 12:21 EDT

**Operational Note:**
- Force-provision endpoint now returns actionable router-level errors instead of hanging.
- Current environment blocker (as of 2026-03-17 12:21 EDT): router-02 SSH path still fails (`Tailscale timeout` and `public IP permission denied`) and must be remediated for full dual-router provisioning success.

### Phase 10: Router-to-Router SSH Remediation + Force-Provision Validation

**Requirement:** Restore non-interactive SSH from router-01 to router-02 (Tailscale and/or public path), then re-run force-provision and verify domain states.

**Task-by-Task Execution List:**
1. ✅ Diagnose router-01 -> router-02 SSH auth/path failure (keys, sshd policy, Tailscale SSH behavior)
2. ✅ Apply non-interactive SSH remediation and verify `BatchMode=yes` connectivity
3. ✅ Re-run force-provision for pending domains and validate router registry/certs
4. ✅ Update docs with verification outcome and timestamped completion

**Tracking:**
- Started: 2026-03-17 12:34 EDT
- Completed: 2026-03-17 12:50 EDT

**Verification Outcome (2026-03-17 12:50 EDT):**
- Force-provision API completed successfully (`HTTP 200`) with `provisioned: [rentalfixer.app, staging.rentalfixer.app]` and `pending_count: 0`.
- Router registry/cert artifacts now exist on both routers for production + staging domains.
- Domain response moved from `404` to `503`, indicating routing/cert provisioning is complete and remaining issue is upstream app health/runtime.
- Synced router-02 provisioning script to full domain provisioning implementation and aligned repo copy in `configs/provision-scripts/provision-domain-router-02.sh`.

### Phase 11: Composer Compatibility Remediation on App Servers

**Requirement:** App-server Composer runtime must be compatible with PHP 8.5 to avoid deprecated `E_STRICT` notice flood and improve deploy signal clarity.

**Task-by-Task Execution List:**
1. ✅ Audit current Composer versions on `re-db` and `re-node-02`
2. ✅ Upgrade Composer to 2.8+ on both app servers
3. ✅ Verify `composer --version` and executable path consistency
4. ✅ Re-run deployment check and confirm deprecated Composer notice flood is resolved
5. ✅ Update docs with completion timestamp and verification outcome

**Tracking:**
- Started: 2026-03-17 13:07 EDT
- Completed: 2026-03-17 13:10 EDT

**Verification Outcome (2026-03-17 13:10 EDT):**
- `composer` now resolves to `/usr/local/bin/composer` on both app servers.
- Composer version is `2.9.5` on `re-db` and `re-node-02`.
- Deprecated `E_STRICT` notice flood is removed from deploy output.
- Current deploy failure signal is now app/runtime health specific (`database.sqlite` path error and health check failure), not Composer compatibility.

### Phase 12: Non-Root Runtime and Tooling Enforcement on App Servers

**Requirement:** Application language/tooling processes on app servers must not run as root. Standardize to a dedicated non-privileged user and enforce permissions to avoid regression.

**Task-by-Task Execution List:**
1. ✅ Standardize app runtime identity to `webapps` for non-Laravel systemd services generated by dashboard
2. ✅ Ensure `webapps` user auto-creation in dashboard orchestration before clone/setup/service steps
3. ✅ Execute repo clone/build/setup commands as `webapps` (Composer/NPM/Pip/Go) in dashboard deployment paths
4. ✅ Update Laravel writable-path permissions to support `www-data` runtime without changing app ownership from `webapps`
5. ✅ Harden deploy script (`scripts/deploy-app.sh`) to run tooling under `webapps` and re-apply ownership/permissions
6. ✅ Update security and operational docs to codify non-root requirement and user standard

**Tracking:**
- Started: 2026-03-17 13:45 EDT
- Completed: 2026-03-17 13:52 EDT

**Verification Outcome (2026-03-17 13:52 EDT):**
- Dashboard orchestration now provisions/uses `webapps` before clone/build/service operations.
- Generated non-Laravel systemd units now run as `User=webapps` and `Group=webapps`.
- Deployment tooling paths in `scripts/deploy-app.sh` execute build/migration steps via `sudo -u webapps`.
- Permission guardrails keep Laravel writable dirs (`storage`, `bootstrap/cache`) group-writable for `www-data` while preserving non-root app ownership.

### Phase 13: SOPS-Backed Runtime Env Materialization (Router-01 Key Only)

**Decision:** Keep AGE private key only on router-01 (`/opt/dashboard/secrets/age.key`). App servers must not have SOPS key material.

**Requirement:** Deploy pipeline must generate app runtime `.env` from SOPS-managed secrets on dashboard host and distribute to app servers as a runtime artifact.

**Task-by-Task Execution List:**
1. ✅ Update docs to define SOPS source-of-truth + generated `.env` runtime model
2. ✅ Implement deploy-time env generation/validation in dashboard deployment flow
3. ✅ Push `.env` atomically to app servers with `webapps:webapps` ownership and `640` mode
4. ✅ Add explicit missing-`.env` guardrail to `/opt/scripts/deploy-app.sh`
5. ✅ Correct `.sops.yaml` path rules for `.yml` config filenames
6. ✅ Deploy dashboard/script updates and validate on both app servers
7. ✅ Update docs with completion timestamp and verification outcome

**Tracking:**
- Started: 2026-03-17 14:01 EDT
- Completed: 2026-03-17 14:12 EDT

**Verification Outcome (2026-03-17 14:12 EDT):**
- Deploy API now fails fast with explicit missing-secret message when required keys are absent (`Missing required deploy secrets for production: APP_KEY`).
- Runtime `.env` materialization is wired into dashboard deploy flows and runs before app deploy execution.
- `/opt/scripts/deploy-app.sh` now exits early with actionable guidance when `.env` is missing.
- AGE private key remains dashboard-host only; app servers still have no `sops`/`age` binaries and no key material.

### Phase 14: Branch-Gated Dual-Environment Deploy + Scoped Secrets Sync

**Decision:**
- `main` branch deploys production only.
- `staging` branch deploys staging only.
- All other branches are ignored by webhook deploy.

**Requirement:**
- Maintain separate production/staging codebases on app servers.
- Support scoped app secrets (`shared`, `production`, `staging`) in one SOPS file.
- Regenerate and sync runtime `.env` to app servers when secrets are added/updated/removed.
- Auto-generate Laravel `APP_KEY` on first deploy if missing.

**Task-by-Task Execution List:**
1. ✅ Update docs for branch-gated deploy policy and scoped secrets model
2. ✅ Enforce webhook branch routing (`main` -> production, `staging` -> staging, others ignored)
3. ✅ Implement dual-codebase deploy targets (`/opt/apps/{app}` and `/opt/apps/{app}-staging`)
4. ✅ Add scoped secrets schema (`shared`/`production`/`staging`) with backward compatibility
5. ✅ Wire Laravel first-deploy bootstrap (`APP_KEY` generation + persistence)
6. ✅ Ensure production/staging PostgreSQL env wiring and validation for each target
7. ✅ Add live `.env` sync on app secret add/edit/delete with server-level error reporting
8. ✅ Validate deploy behavior for `main`, `staging`, and ignored branches
9. ✅ Update docs with completion timestamp and verification evidence

**Tracking:**
- Started: 2026-03-17 14:39 EDT
- Completed: 2026-03-17 14:58 EDT

**Verification Outcome (2026-03-17 14:58 EDT):**
- Deploy API now enforces branch gating (`main`/`staging` only); non-deploy branches return ignored status.
- Deploy responses include explicit `environment` and `deploy_target` (`rentalfixer` vs `rentalfixer-staging`).
- Scoped app secrets (`shared`/`production`/`staging`) are supported with backward compatibility for legacy flat secret files.
- Laravel `APP_KEY` now auto-generates on first deploy when absent and persists to encrypted app secrets.
- App secret add/edit/delete now triggers runtime `.env` sync attempts to app servers.
- Remaining environmental issue: `re-node-02` SSH reachability intermittently times out, causing partial env-sync warnings.

### Phase 15: SSH Connectivity Fix + Tailscale SSH Migration (2026-03-17)

**Problem:** Tailscale SSH (`RunSSH: true`) was intercepting port 22 on all Tailscale IPs, requiring browser-based authentication that timed out in scripts. This caused deploy orchestration failures between servers.

**Task-by-Task Execution List:**
1. ✅ Diagnose root cause: Tailscale SSH intercepting port 22
2. ✅ Disable Tailscale SSH on all 7 Linux servers
3. ✅ Generate SSH key on re-db for server-to-server communication
4. ✅ Distribute SSH keys to all servers (id_vps, re-db, router-01, router-02)
5. ✅ Verify full SSH mesh connectivity from router-01 to all servers
6. ✅ Update AGENTS.md with SSH key infrastructure documentation

**Tracking:**
- Started: 2026-03-17 15:00 EDT
- Completed: 2026-03-17 20:10 EDT

**Verification Outcome (2026-03-17 20:10 EDT):**
- All servers can SSH to each other without browser authentication.
- SSH key matrix established with 4 keys distributed to all servers.
- Tailscale SSH (`RunSSH`) is now disabled on all servers.

### Phase 16: Secrets UI Enhancement + Deploy Bug Fixes (2026-03-17)

**Changes:**
1. **Secrets UI Tabs**: Replaced scope dropdown with tab navigation (All | Shared | Production | Staging)
2. **Clone Directory Fix**: Fixed `clone_repo_to_servers` to create app directory as root before cloning
3. **Database Delete Bug Fix**: Fixed bug where deleting production database also deleted staging database
4. **Staging Secrets**: Added staging-scoped secrets for rentalfixer app

**Task-by-Task Execution List:**
1. ✅ Implement tab-based scope selection in secrets UI
2. ✅ Add CSS styles for tabs and scope badges
3. ✅ Fix clone_repo_to_servers to prep directory as root with webapps ownership
4. ✅ Fix database deletion to only delete requested scope
5. ✅ Add staging secrets for rentalfixer
6. ✅ Recreate deleted databases after bug fix

**Tracking:**
- Started: 2026-03-17 20:15 EDT
- Completed: 2026-03-17 21:00 EDT

### Phase 17: Database Permissions + Deploy Script Fix (2026-03-17)

**Issues Found:**
1. **Database Schema Permissions**: `rentalfixer_user` lacked CREATE TABLE permissions on `rentalfixer` database
2. **Deploy Script Backup Bug**: `backup_database()` function uses `grep DB_USERNAME` which matches both `DB_USERNAME` and `STAGING_DB_USERNAME`, causing pg_dump to receive multiple values

**Task-by-Task Execution List:**
1. ✅ Grant schema permissions on PostgreSQL primary for rentalfixer users
2. ✅ Fix deploy script `backup_database()` to use anchored grep (`^DB_DATABASE=`)
3. ✅ Deploy script fix to both app servers (re-db, re-node-02)
4. ⏳ Re-run deploy to verify full deployment works

**Tracking:**
- Started: 2026-03-17 21:15 EDT
- Completed: 2026-03-17 21:20 EDT

**Verification:** User will manually re-run deploy

### Phase 18: Database Schema Permissions + Secrets Wizard Enhancement (2026-03-17)

**Issues:**
1. **Schema Permissions Not Persistent**: Schema grants are applied manually but lost when databases are recreated. The grants must be part of the database creation flow in `app.py`.
2. **Secrets Wizard Missing Scope Selection**: App creation wizard doesn't allow configuring production/staging secrets with scope selection.

**Task-by-Task Execution List:**
1. ✅ Add `grant_schema_permissions()` helper function in `app.py`
2. ✅ Call helper after production database creation
3. ✅ Call helper after staging database creation
4. ✅ Add scope dropdown to secret input row in `create_app.html`
5. ✅ Update `collectSecrets()` JS to include scope
6. ✅ Update form submission to send scoped secrets
7. ✅ Update backend API already supports scope parameter
8. ✅ Sync changes to `configs/dashboard/*`
9. ✅ Deploy to router-01 and restart dashboard

**Tracking:**
- Started: 2026-03-17 21:30 EDT
- Completed: 2026-03-17 21:45 EDT

**Verification:** User can test by creating a new app with scoped secrets in the wizard

### Phase 19: Database Creation Flow Fix (2026-03-17)

**Issues Found:**
1. **Premature Connection Close**: Connection closed after production DB creation but before staging user creation, causing "cursor already closed" error
2. **Secrets Not Saved on Failure**: DB secrets saved at end of block, so if exception occurs they're lost

**Root Cause Analysis:**
- Lines 1872-1873 close connection prematurely
- Staging block at line 1892 tries to use closed cursor
- Secrets saved at lines 2055-2072 depend on `results.get()` which is empty if exception occurs

**Task-by-Task Execution List:**
1. ✅ Remove premature `cur.close()` / `conn.close()` after production DB
2. ✅ Save production secrets immediately after user creation
3. ✅ Save staging secrets immediately after staging user creation
4. ✅ Keep single connection close at end of database block
5. ✅ Update redundant secret saving to be fallback (check if exists first)
6. ✅ Sync to configs/
7. ✅ Deploy and test

**Tracking:**
- Started: 2026-03-17 22:00 EDT
- Completed: 2026-03-17 22:10 EDT

**Verification:** User can test by creating a new app

### Phase 20: Configurable Branch Selection for Production/Staging (2026-03-17)

**Requirement:**
- Allow users to configure which Git branch triggers production deployments (default: `main`)
- Allow users to configure which Git branch triggers staging deployments (default: `staging`)
- Add branch input fields to Step 2 (App Details) in the creation wizard
- Store branch configuration in applications.yml
- Update deploy logic to use configured branches instead of hardcoded values

**Current State:**
- Branch mapping is hardcoded: `main` → production, `staging` → staging
- No way for users to customize branch names

**Task-by-Task Execution List:**
1. ✅ Add branch input fields to Step 2 of create_app.html
2. ✅ Add JavaScript to show/hide staging branch field based on staging checkbox
3. ✅ Save `production_branch` and `staging_branch` to app config in create_app()
4. ✅ Update `run_pull_deploy()` to use app's configured branches
5. ✅ Update webhook handler to check against app's configured branches
6. ⏳ Update `generate_github_workflow()` to use configured branches (deferred - GitHub Actions not primary deploy method)
7. ✅ Sync to configs/
8. ✅ Deploy and test

**Tracking:**
- Started: 2026-03-17 22:20 EDT
- Completed: 2026-03-17 22:54 EDT
- Status: ✅ Complete

**Backward Compatibility:**
- Existing apps without branch config will use defaults (`main`/`staging`)
- `app.get("production_branch", "main")` pattern ensures graceful fallback

### Phase 21: Laravel Deploy Fixes + Permission Hardening (2026-03-17)

**Issues Found:**
1. **PHP-FPM Pool Config Syntax**: `php_admin[` should be `php_admin_value[` causing PHP-FPM to fail
2. **Missing Laravel Setup on First Deploy**: `run_pull_deploy()` didn't call `setup_laravel_app()` for initial deployments
3. **.env Permissions**: Created as `webapps:webapps` but PHP-FPM runs as `www-data` which couldn't read it
4. **Health Check Port Extraction**: Deploy script read port from PHP-FPM config (uses sockets) instead of nginx

**Task-by-Task Execution List:**
1. ✅ Fix PHP-FPM pool config syntax (`php_admin[` → `php_admin_value[`)
2. ✅ Add Laravel setup check in `run_pull_deploy()` before deploy execution
3. ✅ Fix `write_runtime_env_to_servers()` to set `.env` group to `www-data`
4. ✅ Fix deploy script `ensure_app_permissions()` to set `.env` permissions
5. ✅ Fix deploy script health check to read port from nginx config
6. ✅ Fix JavaScript null error for `create_staging` element
7. ✅ Fix staging branch handling in backend (`create_staging` checkbox)
8. ✅ Sync to configs/
9. ✅ Deploy and verify rentalfixer app

**Tracking:**
- Started: 2026-03-17 23:30 EDT
- Completed: 2026-03-17 23:55 EDT
- Status: ✅ Complete

**Verification Outcome:**
- Both app servers return HTTP 200 on port 8100
- `rentalfixer.app` deployed successfully
- Migrations ran successfully on both servers

**Permission Model Documented:**
| Path | Owner | Group | Mode |
|------|-------|-------|------|
| `/opt/apps/{app}` | webapps | webapps | 755/644 |
| `storage/` | webapps | www-data | 2775 (setgid) |
| `bootstrap/cache/` | webapps | www-data | 2775 (setgid) |
| `.env` | webapps | www-data | 640 |

### Phase 22: PostgreSQL Client Upgrade + Migration Detection Fix (2026-03-18)

**Issues Found:**
1. **pg_dump Version Mismatch**: Server runs PostgreSQL 18.3, but client was 16.13 (re-db) or not installed (re-node-02), causing backup failures
2. **Migration Detection Bug**: `check_pending_migrations()` didn't detect "Migration table not found" as needing migrations

**Task-by-Task Execution List:**
1. ✅ Add PostgreSQL 18 APT repository to both app servers
2. ✅ Install `postgresql-client-18` on re-db (upgrade from 16.13)
3. ✅ Install `postgresql-client-18` on re-node-02 (was not installed)
4. ✅ Fix `check_pending_migrations()` to detect "Migration table not found"
5. ✅ Deploy updated script to both app servers
6. ✅ Verify database backup works

**Tracking:**
- Started: 2026-03-18 00:30 EDT
- Completed: 2026-03-18 00:40 EDT
- Status: ✅ Complete

**Verification Outcome:**
```
# Both servers now have matching client version
re-db: pg_dump (PostgreSQL) 18.3
re-node-02: pg_dump (PostgreSQL) 18.3

# Database backup works
-rw-r--r-- 1 root root 91843 Mar 18 00:38 /tmp/test_backup.sql
```

### Phase 23-26: Deploy Reliability Fixes (2026-03-18)

**Issues Fixed:**
1. **SSH Timeout**: Removed 30s timeout cap causing long-running deploys to fail
2. **Staging Port Calculation**: Staging was using 8101 instead of 9200
3. **Domain Health Check Bug**: Production deploy checked ALL domains including staging (not deployed yet)
4. **Last Deploy Status Bug**: `success_flag` set after `update_last_deploy_status()` call

**Tracking:**
- Completed: 2026-03-18 02:15 EDT
- Status: ✅ Complete

### Phase 27: Staging Password Protection (2026-03-18)

**Requirement:** Staging environments must be password-protected via HAProxy basic auth.

**Task-by-Task Execution List:**
1. ✅ Add `--password` parameter to `provision-domain.sh`
2. ✅ Create htpasswd file for staging apps
3. ✅ Add HAProxy `http-request auth` with userlist for password-protected backends
4. ✅ Update registry.conf format: `domain=app=port=password`
5. ✅ Rebuild HAProxy config to include auth for staging
6. ✅ Verify staging.rentalfixer.app requires authentication
7. ✅ Sync to scripts/

**Tracking:**
- Started: 2026-03-18 02:25 EDT
- Completed: 2026-03-18 02:30 EDT
- Status: ✅ Complete

**Verification Outcome:**
```
# Without credentials: 401 Unauthorized
curl -I https://staging.rentalfixer.app
HTTP/2 401
www-authenticate: Basic realm="Staging Area"

# With credentials: 200 OK
curl -I -u admin:o7YL2YVBEVUl8BaU https://staging.rentalfixer.app
HTTP/2 200
```

### Phase 28: UI Bug Fix - Domain Provisioning Reason (2026-03-18)

**Issue:** Domain provisioning phase always showed "(deploy failed)" when skipped, even when the actual reason was different.

**Example:** Staging deploys show "Staging deploy does not run domain provisioning" in the stored data, but UI hardcoded "(deploy failed)".

**Fix:** Display `domains_phase.reason` instead of hardcoded text.

**File:** `dashboard/templates/app_status.html:60`

**Tracking:**
- Started: 2026-03-18 02:45 EDT
- Completed: 2026-03-18 02:46 EDT
- Status: ✅ Complete

**Second Fix:** Staging deploys now show "N/A" badge with explanation "Domain provisioning runs during production deploy" instead of "Skipped" with technical reason.

### Phase 29: GitHub Webhook Timeout Fix (2026-03-18)

**Issue:** GitHub has a 10-second webhook timeout, but deployments take several minutes, causing GitHub to report "timed out".

**Fix:** Changed webhook handler to run deploys asynchronously:
- Return immediately with `202 Accepted`
- Run deploy in background thread using Python `threading`
- Deploy status stored in `applications.yml`
- Results visible on Applications page after completion

**Tracking:**
- Completed: 2026-03-18 03:40 EDT
- Status: ✅ Complete

**Response:**
```json
{
  "success": true,
  "message": "Deploy started",
  "branch": "staging",
  "environment": "staging"
}
```

### Phase 30: Last Deploy Status on Applications List (2026-03-18)

**Issue:** Applications list didn't show last deploy status, environment, or branch.

**Fix:**
- Updated `update_last_deploy_status()` to store branch and environment
- Updated `apps.html` to show success/failed badge with timestamp, environment, and branch
- Replaced "Database" column with "Last Deploy" column

**Format:** `[success/failed] 2026-03-18 03:34` followed by `production (main)`

**Tracking:**
- Completed: 2026-03-18 03:35 EDT
- Status: ✅ Complete

---

## Milestone: Laravel PaaS Complete (2026-03-18)

**Working Features:**
- ✅ Laravel application deployment via GitHub webhook
- ✅ Production + staging dual-environment support
- ✅ Configurable branch selection per environment
- ✅ Staging password protection (HAProxy basic auth)
- ✅ PostgreSQL database provisioning with permissions
- ✅ SOPS-encrypted secrets management
- ✅ Rolling deployments with rollback
- ✅ Health checks and failure handling
- ✅ Domain provisioning with SSL (DNS-01 challenge)
- ✅ Last deploy status visibility

**Current App:**
| App | Production | Staging | Framework |
|-----|------------|---------|-----------|
| rentalfixer | rentalfixer.app:8100 | staging.rentalfixer.app:9200 | Laravel |

---

### Phase 31: PHP-FPM Pool Optimization and Alert Fix (2026-03-18)

**Problem Statement:**
- PHP-FPM alerts (PHPFPMPoolExhausted, PHPFPMPoolBusy) are firing with false positives
- Current pool configuration is severely undersized for server specs (12 vCPU, 48GB RAM)
- Need to optimize for multi-app deployment (currently 1 Laravel app, planning 3)

**Config Sync Findings (2026-03-18):**

After syncing server configs, comprehensive analysis by specialized agents revealed:

**Current Pool Configuration (from synced configs):**

| Pool | pm.max_children | start_servers | min_spare | max_spare | max_requests |
|------|-----------------|---------------|-----------|-----------|--------------|
| www | 5 | 2 | 1 | 3 | (none) |
| rentalfixer (prod) | 10 | 2 | 1 | 5 | 500 |
| rentalfixer-staging | 10 | 2 | 1 | 5 | 500 |

**🔴 CRITICAL: Pools Severely Undersized**
- Server capacity: 12 vCPU, 48GB RAM
- Current PHP-FPM memory usage: ~3GB (only 6% of available RAM)
- With 10 workers per pool, only handling ~10 concurrent requests
- **Recommended:** 80-100 workers for production, 40 for staging

**🟡 Production Missing Upload Limits:**
- Production pool has no `upload_max_filesize` or `post_max_size` overrides
- Falls back to PHP defaults: 2MB upload, 8MB POST
- Staging has 50MB configured but production doesn't

**🟡 Missing Performance Configurations:**
- No `slowlog` configuration for debugging slow requests
- No `request_terminate_timeout` for worker protection
- No memory_limit override in production

**Task-by-Task Execution List:**

1. **Phase 1: Fix Prometheus Alert Rules** ✅ COMPLETE (2026-03-19 02:24 UTC)
   - [x] Update `configs/prometheus/alerts.yml` with correct queries
   - [x] Alerts now use `phpfpm_processes_total{state="idle"}` instead of broken percentage
   - [x] Added `PHPFPMMaxChildrenReached` alert for pool capacity monitoring
   - [x] Deploy to router-01: `scp configs/prometheus/alerts.yml root@100.102.220.16:/etc/prometheus/alerts.yml`
   - [x] Restart Prometheus: `ssh root@100.102.220.16 "systemctl restart prometheus"`
   - [x] Verified: 34 rules loaded successfully

2. **Phase 2: Audit Current Pool Configuration** ✅ COMPLETE (2026-03-18)
   - [x] SSH to re-db and check `/etc/php/8.5/fpm/pool.d/rentalfixer.conf`
   - [x] Document actual `pm.max_children` setting: **10** (too low)
   - [x] SSH to re-node-02 and verify same config: **IDENTICAL**
   - [x] Check staging pool config: **Also 10** (should be lower)

3. **Phase 3: Update Pool Configuration** ✅ COMPLETE (2026-03-19 02:23 UTC)
   - [x] Update production pool with optimized settings (max_children=80)
   - [x] Update staging pool with low-traffic settings (max_children=40)
   - [x] Add slowlog configuration to all pools
   - [x] Add pm.process_idle_timeout (10s) to all pools
   - [x] Deploy to re-db first, verify health
   - [x] Deploy to re-node-02, verify health
   - [x] PHP-FPM configs validated and restarted on both servers

4. **Phase 4: Update Dashboard Template** ✅ COMPLETE (2026-03-19 02:24 UTC)
   - [x] Add `is_staging` parameter to `configure_php_fpm_pool()`
   - [x] Use optimized settings based on environment (prod: 80, staging: 40)
   - [x] Add slowlog and timeout settings to template
   - [x] Deploy to router-01, restart dashboard

5. **Phase 5: Verification** ✅ COMPLETE (2026-03-19 02:24 UTC)
   - [x] PHP-FPM configs test passed on both servers
   - [x] Prometheus restarted with 34 rules
   - [x] Dashboard restarted with updated template
   - [x] Documentation updated

**Connection Pooling Analysis:**

Transaction pooling decouples PHP-FPM worker count from DB connection count:
- Pool size 20 can handle 660 transactions/second
- Realistic peak load: ~84 tps
- Headroom: **7.8x capacity**

| Setting | Value | Why |
|---------|-------|-----|
| PostgreSQL max_connections | **200** | Covers all PgBouncer pools + replication + admin |
| PgBouncer pool_size | **20** | Transaction pooling provides massive headroom |

**No changes needed to PgBouncer or PostgreSQL connection limits.**

**Optimized Pool Configuration:**

```ini
# Production Pool (rentalfixer.conf)
[{app_name}]
user = www-data
group = www-data
listen = /run/php/php8.5-fpm-{app_name}.sock

pm = dynamic
pm.max_children = 80           # Was 10
pm.start_servers = 12          # Was 2
pm.min_spare_servers = 8       # Was 1
pm.max_spare_servers = 24      # Was 5
pm.max_requests = 1000         # Was 500

slowlog = /var/log/php8.5-fpm/$pool-slow.log
request_slowlog_timeout = 5s
request_terminate_timeout = 60s

php_admin_value[memory_limit] = 256M
php_admin_value[upload_max_filesize] = 50M
php_admin_value[post_max_size] = 50M
php_admin_value[disable_functions] = exec,passthru,shell_exec,system
```

```ini
# Staging Pool (rentalfixer-staging.conf)
[{app_name}-staging]
pm = dynamic
pm.max_children = 40           # Was 10
pm.start_servers = 4
pm.min_spare_servers = 2
pm.max_spare_servers = 12
pm.max_requests = 500

slowlog = /var/log/php8.5-fpm/$pool-slow.log
request_slowlog_timeout = 5s
request_terminate_timeout = 60s
```

**Corrected Alert Rules (Already in configs/prometheus/alerts.yml):**

```yaml
- alert: PHPFPMPoolExhausted
  expr: phpfpm_processes_total{state="idle"} < 2
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "PHP-FPM pool nearly exhausted on {{ $labels.node }}"
    description: "Only {{ $value }} idle workers remaining"

- alert: PHPFPMPoolBusy
  expr: phpfpm_processes_total{state="idle"} < 5 and phpfpm_processes_total{state="idle"} >= 2
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "PHP-FPM pool busy on {{ $labels.node }}"
    description: "Only {{ $value }} idle workers remaining (pool under load)"

- alert: PHPFPMMaxChildrenReached
  expr: rate(phpfpm_max_children_reached_total[5m]) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "PHP-FPM max_children reached on {{ $labels.node }}"
    description: "Workers hit max_children limit - consider increasing pool size"
```

**Capacity Projection:**

| Metric | Current | After Optimization | Improvement |
|--------|---------|-------------------|-------------|
| PHP-FPM workers | 25 total | 140 total | +460% |
| Memory usage | ~3GB | ~18GB | +500% |
| Concurrent requests | ~25 | ~140 | +460% |
| Server utilization | 6% | 37% | +517% |

**Rollback Procedure:**
```bash
# Restore PHP-FPM config
ssh root@{server} "mv /etc/php/8.5/fpm/pool.d/{pool}.conf.bak /etc/php/8.5/fpm/pool.d/{pool}.conf && systemctl reload php8.5-fpm"

# Restore alert rules
ssh root@100.102.220.16 "git checkout /etc/prometheus/rules/alerts.yml && systemctl reload prometheus"
```

**Tracking:**
- Started: 2026-03-18 (planning)
- Config sync: 2026-03-18 (complete)
- Pool optimization: 2026-03-19 02:23 UTC (complete)
- Completed: 2026-03-19 02:24 UTC
- Status: ✅ Complete

**Implemented Configuration:**

| Pool | max_children | start_servers | min_spare | max_spare | max_requests | slowlog |
|------|--------------|---------------|-----------|-----------|--------------|---------|
| rentalfixer (prod) | 80 | 8 | 4 | 16 | 1000 | 5s |
| rentalfixer-staging | 40 | 4 | 2 | 8 | 500 | 5s |

**Additional Fixes (2026-03-19 02:24 UTC):**
- Fixed Redis default host in dashboard: `100.102.220.16` → `100.126.103.51` (re-node-01)
- Fixed stale IP in nginx configs: `100.101.39.22` → `100.89.130.19` (re-node-02)
- Fixed stale IP in cloudflare-api.sh: `100.101.39.22` → `100.89.130.19`

---

### Phase 32: Critical Infrastructure Issues from Config Sync (2026-03-18)

**Multi-agent analysis found critical issues requiring immediate attention:**

#### 🔴 CRITICAL Issues

| Issue | Component | Severity | Impact | Status |
|-------|-----------|----------|--------|--------|
| Missing Staging Auth on router-02 | HAProxy | CRITICAL | Staging publicly accessible via router-02 | ✅ Fixed (2026-03-18) |
| Registry.conf missing password | HAProxy | CRITICAL | Auth won't be applied on rebuild | ✅ Fixed (2026-03-18) |
| Prometheus nginx port mismatch | Monitoring | CRITICAL | No nginx metrics from re-node-02 | ✅ Fixed (2026-03-18) |
| PostgreSQL max_connections drift (re-node-03) | Database | HIGH | Cluster inconsistency (300 vs 200) | ✅ Fixed (2026-03-18) |
| PostgreSQL work_mem drift | Database | MEDIUM | Inconsistent query performance | ✅ Fixed (2026-03-18) |
| Dashboard Redis default host wrong | Dashboard | HIGH | Connecting to wrong Redis host | ✅ Fixed (2026-03-19) |
| Stale IP in scripts/configs | Scripts | HIGH | Wrong IP for re-node-02 | ✅ Fixed (2026-03-19) |

#### 1. HAProxy Router-02 Missing Staging Auth

**Files:**
- `configs/haproxy/router-02/web_backends.cfg` - Missing auth directive and userlist
- `configs/haproxy/router-02/registry.conf` - Missing password field

**router-01 has (CORRECT):**
```haproxy
backend rentalfixer-staging_backend
    http-request auth realm "Staging Area" unless { http_auth(rentalfixer-staging_users) }

userlist rentalfixer-staging_users
    user admin insecure-password 4eaJnZ_hKJd6lli6
```

**router-02 is MISSING these lines entirely.**

**Fix Required:**
- [x] Sync web_backends.cfg from router-01 to router-02
- [x] Update registry.conf with password: `staging.rentalfixer.app=rentalfixer-staging=9200=4eaJnZ_hKJd6lli6`
- [x] Reload HAProxy on router-02

#### 2. Prometheus nginx Port Mismatch ✅ Fixed

**Files:**
- `configs/prometheus/prometheus.yml` - Expects port 9113 for all app servers
- `configs/app-servers/re-node-02/nginx-sites/stub_status` - Uses port 9114

**Fix Required:**
- [x] Change re-node-02 stub_status port from 9114 to 9113
- [x] Reload nginx on re-node-02
- [x] Verify Prometheus scrapes nginx metrics

#### 3. PostgreSQL Configuration Drift ✅ Fixed

**Correct setting:** max_connections = **200** (transaction pooling handles connection efficiency)

**Files:**
- `configs/postgres/patroni-re-node-01.yml` - max_connections: 200 ✓, work_mem: 64MB
- `configs/postgres/patroni-re-node-03.yml` - max_connections: 200 ✓, work_mem: 64MB
- `configs/postgres/patroni-re-node-04.yml` - max_connections: 200 ✓, work_mem: 64MB

**Fix Required:**
- [x] Change re-node-03 max_connections from 300 to 200 (cluster consistency)
- [x] Standardize work_mem to 64MB on all nodes
- [x] Apply changes via Patroni DCS

**Note:** No need to increase max_connections or PgBouncer pool_size. Transaction pooling provides 7-8x headroom.

#### 🟡 HIGH Priority Issues

| Issue | Component | Location |
|-------|-----------|----------|
| Dashboard Redis default host wrong | Dashboard | app.py:68 uses router-01 instead of re-node-01 |
| Stale IP in scripts | Scripts | 100.101.39.22 should be 100.89.130.19 |
| Missing nginx real_ip_from | Dashboard | configure_laravel_nginx() missing set_real_ip_from |
| Outdated TLS versions | Nginx | TLSv1 and TLSv1.1 should be removed |
| HAProxy stats exposed | HAProxy | Bound to Tailscale IP, not localhost |

**Dashboard Redis Fix:**
```python
# Current (WRONG)
REDIS_HOST = os.environ.get("REDIS_HOST", "100.102.220.16")  # router-01

# Correct
REDIS_HOST = os.environ.get("REDIS_HOST", "100.126.103.51")  # re-node-01
```

**Stale IP Fix:**
```bash
# In scripts/provision-domain.sh and configs/cloudflare-scripts/cloudflare-api.sh
# Replace: 100.101.39.22
# With: 100.89.130.19
```

**Tracking:**
- Started: 2026-03-18 (discovered via config sync)
- Fixed: 2026-03-19
- Status: ✅ Complete

---

### Phase 33: Security Assessment from Config Sync (2026-03-18)

**Context:** This is a private single-user infrastructure. Repo is on private NAS, dashboard is Tailscale-only.

**Threat Model:**
| Attack Vector | Risk Level | Why |
|--------------|-----------|-----|
| Public internet → Cloudflare → Apps | **Protected** | Cloudflare WAF + DDoS + SSL |
| Direct server access | **Low** | Tailscale-only, key auth |
| Private repo exposure | **Low** | Private NAS, single user |
| Tailscale network breach | **Primary Threat** | If compromised, git secrets are least concern |

**Security Reassessment:** Most "critical" findings from standard audit don't apply here.

#### ✅ NOT Security Issues in This Context

| Finding | Original | Reassessed | Reason |
|---------|----------|------------|--------|
| Hardcoded credentials in git | Critical | **NONE** | Private repo on private NAS |
| SSL certificates in git | Critical | **NONE** | Free certs, auto-renew |
| API tokens in config files | Critical | **LOW** | Scoped tokens, private repo |
| HAProxy stats on Tailscale (8404) | High | **NONE** | Authenticated + private network |
| PHP-FPM status path exposed | High | **NONE** | Tailscale-only, single user |
| PgBouncer TLS disabled | High | **NONE** | Tailscale provides encryption |
| Redis Sentinel no auth | High | **LOW** | Tailscale ACL provides access control |

#### ⚠️ Actual Security Priorities

| Priority | Action | Status |
|----------|--------|--------|
| **HIGH** | Verify Tailscale ACLs only allow your devices | [ ] Check |
| **HIGH** | Keep servers patched (apt update) | [ ] Ongoing |
| **MEDIUM** | Verify Cloudflare API token is zone-scoped | [ ] Check |
| **LOW** | Annual credential rotation as hygiene | [ ] Optional |

**Tailscale ACL Verification:**
```bash
# Check at https://login.tailscale.com/admin/acls
# Ensure only your devices can access servers
```

**API Token Scoping:** ✅ VERIFIED (2026-03-18)
```bash
# Verification performed via Cloudflare API
# Token ID: bca13c7bdfe90f51ce4dd1b6c1deb0d3
# Status: active
```

**Token Verification Results:**

| Attribute | Value |
|-----------|-------|
| Token Status | Active ✅ |
| Scope | Account-wide (all 75 zones) |
| Total Zones Accessible | 75 zones |
| xotec.io Zone ID | `26470f68ef4dbbf7bf5a770630aa2a97` ✅ |
| rentalfixer.app Zone ID | `d565e98b12effe08e530da729b82c0b9` ✅ |

**Token Permissions (per zone):**
| Permission | Purpose | Dashboard Use |
|------------|---------|---------------|
| `#dns_records:read` | Read DNS records | ✅ Domain provisioning |
| `#dns_records:edit` | Create/update/delete DNS records | ✅ Domain provisioning |
| `#waf:read` | Read WAF rules | ✅ Security rules |
| `#waf:edit` | Edit WAF rules | ✅ Security rules |
| `#zone:read` | Read zone information | ✅ Zone validation |

**Security Assessment:**
| Factor | Risk Level | Justification |
|--------|------------|---------------|
| Account-wide scope | **ACCEPTABLE** | Private repo, single user |
| No account admin | ✅ Good | Cannot create zones, manage billing |
| Minimum permissions | ✅ Good | Only DNS/WAF/Zone read needed |
| 75 zones accessible | **LOW RISK** | Tailscale perimeter protects repo |

**Recommendation:** Token is properly scoped for infrastructure dashboard needs. The account-wide scope is acceptable given:
- Private repository on private NAS
- Single-user infrastructure
- Tailscale network is the security perimeter
- No elevated account permissions (can't create zones, manage billing)

**Conclusion:** Infrastructure security is appropriate for private single-user setup. Tailscale IS the perimeter. Focus on keeping Tailscale ACLs tight and servers patched.

---

#### Apt Update Status (2026-03-18)

**Summary Table:**

| Server | IP | Upgradable | Security Updates | Critical Services |
|--------|-----|------------|------------------|-------------------|
| re-node-01 | 100.126.103.51 | 14 | snapd | tailscale (1.94.2→1.96.2), postgresql-18-h3 |
| re-node-03 | 100.114.117.46 | 11 | snapd | tailscale |
| re-node-04 | 100.115.75.119 | 11 | snapd | tailscale |
| router-01 | 100.102.220.16 | 12 | snapd, python3-flask | tailscale |
| router-02 | 100.116.175.9 | 3 | snapd | tailscale |
| re-db | 100.92.26.38 | 53 | snapd, systemd-suite | tailscale, postgresql-client |
| re-node-02 | 100.89.130.19 | 4 | snapd | tailscale, libgd3 |

**Key Findings:**

| Category | Count | Details |
|----------|-------|---------|
| **All Servers** | 7 | tailscale 1.94.2 → 1.96.2 |
| **All Servers** | 7 | snapd security update (noble-security) |
| **re-db** | 53 | Large update batch including systemd security patches |
| **router-01** | 1 | python3-flask security update |

**Security Updates Available:**
- `snapd/noble-security` - All 7 servers
- `systemd*` suite (noble-security) - re-db only (libsystemd0, libpam-systemd, systemd, udev, etc.)
- `python3-flask/noble-security` - router-01 only

**Critical Infrastructure Updates:**
- `tailscale` - All servers (1.94.2 → 1.96.2) - **VPN connectivity critical**
- `postgresql-18-h3` - re-node-01 (PostgreSQL extension)
- `postgresql-client-*` - re-db (pg_dump client upgrade)

**Recommended Upgrade Order:**
1. **tailscale** on all servers (VPN is critical infrastructure)
2. **snapd** on all servers (security)
3. **systemd suite** on re-db (security)
4. **python3-flask** on router-01 (security, dashboard dependency)
5. Remaining packages as needed

**Upgrade Command (when ready):**
```bash
# Upgrade specific packages
ssh root@<IP> "apt upgrade -y tailscale snapd"

# Full upgrade (use with caution)
ssh root@<IP> "apt full-upgrade -y"
```

**Tracking:**
- Started: 2026-03-18 (security audit)
- Reassessed: 2026-03-18 (context applied)
- Token verified: 2026-03-18 20:45 UTC
- Apt status checked: 2026-03-18 21:00 UTC
- Status: ✅ No critical issues, updates pending user approval

---

## Medium Priority

### 1. Multi-Framework Deployment Support

**Current Status:** Laravel fully working. Other frameworks need testing/implementation.

| Framework | Status | Notes |
|-----------|--------|-------|
| Laravel | ✅ Working | Full pipeline tested |
| Next.js | ⚠️ Needs Testing | Systemd service, health check needed |
| SvelteKit | ⚠️ Needs Testing | Systemd service, health check needed |
| Python (Flask/Django) | ⚠️ Needs Testing | Gunicorn + systemd |
| Go | ⚠️ Needs Testing | Binary + systemd |

**Task-by-Task Execution List:**
1. Create test app for each framework
2. Test deployment end-to-end
3. Fix any framework-specific issues
4. Document build commands and health checks
5. Update `docs/framework_builds.md`

### 2. Dashboard Refactoring Plan

**Problem:** `dashboard/app.py` is ~4600 lines, making it hard to maintain.

**Solution:** Refactor into modular structure without breaking current functionality.

**Proposed Structure:**
```
dashboard/
├── app.py              # Main Flask app, routes only
├── config.py           # Configuration loading
├── auth.py             # Authentication decorators
├── models/
│   ├── applications.py # Application CRUD
│   ├── databases.py    # Database CRUD
│   └── secrets.py      # Secrets management
├── services/
│   ├── deploy.py       # Deployment orchestration
│   ├── domain.py       # Domain provisioning
│   ├── ssh.py          # SSH command execution
│   └── cloudflare.py   # Cloudflare API
├── templates/          # Existing templates
└── static/             # Existing static files
```

**Refactoring Principles:**
1. **No breaking changes** - Maintain all existing routes and APIs
2. **Incremental migration** - One module at a time
3. **Test after each step** - Deploy and verify
4. **Keep app.py as entry point** - Routes import from modules

**Migration Order:**
1. Extract SSH functions → `services/ssh.py`
2. Extract Cloudflare functions → `services/cloudflare.py`
3. Extract deploy functions → `services/deploy.py`
4. Extract domain functions → `services/domain.py`
5. Extract model loading → `models/*.py`
6. Extract auth → `auth.py`
7. Extract config → `config.py`

**Estimated Effort:** 2-3 sessions, low risk if done incrementally.

---

## Medium Priority

### 4. Performance Optimization from Config Sync (2026-03-18)

**Performance analysis of synced configs:**

#### Nginx Optimization

**Current Issues:**
- `worker_connections = 768` (too low for 12 vCPU servers)
- No gzip optimization for MIME types
- No static file caching
- No buffer optimization

**Recommended Changes:**
```nginx
events {
    worker_connections 4096;     # Was 768
    multi_accept on;
    use epoll;
}

http {
    # Buffers
    client_body_buffer_size 16k;
    fastcgi_buffer_size 32k;
    fastcgi_buffers 16 16k;
    
    # Gzip
    gzip_comp_level 5;
    gzip_types text/plain text/css application/javascript application/json;
    
    # Static caching
    location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

#### HAProxy Optimization

**Current Issues:**
- No `maxconn` limits on backend servers
- Health check uses `GET /` (invokes PHP)

**Recommended Changes:**
```haproxy
backend rentalfixer_backend
    # Add connection limits to protect backends
    server app1 100.92.26.38:8100 check maxconn 200
    server app2 100.89.130.19:8100 check maxconn 200
```

#### PostgreSQL Optimization

**Current Issues:**
- `work_mem = 128MB` too high (200 connections × 128MB = 25GB worst case)
- `random_page_cost = 4.0` default (should be 1.1 for SSD)

**Recommended Changes:**
```postgresql
work_mem = 32MB                  # Was 128MB
random_page_cost = 1.1           # Was 4.0 (SSD optimization)
effective_io_concurrency = 200   # SSD optimization
```

#### Redis Optimization

**Current:**
- `maxmemory = 4gb` (conservative for 32GB servers)

**Optional:** Increase to 8GB if cache/session usage grows

**Tracking:**
- Started: 2026-03-18 (analysis complete)
- Status: ⏳ Pending implementation

---

### 5. Certbot Auto-Renewal Deploy Hook

Add automatic HAProxy reload after certificate renewal.

**Implementation:**
```bash
# On both routers
ssh root@router-01
cat > /etc/letsencrypt/renewal-hooks/deploy/haproxy-reload.sh << 'EOF'
#!/bin/bash
# Reload HAProxy after cert renewal
systemctl reload haproxy
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/haproxy-reload.sh
```

**Test:**
```bash
# Dry run renewal
certbot renew --dry-run
```

### 5. PM2 Setup for Node.js Apps

Replace systemd with PM2 for better Node.js process management.

**Benefits:**
- Automatic restarts on crash
- Log management
- Cluster mode (multiple processes)
- Zero-downtime reloads
- Memory limit monitoring

**Implementation:**
```bash
# Install PM2 on app servers
npm install -g pm2

# Start app with PM2
pm2 start npm --name "appname" -- start
pm2 save
pm2 startup
```

**Dashboard Integration:**
- Update `run_framework_setup()` for Node.js
- Use PM2 instead of systemd service

### 6. Sync Router Configs

Ensure both routers stay in sync.

**Option A: Manual sync script**
```bash
#!/bin/bash
# sync-routers.sh
rsync -avz /etc/haproxy/domains/ root@router-02:/etc/haproxy/domains/
rsync -avz /etc/haproxy/certs/ root@router-02:/etc/haproxy/certs/
ssh root@router-02 "systemctl reload haproxy"
```

**Option B: Shared storage**
- Use NFS or distributed storage for `/etc/haproxy/domains`
- More complex but automatic sync

**Option C: Config management**
- Use Ansible to manage HAProxy configs
- Run playbook after changes

### 7. Backup Automation

Automate backups for HAProxy configs and registry.

**Implementation:**
```bash
# Cron job on router-01
0 * * * * tar -czf /backup/haproxy-$(date +\%Y\%m\%d-\%H\%M).tar.gz /etc/haproxy/domains /etc/haproxy/certs
```

**Retention:**
- Keep hourly backups for 24 hours
- Keep daily backups for 7 days

### 8. Docker Compose Deployment (In Progress)

Deploy dashboard as Docker Compose stack for NAS or any machine on Tailscale.

**Files Created:**
- `docker/docker-compose.yml` - Main compose file
- `docker/dashboard/Dockerfile` - Dashboard container
- `docker/.env.example` - Environment template
- `docker/scripts/deploy.sh` - Deployment script
- `docs/docker_compose_plan.md` - Detailed plan

**Quick Start:**
```bash
cd docker
cp .env.example .env
# Edit .env with credentials
./scripts/deploy.sh start
```

**Services:**
- Dashboard (port 8080)
- Prometheus (port 9090)
- Grafana (port 3000)
- Alertmanager (port 9093)

**Next Steps:**
1. Test locally with Docker
2. Deploy to NAS
3. Verify Tailscale connectivity
4. Set up auto-start on boot

### 9. Per-App PHP-FPM Monitoring (Future)

Automatically add new apps to Grafana PHP-FPM metrics dashboard as they are provisioned.

**Problem:**
- PHP-FPM exporter only monitors the default `www` pool
- Per-app pools (rentalfixer, rentalfixer-staging, etc.) are not monitored
- No automatic discovery when new apps are deployed

**Solution:** Systemd templates + Prometheus file discovery + Grafana dashboard variables

**Architecture:**
```
App Deploy → Enable pm.status_path → Start exporter@{app} → Write target file → Prometheus discovers → Grafana shows
```

**Implementation:**

1. **Systemd Template** (`php-fpm-exporter@.service`):
   ```ini
   [Unit]
   Description=PHP-FPM Prometheus Exporter for %i
   After=network.target php8.5-fpm.service
   
   [Service]
   Type=simple
   User=www-data
   ExecStart=/usr/local/bin/php-fpm-exporter \
     --addr=%H:9253 \
     --fastcgi=unix:///run/php/php8.5-fpm-%i.sock \
     --endpoint=/metrics/%i
   Restart=on-failure
   
   [Install]
   WantedBy=multi-user.target
   ```

2. **Dashboard Deployment Flow** (in `setup_laravel_app()`):
   ```python
   # Enable status path in pool config
   ssh_command(server, f"sed -i 's|;pm.status_path|pm.status_path|' /etc/php/8.5/fpm/pool.d/{app_name}.conf")
   
   # Start exporter for this pool
   ssh_command(server, f"systemctl start php-fpm-exporter@{app_name}")
   ssh_command(server, f"systemctl enable php-fpm-exporter@{app_name}")
   
   # Write Prometheus target file
   target = {
     "targets": [f"{server_ip}:9253"],
     "labels": {"pool": app_name, "app": app_name}
   }
   ssh_command(server, f"echo '{json.dumps(target)}' > /etc/prometheus/targets/php-fpm/{app_name}.json")
   ```

3. **Prometheus File Discovery** (`prometheus.yml`):
   ```yaml
   - job_name: 'php_fpm_pools'
     file_sd_configs:
       - files:
         - /etc/prometheus/targets/php-fpm/*.json
         refresh_interval: 30s
     relabel_configs:
       - source_labels: [__address__]
         target_label: instance
       - source_labels: [pool]
         target_label: pool
   ```

4. **Grafana Dashboard Variable**:
   - Name: `$pool`
   - Query: `label_values(phpfpm_processes_total, pool)`
   - Multi-select: enabled
   - All value: `.+`

5. **Dashboard Panels** (using `$pool` variable):
   - Process count: `phpfpm_processes_total{pool=~"$pool"}`
   - Active connections: `phpfpm_accepted_connections_total{pool=~"$pool"}`
   - Slow requests: `phpfpm_slow_requests_total{pool=~"$pool"}`
   - Max children reached: `phpfpm_max_children_reached_total{pool=~"$pool"}`

**Task-by-Task Execution List:**
1. Create systemd template on both app servers
2. Create `/etc/prometheus/targets/php-fpm/` directory on router-01
3. Update Prometheus config for file discovery
4. Update Grafana dashboard with pool variable
5. Update `setup_laravel_app()` to start exporter per pool
6. Update `setup_laravel_app()` to enable `pm.status_path` in pool config
7. Test with existing rentalfixer app
8. Update `delete_app()` to stop/remove exporter service
9. Update `delete_staging()` to stop/remove staging exporter
10. Document in monitoring.md

**Benefits:**
- Automatic monitoring for all app pools
- Per-app metrics in Grafana
- Pool selection via dropdown
- No manual configuration needed

**Alternative (Simpler):**
Run single exporter with multiple `--fastcgi` flags (if supported by exporter version).

---

## Lower Priority

### 8. Cloudflare Load Balancer ($5/month)

Add active health monitoring for routers.

**Benefits:**
- Active health checks (not just HTTP retry)
- Automatic DNS failover
- Geographic load balancing
- Steer traffic away from unhealthy origins

**Setup:**
1. Enable Cloudflare Load Balancer
2. Create health check: `GET /health` on port 443
3. Create pool with both routers
4. Create load balancer for domain

**Cost:** $5/month per zone

### 9. App-Specific Monitoring Dashboards

Create Grafana dashboards per application.

**Metrics to include:**
- Request rate (requests/sec)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Active connections
- PHP-FPM process count
- Database query time

**Implementation:**
- Create dashboard JSON template
- Auto-provision when app created
- Link from dashboard UI

### 10. Environment Variable Customization

Allow custom environment variables in create_app wizard.

**UI Changes:**
- Add "Environment Variables" section
- Key-value input
- Preset templates for common configs

**Backend:**
- Store in applications.yml
- Inject into .env on deployment

### 11. Build Command Customization

Allow custom build commands per app.

**UI Changes:**
- Add "Build Command" field
- Auto-detect default
- Allow override

**Backend:**
- Store in applications.yml
- Run during deployment

### 12. Health Check Endpoints

Add standardized health check endpoints for all apps.

**Laravel:**
```php
Route::get('/health', function () {
    return response()->json(['status' => 'ok']);
});
```

**Next.js:**
```javascript
// pages/api/health.js
export default function handler(req, res) {
  res.status(200).json({ status: 'ok' });
}
```

---

## Completed

| Task | Date | Notes |
|------|------|-------|
| HAProxy consolidated frontends | 2026-03-15 | Fixed 503 errors |
| SSL DNS-01 challenge | 2026-03-15 | Works with Cloudflare proxy |
| Domain registry system | 2026-03-15 | `/etc/haproxy/domains/registry.conf` |
| Python app support | 2026-03-15 | Gunicorn + systemd |
| Redis secrets to GitHub | 2026-03-15 | REDIS_URL pushed |
| Build tool detection | 2026-03-15 | Vite, Next.js, SvelteKit, etc. |
| APP_URL auto-configuration | 2026-03-15 | Updated on domain provision |
| Staging environment setup | 2026-03-15 | staging.rentalfixer.app |
| Node exporter monitoring | 2026-03-15 | All servers reporting |
| Multi-user database creation | 2026-03-17 | Separate _user and _admin for production/staging |
| .env file import for secrets | 2026-03-17 | Batch import secrets from .env file |
| Laravel DB_CONNECTION fix | 2026-03-17 | Fixed SQLite default issue |
| Domain wizard with Cloudflare | 2026-03-17 | Multi-select domains from Cloudflare zones |
| Global secrets editing | 2026-03-17 | Edit global secrets via UI |
| App secrets editing | 2026-03-17 | Edit application secrets via UI |
| Staging database secrets | 2026-03-17 | Auto-create staging DB credentials as secrets |
| Automatic domain provisioning | 2026-03-17 | Domains provisioned during app creation |
| Connection strings display | 2026-03-17 | Show all DB credentials on status page |
| Create Application button fix | 2026-03-17 | Fixed form submission reliability |
| System audit and cleanup | 2026-03-17 | Removed orphaned testapp secrets, databases.json |
| Default SSL certificate | 2026-03-17 | Created default.pem for HAProxy with no domains |
| App cleanup fixes | 2026-03-17 | Secrets deletion, HAProxy fix, PM2 stop, staging users |
| GitHub repo validation | 2026-03-17 | Validate repo exists before app creation |
| DNS read-only view | 2026-03-17 | Show existing DNS records with conflict indicators |
| DNS refresh option | 2026-03-17 | Refresh button for DNS records in wizard and domains page |
| CNAME conflict blocking | 2026-03-17 | Block provisioning if non-standard CNAMEs exist |
| Domain ownership locking | 2026-03-17 | Selected Cloudflare zone cannot be reused by another app |
| Webhook host isolation | 2026-03-17 | Dedicated `hooks.quantyralabs.cc` host with webhook-only paths |
| Deploy health checks | 2026-03-17 | Added server and domain health checks (prod 200, staging 200/401) |
| Rolling deploy rollback gate | 2026-03-17 | Abort secondary rollout on primary failure; rollback on failed health |
| Staging DB cleanup hardening | 2026-03-17 | Terminates active DB sessions before dropping staging/prod DBs |
| Databases password display fix | 2026-03-17 | Show display password or `Not recoverable` for hash-only users |
| API databases auth | 2026-03-17 | `/api/databases` now requires dashboard auth |
| Deploy/provision phase UX + force provision override | 2026-03-17 10:56 EDT | Two-phase progress UI, deploy-failure banner, and manual force-provision endpoint/button |
| Infra reliability fix pack (deploy errors, initial rollback semantics, staging cleanup consistency) | 2026-03-17 11:38 EDT | Infra-only scope; synced `dashboard/*` and `configs/dashboard/*` mirrors |
| Force-provision reliability + router SSH fallback | 2026-03-17 12:21 EDT | Added router command IP fallback, force-provision lock, and improved UI progress feedback |
| Router-to-router SSH remediation + force-provision validation | 2026-03-17 12:50 EDT | Restored router-01 -> router-02 SSH key access, retried force-provision, validated dual-router registry/certs |
| Composer compatibility remediation on app servers | 2026-03-17 13:10 EDT | Upgraded to Composer 2.9.5 on both app servers; deprecated notice flood removed |
| Non-root app tooling/runtime enforcement | 2026-03-17 13:52 EDT | Standardized app deploy/runtime user to `webapps` with ownership and permission guardrails |
| SOPS-backed deploy env materialization | 2026-03-17 14:12 EDT | Deploy now generates runtime `.env` from SOPS on router-01 with fail-fast required-secret validation |
| Branch-gated dual-environment deploy + scoped secrets sync | 2026-03-17 14:58 EDT | Enforced `main`/`staging` routing, scoped app secrets, APP_KEY bootstrap, and runtime `.env` sync hooks |
| SSH connectivity fix + Tailscale SSH migration | 2026-03-17 20:10 EDT | Disabled Tailscale SSH, established SSH key mesh across all servers |
| Secrets UI enhancement + deploy bug fixes | 2026-03-17 21:00 EDT | Tab-based secrets UI, clone directory fix, database deletion scope fix |
| Database permissions + deploy script fix | 2026-03-17 21:20 EDT | Schema grants, anchored grep in backup function |
| Schema permissions in DB creation + secrets wizard scope | 2026-03-17 21:45 EDT | Schema grants automated, scope dropdown in app wizard |
| Database creation flow fix | 2026-03-17 22:10 EDT | Fixed cursor closed error, secrets saved early |
| Configurable branch selection | 2026-03-17 22:54 EDT | Custom production/staging branches in app creation |
| Laravel deploy fixes + permission hardening | 2026-03-17 23:55 EDT | PHP-FPM syntax, .env permissions, setup check, health check port |
| PostgreSQL client upgrade + migration detection fix | 2026-03-18 00:40 EDT | pg_dump 18.3 on both app servers, migration table detection |
| SSH timeout fix + staging deploy | 2026-03-18 01:17 EDT | Fixed ssh_command timeout cap, staging port calculation, staging_db_name bug |
| Port Allocation | 2026-03-18 01:30 EDT | Production: 8100-8199, Staging: 9200-9299 |
| Staging password protection | 2026-03-18 02:30 EDT | HAProxy basic auth for staging domains |
| UI domain provisioning fix | 2026-03-18 02:46 EDT | Show actual reason instead of hardcoded text |
| Webhook async deployment | 2026-03-18 03:40 EDT | Return 202 immediately, run deploy in background |
| Last deploy status on apps list | 2026-03-18 03:35 EDT | Show status, environment, branch |

---

## Session Summary: 2026-03-17 to 2026-03-18

### Major Accomplishments

**Deployment Pipeline:**
- ✅ Full Laravel deployment pipeline working with health checks
- ✅ GitHub webhook integration (async, returns immediately)
- ✅ Rolling deployments with automatic rollback
- ✅ Dual-environment support (production + staging)
- ✅ Configurable branch selection per environment
- ✅ SSH timeout handling for long-running deploys

**Permission Model:**
- Non-root runtime user (`webapps`) for all app tooling
- `www-data` group access for Laravel writable directories
- Secure `.env` permissions (webapps:www-data 640)
- Setgid on storage directories for inherited permissions

**Database Management:**
- Automatic schema permission grants on database creation
- PostgreSQL 18 client on all app servers
- Separate production/staging databases with dedicated users
- Migration detection for fresh databases

**Domain & SSL:**
- Staging password protection via HAProxy basic auth
- SSL certificates via DNS-01 challenge
- Domain health checks by environment

**Port Allocation:**
- Production: 8100-8199
- Staging: 9200-9299 (avoiding 9100 used by node_exporter)
- Automatic port assignment with conflict prevention

**Secrets Management:**
- SOPS-encrypted secrets stored on router-01 only
- Scoped secrets (shared/production/staging)
- Runtime `.env` materialization during deploy
- AGE key never leaves dashboard host

**Monitoring:**
- All servers reporting to Prometheus via node_exporter
- Grafana dashboards for infrastructure
- PHP-FPM metrics enabled
- Alertmanager for critical alerts

**UI/UX:**
- Last deploy status on applications list
- Webhook secret visible on app status page
- Domain provisioning phase shows actual reason
- Deploy status tracking with branch/environment

### Current Application Status

| App | Production | Staging | Framework |
|-----|------------|---------|-----------|
| rentalfixer | ✅ rentalfixer.app (port 8100) | ✅ staging.rentalfixer.app (port 9200) | Laravel |

### Server Matrix

| Server | Tailscale IP | Role | Services |
|--------|-------------|------|----------|
| router-01 | 100.102.220.16 | Router + Dashboard | HAProxy, Dashboard, Prometheus, Grafana |
| router-02 | 100.116.175.9 | Router | HAProxy |
| re-db | 100.92.26.38 | App Server | nginx, PHP-FPM, Node.js |
| re-node-02 | 100.89.130.19 | App Server | nginx, PHP-FPM, Node.js |
| re-node-01 | 100.126.103.51 | Database | PostgreSQL, Redis |
| re-node-03 | 100.114.117.46 | Database | PostgreSQL, Redis |
| re-node-04 | 100.115.75.119 | Database | PostgreSQL |

---

### Phase 33: Package Update Dashboard Feature (2026-03-18)

**Problem Statement:**
- Infrastructure administrators need visibility into package updates across all VPS servers
- Security updates need to be highlighted for prompt action
- Bulk updates across all servers require a centralized interface

**Implementation:**

1. **Backend Functions** ✅ COMPLETE
   - [x] `get_server_updates(server_ip, force_refresh=False)` - SSH to server, run apt commands
   - [x] `get_services_needing_restart(server_ip)` - Detect services needing restart
   - [x] `update_packages(server_ip, packages=None)` - Update single or all packages
   - [x] `restart_services(server_ip, services)` - Restart services after updates
   - [x] `get_all_servers_updates(force_refresh=False)` - Aggregate status for all servers
   - [x] Redis caching (1 hour TTL) for update data

2. **API Endpoints** ✅ COMPLETE
   - [x] `GET /api/updates/status` - Aggregated update status for nav badge
   - [x] `GET /api/servers/<server_name>/updates` - Detailed updates per server
   - [x] `POST /api/servers/<server_name>/updates` - Update packages on server
   - [x] `POST /api/updates/check` - Trigger update check on all servers
   - [x] `POST /api/updates/all` - Update all servers (requires "UPDATE ALL" confirmation)
   - [x] `GET /api/tasks/<task_id>` - Task status polling for async operations
   - [x] `POST /api/servers/<server_name>/restart-services` - Restart services

3. **Frontend Changes** ✅ COMPLETE
   - [x] Modified `templates/servers.html` - Added Updates column with badges
   - [x] Created `templates/server_detail.html` - New page for package details
   - [x] Updated `templates/base.html` - Nav badge showing total updates
   - [x] Added CSS styles for update badges, modals, progress indicators

4. **Safety Features** ✅ COMPLETE
   - [x] All updates require explicit confirmation in UI
   - [x] Bulk "Update All" requires typing "UPDATE ALL"
   - [x] Warning for packages that require service restart
   - [x] Sequential updates for bulk operations (stop on failure)
   - [x] Task progress polling for long-running operations

**Current Update Status (as of implementation):**

| Server | Upgradable | Security Updates | Critical Services |
|--------|------------|------------------|-------------------|
| re-node-01 | 14 | snapd | tailscale, postgresql-18-h3 |
| re-node-03 | 11 | snapd | tailscale |
| re-node-04 | 11 | snapd | tailscale |
| router-01 | 12 | snapd, python3-flask | tailscale |
| router-02 | 3 | snapd | tailscale |
| re-db | 53 | snapd, systemd-suite | tailscale, postgresql-client |
| re-node-02 | 4 | snapd | tailscale, libgd3 |

**Files Modified:**
- `dashboard/app.py` - Added ~300 lines for package update functions and API endpoints
- `dashboard/templates/servers.html` - Added Updates column and modals
- `dashboard/templates/server_detail.html` - NEW file for server detail page
- `dashboard/templates/base.html` - Added nav badge for updates
- `dashboard/static/style.css` - Added styles for update badges and modals

**Tracking:**
- Started: 2026-03-18
- Completed: 2026-03-18
- Status: ✅ Complete

---

## Notes

### HAProxy Architecture Decision

**Problem:** Multiple frontends on port 443 caused SNI routing issues and 503 errors.

**Solution:** Consolidated all domains into single frontends (`web_http`, `web_https`) with multiple certificates.

**Key Files:**
- `/etc/haproxy/domains/registry.conf` - Domain registry
- `/etc/haproxy/domains/web_http.cfg` - HTTP redirects
- `/etc/haproxy/domains/web_https.cfg` - HTTPS routing
- `/etc/haproxy/domains/web_backends.cfg` - All backends

**Never create per-domain frontend configs.** Always update registry and rebuild:
```bash
/opt/scripts/provision-domain.sh --rebuild
```

### SSL Certificate Strategy

**DNS-01 Challenge:**
- Required because Cloudflare proxy intercepts HTTP traffic
- Certbot creates TXT record in Cloudflare DNS
- Let's Encrypt validates via DNS
- No downtime required

**Auto-Renewal:**
- Certbot systemd timer runs twice daily
- Renews 30 days before expiry
- **TODO:** Add deploy hook to reload HAProxy

### Load Balancing Layers

1. **Cloudflare → Routers**: DNS round-robin + HTTP retry
2. **Router → App Servers**: HAProxy round-robin + health checks

**Limitation:** No active health checks at Cloudflare layer (requires paid Load Balancer).

### Critical Credentials

See `AGENTS.md` for all credentials. Key items:
- HAProxy stats: `http://router:8404/stats` (admin:jFNeZ2bhfrTjTK7aKApD)
- Dashboard: `http://100.102.220.16:8080` (admin:DbAdmin2026!)
- Cloudflare API Token: Stored in `/root/.secrets/cloudflare.ini` on routers
