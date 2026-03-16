# Redis High Availability

## Architecture

```
                    ┌─────────────────┐
                    │   Application   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
        ┌─────▼─────┐               ┌───────▼─────┐
        │ router-01 │               │  router-02  │
        │  HAProxy  │               │   HAProxy   │
        └─────┬─────┘               └───────┬─────┘
              │                             │
    ┌─────────┼─────────┐         ┌─────────┼─────────┐
    │         │         │         │         │         │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│Redis  │ │Redis  │ │Sentinel│ │Redis  │ │Redis  │ │Sentinel│
│ :6379 │ │ :6380 │ │ :26379│ │ :6379 │ │ :6380 │ │ :26379│
│Write  │ │Read   │ │       │ │Write  │ │Read   │ │       │
└───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘
    │         │                   │         │
    └─────────┼───────────────────┘         │
              │                             │
        ┌─────▼─────────────────────────────▼─────┐
        │           Redis Cluster                 │
        │  ┌─────────────┐   ┌─────────────┐      │
        │  │  re-node-01 │   │  re-node-03 │      │
        │  │   (Master)  │◄──┤  (Replica)  │      │
        │  │ 100.126.103.│   │ 100.114.117.│      │
        │  │    51:6379  │   │    46:6379  │      │
        │  └─────────────┘   └─────────────┘      │
        └─────────────────────────────────────────┘
```

## Connection Methods

### Option 1: HAProxy (Recommended for apps)

**Write (Master):**
```
router-01: 100.102.220.16:6379
router-02: 100.116.175.9:6379
```

**Read (Replica - load balanced):**
```
router-01: 100.102.220.16:6380
router-02: 100.116.175.9:6380
```

**Connection string:**
```
redis://:CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk@100.102.220.16:6379
```

### Option 2: Sentinel (Automatic failover discovery)

**Sentinel endpoints:**
```
router-01: 100.102.220.16:26379
router-02: 100.116.175.9:26379
```

**Go example:**
```go
client := redis.NewFailoverClient(&redis.FailoverOptions{
    MasterName:    "quantyra_redis",
    SentinelAddrs: []string{
        "100.102.220.16:26379",
        "100.116.175.9:26379",
    },
    Password: "CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk",
})
```

### Option 3: Direct (Not recommended)

**Master:** 100.126.103.51:6379
**Replica:** 100.114.117.46:6379

## HAProxy Health Checks

HAProxy uses TCP checks to verify Redis role:

**Master check (port 6379):**
1. AUTH with password
2. INFO replication
3. Expect `role:master`

**Replica check (port 6380):**
1. AUTH with password
2. INFO replication
3. Expect `role:slave`

## Failover Process

### Automatic (Sentinel)

1. Sentinel detects master down (5 seconds)
2. Sentinels agree on failover (quorum: 2)
3. Sentinel promotes replica to master
4. HAProxy health checks detect new topology
5. Traffic routes to new master automatically

### Manual

```bash
# Check current master
redis-cli -h 100.102.220.16 -p 26379 SENTINEL master quantyra_redis

# Force failover
redis-cli -h 100.102.220.16 -p 26379 SENTINEL failover quantyra_redis

# Verify new master
redis-cli -h 100.102.220.16 -p 26379 SENTINEL master quantyra_redis
```

## Monitoring

**Redis Exporter:**
- re-node-01: http://100.126.103.51:9121/metrics
- re-node-03: http://100.114.117.46:9121/metrics

**Alerts configured:**
- RedisDown
- RedisMemoryHigh (>85%)
- RedisConnectionsHigh (>80%)
- RedisReplicationBroken

## Configuration Files

| File | Location |
|------|----------|
| Redis config (re-node-01) | `configs/redis/redis-re-node-01.conf` |
| Redis config (re-node-03) | `configs/redis/redis-re-node-03.conf` |
| Sentinel config | `configs/redis/sentinel.conf` |
| HAProxy config | `configs/haproxy/haproxy-router-01.cfg` |

## Credentials

**Redis Password:** `CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk`

**Sentinel Monitor:** `quantyra_redis`