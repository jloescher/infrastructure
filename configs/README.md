# Infrastructure Configurations

This directory contains all configuration files synced from the production servers.

## Directory Structure

```
configs/
├── haproxy/
│   ├── router-01/          # HAProxy configs from router-01 (172.93.54.112)
│   │   ├── haproxy.cfg     # Main HAProxy config
│   │   ├── registry.conf   # Domain registry
│   │   ├── web_http.cfg    # HTTP frontend
│   │   ├── web_https.cfg   # HTTPS frontend
│   │   └── web_backends.cfg # All backends
│   └── router-02/          # HAProxy configs from router-02 (23.29.118.6)
│
├── app-servers/
│   ├── re-db/              # App server 1 (100.92.26.38)
│   │   ├── nginx.conf
│   │   ├── sites-enabled.conf
│   │   └── php-fpm/        # PHP-FPM pool configs
│   └── re-node-02/         # App server 2 (100.101.39.22)
│       ├── nginx.conf
│       ├── sites-enabled.conf
│       └── php-fpm/
│
├── postgres/
│   ├── patroni-*.yml       # Patroni configs per node
│   ├── dcs-*.yml          # DCS configs per node
│   └── postgresql-*.conf  # PostgreSQL configs (non-default only)
│
├── redis/
│   └── redis-*.conf       # Redis configs per node
│
├── dashboard/
│   ├── .env.example       # Dashboard environment (sanitized)
│   ├── applications.yml   # Application definitions
│   └── databases.yml      # Database definitions
│
├── certbot/
│   └── renewal-*.conf     # Certificate renewal configs
│
├── systemd/
│   └── *.service          # Systemd service files
│
├── provision-scripts/
│   └── provision-domain-*.sh  # Domain provisioning scripts
│
└── apps/
    └── *.env.example      # App environment files (sanitized)
```

## Syncing Configs

To sync configs from servers to this directory:

```bash
# Run from infrastructure root
./scripts/sync-configs.sh
```

## Important Notes

1. **Never commit actual secrets** - All .env files should be sanitized
2. **Registry is source of truth** - Domain registry controls HAProxy routing
3. **Both routers should match** - Domain configs should be identical
4. **App servers should match** - Nginx/PHP-FPM configs should be identical

## Server IPs

| Server | Tailscale IP | Public IP |
|--------|--------------|-----------|
| router-01 | 100.102.220.16 | 172.93.54.112 |
| router-02 | 100.116.175.9 | 23.29.118.6 |
| re-db | 100.92.26.38 | 208.87.128.115 |
| re-node-02 | 100.101.39.22 | 23.29.118.8 |
| re-node-01 | 100.126.103.51 | - |
| re-node-03 | 100.114.117.46 | - |
| re-node-04 | 100.115.75.119 | - |
