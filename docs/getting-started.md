# Getting Started with Quantyra PaaS

## Quick Start

1. Access the dashboard at http://100.102.220.16:8080
2. Login with admin / DbAdmin2026!
3. Create your first application
4. Configure domains
5. Deploy!

## First Application

### Step 1: Create Application

1. Navigate to **Applications** → **Create Application**
2. Fill in:
   - **Name**: my-app
   - **Framework**: Laravel (or Next.js, Python, Go)
   - **Repository**: https://github.com/user/my-app
   - **Production Branch**: main
   - **Staging Branch**: staging

3. Click **Create Application**

### Step 2: Configure Environment

1. Go to **Applications** → **my-app** → **Secrets**
2. Add required environment variables:
   - `APP_KEY` (for Laravel)
   - `DB_DATABASE`
   - `DB_USERNAME`
   - `DB_PASSWORD`

### Step 3: Provision Domain

1. Go to **Applications** → **my-app** → **Domains**
2. Click **Add Domain**
3. Configure:
   - **Domain**: myapp.example.com
   - **Environment**: Production
   - **SSL**: Enabled
4. Click **Provision**

### Step 4: Deploy

1. Go to **Applications** → **my-app**
2. Click **Deploy**
3. Select branch and click **Deploy Now**
4. Watch real-time progress

## Framework-Specific Guides

### Laravel

1. Ensure `composer.json` exists in root
2. Add these secrets:
   - `APP_KEY`
   - `DB_*` variables
3. Migrations run automatically

### Next.js

1. Ensure `package.json` and `next.config.js` exist
2. Add `NEXT_PUBLIC_*` variables as needed
3. Build happens automatically

### Python (Flask/Django)

1. Ensure `requirements.txt` exists
2. For Django, add `SECRET_KEY`
3. Gunicorn configured automatically

### Go

1. Ensure `go.mod` exists
2. Binary built automatically
3. Runs as systemd service

## Adding Services

### Redis

1. Go to **Applications** → **my-app** → **Services**
2. Click **Add Service**
3. Select **Redis**
4. Set memory limit
5. Connection string auto-injected

### Meilisearch

1. Click **Add Service**
2. Select **Meilisearch**
3. API key auto-generated
4. Use for search functionality

## Monitoring

### Prometheus

Access at http://100.102.220.16:9090

### Grafana

Access at http://100.102.220.16:3000

Default credentials: admin / admin

### Alerts

1. Go to **Alerts** in dashboard
2. View active alerts
3. Create silences for maintenance

## Troubleshooting

### Deployment Failed

1. Check **Deployment Logs** in dashboard
2. SSH to server: `ssh root@100.92.26.38`
3. Check service: `systemctl status php8.5-fpm`

### Domain Not Accessible

1. Check DNS in Cloudflare
2. Verify SSL certificate: `certbot certificates`
3. Check HAProxy: `haproxy -c -f /etc/haproxy/haproxy.cfg`

### Database Connection Issues

1. Check PostgreSQL cluster: `patronictl list`
2. Verify credentials in Secrets
3. Test connection: `psql -h router-01 -p 5000 -U user -d database`

## Key Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Dashboard | http://100.102.220.16:8080 | PaaS management UI |
| HAProxy Stats | http://100.102.220.16:8404/stats | Load balancer status |
| Prometheus | http://100.102.220.16:9090 | Metrics |
| Grafana | http://100.102.220.16:3000 | Dashboards |
| Alertmanager | http://100.102.220.16:9093 | Alert management |

## Server Inventory

| Server | Tailscale IP | Public IP | Role |
|--------|--------------|-----------|------|
| router-01 | 100.102.220.16 | 172.93.54.112 | HAProxy, Monitoring, Dashboard |
| router-02 | 100.116.175.9 | 23.29.118.6 | HAProxy (Secondary) |
| re-db | 100.92.26.38 | 208.87.128.115 | App Server (Primary) |
| re-node-02 | 100.89.130.19 | 23.227.173.245 | App Server (ATL) |
| re-node-01 | 100.126.103.51 | 104.225.216.26 | PostgreSQL, Redis Master |
| re-node-03 | 100.114.117.46 | 172.93.54.145 | PostgreSQL Leader, Redis Replica |
| re-node-04 | 100.115.75.119 | 172.93.54.122 | PostgreSQL Replica, etcd |

## Next Steps

- Read the [API Documentation](api.md) for programmatic access
- Review the [Runbook](runbook.md) for operational procedures
- Explore the [Architecture](architecture-diagram.md) for system understanding