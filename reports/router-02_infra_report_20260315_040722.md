# Infrastructure Report - router-02
**Generated:** Sun Mar 15 04:07:22 UTC 2026
**Timestamp:** 20260315_040722

# System Information

```
Linux router-02 6.8.0-85-generic #85-Ubuntu SMP PREEMPT_DYNAMIC Thu Sep 18 15:26:59 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux

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
CPU(s):                               2
Model name:                           Intel(R) Xeon(R) Silver 4216 CPU @ 2.10GHz
BIOS Model name:                      pc-q35-10.0  CPU @ 2.0GHz
Thread(s) per core:                   1
Core(s) per socket:                   1
Socket(s):                            2

Memory:
               total        used        free      shared  buff/cache   available
Mem:           7.8Gi       510Mi       4.7Gi       812Ki       2.9Gi       7.3Gi
Swap:             0B          0B          0B

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     160G disk            
├─sda1    1M part            
└─sda2  160G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           795M  792K  794M   1% /run
/dev/sda2       158G  4.2G  146G   3% /
tmpfs           3.9G  4.0K  3.9G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           795M   16K  795M   1% /run/user/0
```

# Network Information

## Tailscale

```
100.116.175.9   router-02              jloescher@  linux  -                                                                      
100.74.169.15   iphone172              jloescher@  iOS    -                                                                      
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  active; direct 47.201.4.123:14773, tx 20904 rx 202168                  
100.92.26.38    re-db                  jloescher@  linux  active; direct [2602:ff16:3:0:1:446:0:1]:41641, tx 4004948 rx 4851016  
100.126.103.51  re-node-01             jloescher@  linux  active; direct [2602:ff16:3:0:1:d6:0:1]:41641, tx 1512580 rx 4327196   
100.101.39.22   re-node-02             jloescher@  linux  active; direct [2602:ff16:3:1299::1]:41641, tx 1484748 rx 1131700      
100.114.117.46  re-node-03             jloescher@  linux  active; direct [2602:ff16:11:11fb::1]:41641, tx 1396496 rx 3415036     
100.115.75.119  re-node-04             jloescher@  linux  active; direct [2602:ff16:11:10c6::1]:41641, tx 1273620 rx 3096564     
100.102.220.16  router-01              jloescher@  linux  -                                                                      

100.116.175.9
fd7a:115c:a1e0::1c36:af09
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
    link/ether 52:54:28:dd:2b:61 brd ff:ff:ff:ff:ff:ff
    inet 23.29.118.6/24 brd 23.29.118.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:3:10a3::1/48 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:28ff:fedd:2b61/64 scope link 
       valid_lft forever preferred_lft forever
4: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.116.175.9/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::1c36:af09/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5158:ce5e:56ce:13ae/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
tcp   LISTEN 0      4096                    127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:443        0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:80         0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:8405       0.0.0.0:*          
tcp   LISTEN 0      4096                 100.116.175.9:33052      0.0.0.0:*          
tcp   LISTEN 0      4096                 127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      4096                 100.116.175.9:5000       0.0.0.0:*          
tcp   LISTEN 0      4096                 100.116.175.9:5001       0.0.0.0:*          
tcp   LISTEN 0      4096                             *:9100             *:*          
tcp   LISTEN 0      4096   [fd7a:115c:a1e0::1c36:af09]:55474         [::]:*          
tcp   LISTEN 0      4096                          [::]:22            [::]:*          
```

# PostgreSQL / Patroni

## Patroni Status

```
Patroni not installed
```

## PostgreSQL Status

```
PostgreSQL not installed
```

## PostgreSQL Config

```
PostgreSQL config directory not found
```

# Redis

## Redis Status

```
Redis not installed
```

## Redis Config

```
Redis config not found
```

# Router Services (HAProxy, etcd)

## HAProxy

