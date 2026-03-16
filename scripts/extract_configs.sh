#!/bin/bash
set -euo pipefail

# Extract HAProxy configs from routers
echo "=== Extracting HAProxy configs ==="
for router in router-01 router-02; do
    ip=$(grep "$router" /Users/jonathanloescher/Code/infrastructure/ansible/inventory/hosts.yml | grep ansible_host | head -1 | awk '{print $3}' | tr -d ':')
    
    if [ "$router" = "router-01" ]; then
        ip="100.102.220.16"
    else
        ip="100.116.175.9"
    fi
    
    echo "Extracting from $router ($ip)..."
    ssh root@$ip "cat /etc/haproxy/haproxy.cfg" > "/Users/jonathanloescher/Code/infrastructure/configs/haproxy/haproxy-${router}.cfg" 2>/dev/null || echo "Failed to extract from $router"
done

# Extract Patroni configs from DB nodes
echo ""
echo "=== Extracting Patroni configs ==="
for node in re-node-01 re-node-03 re-node-04; do
    case $node in
        re-node-01) ip="100.126.103.51" ;;
        re-node-03) ip="100.114.117.46" ;;
        re-node-04) ip="100.115.75.119" ;;
    esac
    
    echo "Extracting from $node ($ip)..."
    ssh root@$ip "cat /etc/patroni/config.yml 2>/dev/null || cat /etc/patroni.yml 2>/dev/null || echo 'Patroni config not found'" > "/Users/jonathanloescher/Code/infrastructure/configs/patroni/patroni-${node}.yml" 2>/dev/null || echo "Failed to extract from $node"
done

# Extract PostgreSQL configs
echo ""
echo "=== Extracting PostgreSQL configs ==="
for node in re-node-01 re-node-03 re-node-04; do
    case $node in
        re-node-01) ip="100.126.103.51" ;;
        re-node-03) ip="100.114.117.46" ;;
        re-node-04) ip="100.115.75.119" ;;
    esac
    
    echo "Extracting from $node ($ip)..."
    mkdir -p "/Users/jonathanloescher/Code/infrastructure/configs/postgresql"
    ssh root@$ip "cat /etc/postgresql/18/main/postgresql.conf 2>/dev/null" > "/Users/jonathanloescher/Code/infrastructure/configs/postgresql/postgresql-${node}.conf" 2>/dev/null || echo "Failed to extract postgresql.conf from $node"
    ssh root@$ip "cat /etc/postgresql/18/main/pg_hba.conf 2>/dev/null" > "/Users/jonathanloescher/Code/infrastructure/configs/postgresql/pg_hba-${node}.conf" 2>/dev/null || echo "Failed to extract pg_hba.conf from $node"
done

# Scan for services on app servers
echo ""
echo "=== Scanning services on app servers ==="
for server in re-db re-node-02; do
    case $server in
        re-db) ip="100.92.26.38" ;;
        re-node-02) ip="100.89.130.19" ;;
    esac
    
    echo ""
    echo "--- $server ($ip) ---"
    ssh root@$ip "systemctl list-units --type=service --state=running --no-pager | grep -E '(caddy|go|nginx|apache|docker|node|python|ruby|java)' || true" 2>/dev/null
    echo ""
    echo "Listening ports:"
    ssh root@$ip "ss -tlnp | grep -E ':(80|443|8001|9090|3000|8080)'" 2>/dev/null || true
    echo ""
    echo "Process list (filtered):"
    ssh root@$ip "ps aux | grep -E '(caddy|go|nginx|node|python|ruby|java|docker)' | grep -v grep" 2>/dev/null || true
done

echo ""
echo "=== Done ==="
