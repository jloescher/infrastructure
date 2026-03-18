# Dashboard Refactoring Migration Plan

**Status:** Planning Phase (NOT IMPLEMENTED YET)
**Created:** 2026-03-18
**Target:** Refactor `dashboard/app.py` (4,598 lines) into modular structure without breaking existing functionality

---

## Overview

### Current State

- **File:** `dashboard/app.py` - 4,598 lines
- **Composition:** ~50 route handlers, ~150 helper functions, 20+ global variables
- **Issues:** Monolithic structure, difficult to maintain, mixed concerns

### Target State

```
dashboard/
├── __init__.py              # Flask app factory
├── app.py                   # Entry point only
├── config.py                # Configuration constants
├── auth.py                  # Authentication decorators
│
├── models/
│   ├── __init__.py
│   ├── applications.py      # Application CRUD
│   └── databases.py         # Database CRUD
│
├── services/
│   ├── __init__.py
│   ├── ssh.py               # SSH command execution
│   ├── cloudflare.py        # Cloudflare API
│   ├── github.py            # GitHub API & secrets
│   ├── deploy.py            # Deployment orchestration
│   ├── domain.py            # Domain provisioning
│   └── monitoring.py        # Health checks
│
├── routes/
│   ├── __init__.py          # Registers all blueprints
│   ├── main.py              # /, /servers, /docs
│   ├── apps.py              # /apps/*
│   ├── databases.py         # /databases/*
│   ├── secrets.py           # /secrets/*
│   ├── settings.py          # /settings/*
│   ├── webhooks.py          # /api/webhooks/*
│   └── api.py               # /api/* endpoints
│
├── templates/               # Unchanged
├── static/                  # Unchanged
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── pytest.ini
    ├── test_config.py
    ├── test_auth.py
    ├── test_models/
    ├── test_services/
    ├── test_routes/
    ├── benchmarks/
    └── benchmark_results/
```

---

## Migration Principles

### Non-Negotiable Requirements

1. **Zero Breaking Changes** - All existing functionality must continue to work
2. **Test-First Approach** - Create tests before migrating any code
3. **90% Test Coverage** - Minimum coverage threshold
4. **Mock External Services** - No real database/API calls in tests
5. **Performance Benchmarks** - Track and prevent regressions
6. **Incremental Deployment** - One phase at a time with verification
7. **Rollback Strategy** - Every phase has clean rollback

### Testing Strategy

- **Local Tests First:** All tests pass locally before deployment
- **Live Tests Second:** Test against deployed system after each phase
- **Manual Verification:** Human verification of critical paths
- **Coverage Enforcement:** Build fails if coverage < 90%

---

## Pre-Phase 0: Test Suite Creation

**Duration:** 3-4 hours
**Risk:** None (no code migration yet)

### Objectives

Create comprehensive test suite that validates current behavior before any refactoring.

### Deliverables

#### Test Framework Files

```
dashboard/tests/
├── __init__.py
├── conftest.py                    # Central fixtures
├── pytest.ini                     # Pytest configuration
│
├── test_config.py                 # Config loading tests
├── test_auth.py                   # Authentication tests
│
├── test_models/
│   ├── __init__.py
│   ├── test_applications.py       # Application CRUD tests
│   └── test_databases.py          # Database CRUD tests
│
├── test_services/
│   ├── __init__.py
│   ├── test_ssh.py                # SSH command tests
│   ├── test_cloudflare.py         # Cloudflare API tests
│   ├── test_github.py             # GitHub API tests
│   ├── test_deploy.py             # Deployment tests
│   ├── test_domain.py             # Domain provisioning tests
│   └── test_monitoring.py         # Health check tests
│
├── test_routes/
│   ├── __init__.py
│   ├── test_main.py               # Main route tests
│   ├── test_apps.py               # App route tests
│   ├── test_databases.py          # Database route tests
│   ├── test_secrets.py            # Secrets route tests
│   ├── test_settings.py           # Settings route tests
│   └── test_webhooks.py           # Webhook route tests
│
├── benchmarks/
│   ├── __init__.py
│   ├── bench_routes.py            # Route response benchmarks
│   └── bench_deploy.py            # Deploy time benchmarks
│
└── benchmark_results/
    └── .gitkeep
```

