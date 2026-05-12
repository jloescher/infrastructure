# Coolify Deployment Tuning

> Fixes applied to make Laravel Dockerfile builds deploy reliably via Coolify v4.
>
> **Date**: 2026-05-12

## Problem

Deployments of `jloescher/jonathanloescher` (Laravel, Dockerfile build pack) failed with two distinct issues:

1. **Build stage target**: The Dockerfile (`/Dockerfile.optimized`) is multi-stage with a `production` stage that includes a `HEALTHCHECK` directive. Coolify's `dockerfile_target_build` was `null`, so Coolify used the default stage which had no healthcheck. This caused `docker inspect ... State.Health` to return "map has no entry for key Health" and the rolling update failed.

2. **Layer extraction timeout**: Build completed all steps and exported layers, but failed during unpacking to the local image store with `failed to extract layer ...: context canceled`. Root cause was Docker daemon BuildKit I/O contention during large (265MB+) layer extraction with no throttling configured.

3. **Wrong Traefik port**: `ports_exposes` was `3000` but the production container listens on port 80. Traefik routed to port 3000 → 502 Bad Gateway.

4. **Secrets baked into build**: All 63 env vars were marked `is_buildtime: true`, meaning they were injected as `--build-arg` flags. Only a few (APP_ENV, APP_KEY, APP_URL, APP_NAME, VITE_APP_NAME) are needed at build time.

5. **Single-server deployment**: App was only on re-db (server 0). HAProxy load balances TCP across both re-db and re-node-02, but re-node-02 returned 503 because it had no app container.

## Changes Applied

### 1. Docker Daemon Configuration

**File**: `/etc/docker/daemon.json` on **re-db** and **re-node-02**

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "default-address-pools": [
    {"base":"10.0.0.0/8","size":24}
  ],
  "max-concurrent-uploads": 1,
  "max-concurrent-downloads": 1,
  "builder": {
    "gc": {
      "enabled": true,
      "defaultKeepStorage": "10GB"
    }
  }
}
```

| Setting | Before | After | Reason |
|---------|--------|-------|--------|
| `max-concurrent-uploads` | (default) | `1` | Reduce I/O contention during layer export |
| `max-concurrent-downloads` | (default) | `1` | Reduce I/O contention during layer pull |
| `builder.gc.defaultKeepStorage` | (default) | `10GB` | Prevent BuildKit cache eviction mid-build |

**Note**: re-node-02 also has `"metrics-addr": "0.0.0.0:9323"` for Prometheus Docker metrics.

Docker was restarted on both servers after changes. All Coolify containers returned healthy.

### 2. Coolify Application Settings (via Tinker/DB)

| Setting | Before | After | Coolify DB Column |
|---------|--------|-------|-------------------|
| Dockerfile target build | `null` | `production` | `applications.dockerfile_target_build` |
| Exposed port | `3000` | `80` | `applications.ports_exposes` |
| Traefik labels | port 3000 | port 80 | `applications.custom_labels` (base64) |

**Commands used** (via `docker exec coolify php artisan tinker`):

```php
// Set build target to production stage
$a = \App\Models\Application::find(1);
$a->dockerfile_target_build = "production";
$a->save();

// Fix exposed port
$a->ports_exposes = "80";
$a->save();

