#!/bin/bash
# Sync all configurations from production servers to local repo
# Run from infrastructure root directory

# Removed set -e to handle missing files gracefully
# set -e

echo "Syncing configurations from production servers..."

# ==================== HAProxy ====================
echo "=== HAProxy ==="
mkdir -p configs/haproxy/router-01 configs/haproxy/router-02

ssh root@100.102.220.16 "cat /etc/haproxy/haproxy.cfg" > configs/haproxy/router-01/haproxy.cfg
ssh root@100.102.220.16 "cat /etc/haproxy/domains/registry.conf" > configs/haproxy/router-01/registry.conf
ssh root@100.102.220.16 "cat /etc/haproxy/domains/web_http.cfg" > configs/haproxy/router-01/web_http.cfg
ssh root@100.102.220.16 "cat /etc/haproxy/domains/web_https.cfg" > configs/haproxy/router-01/web_https.cfg
ssh root@100.102.220.16 "cat /etc/haproxy/domains/web_backends.cfg" > configs/haproxy/router-01/web_backends.cfg

ssh root@100.116.175.9 "cat /etc/haproxy/haproxy.cfg" > configs/haproxy/router-02/haproxy.cfg
ssh root@100.116.175.9 "cat /etc/haproxy/domains/registry.conf" > configs/haproxy/router-02/registry.conf
ssh root@100.116.175.9 "cat /etc/haproxy/domains/web_http.cfg" > configs/haproxy/router-02/web_http.cfg
ssh root@100.116.175.9 "cat /etc/haproxy/domains/web_https.cfg" > configs/haproxy/router-02/web_https.cfg
ssh root@100.116.175.9 "cat /etc/haproxy/domains/web_backends.cfg" > configs/haproxy/router-02/web_backends.cfg

echo "HAProxy configs synced"

# ==================== Dashboard ====================
# NOTE: Old Flask dashboard removed - now using Coolify
# Dashboard configs no longer exist on router-01
echo "=== Dashboard (Obsolete) ==="
echo "  Skipped - old Flask dashboard removed, using Coolify instead"

# ==================== Provision Scripts ====================
echo "=== Provision Scripts ==="
mkdir -p configs/provision-scripts configs/cloudflare-scripts
ssh root@100.102.220.16 "cat /opt/scripts/provision-domain.sh" > configs/provision-scripts/provision-domain.sh
ssh root@100.102.220.16 "cat /opt/scripts/cloudflare/cloudflare-api.sh" > configs/cloudflare-scripts/cloudflare-api.sh
echo "Provision scripts synced"

# ==================== App Servers ====================
echo "=== App Servers ==="
echo "  Skipped host nginx/php-fpm sync on app servers (Coolify + Docker runtime)"

echo "App server configs synced"

# ==================== PostgreSQL/Patroni ====================
echo "=== PostgreSQL/Patroni ==="
mkdir -p configs/postgres

for node in "100.126.103.51:re-node-01" "100.114.117.46:re-node-03" "100.115.75.119:re-node-04"; do
    ip=$(echo $node | cut -d: -f1)
    name=$(echo $node | cut -d: -f2)
    ssh root@$ip "cat /etc/patroni.yml" > configs/postgres/patroni-$name.yml 2>/dev/null
    ssh root@$ip "cat /etc/patroni/dcs.yml" > configs/postgres/dcs-$name.yml 2>/dev/null
    ssh root@$ip "cat /etc/postgresql/*/main/postgresql.conf 2>/dev/null | grep -v '^#' | grep -v '^$'" > configs/postgres/postgresql-$name.conf 2>/dev/null
done

echo "PostgreSQL configs synced"

# ==================== pgBouncer ====================
echo "=== pgBouncer ==="
mkdir -p configs/pgbouncer
ssh root@100.102.220.16 "cat /etc/pgbouncer/pgbouncer.ini" > configs/pgbouncer/pgbouncer-router-01.ini 2>/dev/null
ssh root@100.102.220.16 "cat /etc/pgbouncer/userlist.txt" | sed 's/".*"/"***"/' > configs/pgbouncer/userlist-router-01.txt.example 2>/dev/null
ssh root@100.116.175.9 "cat /etc/pgbouncer/pgbouncer.ini" > configs/pgbouncer/pgbouncer-router-02.ini 2>/dev/null
ssh root@100.116.175.9 "cat /etc/pgbouncer/userlist.txt" | sed 's/".*"/"***"/' > configs/pgbouncer/userlist-router-02.txt.example 2>/dev/null
echo "pgBouncer configs synced"

