# Infrastructure Plan

This document tracks current tasks, priorities, and future improvements for the Quantyra infrastructure.

## Status Overview

| Component | Status | Notes |
|-----------|--------|-------|
| HAProxy (Consolidated Frontends) | ✅ Complete | Both routers working |
| SSL Certificates (DNS-01) | ✅ Complete | Auto-renewal configured |
| Production (rentalfixer.app) | ✅ Working | Both routers serving |
| Staging (staging.rentalfixer.app) | ✅ Working | Both routers serving |
| Dashboard | ✅ Working | Deployed with all features |
| PostgreSQL Cluster | ✅ Working | 3-node Patroni cluster |
| Redis Cluster | ✅ Working | Master-replica with Sentinel |
| Monitoring | ✅ Working | Prometheus, Grafana, Alertmanager |

---

## Immediate Priority (Next Session)

### 1. Test Automatic Staging Provisioning

Validate the complete staging workflow through the dashboard.

**Steps:**
1. Create a new test application via dashboard
2. Provision staging environment
3. Verify:
   - SSL certificate created on both routers
   - HAProxy config generated (registry + rebuilt configs)
   - Nginx config on both app servers
   - PHP-FPM pool created
   - Database created
   - .env configured with APP_ENV=staging

**Validation:**
```bash
# Check staging works
curl -sI https://staging.testapp.domain.tld

# Check HAProxy registry
ssh root@router-01 "cat /etc/haproxy/domains/registry.conf"

# Check configs rebuilt
ssh root@router-01 "cat /etc/haproxy/domains/web_https.cfg | grep staging"
```

### 2. Test Delete Staging Functionality

Verify staging deletion works without affecting production.

**Steps:**
1. Delete staging environment via dashboard
2. Verify:
   - Staging nginx config removed from app servers
   - Staging PHP-FPM pool removed
   - Staging SSL cert removed from routers
   - Staging entry removed from registry
   - HAProxy configs rebuilt
   - Production still working

**Validation:**
```bash
# Staging should return 404/503
curl -sI https://staging.testapp.domain.tld

# Production should still work
curl -sI https://testapp.domain.tld
```

### 3. Verify GitHub Actions Workflow

Test CI/CD pipeline triggers correctly.

**Steps:**
1. Make a change to test app
2. Push to `staging` branch
3. Verify staging deployment triggers
4. Merge to `main`
5. Verify production deployment triggers

**Check:**
```bash
# View workflow runs
gh run list --repo owner/repo

# View workflow logs
gh run view --repo owner/repo
```

---

## Medium Priority

### 4. Certbot Auto-Renewal Deploy Hook

Add automatic HAProxy reload after certificate renewal.

**Implementation:**
```bash
# On both routers
ssh root@router-01
cat > /etc/letsencrypt/renewal-hooks/deploy/haproxy-reload.sh << 'EOF'
#!/bin/bash
# Reload HAProxy after cert renewal
systemctl reload haproxy
EOF
chmod +x /etc/letsencrypt/renewal-hooks/deploy/haproxy-reload.sh
```

**Test:**
```bash
# Dry run renewal
certbot renew --dry-run
```

### 5. PM2 Setup for Node.js Apps

Replace systemd with PM2 for better Node.js process management.

**Benefits:**
- Automatic restarts on crash
- Log management
- Cluster mode (multiple processes)
- Zero-downtime reloads
- Memory limit monitoring

**Implementation:**
```bash
# Install PM2 on app servers
npm install -g pm2

# Start app with PM2
pm2 start npm --name "appname" -- start
pm2 save
pm2 startup
```

**Dashboard Integration:**
- Update `run_framework_setup()` for Node.js
- Use PM2 instead of systemd service

### 6. Sync Router Configs

Ensure both routers stay in sync.

**Option A: Manual sync script**
```bash
#!/bin/bash
# sync-routers.sh
rsync -avz /etc/haproxy/domains/ root@router-02:/etc/haproxy/domains/
rsync -avz /etc/haproxy/certs/ root@router-02:/etc/haproxy/certs/
ssh root@router-02 "systemctl reload haproxy"
```

**Option B: Shared storage**
- Use NFS or distributed storage for `/etc/haproxy/domains`
- More complex but automatic sync

**Option C: Config management**
- Use Ansible to manage HAProxy configs
- Run playbook after changes

### 7. Backup Automation

Automate backups for HAProxy configs and registry.

