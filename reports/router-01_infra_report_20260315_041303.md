# Infrastructure Report - router-01
**Generated:** Sun Mar 15 04:13:03 UTC 2026
**Timestamp:** 20260315_041303

# System Information

```
Linux router-01 6.8.0-85-generic #85-Ubuntu SMP PREEMPT_DYNAMIC Thu Sep 18 15:26:59 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux

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
Mem:           7.8Gi       694Mi       2.4Gi       848Ki       5.0Gi       7.1Gi
Swap:             0B          0B          0B

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     160G disk            
├─sda1    1M part            
└─sda2  160G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           795M  824K  794M   1% /run
/dev/sda2       158G  6.3G  144G   5% /
tmpfs           3.9G  4.0K  3.9G   1% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           795M   16K  795M   1% /run/user/0
```

# Network Information

## Tailscale

```
100.102.220.16  router-01              jloescher@  linux  -                                                                      
100.74.169.15   iphone172              jloescher@  iOS    -                                                                      
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  active; direct 47.201.4.123:14773, tx 34132572 rx 2450524              
100.92.26.38    re-db                  jloescher@  linux  active; direct 208.87.128.115:41641, tx 4139780 rx 5112708             
100.126.103.51  re-node-01             jloescher@  linux  active; direct [2602:ff16:3:0:1:d6:0:1]:41641, tx 5245668 rx 18493748  
100.101.39.22   re-node-02             jloescher@  linux  active; direct [2602:ff16:3:1299::1]:41641, tx 1559012 rx 1188436      
100.114.117.46  re-node-03             jloescher@  linux  active; direct [2602:ff16:11:11fb::1]:41641, tx 4694420 rx 16738748    
100.115.75.119  re-node-04             jloescher@  linux  active; direct [2602:ff16:11:10c6::1]:41641, tx 4285976 rx 15423268    
100.116.175.9   router-02              jloescher@  linux  -                                                                      

100.102.220.16
fd7a:115c:a1e0::1136:dc10
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
    link/ether 52:54:83:6b:83:66 brd ff:ff:ff:ff:ff:ff
    inet 172.93.54.112/24 brd 172.93.54.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:11:12a0::1/48 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:83ff:fe6b:8366/64 scope link 
       valid_lft forever preferred_lft forever
4: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.102.220.16/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::1136:dc10/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::7679:6430:a481:8e76/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
tcp   LISTEN 0      4096                 127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:62711      0.0.0.0:*          
tcp   LISTEN 0      4096                    127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:8405       0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:80         0.0.0.0:*          
tcp   LISTEN 0      511                      127.0.0.1:6379       0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      4096                     127.0.0.1:2379       0.0.0.0:*          
tcp   LISTEN 0      4096                       0.0.0.0:443        0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:9090       0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:5000       0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:5001       0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:2380       0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:2379       0.0.0.0:*          
tcp   LISTEN 0      4096                100.102.220.16:3000       0.0.0.0:*          
tcp   LISTEN 0      4096                             *:9100             *:*          
tcp   LISTEN 0      4096                          [::]:22            [::]:*          
tcp   LISTEN 0      4096   [fd7a:115c:a1e0::1136:dc10]:55879         [::]:*          
tcp   LISTEN 0      511                          [::1]:6379          [::]:*          
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
Redis not responding on Tailscale IP