```
HAProxy version 2.8.16-0ubuntu0.24.04.1 2025/12/03 - https://haproxy.org/
Status: long-term supported branch - will stop receiving fixes around Q2 2028.
Known bugs: http://www.haproxy.org/bugs/bugs-2.8.16.html
Running on: Linux 6.8.0-85-generic #85-Ubuntu SMP PREEMPT_DYNAMIC Thu Sep 18 15:26:59 UTC 2025 x86_64

● haproxy.service - HAProxy Load Balancer
     Loaded: loaded (/usr/lib/systemd/system/haproxy.service; enabled; preset: enabled)
     Active: active (running) since Sat 2026-03-14 22:18:21 UTC; 5h 49min ago
       Docs: man:haproxy(1)
             file:/usr/share/doc/haproxy/configuration.txt.gz
   Main PID: 17442 (haproxy)
     Status: "Ready."
      Tasks: 3 (limit: 9434)
     Memory: 13.6M (peak: 14.1M)
        CPU: 40.812s
     CGroup: /system.slice/haproxy.service
             ├─17442 /usr/sbin/haproxy -Ws -f /etc/haproxy/haproxy.cfg -p /run/haproxy.pid -S /run/haproxy-master.sock
             └─17444 /usr/sbin/haproxy -Ws -f /etc/haproxy/haproxy.cfg -p /run/haproxy.pid -S /run/haproxy-master.sock

Mar 15 03:02:06 router-02 haproxy[17444]: Connect from 176.65.148.66:40062 to 23.29.118.6:80 (web_http/HTTP)
Mar 15 03:02:07 router-02 haproxy[17444]: Connect from 176.65.148.66:40062 to 23.29.118.6:80 (web_http/HTTP)
Mar 15 03:02:08 router-02 haproxy[17444]: Connect from 176.65.148.66:40062 to 23.29.118.6:80 (web_http/HTTP)
Mar 15 03:02:09 router-02 haproxy[17444]: Connect from 176.65.148.66:40064 to 23.29.118.6:80 (web_http/HTTP)
Mar 15 03:02:11 router-02 haproxy[17444]: Connect from 176.65.148.66:40078 to 23.29.118.6:80 (web_http/HTTP)
Mar 15 03:06:13 router-02 haproxy[17444]: Connect from 34.96.41.250:50289 to 23.29.118.6:443 (web_https/TCP)
```

## HAProxy Config

```
global
    log /dev/log local0
    log /dev/log local1 notice
    user haproxy
    group haproxy
    daemon
    maxconn 50000
    stats socket /run/haproxy/admin.sock mode 660 level admin expose-fd listeners

defaults
    log global
    option dontlognull
    timeout connect 5s
    timeout client 60s
    timeout server 60s
    retries 3

frontend haproxy_metrics
    bind :8405
    mode http
    http-request use-service prometheus-exporter if { path /metrics }
    no log

frontend pg_rw
    bind 100.116.175.9:5000
    mode tcp
    default_backend pg_primary

backend pg_primary
    mode tcp
    option httpchk GET /primary
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server re-node-01 100.126.103.51:5432 check port 8008
    server re-node-03 100.114.117.46:5432 check port 8008
    server re-node-04 100.115.75.119:5432 check port 8008

frontend pg_ro
    bind 100.116.175.9:5001
    mode tcp
    default_backend pg_replicas

backend pg_replicas
    mode tcp
    balance roundrobin
    option httpchk GET /replica
    http-check expect status 200
    default-server inter 3s fall 3 rise 2 on-marked-down shutdown-sessions
    server re-node-03 100.114.117.46:5432 check port 8008
    server re-node-04 100.115.75.119:5432 check port 8008
    server re-node-01 100.126.103.51:5432 check port 8008 backup

frontend web_http
    bind :80
    mode http
    option forwardfor
    default_backend apps_http

backend apps_http
    mode http
    balance roundrobin
    option httpchk GET /
    http-check expect status 200-399
    default-server inter 3s fall 3 rise 2
    server app1 100.92.26.38:80 check
    server app2 100.101.39.22:80 check

frontend web_https
    bind :443
    mode tcp
    default_backend apps_https

backend apps_https
    mode tcp
    balance roundrobin
    option tcp-check
    default-server inter 3s fall 3 rise 2
    server app1 100.92.26.38:443 check
    server app2 100.101.39.22:443 check
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
  dbus.service                loaded active running D-Bus System Message Bus
  getty@tty1.service          loaded active running Getty on tty1
  haproxy.service             loaded active running HAProxy Load Balancer
  multipathd.service          loaded active running Device-Mapper Multipath Device Controller
  node_exporter.service       loaded active running Prometheus Node Exporter
  qemu-guest-agent.service    loaded active running QEMU Guest Agent
  rsyslog.service             loaded active running System Logging Service
  ssh.service                 loaded active running OpenBSD Secure Shell server
  systemd-journald.service    loaded active running Journal Service
  systemd-logind.service      loaded active running User Login Management
  systemd-networkd.service    loaded active running Network Configuration
  systemd-resolved.service    loaded active running Network Name Resolution
  systemd-timesyncd.service   loaded active running Network Time Synchronization
  systemd-udevd.service       loaded active running Rule-based Manager for Device Events and Files
  tailscaled.service          loaded active running Tailscale node agent
  unattended-upgrades.service loaded active running Unattended Upgrades Shutdown
  user@0.service              loaded active running User Manager for UID 0

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.
        SUB    → The low-level unit activation state, values depend on unit type.

17 loaded units listed.
```

