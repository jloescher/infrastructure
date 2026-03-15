# Infrastructure Report - re-node-01
**Generated:** Sun Mar 15 04:07:05 UTC 2026
**Timestamp:** 20260315_040705

# System Information

```
Linux re-node-01 6.8.0-106-generic #106-Ubuntu SMP PREEMPT_DYNAMIC Fri Mar  6 07:58:08 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

PRETTY_NAME="Ubuntu 24.04.4 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.4 LTS (Noble Numbat)"
VERSION_CODENAME=noble
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=noble
LOGO=ubuntu-logo
```

## Hardware Specs

```
CPU:
CPU(s):                                  8
Model name:                              Intel(R) Xeon(R) Silver 4216 CPU @ 2.10GHz
BIOS Model name:                         pc-q35-10.0  CPU @ 2.0GHz
Thread(s) per core:                      1
Core(s) per socket:                      1
Socket(s):                               8

Memory:
               total        used        free      shared  buff/cache   available
Mem:            31Gi       9.4Gi        18Gi       8.3Gi        11Gi        21Gi
Swap:          4.0Gi       3.3Mi       4.0Gi

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     640G disk            
├─sda1    1M part            
└─sda2  640G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           3.2G  840K  3.2G   1% /run
/dev/sda2       630G   87G  511G  15% /
tmpfs            16G  5.1M   16G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           3.2G   16K  3.2G   1% /run/user/0
```

# Network Information

## Tailscale

```
100.126.103.51  re-node-01             jloescher@  linux  -                                                                         
100.74.169.15   iphone172              jloescher@  iOS    -                                                                         
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  active; direct 47.201.4.123:14773, tx 72012 rx 247260                     
100.92.26.38    re-db                  jloescher@  linux  active; direct [2602:ff16:3:0:1:446:0:1]:41641, tx 23677420 rx 111982372  
100.101.39.22   re-node-02             jloescher@  linux  -                                                                         
100.114.117.46  re-node-03             jloescher@  linux  active; direct [2602:ff16:11:11fb::1]:41641, tx 3094596424 rx 24139192    
100.115.75.119  re-node-04             jloescher@  linux  active; direct [2602:ff16:11:10c6::1]:41641, tx 2974948248 rx 12739384    
100.102.220.16  router-01              jloescher@  linux  active; direct 172.93.54.112:41641, tx 17607892 rx 4702820                
100.116.175.9   router-02              jloescher@  linux  active; direct [2602:ff16:3:10a3::1]:41641, tx 4439608 rx 1393920         

100.126.103.51
fd7a:115c:a1e0::3e37:6733
```

## Network Interfaces

```
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
    inet6 ::1/128 scope host noprefixroute 
       valid_lft forever preferred_lft forever
2: enp3s0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP group default qlen 1000
    link/ether 52:54:d0:c0:d4:af brd ff:ff:ff:ff:ff:ff
    inet 104.225.216.26/24 brd 104.225.216.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:3:0:1:d6:0:1/64 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:d0ff:fec0:d4af/64 scope link 
       valid_lft forever preferred_lft forever
3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.126.103.51/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::3e37:6733/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::91a0:c2a8:be72:fd8b/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                        127.0.0.1:323        0.0.0.0:*          
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                            [::1]:323           [::]:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
tcp   LISTEN 0      65535                127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      600                 100.126.103.51:5432       0.0.0.0:*          
tcp   LISTEN 0      65535                   127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      65535                      0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      511                 100.126.103.51:6379       0.0.0.0:*          
tcp   LISTEN 0      128                 100.126.103.51:6432       0.0.0.0:*          
tcp   LISTEN 0      600                      127.0.0.1:5432       0.0.0.0:*          
tcp   LISTEN 0      65535               100.126.103.51:32830      0.0.0.0:*          
tcp   LISTEN 0      5                          0.0.0.0:8008       0.0.0.0:*          
tcp   LISTEN 0      65535                            *:9187             *:*          
tcp   LISTEN 0      65535                            *:9100             *:*          
tcp   LISTEN 0      65535  [fd7a:115c:a1e0::3e37:6733]:46705         [::]:*          
tcp   LISTEN 0      65535                         [::]:22            [::]:*          
```

