#!/bin/bash
set -euo pipefail

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_postgresql() {
    log "Checking PostgreSQL cluster..."
    
    local write_host="100.102.220.16"
    local read_host="100.102.220.16"
    local write_port="5000"
    local read_port="5001"
    
    if timeout 5 bash -c "echo > /dev/tcp/$write_host/$write_port" 2>/dev/null; then
        log "✓ PostgreSQL write endpoint ($write_host:$write_port) is reachable"
    else
        log "✗ PostgreSQL write endpoint ($write_host:$write_port) is NOT reachable"
        return 1
    fi
    
    if timeout 5 bash -c "echo > /dev/tcp/$read_host/$read_port" 2>/dev/null; then
        log "✓ PostgreSQL read endpoint ($read_host:$read_port) is reachable"
    else
        log "✗ PostgreSQL read endpoint ($read_host:$read_port) is NOT reachable"
        return 1
    fi
    
    return 0
}

check_patroni() {
    log "Checking Patroni cluster..."
    
    local nodes=(
        "100.126.103.51:8008"
        "100.114.117.46:8008"
        "100.115.75.119:8008"
    )
    
    local leader_found=false
    
    for node in "${nodes[@]}"; do
        local ip=$(echo $node | cut -d: -f1)
        local port=$(echo $node | cut -d: -f2)
        
        local response=$(curl -s -m 5 "http://$ip:$port/health" 2>/dev/null || echo "failed")
        
        if [ "$response" != "failed" ]; then
            local role=$(curl -s -m 5 "http://$ip:$port/patroni" | jq -r '.role' 2>/dev/null || echo "unknown")
            log "✓ Patroni node $ip ($role) is healthy"
            
            if [ "$role" = "master" ] || [ "$role" = "leader" ]; then
                leader_found=true
            fi
        else
            log "✗ Patroni node $ip is NOT responding"
        fi
    done
    
    if [ "$leader_found" = true ]; then
        log "✓ Patroni cluster has a leader"
        return 0
    else
        log "✗ Patroni cluster has NO leader"
        return 1
    fi
}

check_redis() {
    log "Checking Redis..."
    
    local nodes=(
        "100.126.103.51:6379"
        "100.114.117.46:6379"
    )
    
    for node in "${nodes[@]}"; do
        local ip=$(echo $node | cut -d: -f1)
        local port=$(echo $node | cut -d: -f2)
        
        if redis-cli -h "$ip" -p "$port" ping 2>/dev/null | grep -q "PONG"; then
            local role=$(redis-cli -h "$ip" -p "$port" INFO replication 2>/dev/null | grep "role:" | cut -d: -f2 | tr -d '\r')
            log "✓ Redis at $ip:$port is healthy ($role)"
        else
            log "✗ Redis at $ip:$port is NOT responding"
        fi
    done
    
    return 0
}

check_haproxy() {
    log "Checking HAProxy..."
    
    local routers=(
        "100.102.220.16"
        "100.116.175.9"
    )
    
    local stats_port="8404"
    
    for router in "${routers[@]}"; do
        local stats_url="http://$router:$stats_port/stats"
        
        if curl -s -m 5 -u admin:admin "$stats_url" 2>/dev/null | grep -q "pxname"; then
            log "✓ HAProxy on $router is healthy"
        else
            log "✗ HAProxy on $router is NOT responding"
        fi
    done
    
    return 0
}

check_etcd() {
    log "Checking etcd..."
    
    local etcd_host="100.102.220.16"
    local etcd_port="2379"
    
    if curl -s -m 5 "http://$etcd_host:$etcd_port/health" 2>/dev/null | jq -e '.health == "true"' > /dev/null; then
        log "✓ etcd at $etcd_host:$etcd_port is healthy"
        return 0
    else
        log "✗ etcd at $etcd_host:$etcd_port is NOT healthy"
        return 1
    fi
}

check_prometheus() {
    log "Checking Prometheus..."
    
    local prometheus_host="100.102.220.16"
    local prometheus_port="9090"
    
    if curl -s -m 5 "http://$prometheus_host:$prometheus_port/-/healthy" 2>/dev/null | grep -q .; then
        log "✓ Prometheus is healthy"
        return 0
    else
        log "✗ Prometheus is NOT healthy"
        return 1
    fi
}

