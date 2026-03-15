# Infrastructure Report - re-node-03
**Generated:** Sun Mar 15 04:07:08 UTC 2026
**Timestamp:** 20260315_040708

# System Information

```
Linux re-node-03 6.8.0-106-generic #106-Ubuntu SMP PREEMPT_DYNAMIC Fri Mar  6 07:58:08 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux

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
BIOS Model name:                         pc-q35-7.2  CPU @ 2.0GHz
Thread(s) per core:                      1
Core(s) per socket:                      1
Socket(s):                               8

Memory:
               total        used        free      shared  buff/cache   available
Mem:            31Gi       1.5Gi        29Gi       657Mi       1.2Gi        29Gi
Swap:          4.0Gi        31Mi       4.0Gi

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     640G disk            
├─sda1    1M part            
└─sda2  640G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           3.2G  844K  3.2G   1% /run
/dev/sda2       630G   41G  558G   7% /
tmpfs            16G  1.1M   16G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           3.2G   16K  3.2G   1% /run/user/0
```

# Network Information

## Tailscale

```
100.114.117.46  re-node-03             jloescher@  linux  -                                                                  
100.74.169.15   iphone172              jloescher@  iOS    -                                                                  
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  active; direct 47.201.4.123:41641, tx 21544 rx 202456              
100.92.26.38    re-db                  jloescher@  linux  active; direct 208.87.128.115:41641, tx 26296 rx 32112             
100.126.103.51  re-node-01             jloescher@  linux  active; direct 104.225.216.26:41641, tx 25683640 rx 3074535528     
100.101.39.22   re-node-02             jloescher@  linux  -                                                                  
100.115.75.119  re-node-04             jloescher@  linux  -                                                                  
100.102.220.16  router-01              jloescher@  linux  active; direct 172.93.54.112:41641, tx 15896792 rx 4213400         
100.116.175.9   router-02              jloescher@  linux  active; direct [2602:ff16:3:10a3::1]:41641, tx 3524876 rx 1288516  

100.114.117.46
fd7a:115c:a1e0::1b37:752e
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
    link/ether 52:54:42:44:b3:ba brd ff:ff:ff:ff:ff:ff
    inet 172.93.54.145/24 brd 172.93.54.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:11:11fb::1/48 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:42ff:fe44:b3ba/64 scope link 
       valid_lft forever preferred_lft forever
3: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.114.117.46/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::1b37:752e/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::f6ba:86e2:77f6:d66b/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                        127.0.0.1:323        0.0.0.0:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
udp   UNCONN 0      0                            [::1]:323           [::]:*          
tcp   LISTEN 0      65535                      0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      65535                   127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      5                          0.0.0.0:8008       0.0.0.0:*          
tcp   LISTEN 0      65535               100.114.117.46:58704      0.0.0.0:*          
tcp   LISTEN 0      65535                127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      511                 100.114.117.46:6379       0.0.0.0:*          
tcp   LISTEN 0      600                      127.0.0.1:5432       0.0.0.0:*          
tcp   LISTEN 0      600                 100.114.117.46:5432       0.0.0.0:*          
tcp   LISTEN 0      65535                         [::]:22            [::]:*          
tcp   LISTEN 0      65535                            *:9100             *:*          
tcp   LISTEN 0      65535                            *:9187             *:*          
tcp   LISTEN 0      65535  [fd7a:115c:a1e0::1b37:752e]:43643         [::]:*          
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
listen_addresses = '127.0.0.1,100.114.117.46'
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
primary_conninfo = 'dbname=postgres user=patroni_repl passfile=/var/lib/postgresql/.pgpass_patroni host=100.126.103.51 port=5432 sslmode=prefer application_name=re-node-03 gssencmode=prefer channel_binding=prefer sslnegotiation=postgres'
primary_slot_name = 're_node_03'
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
bind 100.114.117.46
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
replicaof 100.126.103.51 6379
masterauth CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
replica-serve-stale-data yes
replica-read-only yes
repl-diskless-sync yes
repl-diskless-sync-delay 5
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
rename-command SHUTDOWN SHUTDOWN_re-node-03
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
etcdctl version: 3.5.25
API version: 3.5

etcd not configured
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

21 loaded units listed.
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
5432/tcp                   DENY IN     Anywhere                  
22/tcp                     ALLOW IN    Anywhere                  
5432/tcp                   ALLOW IN    100.126.103.51            
6432/tcp                   ALLOW IN    100.107.244.55            
6432/tcp                   ALLOW IN    100.126.103.51            
6432/tcp                   ALLOW IN    100.115.75.119            
6432/tcp                   DENY IN     Anywhere                  
6432/tcp                   ALLOW IN    100.64.0.0/10             
6379                       ALLOW IN    100.64.0.0/10              # DragonflyDB Tailscale
22/tcp (OpenSSH (v6))      ALLOW IN    Anywhere (v6)             
5432/tcp (v6)              DENY IN     Anywhere (v6)             
22/tcp (v6)                ALLOW IN    Anywhere (v6)             
6432/tcp (v6)              DENY IN     Anywhere (v6)             

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
root     pts/0        2026-03-15 02:52 (100.107.244.55)
```

