#!/bin/bash
# Sync all configurations from production servers to local repo
# Run from infrastructure root directory

set -e

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
echo "=== Dashboard ==="
mkdir -p configs/dashboard
ssh root@100.102.220.16 "cat /opt/dashboard/config/.env 2>/dev/null" | sed 's/=.*/=/' > configs/dashboard/.env.example
ssh root@100.102.220.16 "cat /opt/dashboard/config/applications.yml 2>/dev/null" > configs/dashboard/applications.yml
ssh root@100.102.220.16 "cat /opt/dashboard/config/databases.yml 2>/dev/null" > configs/dashboard/databases.yml
ssh root@100.102.220.16 "cat /etc/systemd/system/dashboard.service" > configs/dashboard/dashboard.service

# SQLite database backup
scp -q root@100.102.220.16:/data/paas.db configs/dashboard/paas.db 2>/dev/null || echo "  Warning: Could not sync paas.db"

# Encryption key backup (DO NOT COMMIT TO GIT)
scp -q root@100.102.220.16:/data/vault.key configs/dashboard/vault.key 2>/dev/null || echo "  Warning: Could not sync vault.key"

echo "Dashboard configs synced"

# ==================== Provision Scripts ====================
echo "=== Provision Scripts ==="
mkdir -p configs/provision-scripts configs/cloudflare-scripts
ssh root@100.102.220.16 "cat /opt/scripts/provision-domain.sh" > configs/provision-scripts/provision-domain.sh
ssh root@100.102.220.16 "cat /opt/scripts/cloudflare/cloudflare-api.sh" > configs/cloudflare-scripts/cloudflare-api.sh
echo "Provision scripts synced"

# ==================== App Servers ====================
echo "=== App Servers ==="
mkdir -p configs/app-servers/re-db/nginx-sites configs/app-servers/re-node-02/nginx-sites
mkdir -p configs/app-servers/re-db/php-fpm configs/app-servers/re-node-02/php-fpm

for server in "100.92.26.38:re-db" "100.89.130.19:re-node-02"; do
    ip=$(echo $server | cut -d: -f1)
    name=$(echo $server | cut -d: -f2)
    
    ssh root@$ip "cat /etc/nginx/nginx.conf" > configs/app-servers/$name/nginx.conf
    ssh root@$ip "cat /etc/nginx/sites-enabled/* 2>/dev/null" > configs/app-servers/$name/sites-enabled.conf
    
    # Individual site configs
    for site in rentalfixer rentalfixer-staging stub_status default; do
        ssh root@$ip "cat /etc/nginx/sites-available/$site 2>/dev/null" > "configs/app-servers/$name/nginx-sites/$site" 2>/dev/null
    done
    
    # PHP-FPM
    ssh root@$ip "cat /etc/php/8.5/fpm/php-fpm.conf" > configs/app-servers/$name/php-fpm/php-fpm.conf 2>/dev/null
    for pool in $(ssh root@$ip "ls /etc/php/8.5/fpm/pool.d/*.conf 2>/dev/null"); do
        poolname=$(basename $pool)
        ssh root@$ip "cat /etc/php/8.5/fpm/pool.d/$poolname" > "configs/app-servers/$name/php-fpm/$poolname"
    done
done

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

# ==================== Redis ====================
echo "=== Redis ==="
mkdir -p configs/redis
ssh root@100.126.103.51 "cat /etc/redis/redis.conf" > configs/redis/redis-re-node-01.conf 2>/dev/null
ssh root@100.114.117.46 "cat /etc/redis/redis.conf" > configs/redis/redis-re-node-03.conf 2>/dev/null
echo "Redis configs synced"

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
ssh root@100.102.220.16 "cat /etc/logrotate.d/nginx" > configs/logrotate/nginx 2>/dev/null
echo "Logrotate configs synced"

# ==================== App .env examples ====================
echo "=== App .env examples ==="
mkdir -p configs/apps
for app in rentalfixer rentalfixer-staging; do
    ssh root@100.92.26.38 "cat /opt/apps/$app/.env 2>/dev/null" | sed 's/=.*/=***/' > "configs/apps/$app-re-db.env.example" 2>/dev/null
    ssh root@100.89.130.19 "cat /opt/apps/$app/.env 2>/dev/null" | sed 's/=.*/=***/' > "configs/apps/$app-re-node-02.env.example" 2>/dev/null
done
echo "App .env examples synced"

# ==================== Cleanup ====================
find configs/ -size 0 -delete

echo ""
echo "=== Sync complete ==="
echo "Config files synced: $(find configs -type f | wc -l)"
echo ""
echo "Run 'git status' to see changes"