# Security

## Firewall (UFW)

```
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing), disabled (routed)
New profiles: skip

To                         Action      From
--                         ------      ----
22/tcp (OpenSSH)           ALLOW IN    Anywhere                  
80/tcp                     ALLOW IN    Anywhere                  
443/tcp                    ALLOW IN    Anywhere                  
8405/tcp                   ALLOW IN    Anywhere                  
5000/tcp                   ALLOW IN    Anywhere                  
5001/tcp                   ALLOW IN    Anywhere                  
22/tcp (OpenSSH (v6))      ALLOW IN    Anywhere (v6)             
80/tcp (v6)                ALLOW IN    Anywhere (v6)             
443/tcp (v6)               ALLOW IN    Anywhere (v6)             
8405/tcp (v6)              ALLOW IN    Anywhere (v6)             
5000/tcp (v6)              ALLOW IN    Anywhere (v6)             
5001/tcp (v6)              ALLOW IN    Anywhere (v6)             

```

## SSH Config

```
Include /etc/ssh/sshd_config.d/*.conf
PermitRootLogin yes
KbdInteractiveAuthentication no
PermitRootLogin yes
UsePAM yes
X11Forwarding yes
PrintMotd no
AcceptEnv LANG LC_*
Subsystem	sftp	/usr/lib/openssh/sftp-server
```

## Active SSH Sessions

```
```

# Backup Configuration

## Backup Directories

```
=== /var/backups ===
total 944K
drwxr-xr-x  2 root root 4.0K Mar 15 00:00 .
drwxr-xr-x 13 root root 4.0K May 20  2024 ..
-rw-r--r--  1 root root  40K Mar 15 00:00 alternatives.tar.0
-rw-r--r--  1 root root 1.9K Mar 14 21:31 alternatives.tar.1.gz
-rw-r--r--  1 root root 1.9K Oct 14 17:03 alternatives.tar.2.gz
-rw-r--r--  1 root root  29K Mar 14 22:12 apt.extended_states.0
-rw-r--r--  1 root root 3.2K Oct 14 17:04 apt.extended_states.1.gz
-rw-r--r--  1 root root    0 Mar 15 00:00 dpkg.arch.0
-rw-r--r--  1 root root   32 Mar 14 21:31 dpkg.arch.1.gz
-rw-r--r--  1 root root   32 Oct 14 17:03 dpkg.arch.2.gz
-rw-r--r--  1 root root 1.4K Mar 14 22:12 dpkg.diversions.0
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.1.gz
-rw-r--r--  1 root root  333 May 20  2024 dpkg.diversions.2.gz
-rw-r--r--  1 root root   65 Apr 23  2024 dpkg.statoverride.0
-rw-r--r--  1 root root   99 Apr 23  2024 dpkg.statoverride.1.gz
-rw-r--r--  1 root root   99 Apr 23  2024 dpkg.statoverride.2.gz
-rw-r--r--  1 root root 549K Mar 14 22:15 dpkg.status.0
-rw-r--r--  1 root root 133K Oct 14 17:09 dpkg.status.1.gz
-rw-r--r--  1 root root 132K May 20  2024 dpkg.status.2.gz

```

## Cron Jobs (Backups)

```
No user crontab

No backup cron jobs found
```

# System Resources (Current)

```
 04:07:22 up  6:35,  1 user,  load average: 0.00, 0.00, 0.00

top - 04:07:23 up  6:35,  1 user,  load average: 0.00, 0.00, 0.00
Tasks: 149 total,   1 running, 148 sleeping,   0 stopped,   0 zombie
%Cpu(s):  0.0 us,  4.3 sy,  0.0 ni, 91.3 id,  4.3 wa,  0.0 hi,  0.0 si,  0.0 st 
MiB Mem :   7942.0 total,   4778.0 free,    523.6 used,   2952.3 buff/cache     
MiB Swap:      0.0 total,      0.0 free,      0.0 used.   7418.5 avail Mem 

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
      1 root      20   0   22224  13312   9600 S   0.0   0.2   0:14.22 systemd
      2 root      20   0       0      0      0 S   0.0   0.0   0:00.03 kthreadd
      3 root      20   0       0      0      0 S   0.0   0.0   0:00.00 pool_wo+
      4 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      5 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      6 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      7 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      9 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
```

---
Report generated at: Sun Mar 15 04:07:23 UTC 2026