#### Configuration Files

**requirements-test.txt:**
```
pytest>=7.0.0
pytest-mock>=3.10.0
pytest-benchmark>=4.0.0
pytest-cov>=4.0.0
responses>=0.23.0
freezegun>=1.2.0
```

**pytest.ini:**
```ini
[pytest]
testpaths = dashboard/tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --cov=dashboard
    --cov-report=term-missing
    --cov-report=html:dashboard/tests/coverage
    --cov-fail-under=90
benchmark_storage = file
benchmark_storage_location = dashboard/tests/benchmark_results
```

### Fixture Categories

#### Configuration Fixtures
- `test_config` - Test configuration values
- `mock_env` - Mock environment variables
- `app` - Flask app instance
- `client` - Test client

#### External Service Mocks
- `mock_ssh_success` - Successful SSH command
- `mock_ssh_failure` - Failed SSH command
- `mock_ssh_timeout` - SSH timeout
- `mock_cloudflare_api` - Cloudflare API responses
- `mock_github_api` - GitHub API responses
- `mock_patroni` - PostgreSQL connection to Patroni (mocked, no real DB)
- `mock_redis` - Redis connection
- `mock_prometheus` - Prometheus API

#### Test Data Fixtures
- `sample_app` - Sample application config
- `sample_database` - Sample database config
- `sample_domain` - Sample domain config
- `temp_applications_file` - Temporary YAML file
- `temp_databases_file` - Temporary YAML file

#### Auth Fixtures
- `auth_headers` - Basic auth headers
- `webhook_signature` - HMAC signature generator

#### Benchmark Fixtures
- `benchmark_thresholds` - Performance thresholds
- `store_benchmark_result` - Store benchmark JSON

### Test Categories

#### Unit Tests (Fast, Isolated)
- Config loading
- Helper functions with mocked dependencies
- Data transformations

#### Integration Tests (Slower, Some Dependencies)
- Model operations with temporary YAML files
- Service functions with mocked external calls
- Route handlers with mocked services

#### End-to-End Tests (Full Stack)
- Create application → deploy → verify
- Webhook → deploy → health check

### Performance Thresholds

| Metric | Threshold |
|--------|-----------|
| Dashboard load | < 2000ms |
| Apps list | < 500ms |
| App status | < 500ms |
| Create app | < 1000ms |
| Webhook response | < 1000ms |
| Deploy total | < 300s |
| Domain provision | < 120s |

### Success Criteria

- [ ] All test files created
- [ ] `pytest dashboard/tests/` runs successfully
- [ ] Initial coverage measured
- [ ] Benchmarks execute successfully
- [ ] Baseline results stored in `benchmark_results/`

---

## Phase A: Config Extraction

**Duration:** 1-2 hours
**Risk:** Zero (only moving constants)

### What Gets Extracted

