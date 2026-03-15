#!/bin/bash
set -euo pipefail

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
HOSTNAME=$(hostname)
REPORT_FILE="/tmp/${HOSTNAME}_infra_report_${TIMESTAMP}.md"

cat > "$REPORT_FILE" << EOF
# Infrastructure Report - $HOSTNAME
**Generated:** $(date)
**Timestamp:** $TIMESTAMP

EOF

echo "# System Information" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
uname -a >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
cat /etc/os-release >> "$REPORT_FILE" 2>/dev/null || echo "OS info not available" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Hardware Specs" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "CPU:" >> "$REPORT_FILE"
lscpu | grep -E "^CPU\(s\)|Model name|Thread|Core|Socket" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "Memory:" >> "$REPORT_FILE"
free -h >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "Disk:" >> "$REPORT_FILE"
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
df -h >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Network Information" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Tailscale" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v tailscale &> /dev/null; then
    tailscale status >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    tailscale ip >> "$REPORT_FILE"
else
    echo "Tailscale not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Network Interfaces" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
ip addr show >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Listening Ports" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
ss -tuln >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# PostgreSQL / Patroni" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Patroni Status" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v patronictl &> /dev/null; then
    patronictl list 2>/dev/null >> "$REPORT_FILE" || echo "Patroni not configured" >> "$REPORT_FILE"
else
    echo "Patroni not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## PostgreSQL Status" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v pg_isready &> /dev/null; then
    pg_isready >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    if command -v psql &> /dev/null; then
        sudo -u postgres psql -c "SELECT version();" 2>/dev/null >> "$REPORT_FILE" || echo "Cannot connect to PostgreSQL" >> "$REPORT_FILE"
    fi
else
    echo "PostgreSQL not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## PostgreSQL Config" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if [ -d /etc/postgresql ]; then
    PG_VERSION=$(ls /etc/postgresql | head -1)
    PG_CONF="/etc/postgresql/${PG_VERSION}/main/postgresql.conf"
    if [ -f "$PG_CONF" ]; then
        grep -v "^#" "$PG_CONF" | grep -v "^$" | head -50 >> "$REPORT_FILE"
    fi
else
    echo "PostgreSQL config directory not found" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Redis" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Redis Status" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v redis-cli &> /dev/null; then
    TAILSCALE_IP=$(tailscale ip --1 2>/dev/null || echo "127.0.0.1")
    redis-cli -h "$TAILSCALE_IP" ping 2>/dev/null >> "$REPORT_FILE" || echo "Redis not responding on Tailscale IP" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    redis-cli -h "$TAILSCALE_IP" INFO replication 2>/dev/null | head -20 >> "$REPORT_FILE"
else
    echo "Redis not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Redis Config" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if [ -f /etc/redis/redis.conf ]; then
    grep -v "^#" /etc/redis/redis.conf | grep -v "^$" | head -50 >> "$REPORT_FILE"
else
    echo "Redis config not found" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Router Services (HAProxy, etcd)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## HAProxy" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v haproxy &> /dev/null; then
    haproxy -v >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    systemctl status haproxy --no-pager 2>/dev/null | head -20 >> "$REPORT_FILE"
else
    echo "HAProxy not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## HAProxy Config" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if [ -f /etc/haproxy/haproxy.cfg ]; then
    cat /etc/haproxy/haproxy.cfg >> "$REPORT_FILE"
else
    echo "HAProxy config not found" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## etcd" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v etcdctl &> /dev/null; then
    etcdctl version >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    etcdctl member list 2>/dev/null >> "$REPORT_FILE" || echo "etcd not configured" >> "$REPORT_FILE"
else
    echo "etcd not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Monitoring (Prometheus, Grafana)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Prometheus" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v prometheus &> /dev/null; then
    prometheus --version 2>&1 | head -1 >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    systemctl status prometheus --no-pager 2>/dev/null | head -20 >> "$REPORT_FILE"
else
    echo "Prometheus not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Prometheus Config" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if [ -f /etc/prometheus/prometheus.yml ]; then
    cat /etc/prometheus/prometheus.yml >> "$REPORT_FILE"
else
    echo "Prometheus config not found" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Grafana" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v grafana-server &> /dev/null; then
    grafana-server -v >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    systemctl status grafana-server --no-pager 2>/dev/null | head -20 >> "$REPORT_FILE"
else
    echo "Grafana not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Docker" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Docker Info" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v docker &> /dev/null; then
    docker --version >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" >> "$REPORT_FILE"
else
    echo "Docker not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Docker Compose Files" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
for compose_file in $(find /opt /home -name "docker-compose.yml" -o -name "docker-compose.yaml" 2>/dev/null); do
    echo "### $compose_file" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "\`\`\`yaml" >> "$REPORT_FILE"
    cat "$compose_file" >> "$REPORT_FILE"
    echo "\`\`\`" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
done

echo "# Running Services" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
systemctl list-units --type=service --state=running --no-pager >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Security" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Firewall (UFW)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if command -v ufw &> /dev/null; then
    ufw status verbose >> "$REPORT_FILE"
else
    echo "UFW not installed" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## SSH Config" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
if [ -f /etc/ssh/sshd_config ]; then
    grep -v "^#" /etc/ssh/sshd_config | grep -v "^$" >> "$REPORT_FILE"
else
    echo "SSH config not found" >> "$REPORT_FILE"
fi
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Active SSH Sessions" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
who >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# Backup Configuration" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Backup Directories" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
for backup_dir in /backup /var/backups /opt/backups; do
    if [ -d "$backup_dir" ]; then
        echo "=== $backup_dir ===" >> "$REPORT_FILE"
        ls -lah "$backup_dir" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    fi
done
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "## Cron Jobs (Backups)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
crontab -l 2>/dev/null >> "$REPORT_FILE" || echo "No user crontab" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
cat /etc/cron.d/* 2>/dev/null | grep -i backup >> "$REPORT_FILE" || echo "No backup cron jobs found" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "# System Resources (Current)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
uptime >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
top -bn1 | head -15 >> "$REPORT_FILE"
echo "\`\`\`" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

echo "---" >> "$REPORT_FILE"
echo "Report generated at: $(date)" >> "$REPORT_FILE"

echo "Report generated: $REPORT_FILE"
echo ""
echo "To copy this report to your local machine:"
echo "  scp ${HOSTNAME}:${REPORT_FILE} ./reports/"