# PostgreSQL / Patroni

## Patroni Status

```
```

## PostgreSQL Status

```
/var/run/postgresql:5432 - accepting connections

                                                               version                                                               
-------------------------------------------------------------------------------------------------------------------------------------
 PostgreSQL 18.3 (Ubuntu 18.3-1.pgdg24.04+1) on x86_64-pc-linux-gnu, compiled by gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, 64-bit
(1 row)

```

## PostgreSQL Config

```
include 'postgresql.base.conf'
cluster_name = 'quantyra_pg'
effective_cache_size = '24GB'
hot_standby = 'on'
listen_addresses = '127.0.0.1,100.126.103.51'
maintenance_work_mem = '2GB'
max_connections = '300'
max_locks_per_transaction = '64'
max_prepared_transactions = '0'
max_replication_slots = '10'
max_wal_senders = '10'
max_worker_processes = '8'
port = '5432'
shared_buffers = '8GB'
synchronous_commit = 'off'
track_commit_timestamp = 'off'
unix_socket_directories = '/var/run/postgresql'
wal_keep_size = '8GB'
wal_level = 'replica'
wal_log_hints = 'on'
work_mem = '64MB'
hba_file = '/etc/postgresql/18/main/pg_hba.conf'
ident_file = '/etc/postgresql/18/main/pg_ident.conf'
primary_conninfo = 'dbname=postgres user=patroni_repl passfile=/var/lib/postgresql/.pgpass_patroni host=100.114.117.46 port=5432 sslmode=prefer application_name=re-node-01 gssencmode=prefer channel_binding=prefer sslnegotiation=postgres'
primary_slot_name = 're_node_01'
recovery_target = ''
recovery_target_lsn = ''
recovery_target_name = ''
recovery_target_time = ''
recovery_target_timeline = 'latest'
recovery_target_xid = ''
```

# Redis

## Redis Status

```
NOAUTH Authentication required.


NOAUTH Authentication required.
```

## Redis Config

```
bind 100.126.103.51
port 6379
tcp-backlog 511
timeout 0
tcp-keepalive 300
daemonize no
supervised systemd
pidfile /var/run/redis/redis-server.pid
loglevel notice
logfile /var/log/redis/redis-server.log
databases 16
save 900 1
save 300 10
save 60 10000
stop-writes-on-bgsave-error yes
rdbcompression yes
rdbchecksum yes
dbfilename dump.rdb
dir /var/lib/redis
replica-serve-stale-data yes
replica-read-only yes
repl-diskless-sync yes
repl-diskless-sync-delay 5
repl-diskless-sync-max-replicas 1
repl-ping-replica-period 10
repl-timeout 60
repl-disable-tcp-nodelay no
repl-backlog-size 64mb
repl-backlog-ttl 3600
replica-priority 100
requirepass CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
rename-command CONFIG ""
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command KEYS ""
rename-command SHUTDOWN SHUTDOWN_re-node-01
protected-mode yes
maxclients 10000
maxmemory 4gb
maxmemory-policy allkeys-lru
maxmemory-samples 5
maxmemory-eviction-tenacity 10
lazyfree-lazy-eviction yes
lazyfree-lazy-expire yes
lazyfree-lazy-server-del yes
replica-lazy-flush yes
lazyfree-lazy-user-del yes
lazyfree-lazy-user-flush yes
appendonly yes
appendfilename "appendonly.aof"
```

# Router Services (HAProxy, etcd)

## HAProxy

```
HAProxy not installed
```

## HAProxy Config

```
HAProxy config not found
```

## etcd

```
etcd not installed
```

# Monitoring (Prometheus, Grafana)

## Prometheus

```
Prometheus not installed
```

## Prometheus Config

```
Prometheus config not found
```

## Grafana

```
Grafana not installed
```

# Docker

## Docker Info

```
Docker not installed
```

## Docker Compose Files

# Running Services