# Backup Configuration

## Backup Directories

```
=== /var/backups ===
total 2.1M
drwxr-xr-x  4 root     root     4.0K Mar 15 00:00 .
drwxr-xr-x 13 root     root     4.0K Mar 15 02:39 ..
-rw-r--r--  1 root     root      80K Mar 14 00:00 alternatives.tar.0
-rw-r--r--  1 root     root     5.6K Dec 24 00:00 alternatives.tar.1.gz
-rw-r--r--  1 root     root     5.6K Dec 23 00:00 alternatives.tar.2.gz
-rw-r--r--  1 root     root     1.9K Dec 22 04:24 alternatives.tar.3.gz
-rw-r--r--  1 root     root     1.9K Oct 14 17:03 alternatives.tar.4.gz
-rw-r--r--  1 root     root      38K Mar 14 22:41 apt.extended_states.0
-rw-r--r--  1 root     root     4.1K Mar 14 06:11 apt.extended_states.1.gz
-rw-r--r--  1 root     root     4.1K Feb 25 06:07 apt.extended_states.2.gz
-rw-r--r--  1 root     root     4.1K Feb 10 06:52 apt.extended_states.3.gz
-rw-r--r--  1 root     root     4.1K Feb  5 06:51 apt.extended_states.4.gz
-rw-r--r--  1 root     root     4.1K Jan 26 02:45 apt.extended_states.5.gz
-rw-r--r--  1 root     root     4.1K Jan  9 21:24 apt.extended_states.6.gz
-rw-r--r--  1 root     root        0 Mar 15 00:00 dpkg.arch.0
-rw-r--r--  1 root     root       32 Mar 14 00:00 dpkg.arch.1.gz
-rw-r--r--  1 root     root       32 Mar 13 00:00 dpkg.arch.2.gz
-rw-r--r--  1 root     root       32 Mar 11 00:00 dpkg.arch.3.gz
-rw-r--r--  1 root     root       32 Mar  9 00:00 dpkg.arch.4.gz
-rw-r--r--  1 root     root       32 Mar  7 00:00 dpkg.arch.5.gz
-rw-r--r--  1 root     root       32 Mar  5 00:00 dpkg.arch.6.gz
-rw-r--r--  1 root     root     1.6K Dec 23 02:58 dpkg.diversions.0
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.1.gz
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.2.gz
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.3.gz
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.4.gz
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.5.gz
-rw-r--r--  1 root     root      362 Dec 23 02:58 dpkg.diversions.6.gz
-rw-r--r--  1 root     root      251 Jan 26 02:45 dpkg.statoverride.0
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.1.gz
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.2.gz
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.3.gz
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.4.gz
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.5.gz
-rw-r--r--  1 root     root      177 Jan 26 02:45 dpkg.statoverride.6.gz
-rw-r--r--  1 root     root     751K Mar 14 22:41 dpkg.status.0
-rw-r--r--  1 root     root     183K Mar 13 06:39 dpkg.status.1.gz
-rw-r--r--  1 root     root     183K Mar 12 06:02 dpkg.status.2.gz
-rw-r--r--  1 root     root     183K Mar 10 06:45 dpkg.status.3.gz
-rw-r--r--  1 root     root     183K Mar  8 10:56 dpkg.status.4.gz
-rw-r--r--  1 root     root     183K Mar  6 06:51 dpkg.status.5.gz
-rw-r--r--  1 root     root     183K Mar  4 06:47 dpkg.status.6.gz
drwxr-x---  5 postgres postgres 4.0K Dec 29 01:47 postgres
drwxr-xr-x  3 root     root     4.0K Dec 29 01:48 system

```

## Cron Jobs (Backups)

```
No user crontab

No backup cron jobs found
```

# System Resources (Current)

```
 04:07:15 up  1:23,  2 users,  load average: 0.08, 0.36, 0.42

top - 04:07:16 up  1:23,  2 users,  load average: 0.08, 0.36, 0.42
Tasks: 248 total,   1 running, 247 sleeping,   0 stopped,   0 zombie
%Cpu(s):  0.0 us,  3.2 sy,  0.0 ni, 96.0 id,  0.8 wa,  0.0 hi,  0.0 si,  0.0 st 
MiB Mem :  32095.9 total,  30399.0 free,   1549.0 used,   1268.4 buff/cache     
MiB Swap:   4096.0 total,   4064.5 free,     31.4 used.  30546.9 avail Mem 

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
    449 root      rt   0  288988  27324   8760 S   7.1   0.1   0:01.10 multipa+
   9399 root      20   0   12332   5564   3416 R   7.1   0.0   0:00.05 top
      1 root      20   0   21872  13140   9596 S   0.0   0.0   0:04.04 systemd
      2 root      20   0       0      0      0 S   0.0   0.0   0:00.11 kthreadd
      3 root      20   0       0      0      0 S   0.0   0.0   0:00.00 pool_wo+
      4 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      5 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      6 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
```

---
Report generated at: Sun Mar 15 04:07:16 UTC 2026
