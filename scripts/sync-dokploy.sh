#!/bin/bash
# Quick sync of Dokploy and Docker configs only
# For testing the new sync sections

echo "=== Dokploy & Docker Configs Sync ==="

# ==================== Dokploy ====================
echo "=== Dokploy ==="
mkdir -p configs/dokploy/re-db/traefik configs/dokploy/re-node-02/traefik
mkdir -p configs/dokploy/re-db/monitoring configs/dokploy/re-node-02/monitoring

# Manager node (re-db) - Traefik configs
echo "  Syncing re-db Traefik..."
ssh root@100.92.26.38 "cat /etc/dokploy/traefik/traefik.yml" > configs/dokploy/re-db/traefik/traefik.yml 2>/dev/null || true

# Sync all dynamic config files from manager
for file in $(ssh root@100.92.26.38 "ls /etc/dokploy/traefik/dynamic/*.yml 2>/dev/null"); do
    filename=$(basename "$file")
    ssh root@100.92.26.38 "cat /etc/dokploy/traefik/dynamic/$filename" > "configs/dokploy/re-db/traefik/$filename" 2>/dev/null || true
    echo "    Synced: $filename"
done

# ACME certificate metadata (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.92.26.38 "stat -c '%a %U %G %s %y' /etc/dokploy/traefik/dynamic/acme.json 2>/dev/null" > configs/dokploy/re-db/traefik/acme.json.metadata 2>/dev/null || true

# Worker node (re-node-02) - Traefik configs
echo "  Syncing re-node-02 Traefik..."
ssh root@100.89.130.19 "cat /etc/dokploy/traefik/traefik.yml" > configs/dokploy/re-node-02/traefik/traefik.yml 2>/dev/null || true

# Sync all dynamic config files from worker
for file in $(ssh root@100.89.130.19 "ls /etc/dokploy/traefik/dynamic/*.yml 2>/dev/null"); do
    filename=$(basename "$file")
    ssh root@100.89.130.19 "cat /etc/dokploy/traefik/dynamic/$filename" > "configs/dokploy/re-node-02/traefik/$filename" 2>/dev/null || true
    echo "    Synced: $filename"
done

# ACME certificate metadata from worker (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.89.130.19 "stat -c '%a %U %G %s %y' /etc/dokploy/traefik/dynamic/acme.json 2>/dev/null" > configs/dokploy/re-node-02/traefik/acme.json.metadata 2>/dev/null || true

# Dokploy monitoring configs (manager node only)
echo "  Syncing monitoring configs..."
for file in $(ssh root@100.92.26.38 "ls /etc/dokploy/monitoring/dokploy/*.json 2>/dev/null"); do
    filename=$(basename "$file")
    ssh root@100.92.26.38 "cat /etc/dokploy/monitoring/dokploy/$filename" > "configs/dokploy/re-db/monitoring/$filename" 2>/dev/null || true
    echo "    Synced: $filename"
done

echo "Dokploy configs synced"

# ==================== Docker ====================
echo "=== Docker ==="
mkdir -p configs/docker/re-db configs/docker/re-node-02

# Docker daemon configuration from both nodes
echo "  Syncing daemon.json..."
ssh root@100.92.26.38 "cat /etc/docker/daemon.json" > configs/docker/re-db/daemon.json 2>/dev/null || true
ssh root@100.89.130.19 "cat /etc/docker/daemon.json" > configs/docker/re-node-02/daemon.json 2>/dev/null || true

echo "Docker daemon configs synced"

# ==================== Docker Swarm ====================
echo "=== Docker Swarm ==="
mkdir -p configs/docker/swarm

# Swarm status from manager
echo "  Syncing swarm state..."
ssh root@100.92.26.38 "docker node ls" > configs/docker/swarm/nodes.txt 2>/dev/null || true
ssh root@100.92.26.38 "docker service ls" > configs/docker/swarm/services.txt 2>/dev/null || true
ssh root@100.92.26.38 "docker network ls" > configs/docker/swarm/networks.txt 2>/dev/null || true

echo "Docker Swarm state synced"

# ==================== Cleanup ====================
find configs/dokploy configs/docker -size 0 -delete

echo ""
echo "=== Sync complete ==="
echo "Dokploy files: $(find configs/dokploy -type f | wc -l)"
echo "Docker files: $(find configs/docker -type f | wc -l)"
echo ""
echo "Run 'git status configs/dokploy configs/docker' to see changes"