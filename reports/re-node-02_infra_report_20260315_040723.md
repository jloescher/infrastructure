# Infrastructure Report - re-node-02
**Generated:** Sun Mar 15 04:07:23 UTC 2026
**Timestamp:** 20260315_040723

# System Information

```
Linux re-node-02 6.8.0-90-generic #91-Ubuntu SMP PREEMPT_DYNAMIC Tue Nov 18 14:14:30 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux

PRETTY_NAME="Ubuntu 24.04.3 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.3 LTS (Noble Numbat)"
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
CPU(s):                               12
Model name:                           Intel(R) Xeon(R) Silver 4216 CPU @ 2.10GHz
BIOS Model name:                      pc-q35-10.0  CPU @ 2.0GHz
Thread(s) per core:                   1
Core(s) per socket:                   1
Socket(s):                            12

Memory:
               total        used        free      shared  buff/cache   available
Mem:            47Gi       873Mi        43Gi       804Ki       2.8Gi        46Gi
Swap:             0B          0B          0B

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     720G disk            
├─sda1    1M part            
└─sda2  720G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           4.8G  796K  4.8G   1% /run
/dev/sda2       709G  6.3G  667G   1% /
tmpfs            24G     0   24G   0% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           4.8G   16K  4.8G   1% /run/user/0
```

# Network Information

## Tailscale

```
100.101.39.22   re-node-02             jloescher@  linux  -                                                                   
100.74.169.15   iphone172              jloescher@  iOS    -                                                                   
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  active; direct 47.201.4.123:14773, tx 21728 rx 203256               
100.92.26.38    re-db                  jloescher@  linux  -                                                                   
100.126.103.51  re-node-01             jloescher@  linux  -                                                                   
100.114.117.46  re-node-03             jloescher@  linux  -                                                                   
100.115.75.119  re-node-04             jloescher@  linux  -                                                                   
100.102.220.16  router-01              jloescher@  linux  active; direct [2602:ff16:11:12a0::1]:41641, tx 1287236 rx 1417060  
100.116.175.9   router-02              jloescher@  linux  active; direct 23.29.118.6:41641, tx 1244660 rx 1370188             

100.101.39.22
fd7a:115c:a1e0::b137:2716
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
    link/ether 52:54:91:ea:c4:2b brd ff:ff:ff:ff:ff:ff
    inet 23.29.118.8/24 brd 23.29.118.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:3:1299::1/48 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:91ff:feea:c42b/64 scope link 
       valid_lft forever preferred_lft forever
5: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.101.39.22/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::b137:2716/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::d8a3:5f46:f015:be4f/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
tcp   LISTEN 0      4096                    127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      4096                 100.101.39.22:55277      0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      4096                 127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      4096                          [::]:22            [::]:*          
tcp   LISTEN 0      4096   [fd7a:115c:a1e0::b137:2716]:44339         [::]:*          
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
  dbus.service                loaded active running D-Bus System Message Bus
  getty@tty1.service          loaded active running Getty on tty1
  multipathd.service          loaded active running Device-Mapper Multipath Device Controller
  qemu-guest-agent.service    loaded active running QEMU Guest Agent
  rsyslog.service             loaded active running System Logging Service
  ssh.service                 loaded active running OpenBSD Secure Shell server
  systemd-journald.service    loaded active running Journal Service
  systemd-logind.service      loaded active running User Login Management
  systemd-networkd.service    loaded active running Network Configuration
  systemd-resolved.service    loaded active running Network Name Resolution
  systemd-timesyncd.service   loaded active running Network Time Synchronization
  tailscaled.service          loaded active running Tailscale node agent
  unattended-upgrades.service loaded active running Unattended Upgrades Shutdown
  user@0.service              loaded active running User Manager for UID 0

Legend: LOAD   → Reflects whether the unit definition was properly loaded.
        ACTIVE → The high-level unit activation state, i.e. generalization of SUB.
        SUB    → The low-level unit activation state, values depend on unit type.

14 loaded units listed.
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
6379/tcp                   DENY IN     Anywhere                   # Block Dragonfly laravel
6380/tcp                   DENY IN     Anywhere                  
22/tcp                     ALLOW IN    Anywhere                   # SSH
80/tcp                     ALLOW IN    Anywhere                   # HTTP
443/tcp                    ALLOW IN    Anywhere                   # HTTPS
6379/tcp (v6)              DENY IN     Anywhere (v6)              # Block Dragonfly laravel
6380/tcp (v6)              DENY IN     Anywhere (v6)             
22/tcp (v6)                ALLOW IN    Anywhere (v6)              # SSH
80/tcp (v6)                ALLOW IN    Anywhere (v6)              # HTTP
443/tcp (v6)               ALLOW IN    Anywhere (v6)              # HTTPS

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
total 1.6M
drwxr-xr-x  3 root root 4.0K Feb 20 00:00 .
drwxr-xr-x 13 root root 4.0K May 20  2024 ..
-rw-r--r--  1 root root  40K Dec 29 00:00 alternatives.tar.0
-rw-r--r--  1 root root 1.9K Dec 28 21:45 alternatives.tar.1.gz
-rw-r--r--  1 root root 1.9K Oct 14 17:03 alternatives.tar.2.gz
-rw-r--r--  1 root root  28K Feb 10 06:05 apt.extended_states.0
-rw-r--r--  1 root root 3.1K Feb  5 06:05 apt.extended_states.1.gz
-rw-r--r--  1 root root 3.1K Dec 29 06:32 apt.extended_states.2.gz
-rw-r--r--  1 root root 3.2K Oct 14 17:08 apt.extended_states.3.gz
-rw-r--r--  1 root root 3.2K Oct 14 17:04 apt.extended_states.4.gz
-rw-r--r--  1 root root    0 Feb 20 00:00 dpkg.arch.0
-rw-r--r--  1 root root   32 Feb 18 00:00 dpkg.arch.1.gz
-rw-r--r--  1 root root   32 Feb 15 00:00 dpkg.arch.2.gz
-rw-r--r--  1 root root   32 Feb 11 00:00 dpkg.arch.3.gz
-rw-r--r--  1 root root   32 Feb  8 00:00 dpkg.arch.4.gz
-rw-r--r--  1 root root   32 Feb  6 00:00 dpkg.arch.5.gz
-rw-r--r--  1 root root   32 Feb  5 00:00 dpkg.arch.6.gz
-rw-r--r--  1 root root 1.4K Oct 14 17:09 dpkg.diversions.0
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.1.gz
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.2.gz
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.3.gz
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.4.gz
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.5.gz
-rw-r--r--  1 root root  305 Oct 14 17:09 dpkg.diversions.6.gz
-rw-r--r--  1 root root  109 Dec 28 21:55 dpkg.statoverride.0
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.1.gz
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.2.gz
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.3.gz
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.4.gz
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.5.gz
-rw-r--r--  1 root root  125 Dec 28 21:55 dpkg.statoverride.6.gz
-rw-r--r--  1 root root 549K Feb 19 06:49 dpkg.status.0
-rw-r--r--  1 root root 136K Feb 17 06:34 dpkg.status.1.gz
-rw-r--r--  1 root root 136K Feb 14 06:51 dpkg.status.2.gz
-rw-r--r--  1 root root 136K Feb 10 06:05 dpkg.status.3.gz
-rw-r--r--  1 root root 136K Feb  7 06:17 dpkg.status.4.gz
-rw-r--r--  1 root root 136K Feb  5 06:05 dpkg.status.5.gz
-rw-r--r--  1 root root 136K Feb  4 06:16 dpkg.status.6.gz
drwx------  3 root root 4.0K Mar 15 02:30 server

```

