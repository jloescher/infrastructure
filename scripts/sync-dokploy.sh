#!/bin/bash
# Quick sync of Coolify and Docker configs only
# For testing the new sync sections

echo "=== Coolify & Docker Configs Sync ==="

# ==================== Coolify ====================
echo "=== Coolify ==="
mkdir -p configs/coolify/re-db/traefik configs/coolify/re-node-02/traefik

# Manager node (re-db) - Traefik dynamic configs from Coolify proxy
echo "  Syncing re-db Traefik..."
for file in $(ssh root@100.92.26.38 "ls /data/coolify/proxy/*.yml 2>/dev/null"); do
    filename=$(basename "$file")
    ssh root@100.92.26.38 "cat /data/coolify/proxy/$filename" > "configs/coolify/re-db/traefik/$filename" 2>/dev/null || true
    echo "    Synced: $filename"
done

# ACME certificate metadata from manager (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.92.26.38 "stat -c '%a %U %G %s %y' /data/coolify/proxy/acme.json 2>/dev/null" > configs/coolify/re-db/traefik/acme.json.metadata 2>/dev/null || true

# Worker node (re-node-02) - Traefik dynamic configs from Coolify proxy
echo "  Syncing re-node-02 Traefik..."
for file in $(ssh root@100.89.130.19 "ls /data/coolify/proxy/*.yml 2>/dev/null"); do
    filename=$(basename "$file")
    ssh root@100.89.130.19 "cat /data/coolify/proxy/$filename" > "configs/coolify/re-node-02/traefik/$filename" 2>/dev/null || true
    echo "    Synced: $filename"
done

# ACME certificate metadata from worker (DO NOT SYNC CONTENT - contains private keys)
ssh root@100.89.130.19 "stat -c '%a %U %G %s %y' /data/coolify/proxy/acme.json 2>/dev/null" > configs/coolify/re-node-02/traefik/acme.json.metadata 2>/dev/null || true

echo "Coolify configs synced"

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
find configs/coolify configs/docker -size 0 -delete

echo ""
echo "=== Sync complete ==="
echo "Coolify files: $(find configs/coolify -type f | wc -l)"
echo "Docker files: $(find configs/docker -type f | wc -l)"
echo ""
echo "Run 'git status configs/coolify configs/docker' to see changes"