check_grafana() {
    log "Checking Grafana..."
    
    local grafana_host="100.102.220.16"
    local grafana_port="3000"
    
    if curl -s -m 5 "http://$grafana_host:$grafana_port/api/health" 2>/dev/null | jq -e '.database == "ok"' > /dev/null; then
        log "✓ Grafana is healthy"
        return 0
    else
        log "✗ Grafana is NOT healthy"
        return 1
    fi
}

check_node_exporters() {
    log "Checking Node Exporters..."
    
    local nodes=(
        "100.126.103.51:9100"
        "100.114.117.46:9100"
        "100.115.75.119:9100"
        "100.102.220.16:9100"
        "100.116.175.9:9100"
        "100.92.26.38:9100"
        "100.89.130.19:9100"
    )
    
    for node in "${nodes[@]}"; do
        local ip=$(echo $node | cut -d: -f1)
        local port=$(echo $node | cut -d: -f2)
        
        if curl -s -m 5 "http://$ip:$port/metrics" 2>/dev/null | grep -q "node_exporter"; then
            log "✓ Node exporter on $ip is healthy"
        else
            log "✗ Node exporter on $ip is NOT responding"
        fi
    done
    
    return 0
}

check_disk_space() {
    log "Checking disk space..."
    
    local threshold=90
    local critical_threshold=95
    local alert=false
    
    while IFS= read -r line; do
        local usage=$(echo "$line" | awk '{print $5}' | sed 's/%//')
        local mount=$(echo "$line" | awk '{print $6}')
        
        if [ "$usage" -gt "$critical_threshold" ]; then
            log "✗ CRITICAL: Disk usage on $mount is ${usage}%"
            alert=true
        elif [ "$usage" -gt "$threshold" ]; then
            log "⚠ WARNING: Disk usage on $mount is ${usage}%"
            alert=true
        else
            log "✓ Disk usage on $mount is ${usage}%"
        fi
    done < <(df -h | grep -E "^/dev")
    
    if [ "$alert" = true ]; then
        return 1
    fi
    
    return 0
}

check_memory() {
    log "Checking memory..."
    
    local mem_total=$(free -m | awk '/^Mem:/{print $2}')
    local mem_used=$(free -m | awk '/^Mem:/{print $3}')
    local mem_available=$(free -m | awk '/^Mem:/{print $7}')
    
    local usage_percent=$((mem_used * 100 / mem_total))
    
    if [ "$usage_percent" -gt 90 ]; then
        log "✗ CRITICAL: Memory usage is ${usage_percent}%"
        return 1
    elif [ "$usage_percent" -gt 80 ]; then
        log "⚠ WARNING: Memory usage is ${usage_percent}%"
        return 0
    else
        log "✓ Memory usage is ${usage_percent}%"
        return 0
    fi
}

check_load() {
    log "Checking system load..."
    
    local load=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | sed 's/,//')
    local cpus=$(nproc)
    
    local load_int=$(echo "$load" | awk '{print int($1+0.5)}')
    
    if [ "$load_int" -gt "$((cpus * 2))" ]; then
        log "✗ CRITICAL: System load is $load (CPUs: $cpus)"
        return 1
    elif [ "$load_int" -gt "$cpus" ]; then
        log "⚠ WARNING: System load is $load (CPUs: $cpus)"
        return 0
    else
        log "✓ System load is $load (CPUs: $cpus)"
        return 0
    fi
}

main() {
    log "=== System Health Check Started ==="
    log "Host: $(hostname)"
    log ""
    
    local exit_code=0
    
    check_disk_space || exit_code=1
    check_memory || exit_code=1
    check_load || exit_code=1
    log ""
    
    check_postgresql || exit_code=1
    log ""
    
    check_patroni || exit_code=1
    log ""
    
    check_redis || exit_code=1
    log ""
    
    check_haproxy || exit_code=1
    log ""
    
    check_etcd || exit_code=1
    log ""
    
    check_prometheus || exit_code=1
    check_grafana || exit_code=1
    log ""
    
    check_node_exporters || exit_code=1
    log ""
    
    log "=== Health Check Completed ==="
    
    if [ $exit_code -eq 0 ]; then
        log "✓ All checks passed"
    else
        log "✗ Some checks failed"
    fi
    
    exit $exit_code
}

main "$@"