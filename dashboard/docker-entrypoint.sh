#!/bin/bash
# Quantyra PaaS Dashboard - Docker Entrypoint

echo ""
echo "=========================================="
echo "  Quantyra PaaS Dashboard"
echo "=========================================="
echo ""

# Detect how to access the dashboard
if [ -n "$LOCAL_TAILSCALE_IP" ]; then
    DASHBOARD_URL="http://$LOCAL_TAILSCALE_IP:8080"
elif command -v ip &> /dev/null; then
    TAILSCALE_IP=$(ip addr show tailscale0 2>/dev/null | grep -oP 'inet \K[0-9.]+')
    if [ -n "$TAILSCALE_IP" ]; then
        DASHBOARD_URL="http://$TAILSCALE_IP:8080"
    else
        DASHBOARD_URL="http://localhost:8080"
    fi
else
    DASHBOARD_URL="http://localhost:8080"
fi

# Print connection instructions
echo "Dashboard URL: $DASHBOARD_URL"
echo ""
echo "Login Credentials:"
echo "  Username: ${DASHBOARD_USER:-admin}"
echo "  Password: ${DASHBOARD_PASS:-DbAdmin2026!}"
echo ""
echo "API Endpoints:"
echo "  Servers:    $DASHBOARD_URL/api/servers"
echo "  Apps:       $DASHBOARD_URL/api/apps"
echo "  Databases:  $DASHBOARD_URL/api/databases"
echo "  Health:     $DASHBOARD_URL/api/health"
echo ""
echo "Connected Services:"
echo "  PostgreSQL: ${PG_HOST:-100.102.220.16}:${PG_PORT:-5000}"
echo "  Redis:      ${REDIS_HOST:-100.126.103.51}:${REDIS_PORT:-6379}"
echo "  Prometheus: ${PROMETHEUS_URL:-http://100.102.220.16:9090}"
echo "  Grafana:    ${GRAFANA_URL:-http://100.102.220.16:3000}"
echo ""
echo "Data Persistence:"
echo "  Database: /data/paas.db"
echo "  Key:      /data/vault.key"
echo ""
echo "Sync Configs & Database:"
echo "  ./scripts/sync-configs.sh"
echo ""
echo "=========================================="
echo ""

# Start the application
exec python app.py