# ==================== Prometheus/Grafana ====================
echo "=== Monitoring ==="
mkdir -p configs/prometheus configs/grafana/provisioning/{datasources,dashboards,alerting}

ssh root@100.102.220.16 "cat /etc/prometheus/prometheus.yml" > configs/prometheus.yml 2>/dev/null
ssh root@100.102.220.16 "cat /etc/prometheus/rules/alerts.yml" > configs/prometheus/alerts.yml 2>/dev/null
ssh root@100.102.220.16 "cat /etc/alertmanager/alertmanager.yml" > configs/alertmanager.yml 2>/dev/null

ssh root@100.102.220.16 "cat /etc/grafana/grafana.ini" > configs/grafana/grafana.ini 2>/dev/null

for dir in datasources dashboards alerting; do
    for file in $(ssh root@100.102.220.16 "ls /etc/grafana/provisioning/$dir/*.yml 2>/dev/null"); do
        filename=$(basename "$file")
        ssh root@100.102.220.16 "cat /etc/grafana/provisioning/$dir/$filename" > "configs/grafana/provisioning/$dir/$filename" 2>/dev/null
    done
done

echo "Monitoring configs synced"

# ==================== Certbot ====================
echo "=== Certbot ==="
mkdir -p configs/certbot
for cert in $(ssh root@100.102.220.16 "ls /etc/letsencrypt/renewal/ 2>/dev/null"); do
    ssh root@100.102.220.16 "cat /etc/letsencrypt/renewal/$cert" > "configs/certbot/renewal-router-01-$cert" 2>/dev/null
done
for cert in $(ssh root@100.116.175.9 "ls /etc/letsencrypt/renewal/ 2>/dev/null"); do
    ssh root@100.116.175.9 "cat /etc/letsencrypt/renewal/$cert" > "configs/certbot/renewal-router-02-$cert" 2>/dev/null
done
echo "Certbot configs synced"

# ==================== Systemd ====================
echo "=== Systemd ==="
mkdir -p configs/systemd/certbot
ssh root@100.102.220.16 "cat /etc/systemd/system/haproxy.service.d/override.conf" > configs/systemd/haproxy-override.conf 2>/dev/null
ssh root@100.116.175.9 "cat /etc/systemd/system/haproxy.service.d/override.conf" > configs/systemd/haproxy-override-router-02.conf 2>/dev/null
echo "Systemd configs synced"

# ==================== Logrotate ====================
echo "=== Logrotate ==="
mkdir -p configs/logrotate
ssh root@100.102.220.16 "cat /etc/logrotate.d/haproxy" > configs/logrotate/haproxy 2>/dev/null
echo "Logrotate configs synced"

# ==================== App .env examples ====================
# NOTE: Apps now deployed via Coolify - no manual /opt/apps/ directory
echo "=== App .env examples (Obsolete) ==="
echo "  Skipped - apps now managed by Coolify"

# ==================== Coolify ====================
echo "=== Coolify ==="
mkdir -p configs/coolify/re-db/{traefik,source,proxy-dynamic,applications,ssh}
mkdir -p configs/coolify/re-node-02/{traefik,proxy-dynamic}

# Manager node (re-db) - Traefik docker-compose from Coolify proxy
ssh root@100.92.26.38 "cat /data/coolify/proxy/docker-compose.yml" > configs/coolify/re-db/traefik/docker-compose.yml 2>/dev/null || true

# ACME certificate metadata from manager (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.92.26.38 "stat -c '%a %U %G %s %y' /data/coolify/proxy/acme.json 2>/dev/null" > configs/coolify/re-db/traefik/acme.json.metadata 2>/dev/null || true

# Traefik dynamic configs from manager
for file in $(ssh root@100.92.26.38 "ls /data/coolify/proxy/dynamic/ 2>/dev/null"); do
    ssh root@100.92.26.38 "cat /data/coolify/proxy/dynamic/$file" > "configs/coolify/re-db/proxy-dynamic/$file" 2>/dev/null || true
done

# Coolify source compose files (the Coolify stack definition)
ssh root@100.92.26.38 "cat /data/coolify/source/docker-compose.yml" > configs/coolify/re-db/source/docker-compose.yml 2>/dev/null || true
ssh root@100.92.26.38 "cat /data/coolify/source/docker-compose.prod.yml" > configs/coolify/re-db/source/docker-compose.prod.yml 2>/dev/null || true