Lines 29-90 from `app.py`:
- `AUTH_USER`, `AUTH_PASS`, `SECRET_KEY`
- `GITHUB_TOKEN`, `CLOUDFLARE_API_TOKEN`
- `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_PASSWORD`
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`
- `PROMETHEUS_URL`, `GRAFANA_URL`
- `WEBHOOK_PUBLIC_HOST`, `PUBLIC_BASE_URL`
- `BASE_DIR`, `DB_CONFIG_PATH`, `APPS_CONFIG_PATH`
- `ROUTERS`, `APP_SERVERS`, `APP_PORT_RANGE`
- Configuration loading from `.env` file

### Migration Steps

1. Run baseline tests
   ```bash
   pytest dashboard/tests/ -v --cov=dashboard > baseline_phase_a.txt
   ```

2. Create `dashboard/config.py` with extracted constants

3. Modify `dashboard/app.py` to import from config:
   ```python
   from config import *
   ```

4. Run tests
   ```bash
   pytest dashboard/tests/ -v --cov=dashboard > results_phase_a.txt
   ```

5. Compare results
   ```bash
   diff baseline_phase_a.txt results_phase_a.txt
   ```

6. Verify coverage >= 90%

7. Deploy to router-01

8. Run live tests

### Verification Checklist

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Coverage >= 90%
- [ ] Dashboard loads
- [ ] Login works
- [ ] Config values correct

### Rollback

```bash
git revert HEAD
# Or restore backup
cp backups/app.py.phase_A dashboard/app.py
```

---

## Phase B: SSH + Cloudflare + GitHub Services

**Duration:** 2-3 hours
**Risk:** Low (independent services, no interdependencies)

### What Gets Extracted

**services/ssh.py:**
- `ssh_command()` - Line 423
- `run_local_command()` - Line 502
- `run_router_command()` - Line 512
- `run_as_app_user()` - Line 469
- `resolve_public_ip()` - Line 414

**services/cloudflare.py:**
- `cf_api_request()` - Line 3163
- `cf_list_zones()` - Line 3190
- `cf_create_dns_record()` - Line 3213
- `cf_delete_dns_record()` - Line 3229
- `cf_replace_a_records()` - Line 3241
- `cf_list_dns_records()` - Line 3258
- `cf_check_dns_conflicts()` - Line 3284
- `cf_create_firewall_rule()` - Line 3322
- `cf_create_security_rules()` - Line 3343

**services/github.py:**
- `parse_github_repo()` - Line 1246
- `encrypt_secret()` - Line 1261
- `get_github_public_key()` - Line 1272
- `set_github_secret()` - Line 1293
- `delete_github_secret()` - Line 1325
- `list_github_secrets()` - Line 1345
- `push_app_secrets_to_github()` - Line 1366
- `validate_github_repo()` - Line 3434

### Migration Steps

1. Run baseline tests

2. Create service directories
   ```bash
   mkdir -p dashboard/services
   touch dashboard/services/__init__.py
   ```

3. Create `services/ssh.py` with SSH functions

4. Create `services/cloudflare.py` with Cloudflare functions

5. Create `services/github.py` with GitHub functions

6. Update imports in `app.py`:
   ```python
   from services.ssh import ssh_command, run_local_command, run_router_command
   from services.cloudflare import cf_api_request, cf_list_zones, ...
   from services.github import parse_github_repo, encrypt_secret, ...
   ```

7. Run all tests

8. Run benchmarks

9. Deploy and test

### Verification Checklist

- [ ] SSH tests pass
- [ ] Cloudflare tests pass
- [ ] GitHub tests pass
- [ ] Coverage >= 90%
- [ ] Domain provisioning works
- [ ] GitHub secrets work
- [ ] Webhook deploy works

---

## Phase C: Models Extraction

**Duration:** 2-3 hours
**Risk:** Medium (data access layer)

### What Gets Extracted

**models/applications.py:**
- `load_applications()` - Line 244
- `save_applications()` - Line 262
- `ensure_app_domain_schema()` - Line 364
- `get_reserved_base_domains()` - Line 398
- `get_deploy_target_name()` - Line 1084
- `get_app_base_url()` - Line 1076

**models/databases.py:**
- `load_databases()` - Line 229
- `save_databases()` - Line 237
- `get_pg_databases()` - Line 1404
- `terminate_db_connections()` - Line 1420
- `drop_database_safely()` - Line 1427
- `drop_users_safely()` - Line 1432
- `collect_db_cleanup_targets()` - Line 1449
- `cleanup_database_artifacts()` - Line 1490
- `grant_schema_permissions()` - Line 193

### Migration Steps

1. Run baseline tests

2. Create model directories
   ```bash
   mkdir -p dashboard/models
   touch dashboard/models/__init__.py
   ```

3. Create `models/applications.py`

4. Create `models/databases.py`

5. Update imports in `app.py`

6. Run all tests

7. Deploy and test CRUD operations

### Verification Checklist

- [ ] Application model tests pass
- [ ] Database model tests pass
- [ ] Coverage >= 90%
- [ ] Create app works
- [ ] Delete app works
- [ ] Create database works
- [ ] Delete database works
- [ ] YAML persistence correct

---

## Phase D: Deploy + Domain + Monitoring Services

**Duration:** 4-5 hours
**Risk:** Higher (core deployment logic)

### What Gets Extracted

**services/deploy.py:**
- `run_pull_deploy()` - Line 2426
- `rollback_server_to_commit()` - Line 2418
- `update_last_deploy_status()` - Line 2401
- `run_framework_setup()` - Line 801
- `clone_repo_to_servers()` - Line 538
- `detect_build_tools()` - Line 582
- `get_build_command()` - Line 671
- `get_install_command()` - Line 727
- `run_frontend_build()` - Line 743
- `configure_app_environment()` - Line 1063
- `build_deploy_env_material()` - Line 1103
- `write_runtime_env_to_servers()` - Line 1184
- `sync_runtime_env_for_app()` - Line 1216
- `check_local_app_health()` - Line 2361

**services/domain.py:**
- `provision_pending_domains()` - Line 2256
- `provision_domains_cloudflare()` - Line 3396
- `provision_domain_on_routers()` - Line 3526
- `remove_domain_from_routers()` - Line 3562
- `update_app_url()` - Line 3493
- `check_domain_http_health()` - Line 2347
- `build_domains_from_configs()` - Line 279

**services/monitoring.py:**
- `get_pg_cluster_status()` - Line 1545
- `get_redis_info()` - Line 1561
- `get_prometheus_alerts()` - Line 1579
- `check_server()` - Line 1589
- `check_servers_async()` - Line 1602

### Dependencies

```python
# services/deploy.py
from services.ssh import ssh_command
from services.domain import provision_domain_on_routers
from models.applications import load_applications, save_applications
```

### Migration Steps

1. Run baseline tests

2. Create `services/deploy.py`

3. Create `services/domain.py`

4. Create `services/monitoring.py`

5. Update imports in `app.py`

6. Run all tests including deploy benchmarks

7. Full end-to-end test:
   - Trigger webhook
   - Verify deploy starts
   - Check health checks
   - Verify domain provisioning

8. Deploy and test both production and staging deploys

### Verification Checklist

- [ ] Deploy tests pass
- [ ] Domain tests pass
- [ ] Monitoring tests pass
- [ ] Coverage >= 90%
- [ ] Webhook returns 202 in < 1s
- [ ] Deploy completes in < 5min
- [ ] Health checks pass
- [ ] Production deploy works
- [ ] Staging deploy works
- [ ] Domain provisioning works

---

## Phase E: Routes Extraction (Blueprints)

**Duration:** 3-4 hours
**Risk:** Medium (Flask routing)

### What Gets Extracted

**routes/main.py:**
- `/` (index) - Line 1616
- `/servers` - Line 1729
- `/docs` - Line 4139
- `/docs/<doc_name>` - Line 4150
- `/api/health` - Line 4165
- `/api/alerts` - Line 4176
- `/api/servers` - Line 4188
- `/api/disk-space` - Line 4193

**routes/apps.py:**
- `/apps` - Line 1784
- `/apps/create` - Line 1791
- `/apps/<app_name>/status` - Line 3045
- `/apps/<app_name>/deploy` - Line 2883
- `/apps/<app_name>/delete` - Line 2136
- `/apps/<app_name>/staging/delete` - Line 2197
- `/apps/<app_name>/domains` - Line 3578
- `/apps/<app_name>/domains/<domain>/delete` - Line 3719
- `/apps/<app_name>/github-secrets` - Line 4043
- `/api/apps/<app_name>/restart` - Line 3097
- `/api/apps/<app_name>/reload-nginx` - Line 3118
- `/api/apps/<app_name>/reload-phpfpm` - Line 3128
- `/api/apps/<app_name>/clear-cache` - Line 3138

**routes/databases.py:**
- `/databases` - Line 1639
- `/databases/add` - Line 1655
- `/databases/<db_name>/connection` - Line 1719
- `/databases/<db_name>/delete` - Line 3791

**routes/secrets.py:**
- `/secrets` - Line 4262
- `/secrets/global` - Line 4279
- `/secrets/global/add` - Line 4290
- `/secrets/global/<key>/delete` - Line 4316
- `/secrets/global/<key>/edit` - Line 4332
- `/apps/<app_name>/secrets` - Line 4365
- `/apps/<app_name>/secrets/add` - Line 4386
- `/apps/<app_name>/secrets/<key>/delete` - Line 4427
- `/apps/<app_name>/secrets/<key>/edit` - Line 4452
- `/apps/<app_name>/secrets/<key>/reveal` - Line 4499
- `/apps/<app_name>/secrets/export` - Line 4511
- `/api/secrets/<app_name>` - Line 4556

**routes/settings.py:**
- `/settings` - Line 3964
- `/settings/github-token` - Line 3981
- `/settings/cloudflare` - Line 4000

**routes/webhooks.py:**
- `/api/webhooks/github/<app_name>` - Line 2827
- `/<app_name>` - Line 2828

**routes/api.py:**
- `/api/generate-workflow` - Line 1736
- `/api/cloudflare/zones` - Line 1750
- `/api/cloudflare/zones/<zone_id>/dns` - Line 1760
- `/api/github/validate` - Line 1773
- `/api/apps/<app_name>/deploy` - Line 2690
- `/api/apps/<app_name>/redeploy` - Line 2701
- `/api/apps/<app_name>/rollback` - Line 2710
- `/api/apps/<app_name>/domains/force-provision` - Line 2743
- `/api/databases` - Line 4182

### Blueprint Pattern

```python
# routes/apps.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from auth import requires_auth
from models.applications import load_applications, save_applications

