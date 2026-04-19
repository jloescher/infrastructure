"""
Configuration drift detection service.

Detects when server configurations deviate from expected baselines.
"""

import os
import sys
import re
import subprocess
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.drift.configurations import (
    get_expected_config,
    get_services_for_role,
    get_severity,
    get_drift_description
)
import database as db


@dataclass
class DriftResult:
    """Result of a configuration drift check."""
    server: str
    server_ip: str
    service: str
    key: str
    expected: Any
    actual: Any
    severity: str  # 'critical', 'warning', 'info'
    description: str
    timestamp: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class DriftDetector:
    """
    Detect configuration drift on servers.
    
    Compares actual server configurations against expected baselines.
    Supports: PostgreSQL, HAProxy, and system settings.
    """
    
    # SSH connection timeout in seconds
    SSH_TIMEOUT = 30
    
    def __init__(self):
        self.results: List[DriftResult] = []
        self.errors: List[Dict[str, str]] = []
    
    def check_server(self, server: Dict[str, Any]) -> List[DriftResult]:
        """
        Check a single server for configuration drift.
        
        Args:
            server: Server dict with 'name', 'ip', 'role'
            
        Returns:
            List of DriftResult objects
        """
        server_name = server['name']
        server_ip = server['ip']
        role = server.get('role', 'app')
        
        results = []
        
        # Determine which services to check based on role
        services = get_services_for_role(role)
        
        for service in services:
            expected = get_expected_config(server_name, service)
            if not expected:
                continue
            
            try:
                actual = self._get_actual_config(server_ip, service)
                
                for key, expected_value in expected.items():
                    actual_value = actual.get(key)
                    
                    if actual_value is None:
                        continue  # Can't check this config
                    
                    # Normalize values for comparison
                    if self._values_differ(expected_value, actual_value):
                        severity = get_severity(service, key)
                        description = get_drift_description(service, key, expected_value, actual_value)
                        
                        results.append(DriftResult(
                            server=server_name,
                            server_ip=server_ip,
                            service=service,
                            key=key,
                            expected=str(expected_value),
                            actual=str(actual_value),
                            severity=severity,
                            description=description,
                            timestamp=datetime.utcnow().isoformat()
                        ))
            except Exception as e:
                self.errors.append({
                    'server': server_name,
                    'service': service,
                    'error': str(e)
                })
        
        return results
    
    def check_all_servers(self) -> Dict[str, Any]:
        """
        Check all servers for configuration drift.
        
        Returns:
            Dictionary with results summary and details
        """
        servers = db.list_servers()
        all_results = []
        all_errors = []
        
        for server in servers:
            results = self.check_server(server)
            all_results.extend(results)
        
        # Group by server
        by_server = {}
        for result in all_results:
            if result.server not in by_server:
                by_server[result.server] = []
            by_server[result.server].append(result.to_dict())
        
        # Group by service
        by_service = {}
        for result in all_results:
            if result.service not in by_service:
                by_service[result.service] = []
            by_service[result.service].append(result.to_dict())
        
        # Count by severity
        critical_count = sum(1 for r in all_results if r.severity == 'critical')
        warning_count = sum(1 for r in all_results if r.severity == 'warning')
        info_count = sum(1 for r in all_results if r.severity == 'info')
        
        return {
            'total_drifts': len(all_results),
            'critical': critical_count,
            'warning': warning_count,
            'info': info_count,
            'servers_checked': len(servers),
            'servers_with_drift': len(by_server),
            'by_server': by_server,
            'by_service': by_service,
            'errors': self.errors,
            'checked_at': datetime.utcnow().isoformat()
        }
    
    def _values_differ(self, expected: Any, actual: Any) -> bool:
        """
        Check if two values differ significantly.
        
        Handles type coercion and normalization.
        """
        # Convert to strings for comparison
        expected_str = str(expected).lower().strip()
        actual_str = str(actual).lower().strip()
        
        # Handle memory/size values (e.g., '256MB' vs '256mb')
        expected_str = expected_str.replace(' ', '')
        actual_str = actual_str.replace(' ', '')
        
        return expected_str != actual_str
    
    def _ssh_command(self, server_ip: str, command: str) -> str:
        """
        Execute SSH command and return output.
        
        Args:
            server_ip: Server IP address
            command: Command to execute
            
        Returns:
            Command stdout output
        """
        try:
            result = subprocess.run(
                ['ssh', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=no',
                 f'root@{server_ip}', command],
                capture_output=True,
                text=True,
                timeout=self.SSH_TIMEOUT
            )
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise Exception(f"SSH timeout connecting to {server_ip}")
        except Exception as e:
            raise Exception(f"SSH error: {str(e)}")
    
    def _get_actual_config(self, server_ip: str, service: str) -> Dict[str, Any]:
        """
        Get actual configuration from a server.
        
        Args:
            server_ip: Server IP address
            service: Service name
            
        Returns:
            Dictionary of configuration values
        """
        config_getters = {
            'postgresql': self._get_postgresql_config,
            'haproxy': self._get_haproxy_config,
            'system': self._get_system_config,
        }
        
        getter = config_getters.get(service)
        if not getter:
            return {}
        
        return getter(server_ip)
    
    def _get_postgresql_config(self, server_ip: str) -> Dict[str, Any]:
        """Get PostgreSQL configuration from server."""
        config = {}
        
        try:
            # Query settings via psql
            query = """
            SELECT name, setting FROM pg_settings 
            WHERE name IN ('max_connections', 'shared_buffers', 'effective_cache_size', 
                           'work_mem', 'maintenance_work_mem', 'checkpoint_completion_target',
                           'wal_buffers', 'default_statistics_target', 'random_page_cost',
                           'effective_io_concurrency')
            """
            
            output = self._ssh_command(
                server_ip,
                f"sudo -u postgres psql -t -c \"{query}\" 2>/dev/null"
            )
            
            for line in output.split('\n'):
                parts = line.strip().split('|')
                if len(parts) == 2:
                    name = parts[0].strip()
                    value = parts[1].strip()
                    # Try to convert to number
                    try:
                        if '.' in value:
                            config[name] = float(value)
                        else:
                            config[name] = int(value)
                    except ValueError:
                        config[name] = value
                        
        except Exception as e:
            raise Exception(f"Failed to get PostgreSQL config: {str(e)}")
        
        return config
    
    def _get_haproxy_config(self, server_ip: str) -> Dict[str, Any]:
        """Get HAProxy configuration from server."""
        config = {}
        
        try:
            # Get HAProxy defaults
            output = self._ssh_command(
                server_ip,
                'grep -E "^\\s*(maxconn|timeout)" /etc/haproxy/haproxy.cfg 2>/dev/null | head -10'
            )
            
            for line in output.split('\n'):
                line = line.strip()
                
                # Parse maxconn
                match = re.match(r'maxconn\s+(\d+)', line)
                if match:
                    config['maxconn'] = int(match.group(1))
                
                # Parse timeouts
                match = re.match(r'timeout\s+(connect|client|server)\s+(\S+)', line)
                if match:
                    key = f'timeout_{match.group(1)}'
                    config[key] = match.group(2)
                        
        except Exception as e:
            raise Exception(f"Failed to get HAProxy config: {str(e)}")
        
        return config
    
    def _get_system_config(self, server_ip: str) -> Dict[str, Any]:
        """Get system kernel parameters from server."""
        config = {}
        
        try:
            sysctls = [
                'vm.swappiness',
                'vm.dirty_ratio',
                'vm.dirty_background_ratio',
                'net.core.somaxconn',
                'net.ipv4.tcp_max_syn_backlog'
            ]
            
            for sysctl in sysctls:
                output = self._ssh_command(server_ip, f'sysctl -n {sysctl} 2>/dev/null')
                if output:
                    try:
                        config[sysctl] = int(output)
                    except ValueError:
                        config[sysctl] = output
                        
        except Exception as e:
            raise Exception(f"Failed to get system config: {str(e)}")
        
        return config


def check_drift_for_server(server_name: str) -> List[DriftResult]:
    """
    Check a specific server for drift.
    
    Args:
        server_name: Server name
        
    Returns:
        List of drift results
    """
    server = db.get_server_by_name(server_name)
    if not server:
        raise ValueError(f"Server {server_name} not found")
    
    detector = DriftDetector()
    return detector.check_server(server)


def check_all_servers() -> Dict[str, Any]:
    """
    Check all servers for drift.
    
    Returns:
        Dictionary with drift report
    """
    detector = DriftDetector()
    return detector.check_all_servers()