```
  UNIT                        LOAD   ACTIVE SUB     DESCRIPTION
  chrony.service              loaded active running chrony, an NTP client/server
  dbus.service                loaded active running D-Bus System Message Bus
  fail2ban.service            loaded active running Fail2Ban Service
  getty@tty1.service          loaded active running Getty on tty1
  multipathd.service          loaded active running Device-Mapper Multipath Device Controller
  networkd-dispatcher.service loaded active running Dispatcher daemon for systemd-networkd
  node_exporter.service       loaded active running Prometheus Node Exporter
  patroni.service             loaded active running Patroni PostgreSQL HA Cluster Manager
  pgbouncer.service           loaded active running connection pooler for PostgreSQL
  postgres_exporter.service   loaded active running Prometheus PostgreSQL Exporter
  qemu-guest-agent.service    loaded active running QEMU Guest Agent
  redis-server.service        loaded active running Advanced key-value store
  rsyslog.service             loaded active running System Logging Service
  ssh.service                 loaded active running OpenBSD Secure Shell server
  systemd-journald.service    loaded active running Journal Service
  systemd-logind.service      loaded active running User Login Management
  systemd-networkd.service    loaded active running Network Configuration
  systemd-resolved.service    loaded active running Network Name Resolution
  systemd-udevd.service       loaded active running Rule-based Manager for Device Events and Files
  tailscaled.service          loaded active running Tailscale node agent
  unattended-upgrades.service loaded active running Unattended Upgrades Shutdown
  user@0.service              loaded active running User Manager for UID 0

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.
        SUB    → The low-level unit activation state, values depend on unit type.

22 loaded units listed.
```

# Security

## Firewall (UFW)

```
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), deny (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
5432/tcp                   ALLOW IN    100.64.0.0/10             
22/tcp                     ALLOW IN    100.64.0.0/10             
22/tcp (OpenSSH)           ALLOW IN    Anywhere                  
5432/tcp                   ALLOW IN    100.114.117.46            
5432/tcp                   ALLOW IN    100.115.75.119            
6432/tcp                   DENY IN     Anywhere                  
6432/tcp                   ALLOW IN    100.107.244.55            
6432/tcp                   ALLOW IN    100.114.117.46            
6432/tcp                   ALLOW IN    100.115.75.119            
22/tcp                     ALLOW IN    Anywhere                  
6432/tcp                   ALLOW IN    100.64.0.0/10             
5432/tcp on tailscale0     ALLOW IN    Anywhere                  
6432/tcp on tailscale0     ALLOW IN    Anywhere                  
5432/tcp                   DENY IN     Anywhere                  
6379                       ALLOW IN    100.64.0.0/10              # DragonflyDB Tailscale
6379 on tailscale0         ALLOW IN    Anywhere                  
100.126.103.51 6379        ALLOW IN    100.114.117.46            
22/tcp (OpenSSH (v6))      ALLOW IN    Anywhere (v6)             
6432/tcp (v6)              DENY IN     Anywhere (v6)             
22/tcp (v6)                ALLOW IN    Anywhere (v6)             
5432/tcp (v6) on tailscale0 ALLOW IN    Anywhere (v6)             
6432/tcp (v6) on tailscale0 ALLOW IN    Anywhere (v6)             
5432/tcp (v6)              DENY IN     Anywhere (v6)             
6379 (v6) on tailscale0    ALLOW IN    Anywhere (v6)             

```

## SSH Config

```
Include /etc/ssh/sshd_config.d/*.conf
PermitRootLogin without-password
KbdInteractiveAuthentication no
PermitRootLogin without-password
UsePAM yes
X11Forwarding yes
PrintMotd no
AcceptEnv LANG LC_*
Subsystem	sftp	/usr/lib/openssh/sftp-server
PubkeyAcceptedKeyTypes +ssh-rsa
```

## Active SSH Sessions

```
```

# Backup Configuration

## Backup Directories