# Coolify source .env (sanitize secrets)
ssh root@100.92.26.38 "cat /data/coolify/source/.env" | grep -vE "^(DB_PASSWORD|REDIS_PASSWORD|PUSHER_SECRET|PUSHER_KEY|APP_KEY|HONEYBADGER_API_KEY|SESSION_PASSWORD|METRICS_API_TOKEN|CUSTOM_CONFIG_SCRIPT|HOSTED_MIEL)" > configs/coolify/re-db/source/.env.example 2>/dev/null || true

# Coolify database dump (full state: apps, env vars, domains, servers, settings)
ssh root@100.92.26.38 "docker exec coolify-db pg_dump -U coolify coolify --clean --if-exists" > configs/coolify/re-db/coolify-db.dump.sql 2>/dev/null || true

# Application docker-compose and .env files per deployed app
for app_dir in $(ssh root@100.92.26.38 "ls -d /data/coolify/applications/*/ 2>/dev/null"); do
    app_uuid=$(basename "$app_dir")
    mkdir -p "configs/coolify/re-db/applications/$app_uuid"
    ssh root@100.92.26.38 "cat /data/coolify/applications/$app_uuid/docker-compose.yaml" > "configs/coolify/re-db/applications/$app_uuid/docker-compose.yaml" 2>/dev/null || true
    ssh root@100.92.26.38 "cat /data/coolify/applications/$app_uuid/README.md" > "configs/coolify/re-db/applications/$app_uuid/README.md" 2>/dev/null || true
    # Sanitize .env - strip all secret values, keep key names for reference
    ssh root@100.92.26.38 "cat /data/coolify/applications/$app_uuid/.env 2>/dev/null" | sed -E 's/=.*/=***REDACTED***/' > "configs/coolify/re-db/applications/$app_uuid/.env.example" 2>/dev/null || true
done

# Coolify SSH key fingerprint (public key only, not private key material)
ssh root@100.92.26.38 "ls /data/coolify/ssh/keys/ 2>/dev/null" > configs/coolify/re-db/ssh/keys-manifest.txt 2>/dev/null || true
ssh root@100.92.26.38 "ssh-keygen -l -f /data/coolify/ssh/keys/id.root@host.docker.internal.pub 2>/dev/null || true" > configs/coolify/re-db/ssh/key-fingerprint.txt 2>/dev/null || true

# SSL CA cert
ssh root@100.92.26.38 "cat /data/coolify/ssl/coolify-ca.crt" > configs/coolify/re-db/coolify-ca.crt 2>/dev/null || true

# Worker node (re-node-02) - Traefik docker-compose from Coolify proxy
ssh root@100.89.130.19 "cat /data/coolify/proxy/docker-compose.yml" > configs/coolify/re-node-02/traefik/docker-compose.yml 2>/dev/null || true

# ACME certificate metadata from worker (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.89.130.19 "stat -c '%a %U %G %s %y' /data/coolify/proxy/acme.json 2>/dev/null" > configs/coolify/re-node-02/traefik/acme.json.metadata 2>/dev/null || true

# Traefik dynamic configs from worker
for file in $(ssh root@100.89.130.19 "ls /data/coolify/proxy/dynamic/ 2>/dev/null"); do
    ssh root@100.89.130.19 "cat /data/coolify/proxy/dynamic/$file" > "configs/coolify/re-node-02/proxy-dynamic/$file" 2>/dev/null || true
done

echo "Coolify configs synced"

# ==================== Docker ====================
echo "=== Docker ==="
mkdir -p configs/docker/re-db configs/docker/re-node-02

# Docker daemon configuration from both nodes
ssh root@100.92.26.38 "cat /etc/docker/daemon.json" > configs/docker/re-db/daemon.json 2>/dev/null || true
ssh root@100.89.130.19 "cat /etc/docker/daemon.json" > configs/docker/re-node-02/daemon.json 2>/dev/null || true

echo "Docker daemon configs synced"

# ==================== Docker State ====================
echo "=== Docker State ==="
mkdir -p configs/docker/swarm

# Container/network state from both nodes
ssh root@100.92.26.38 "docker network ls" > configs/docker/swarm/networks.txt 2>/dev/null || true
ssh root@100.92.26.38 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'" > configs/docker/swarm/containers-re-db.txt 2>/dev/null || true
ssh root@100.89.130.19 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'" > configs/docker/swarm/containers-re-node-02.txt 2>/dev/null || true

echo "Docker state synced"

# ==================== Cleanup ====================
find configs/ -size 0 -delete

echo ""
echo "=== Sync complete ==="
echo "Config files synced: $(find configs -type f | wc -l)"
echo ""
echo "Run 'git status' to see changes"
