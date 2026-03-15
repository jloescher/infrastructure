# Infrastructure Report - re-db
**Generated:** Sun Mar 15 04:16:50 UTC 2026
**Timestamp:** 20260315_041650

# System Information

```
Linux re-db 6.8.0-90-generic #91-Ubuntu SMP PREEMPT_DYNAMIC Tue Nov 18 14:14:30 UTC 2025 x86_64 x86_64 x86_64 GNU/Linux

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
Mem:            47Gi       1.0Gi        45Gi       844Ki       799Mi        46Gi
Swap:             0B          0B          0B

Disk:
NAME    SIZE TYPE MOUNTPOINT FSTYPE
sda     720G disk            
├─sda1    1M part            
└─sda2  720G part /          ext4

Filesystem      Size  Used Avail Use% Mounted on
tmpfs           4.8G  824K  4.8G   1% /run
/dev/sda2       709G   15G  658G   3% /
tmpfs            24G     0   24G   0% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
tmpfs           4.8G   16K  4.8G   1% /run/user/0
```

# Network Information

## Tailscale

```
100.92.26.38    re-db                  jloescher@  linux  -                                                                        
100.74.169.15   iphone172              jloescher@  iOS    -                                                                        
100.107.244.55  jonathans-macbook-pro  jloescher@  macOS  idle, tx 10640 rx 178232                                                 
100.126.103.51  re-node-01             jloescher@  linux  active; direct [2602:ff16:3:0:1:d6:0:1]:41641, tx 139280796 rx 25957736  
100.101.39.22   re-node-02             jloescher@  linux  -                                                                        
100.114.117.46  re-node-03             jloescher@  linux  active; direct [2602:ff16:11:11fb::1]:41641, tx 42268 rx 29384           
100.115.75.119  re-node-04             jloescher@  linux  active; direct 172.93.54.122:41641, tx 64040 rx 44508                    
100.102.220.16  router-01              jloescher@  linux  active; direct 172.93.54.112:41641, tx 5507044 rx 3867276                
100.116.175.9   router-02              jloescher@  linux  active; direct [2602:ff16:3:10a3::1]:41641, tx 5308708 rx 3802140        

100.92.26.38
fd7a:115c:a1e0::2337:1a26
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
    link/ether 52:54:ce:38:b4:7a brd ff:ff:ff:ff:ff:ff
    inet 208.87.128.115/24 brd 208.87.128.255 scope global enp3s0
       valid_lft forever preferred_lft forever
    inet6 2602:ff16:3:0:1:446:0:1/64 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5054:ceff:fe38:b47a/64 scope link 
       valid_lft forever preferred_lft forever
4: tailscale0: <POINTOPOINT,MULTICAST,NOARP,UP,LOWER_UP> mtu 1280 qdisc fq_codel state UNKNOWN group default qlen 500
    link/none 
    inet 100.92.26.38/32 scope global tailscale0
       valid_lft forever preferred_lft forever
    inet6 fd7a:115c:a1e0::2337:1a26/128 scope global 
       valid_lft forever preferred_lft forever
    inet6 fe80::5868:3161:c6c3:40c0/64 scope link stable-privacy 
       valid_lft forever preferred_lft forever
```

## Listening Ports

```
Netid State  Recv-Q Send-Q               Local Address:Port  Peer Address:PortProcess
udp   UNCONN 0      0                       127.0.0.54:53         0.0.0.0:*          
udp   UNCONN 0      0                    127.0.0.53%lo:53         0.0.0.0:*          
udp   UNCONN 0      0                          0.0.0.0:41641      0.0.0.0:*          
udp   UNCONN 0      0                                *:443              *:*          
udp   UNCONN 0      0                             [::]:41641         [::]:*          
tcp   LISTEN 0      4096                       0.0.0.0:22         0.0.0.0:*          
tcp   LISTEN 0      4096                    127.0.0.54:53         0.0.0.0:*          
tcp   LISTEN 0      4096                  100.92.26.38:61920      0.0.0.0:*          
tcp   LISTEN 0      4096                 127.0.0.53%lo:53         0.0.0.0:*          
tcp   LISTEN 0      4096                             *:8001             *:*          
tcp   LISTEN 0      4096                             *:80               *:*          
tcp   LISTEN 0      4096                          [::]:22            [::]:*          
tcp   LISTEN 0      4096                             *:443              *:*          
tcp   LISTEN 0      4096   [fd7a:115c:a1e0::2337:1a26]:54561         [::]:*          
tcp   LISTEN 0      4096                             *:9090             *:*          
```

# PostgreSQL / Patroni

## Patroni Status

```
Patroni not installed
```

## PostgreSQL Status

```
/var/run/postgresql:5432 - no response