```
=== /var/backups ===
total 2.3M
drwxr-xr-x  4 root     root     4.0K Mar 15 00:00 .
drwxr-xr-x 13 root     root     4.0K Mar 15 02:38 ..
-rw-r--r--  1 root     root      80K Mar 15 00:00 alternatives.tar.0
-rw-r--r--  1 root     root     5.6K Dec 24 00:00 alternatives.tar.1.gz
-rw-r--r--  1 root     root     5.5K Dec 23 00:00 alternatives.tar.2.gz
-rw-r--r--  1 root     root     1.9K Dec 22 04:24 alternatives.tar.3.gz
-rw-r--r--  1 root     root     1.9K Oct 14 17:03 alternatives.tar.4.gz
-rw-r--r--  1 root     root      41K Mar 14 22:29 apt.extended_states.0
-rw-r--r--  1 root     root     4.4K Feb 25 06:49 apt.extended_states.1.gz
-rw-r--r--  1 root     root     4.4K Feb 10 06:29 apt.extended_states.2.gz
-rw-r--r--  1 root     root     4.4K Feb  6 03:08 apt.extended_states.3.gz
-rw-r--r--  1 root     root     4.1K Feb  5 06:42 apt.extended_states.4.gz
-rw-r--r--  1 root     root     4.1K Jan 27 00:47 apt.extended_states.5.gz
-rw-r--r--  1 root     root     4.1K Jan 26 02:44 apt.extended_states.6.gz
-rw-r--r--  1 root     root        0 Mar 15 00:00 dpkg.arch.0
-rw-r--r--  1 root     root       32 Mar 14 00:00 dpkg.arch.1.gz
-rw-r--r--  1 root     root       32 Mar 11 00:00 dpkg.arch.2.gz
-rw-r--r--  1 root     root       32 Mar  9 00:00 dpkg.arch.3.gz
-rw-r--r--  1 root     root       32 Mar  7 00:00 dpkg.arch.4.gz
-rw-r--r--  1 root     root       32 Mar  6 00:00 dpkg.arch.5.gz
-rw-r--r--  1 root     root       32 Feb 28 00:00 dpkg.arch.6.gz
-rw-r--r--  1 root     root     1.6K Dec 23 02:44 dpkg.diversions.0
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.1.gz
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.2.gz
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.3.gz
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.4.gz
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.5.gz
-rw-r--r--  1 root     root      362 Dec 23 02:44 dpkg.diversions.6.gz
-rw-r--r--  1 root     root      251 Jan 26 02:44 dpkg.statoverride.0
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.1.gz
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.2.gz
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.3.gz
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.4.gz
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.5.gz
-rw-r--r--  1 root     root      177 Jan 26 02:44 dpkg.statoverride.6.gz
-rw-r--r--  1 root     root     797K Mar 14 22:29 dpkg.status.0
-rw-r--r--  1 root     root     196K Mar 13 06:42 dpkg.status.1.gz
-rw-r--r--  1 root     root     196K Mar 10 06:33 dpkg.status.2.gz
-rw-r--r--  1 root     root     196K Mar  8 10:56 dpkg.status.3.gz
-rw-r--r--  1 root     root     196K Mar  6 06:09 dpkg.status.4.gz
-rw-r--r--  1 root     root     196K Mar  5 06:52 dpkg.status.5.gz
-rw-r--r--  1 root     root     196K Feb 27 06:30 dpkg.status.6.gz
drwxr-x---  5 postgres postgres 4.0K Dec 29 00:52 postgres
drwxr-x---  3 root     root     4.0K Dec 29 00:52 system

```

## Cron Jobs (Backups)

```
No user crontab

No backup cron jobs found
```

# System Resources (Current)

```
 04:07:07 up  1:28,  1 user,  load average: 0.31, 0.75, 0.83

top - 04:07:08 up  1:28,  1 user,  load average: 0.31, 0.75, 0.83
Tasks: 254 total,   2 running, 252 sleeping,   0 stopped,   0 zombie
%Cpu(s):  1.0 us,  1.9 sy,  0.0 ni, 96.2 id,  1.0 wa,  0.0 hi,  0.0 si,  0.0 st 
MiB Mem :  32095.9 total,  19188.3 free,   9627.4 used,  12229.7 buff/cache     
MiB Swap:   4096.0 total,   4092.7 free,      3.3 used.  22468.4 avail Mem 

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
  12291 root      20   0   12336   5568   3420 R  16.7   0.0   0:00.04 top
      1 root      20   0   21900  13104   9556 S   0.0   0.0   0:03.64 systemd
      2 root      20   0       0      0      0 S   0.0   0.0   0:00.09 kthreadd
      3 root      20   0       0      0      0 S   0.0   0.0   0:00.00 pool_wo+
      4 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      5 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      6 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      7 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
```

---
Report generated at: Sun Mar 15 04:07:08 UTC 2026
