#!/bin/bash
# Sync all configurations from production servers to local repo

set -e

echo "Syncing configurations from production servers..."

# HAProxy configs
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

# Dashboard configs
echo "=== Dashboard ==="
mkdir -p configs/dashboard
ssh root@100.102.220.16 "cat /opt/dashboard/config/.env 2>/dev/null" | sed 's/=.*/=/' > configs/dashboard/.env.example
ssh root@100.102.220.16 "cat /opt/dashboard/config/applications.yml 2>/dev/null" > configs/dashboard/applications.yml
ssh root@100.102.220.16 "cat /opt/dashboard/config/databases.yml 2>/dev/null" > configs/dashboard/databases.yml
echo "Dashboard configs synced"

# Provision scripts
echo "=== Provision Scripts ==="
mkdir -p configs/provision-scripts
ssh root@100.102.220.16 "cat /opt/scripts/provision-domain.sh" > configs/provision-scripts/provision-domain.sh
echo "Provision scripts synced"

# App server configs
echo "=== App Servers ==="
mkdir -p configs/app-servers/re-db/php-fpm configs/app-servers/re-node-02/php-fpm

ssh root@100.92.26.38 "cat /etc/nginx/nginx.conf" > configs/app-servers/re-db/nginx.conf
ssh root@100.92.26.38 "cat /etc/nginx/sites-enabled/* 2>/dev/null" > configs/app-servers/re-db/sites-enabled.conf
ssh root@100.101.39.22 "cat /etc/nginx/nginx.conf" > configs/app-servers/re-node-02/nginx.conf
ssh root@100.101.39.22 "cat /etc/nginx/sites-enabled/* 2>/dev/null" > configs/app-servers/re-node-02/sites-enabled.conf

# PHP-FPM pools
for pool in $(ssh root@100.92.26.38 "ls /etc/php/8.5/fpm/pool.d/*.conf 2>/dev/null"); do
  poolname=$(basename $pool)
  ssh root@100.92.26.38 "cat /etc/php/8.5/fpm/pool.d/$poolname" > "configs/app-servers/re-db/php-fpm/$poolname"
done

for pool in $(ssh root@100.101.39.22 "ls /etc/php/8.5/fpm/pool.d/*.conf 2>/dev/null"); do
  poolname=$(basename $pool)
  ssh root@100.101.39.22 "cat /etc/php/8.5/fpm/pool.d/$poolname" > "configs/app-servers/re-node-02/php-fpm/$poolname"
done

echo "App server configs synced"

# Database configs
echo "=== PostgreSQL/Patroni ==="
mkdir -p configs/postgres

for node in "100.126.103.51:re-node-01" "100.114.117.46:re-node-03" "100.115.75.119:re-node-04"; do
  ip=$(echo $node | cut -d: -f1)
  name=$(echo $node | cut -d: -f2)
  ssh root@$ip "cat /etc/patroni.yml" > configs/postgres/patroni-$name.yml 2>/dev/null
  ssh root@$ip "cat /etc/patroni/dcs.yml" > configs/postgres/dcs-$name.yml 2>/dev/null
done

echo "Database configs synced"

# Redis configs
echo "=== Redis ==="
mkdir -p configs/redis
ssh root@100.126.103.51 "cat /etc/redis/redis.conf" > configs/redis/redis-re-node-01.conf 2>/dev/null
ssh root@100.114.117.46 "cat /etc/redis/redis.conf" > configs/redis/redis-re-node-03.conf 2>/dev/null
echo "Redis configs synced"

# Clean empty files
find configs/ -size 0 -delete

echo ""
echo "=== Sync complete ==="
echo "Run 'git status' to see changes"