apps_bp = Blueprint('apps', __name__)

@apps_bp.route('/apps')
@requires_auth
def apps():
    applications = load_applications()
    return render_template('apps.html', applications=applications)

# ... other routes
```

### Registration

```python
# routes/__init__.py
from flask import Flask
from .main import main_bp
from .apps import apps_bp
from .databases import databases_bp
from .secrets import secrets_bp
from .settings import settings_bp
from .webhooks import webhooks_bp
from .api import api_bp

def register_blueprints(app: Flask):
    app.register_blueprint(main_bp)
    app.register_blueprint(apps_bp)
    app.register_blueprint(databases_bp)
    app.register_blueprint(secrets_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(api_bp)
```

### Migration Steps

1. Run baseline tests

2. Create route directories
   ```bash
   mkdir -p dashboard/routes
   touch dashboard/routes/__init__.py
   ```

3. Create each route file with blueprint

4. Create `routes/__init__.py` with `register_blueprints()`

5. Update `app.py`:
   ```python
   from routes import register_blueprints
   register_blueprints(app)
   ```

6. Run all tests

7. Run benchmarks

8. Deploy and test every route

### Verification Checklist

- [ ] All route tests pass
- [ ] Coverage >= 90%
- [ ] Dashboard loads
- [ ] All pages accessible
- [ ] All forms submit
- [ ] All API endpoints work
- [ ] Auth works on protected routes
- [ ] Webhook works

---

## Phase F: Auth Extraction + Final Cleanup

**Duration:** 1-2 hours
**Risk:** Low

### What Gets Extracted

**auth.py:**
- `check_auth()` - Line 215
- `requires_auth()` - Line 219

### Final app.py

```python
from flask import Flask
from config import SECRET_KEY
from auth import requires_auth
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = SECRET_KEY

register_blueprints(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Migration Steps

1. Run baseline tests

2. Create `auth.py`

3. Update imports in route files

4. Update `app.py` to minimal entry point

5. Run full test suite

6. Run all benchmarks

7. Deploy and full verification

### Verification Checklist

- [ ] Auth tests pass
- [ ] Full test suite passes
- [ ] Coverage >= 90%
- [ ] All benchmarks within thresholds
- [ ] Complete manual verification

---

## Test Execution Commands

### Run All Tests
```bash
pytest dashboard/tests/ -v
```

### Run With Coverage
```bash
pytest dashboard/tests/ --cov=dashboard --cov-report=term-missing --cov-fail-under=90
```

### Run Specific Category
```bash
pytest dashboard/tests/test_models/ -v
pytest dashboard/tests/test_services/ -v
pytest dashboard/tests/test_routes/ -v
```

### Run Benchmarks
```bash
pytest dashboard/tests/benchmarks/ -v --benchmark-only
```

### Generate Coverage Report
```bash
pytest dashboard/tests/ --cov=dashboard --cov-report=html
open dashboard/tests/coverage/index.html
```

### Compare With Baseline
```bash
pytest dashboard/tests/ -v > results.txt
diff baseline.txt results.txt
```

---

## Manual Verification Checklist

After each phase deployment, verify all items:

### Core Functionality
- [ ] Dashboard loads at http://IP:8080
- [ ] Login with admin credentials works
- [ ] Applications list displays correctly
- [ ] Application status page loads

### Deployment
- [ ] Create new application works
- [ ] Deploy via UI button works
- [ ] Deploy via webhook returns 202
- [ ] Production deploy succeeds
- [ ] Staging deploy succeeds
- [ ] Staging password protection works
- [ ] Domain health checks pass

### Database
- [ ] Create database works
- [ ] Delete database works
- [ ] Connection strings display
- [ ] PostgreSQL cluster status shows

### Domains
- [ ] Domain provisioning works
- [ ] SSL certificates generated
- [ ] DNS records created
- [ ] Domain health green

### Secrets
- [ ] Add global secret works
- [ ] Add app secret works
- [ ] Edit secret works
- [ ] Delete secret works
- [ ] Secrets sync to .env

### Settings
- [ ] Save GitHub token works
- [ ] Save Cloudflare settings works

### Performance
- [ ] Dashboard loads in < 2s
- [ ] Apps list loads in < 500ms
- [ ] App status loads in < 500ms
- [ ] Webhook responds in < 1s
- [ ] Deploy completes in < 5min

---

## Rollback Strategy

### Automated Rollback

Every phase creates a backup:
```bash
# Before each phase
cp dashboard/app.py backups/app.py.phase_X
```

### Rollback Procedure

1. **Revert Git Commit:**
   ```bash
   git revert HEAD
   ```

2. **Restore Backup:**
   ```bash
   cp backups/app.py.phase_X dashboard/app.py
   ```

3. **Redeploy:**
   ```bash
   scp dashboard/app.py root@100.102.220.16:/opt/dashboard/app.py
   ssh root@100.102.220.16 "systemctl restart dashboard"
   ```

4. **Verify:**
   ```bash
   pytest dashboard/tests/ -v
   ```

### Backup Directory Structure

```
backups/
├── app.py.phase_a
├── app.py.phase_b
├── app.py.phase_c
├── app.py.phase_d
├── app.py.phase_e
└── app.py.phase_f
```

---

## Coverage Requirements

### Minimum Coverage: 90%

| Module | Target | Priority |
|--------|--------|----------|
| `app.py` | 90% | Critical |
| `config.py` | 100% | High |
| `auth.py` | 100% | High |
| `models/applications.py` | 90% | Critical |
| `models/databases.py` | 90% | Critical |
| `services/ssh.py` | 85% | High |
| `services/cloudflare.py` | 85% | High |
| `services/github.py` | 85% | High |
| `services/deploy.py` | 90% | Critical |
| `services/domain.py` | 85% | High |
| `services/monitoring.py` | 85% | High |
| `routes/*` | 90% | Critical |

---

## Performance Benchmark Storage

### Directory Structure

```
dashboard/tests/benchmark_results/
├── 2026-03-18_initial/
│   ├── routes_baseline.json
│   └── deploy_baseline.json
├── 2026-03-18_phase_a/
│   ├── routes_results.json
│   └── deploy_results.json
├── ...
└── latest/ -> 2026-03-18_phase_X/
```

### Benchmark Result Format

```json
{
  "benchmark": "route_dashboard_load",
  "timestamp": "20260318_120000",
  "phase": "phase_a",
  "metrics": {
    "min_ms": 45.2,
    "max_ms": 52.1,
    "mean_ms": 48.3,
    "median_ms": 47.8,
    "stddev_ms": 2.1
  },
  "threshold_ms": 2000,
  "passed": true,
  "comparison": {
    "previous_mean_ms": 47.9,
    "delta_ms": 0.4,
    "delta_percent": 0.8
  }
}
```

### Regression Detection

Tests fail if performance regresses > 10% from baseline.

---

## Timeline Summary

| Phase | Duration | Tests | Coverage | Benchmarks | Deploy |
|-------|----------|-------|----------|------------|--------|
| Pre-0 | 3-4 hrs | Create | N/A | Create | No |
| A | 1-2 hrs | Unit + Integration | 90%+ | Routes | Yes |
| B | 2-3 hrs | Unit + Integration | 90%+ | Routes | Yes |
| C | 2-3 hrs | Unit + Integration | 90%+ | Routes | Yes |
| D | 4-5 hrs | Unit + Integration + E2E | 90%+ | Routes + Deploy | Yes |
| E | 3-4 hrs | Unit + Integration + E2E | 90%+ | Routes + Deploy | Yes |
| F | 1-2 hrs | Full Suite | 90%+ | Full | Yes |
| **Total** | **16-23 hrs** | | | | |

---

## Success Criteria

### Phase Complete When

1. All automated tests pass
2. Coverage >= 90%
3. All benchmarks within thresholds
4. Manual verification complete
5. Deployed to router-01
6. Live tests pass

### Migration Complete When

1. All 7 phases complete
2. Full test suite passing
3. Coverage >= 90%
4. All benchmarks within thresholds
5. No behavior changes observed
6. Documentation updated

---

## Risk Assessment

| Phase | Risk Level | Mitigation |
|-------|------------|------------|
| Pre-0 | None | No code changes |
| A | Zero | Only constants moved |
| B | Low | Independent services |
| C | Medium | Test all CRUD |
| D | Higher | Test full deploy pipeline |
| E | Medium | Test every route |
| F | Low | Minimal changes |

---

## Notes

### External Service Mocking

- **PostgreSQL:** Mock `psycopg2.connect()` to Patroni cluster
- **Redis:** Mock `redis.Redis()` client
- **SSH:** Mock `subprocess.run()` for command execution
- **Cloudflare:** Mock `requests.request()` for API calls
- **GitHub:** Mock `requests.get/put()` for API calls
- **Prometheus:** Mock `requests.get()` for API calls

### No Real Database in Tests

Tests do NOT connect to real PostgreSQL. The PaaS provisions apps by connecting to the Patroni cluster, but tests mock this connection.

### Live Testing

After deployment, run tests against the live system to verify real behavior matches expected behavior.

---

## Implementation Status

**Status:** NOT STARTED

This plan is ready for review and approval. Implementation will begin when explicitly requested.

**Pre-requisites before starting:**
- [ ] Plan reviewed and approved
- [ ] All questions answered
- [ ] Git repository in clean state
- [ ] Backup of current working code
- [ ] Time allocated for full testing cycle