**Implementation:**
```bash
# Cron job on router-01
0 * * * * tar -czf /backup/haproxy-$(date +\%Y\%m\%d-\%H\%M).tar.gz /etc/haproxy/domains /etc/haproxy/certs
```

**Retention:**
- Keep hourly backups for 24 hours
- Keep daily backups for 7 days

---

## Lower Priority

### 8. Cloudflare Load Balancer ($5/month)

Add active health monitoring for routers.

**Benefits:**
- Active health checks (not just HTTP retry)
- Automatic DNS failover
- Geographic load balancing
- Steer traffic away from unhealthy origins

**Setup:**
1. Enable Cloudflare Load Balancer
2. Create health check: `GET /health` on port 443
3. Create pool with both routers
4. Create load balancer for domain

**Cost:** $5/month per zone

### 9. App-Specific Monitoring Dashboards

Create Grafana dashboards per application.

**Metrics to include:**
- Request rate (requests/sec)
- Response time (p50, p95, p99)
- Error rate (4xx, 5xx)
- Active connections
- PHP-FPM process count
- Database query time

**Implementation:**
- Create dashboard JSON template
- Auto-provision when app created
- Link from dashboard UI

### 10. Environment Variable Customization

Allow custom environment variables in create_app wizard.

**UI Changes:**
- Add "Environment Variables" section
- Key-value input
- Preset templates for common configs

**Backend:**
- Store in applications.yml
- Inject into .env on deployment

### 11. Build Command Customization

Allow custom build commands per app.

**UI Changes:**
- Add "Build Command" field
- Auto-detect default
- Allow override

**Backend:**
- Store in applications.yml
- Run during deployment

### 12. Health Check Endpoints

Add standardized health check endpoints for all apps.

**Laravel:**
```php
Route::get('/health', function () {
    return response()->json(['status' => 'ok']);
});
```

**Next.js:**
```javascript
// pages/api/health.js
export default function handler(req, res) {
  res.status(200).json({ status: 'ok' });
}
```

---

## Completed

| Task | Date | Notes |
|------|------|-------|
| HAProxy consolidated frontends | 2026-03-15 | Fixed 503 errors |
| SSL DNS-01 challenge | 2026-03-15 | Works with Cloudflare proxy |
| Domain registry system | 2026-03-15 | `/etc/haproxy/domains/registry.conf` |
| Python app support | 2026-03-15 | Gunicorn + systemd |
| Redis secrets to GitHub | 2026-03-15 | REDIS_URL pushed |
| Build tool detection | 2026-03-15 | Vite, Next.js, SvelteKit, etc. |
| APP_URL auto-configuration | 2026-03-15 | Updated on domain provision |
| Staging environment setup | 2026-03-15 | staging.rentalfixer.app |
| Node exporter monitoring | 2026-03-15 | All servers reporting |

---

## Notes

### HAProxy Architecture Decision

**Problem:** Multiple frontends on port 443 caused SNI routing issues and 503 errors.

**Solution:** Consolidated all domains into single frontends (`web_http`, `web_https`) with multiple certificates.

**Key Files:**
- `/etc/haproxy/domains/registry.conf` - Domain registry
- `/etc/haproxy/domains/web_http.cfg` - HTTP redirects
- `/etc/haproxy/domains/web_https.cfg` - HTTPS routing
- `/etc/haproxy/domains/web_backends.cfg` - All backends

**Never create per-domain frontend configs.** Always update registry and rebuild:
```bash
/opt/scripts/provision-domain.sh --rebuild
```

### SSL Certificate Strategy

**DNS-01 Challenge:**
- Required because Cloudflare proxy intercepts HTTP traffic
- Certbot creates TXT record in Cloudflare DNS
- Let's Encrypt validates via DNS
- No downtime required

**Auto-Renewal:**
- Certbot systemd timer runs twice daily
- Renews 30 days before expiry
- **TODO:** Add deploy hook to reload HAProxy

### Load Balancing Layers

1. **Cloudflare → Routers**: DNS round-robin + HTTP retry
2. **Router → App Servers**: HAProxy round-robin + health checks

**Limitation:** No active health checks at Cloudflare layer (requires paid Load Balancer).

### Critical Credentials

See `AGENTS.md` for all credentials. Key items:
- HAProxy stats: `http://router:8404/stats` (admin:jFNeZ2bhfrTjTK7aKApD)
- Dashboard: `http://100.102.220.16:8080` (admin:DbAdmin2026!)
- Cloudflare API Token: Stored in `/root/.secrets/cloudflare.ini` on routers