## Cron Jobs (Backups)

```
No user crontab

No backup cron jobs found
```

# System Resources (Current)

```
 04:07:24 up 63 days, 23:03,  1 user,  load average: 1.09, 1.04, 1.01

top - 04:07:24 up 63 days, 23:03,  1 user,  load average: 1.09, 1.04, 1.01
Tasks: 265 total,   1 running, 264 sleeping,   0 stopped,   0 zombie
%Cpu(s):  0.5 us,  1.6 sy,  0.0 ni, 97.3 id,  0.5 wa,  0.0 hi,  0.0 si,  0.0 st 
MiB Mem :  48174.4 total,  45011.9 free,    887.1 used,   2841.9 buff/cache     
MiB Swap:      0.0 total,      0.0 free,      0.0 used.  47287.3 avail Mem 

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
      1 root      20   0   21952  12160   8832 S   0.0   0.0  42:03.73 systemd
      2 root      20   0       0      0      0 S   0.0   0.0   0:31.46 kthreadd
      3 root      20   0       0      0      0 S   0.0   0.0   0:00.00 pool_wo+
      4 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      5 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      6 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      7 root       0 -20       0      0      0 I   0.0   0.0   0:00.00 kworker+
      9 root       0 -20       0      0      0 I   0.0   0.0   0:10.58 kworker+
```

---
Report generated at: Sun Mar 15 04:07:24 UTC 2026