// Regenerate Traefik labels with correct port
$customLabels = str(implode("|coolify|", generateLabelsApplication($a)))->replace("|coolify|", "\n");
$a->custom_labels = base64_encode($customLabels);
$a->save();
```

### 3. Environment Variables: Build-Time vs Runtime

| Metric | Before | After |
|--------|--------|-------|
| Build-time env vars | 63 | 5 |
| Runtime-only env vars | 0 | 58 |

**Build-time (kept)**: `APP_NAME`, `APP_ENV`, `APP_KEY`, `APP_URL`, `VITE_APP_NAME`

**Runtime-only (moved)**: All database credentials, AWS keys, mail secrets, LLM keys, Google OAuth, etc.

This reduces the number of `--build-arg` flags passed to `docker build`, reducing build context size and preventing secrets from being baked into image history.

**Command used**:

```php
$a = \App\Models\Application::find(1);
$buildOnlyKeys = ["APP_NAME","APP_ENV","APP_KEY","APP_URL","VITE_APP_NAME"];
$envs = $a->environment_variables()->where("is_buildtime", true)->get();
foreach ($envs as $e) {
    if (!in_array($e->key, $buildOnlyKeys)) {
        $e->is_buildtime = false;
        $e->save();
    }
}
```

### 4. Multi-Server Deployment

Added re-node-02 as an additional deployment destination:

```php
// Insert additional destination record
\DB::table("additional_destinations")->updateOrInsert(
    ["application_id" => 1, "server_id" => 1],
    ["standalone_docker_id" => 1, "status" => "exited", "updated_at" => now()]
);
```

Both servers now receive deployments independently (each builds its own image).

### 5. Server Timeouts

Both servers already had `dynamic_timeout: 3600` (1 hour) — verified sufficient. Coolify's SSH command timeout is also 3600s (`config('constants.ssh.command_timeout')`). No changes needed.

## Verification

### Build Success

```
#39 exporting layers 0.3s done         # (was 16.8s, faster with caching)
#39 exporting manifest ... done
#39 exporting config ... done
#39 unpacking ... 14.3s done           # (was failing with "context canceled")
#39 DONE 14.9s
```

### Health Check

```
Custom healthcheck found in Dockerfile.
Waiting for the start period (60 seconds) before starting healthcheck.
Attempt 1 of 3 | Healthcheck status: "healthy"
New container is healthy.
Rolling update completed.
```

### Public URL

```
$ curl -sI https://jonathanloescher.com
HTTP/2 200
content-type: text/html; charset=utf-8
server: nginx/1.28.3
```

### Both Servers

| Server | Container | Status | Health |
|--------|-----------|--------|--------|
| re-db (100.92.26.38) | `a128ztjhsepr68uvluz06lpm-*` | Up | healthy |
| re-node-02 (100.89.130.19) | `a128ztjhsepr68uvluz06lpm-*` | Up | healthy |

## Coolify Settings Reference

| Setting | UI Location | Value |
|---------|-------------|-------|
| Build Pack | Configuration → General | `dockerfile` |
| Dockerfile Location | Configuration → General | `/Dockerfile.optimized` |
| Base Directory | Configuration → General | `/` |
| Docker Build Stage Target | Configuration → General | `production` |
| Ports Exposes | Configuration → Ports | `80` |
| Domain | Configuration → Domains | `https://jonathanloescher.com` |
| Git Repository | Configuration → Source | `jloescher/jonathanloescher` |
| Git Branch | Configuration → Source | `main` |

## Deployment Workflow

```
1. Coolify clones GitHub repo
   ↓
2. Creates helper container (coolify-helper)
   ↓
3. Generates build.sh with docker build command
   ├── docker build --target production ...
   ├── Only 5 build-arg flags (not 63)
   └── BuildKit enabled (DOCKER_BUILDKIT=1)
   ↓
4. Build completes all stages
   ├── Builder stage: composer install, npm build
   └── Production stage: COPY artifacts, HEALTHCHECK
   ↓
5. Image exported and unpacked
   ↓
6. Rolling update on each server
   ├── Create new container
   ├── Wait for healthcheck (60s start period)
   ├── Verify healthy
   └── Remove old container
   ↓
7. Traefik auto-configures routing
   ├── Host rule: Host(`jonathanloescher.com`)
   ├── Port: 80
   └── SSL: Let's Encrypt DNS-01
   ↓
8. Complete ✅
```

## Troubleshooting

### Build Fails with "context canceled"

1. Check Docker daemon.json has `max-concurrent-uploads: 1` and `max-concurrent-downloads: 1`
2. Prune build cache: `docker builder prune -f`
3. Prune unused images: `docker image prune -f`
4. Check disk space: `df -h /` (need >50GB free for large builds)
5. Check memory: `free -h` (need >10GB available for BuildKit)

### Health Check Fails

1. Verify `dockerfile_target_build` is set to `production` (the stage with HEALTHCHECK)
2. Check container health: `docker inspect <container> --format '{{.State.Health.Status}}'`
3. Check health log: `docker inspect <container> --format '{{json .State.Health}}'`
4. Verify the app starts within the start_period (default 60s)

### 502 Bad Gateway

1. Verify `ports_exposes` matches the port the app listens on inside the container
2. Check Traefik labels: `docker inspect <container> --format '{{json .Config.Labels}}' | python3 -m json.tool | grep port`
3. Test inside container: `docker exec <container> curl -sI http://127.0.0.1:<port>`

### App Only on One Server

1. Check `additional_destinations` table: `docker exec coolify php artisan tinker --execute="echo \App\Models\Application::find(1)->additional_servers->pluck('name');"`
2. Deploy to additional server via Coolify dashboard or Tinker
3. Verify both servers have running containers: `docker ps --filter name=<app-uuid>`
