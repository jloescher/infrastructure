#!/bin/bash
# Deploy dashboard to router-01
# Usage: ./deploy.sh

set -e

SERVER="root@100.102.220.16"
REMOTE_DIR="/opt/dashboard"

echo "=== Deploying Dashboard ==="

# Create remote directory
ssh $SERVER "mkdir -p $REMOTE_DIR/{templates,static}"

# Copy files
echo "Copying application..."
scp app.py $SERVER:$REMOTE_DIR/
scp requirements.txt $SERVER:$REMOTE_DIR/

# Copy templates
echo "Copying templates..."
scp templates/*.html $SERVER:$REMOTE_DIR/templates/

# Copy static files
echo "Copying static files..."
scp static/*.css $SERVER:$REMOTE_DIR/static/

# Install dependencies
echo "Installing dependencies..."
ssh $SERVER "cd $REMOTE_DIR && pip3 install -r requirements.txt --break-system-packages 2>/dev/null || pip3 install -r requirements.txt"

# Update systemd service
echo "Updating systemd service..."
ssh $SERVER "cat > /etc/systemd/system/dashboard.service << 'EOF'
[Unit]
Description=Quantyra Infrastructure Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$REMOTE_DIR
ExecStart=/usr/bin/python3 $REMOTE_DIR/app.py
Restart=on-failure
RestartSec=5
Environment=PG_HOST=100.102.220.16
Environment=PG_PORT=5000
Environment=PG_USER=patroni_superuser
Environment=PG_PASSWORD=2e7vBpaaVK4vTJzrKebC
Environment=REDIS_HOST=100.102.220.16
Environment=REDIS_PORT=6379
Environment=REDIS_PASSWORD=CcPUa3nvcxHtyNYjztbDyfCCuhgix78novmBDNGk
Environment=PROMETHEUS_URL=http://100.102.220.16:9090
Environment=GRAFANA_URL=http://100.102.220.16:3000
Environment=ALERTMANAGER_URL=http://100.102.220.16:9093

[Install]
WantedBy=multi-user.target
EOF"

# Restart service
ssh $SERVER "systemctl daemon-reload && systemctl enable dashboard && systemctl restart dashboard"

echo "=== Dashboard Deployed ==="
echo "URL: http://100.102.220.16:8080"
echo "Username: admin"
echo "Password: DbAdmin2026!"