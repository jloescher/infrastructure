# Redis Patterns Reference

## Contents
- Connection Patterns
- Caching Strategies
- Data Structure Patterns
- Anti-Patterns

## Connection Patterns

### Sentinel-Aware Connection

```python
from redis.sentinel import Sentinel

sentinel = Sentinel([
    ('100.126.103.51', 26379),
    ('100.114.117.46', 26379)
], socket_timeout=0.1)

master = sentinel.master_for('mymaster', socket_timeout=0.1)
slave = sentinel.slave_for('mymaster', socket_timeout=0.1)
```

### Connection Pooling (Production)

```python
pool = redis.ConnectionPool(
    host='100.126.103.51',
    port=6379,
    password=password,
    max_connections=50,
    decode_responses=True
)
r = redis.Redis(connection_pool=pool)
```

## Caching Strategies

### Cache-Aside Pattern

```python
def get_user(user_id):
    # Try cache first
    cached = r.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)
    
    # Cache miss - load from DB
    user = db.query(User).get(user_id)
    r.setex(f"user:{user_id}", 300, json.dumps(user.to_dict()))
    return user
```

### Write-Through Cache

```python
def update_user(user_id, data):
    # Update DB
    db.update(User).where(User.id == user_id).values(**data)
    
    # Invalidate cache
    r.delete(f"user:{user_id}")
```

## Data Structure Patterns

### Rate Limiting (Sliding Window)

```python
def is_rate_limited(key, limit, window):
    pipe = r.pipeline()
    now = time.time()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zcard(key)
    pipe.zadd(key, {str(now): now})
    pipe.expire(key, window)
    _, count, _, _ = pipe.execute()
    return count >= limit
```

### Distributed Lock

```python
def acquire_lock(lock_name, timeout=10):
    identifier = str(uuid.uuid4())
    lock_key = f"lock:{lock_name}"
    acquired = r.set(lock_key, identifier, nx=True, ex=timeout)
    return identifier if acquired else None

def release_lock(lock_name, identifier):
    lock_key = f"lock:{lock_name}"
    with r.pipeline() as pipe:
        while True:
            try:
                pipe.watch(lock_key)
                if pipe.get(lock_key) == identifier:
                    pipe.multi()
                    pipe.delete(lock_key)
                    pipe.execute()
                    return True
                pipe.unwatch()
                break
            except redis.WatchError:
                continue
    return False
```

## Anti-Patterns

### WARNING: Using KEYS in Production

```bash
# BAD - O(n) operation blocks all clients
KEYS user:*

# GOOD - Use SCAN for iteration
SCAN 0 MATCH user:* COUNT 100
```

**Why This Breaks:** KEYS scans the entire keyspace, blocking Redis while executing. On a production instance with millions of keys, this causes cascading timeouts across all connected applications.

### WARNING: Storing Large Values

```python
# BAD - Storing multi-MB objects
r.set('user:1:full_profile', json.dumps(huge_object))

# GOOD - Store references, shard data
r.hset('user:1', mapping={
    'profile_id': profile_id,
    'cache_version': 'v1'
})
```

**Why This Breaks:** Values over 1MB cause memory fragmentation, slow replication, and block the event loop during serialization. Redis is optimized for small values (under 10KB).

### WARNING: No Connection Timeout

```python
# BAD - Default socket timeout can hang forever
r = redis.Redis(host='100.126.103.51', password=password)

# GOOD - Always set timeouts
r = redis.Redis(
    host='100.126.103.51',
    password=password,
    socket_timeout=5,
    socket_connect_timeout=5
)
```

**Why This Breaks:** Network partitions without timeouts cause applications to hang indefinitely, consuming connection pools and preventing failover detection.

### WARNING: Not Handling Failover

```python
# BAD - Hardcoded master IP
MASTER_IP = '100.126.103.51'

# GOOD - Use Sentinel for automatic failover
sentinel = Sentinel([
    ('100.126.103.51', 26379),
    ('100.114.117.46', 26379)
])
master = sentinel.master_for('mymaster')
```

**Why This Breaks:** During failover, the master IP changes. Hardcoded IPs cause write failures until manually updated. Sentinel provides automatic discovery.