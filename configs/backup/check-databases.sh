#!/usr/bin/env bash
set -euo pipefail

REDIS_PASSWORD="CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk"

echo "=========================================="
echo "  DATABASE HEALTH CHECK - re-node-01"
echo "=========================================="
echo ""

echo "=== SYSTEM RESOURCES ==="
free -h | grep -E "Mem:|Swap:"
echo ""
df -h / | tail -1
echo ""
uptime
echo ""

echo "=== POSTGRESQL STATUS ==="
sudo systemctl is-active postgresql@18-main || echo "PostgreSQL is DOWN!"
echo ""

echo "=== POSTGRESQL CONNECTIONS ==="
sudo -u postgres psql -t -c "
SELECT 
    count(*) as total,
    count(*) FILTER (WHERE state = 'active') as active,
    count(*) FILTER (WHERE state = 'idle') as idle,
    count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
FROM pg_stat_activity;" | xargs
echo ""

echo "=== POSTGRESQL TOP QUERIES (by total time) ==="
sudo -u postgres psql -d xotec_re -c "
SELECT 
    calls,
    round(total_exec_time::numeric, 2) as total_ms,
    round(mean_exec_time::numeric, 2) as mean_ms,
    substring(query, 1, 80) as query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 5;" 2>/dev/null || echo "pg_stat_statements not enabled yet"
echo ""

echo "=== DRAGONFLYDB STATUS ==="
sudo systemctl is-active dragonfly || echo "DragonflyDB is DOWN!"
echo ""

echo "=== DRAGONFLYDB STATS ==="
redis-cli -h 100.126.103.51 -p 6379 -a "$REDIS_PASSWORD" INFO stats 2>/dev/null | grep -E "(connected_clients|total_commands_processed|instantaneous_ops_per_sec)" || echo "Could not connect to DragonflyDB"
echo ""

echo "=== DRAGONFLYDB MEMORY ==="
redis-cli -h 100.126.103.51 -p 6379 -a "$REDIS_PASSWORD" INFO memory 2>/dev/null | grep -E "(used_memory_human|maxmemory_human)" || echo "Could not connect to DragonflyDB"
echo ""

echo "=== DATABASE SIZES ==="
sudo -u postgres psql -c "
SELECT 
    datname,
    pg_size_pretty(pg_database_size(datname)) as size
FROM pg_database
WHERE datname NOT IN ('template0', 'template1')
ORDER BY pg_database_size(datname) DESC;"
echo ""

echo "=========================================="
echo "  Health check complete"
echo "=========================================="
