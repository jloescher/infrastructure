---
name: redis
description: Manages Redis caching, replication, and Sentinel failover for session storage and application caching. Use when configuring Redis connections, troubleshooting replication issues, managing Sentinel failover, or optimizing cache performance in the Quantyra infrastructure.
---

# Redis Skill

Redis 7.x provides session storage and application caching with Sentinel-managed failover between re-node-01 (master) and re-node-03 (replica). All connections require password authentication and use Tailscale networking.

## Quick Start

### Connect to Redis Master

```bash
redis-cli -h 100.126.103.51 -p 6379 -a $REDIS_PASSWORD INFO replication
```

### Python Connection (Dashboard)

```python
import redis

r = redis.Redis(
    host='100.126.103.51',
    port=6379,
    password=os.environ['REDIS_PASSWORD'],
    decode_responses=True
)
r.setex('session:key', 3600, 'value')
```

### Check Sentinel Status

```bash
redis-cli -h 100.126.103.51 -p 26379 INFO sentinel
```

## Key Concepts

| Concept | Usage | Example |
|---------|-------|---------|
| Master | Primary write node | `100.126.103.51:6379` |
| Replica | Read replica with async replication | `100.114.117.46:6379` |
| Sentinel | Failover detection and orchestration | Port `26379` on all nodes |
| maxmemory-policy | Eviction strategy for cache | `allkeys-lru` |

## Common Patterns

### Session Caching with TTL

**When:** Storing Flask sessions or temporary user data

```python
# Set session with 1 hour expiry
r.setex(f"session:{user_id}", 3600, json.dumps(session_data))
```

### Read from Replica, Write to Master

**When:** High read throughput applications

```python
# Writes go to master
master = redis.Redis(host='100.126.103.51', port=6379, password=password)
master.set('key', 'value')

# Reads go to replica
replica = redis.Redis(host='100.114.117.46', port=6379, password=password)
value = replica.get('key')
```

## See Also

- [patterns](references/patterns.md) - Common patterns and anti-patterns
- [workflows](references/workflows.md) - Operational workflows

## Related Skills

- **python** - For Redis client usage patterns
- **flask** - Session management integration
- **ansible** - Redis configuration and deployment
- **patroni** - Similar HA patterns for PostgreSQL
- **haproxy** - Load balancing patterns