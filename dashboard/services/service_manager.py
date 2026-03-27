"""
Service Manager handles lifecycle of add-on services.

This module provides:
- Service creation and deletion
- Docker container management
- Service status monitoring
- Backup and restore operations
"""

import subprocess
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

try:
    from .templates import (
        get_service_template,
        generate_service_config,
        get_connection_string,
        get_environment_variables,
        validate_service_config
    )
except ImportError:
    from templates import (
        get_service_template,
        generate_service_config,
        get_connection_string,
        get_environment_variables,
        validate_service_config
    )

try:
    import database as paas_db
    PAAS_DB_AVAILABLE = True
except ImportError:
    PAAS_DB_AVAILABLE = False


class ServiceManager:
    """
    Manage add-on services for applications.
    
    Services are Docker containers that provide add-on functionality
    like Redis, Meilisearch, MinIO, RabbitMQ, etc.
    """
    
    def __init__(self, server_ip: str = None):
        """
        Initialize service manager.
        
        Args:
            server_ip: Server to run services on (default: first app server)
        """
        self.server_ip = server_ip
        
        # Default server configuration
        self.app_servers = [
            {"name": "re-db", "ip": "100.92.26.38", "public_ip": "208.87.128.115"},
            {"name": "re-node-02", "ip": "100.89.130.19", "public_ip": "23.227.173.245"}
        ]
        
        if not self.server_ip and self.app_servers:
            self.server_ip = self.app_servers[0]["ip"]
    
    def list_available_services(self) -> List[Dict[str, Any]]:
        """
        List all available service templates.
        
        Returns:
            List of service template info
        """
        from .templates import list_service_templates
        return list_service_templates()
    
    def create_service(self, app_name: str, service_type: str, environment: str,
                       custom_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a new service for an application.
        
        Args:
            app_name: Application name
            service_type: Service type (redis, meilisearch, etc.)
            environment: Environment (production/staging)
            custom_config: Optional custom configuration overrides
            
        Returns:
            Dict with success status and service details
        """
        # Get application
        app = None
        if PAAS_DB_AVAILABLE:
            app = paas_db.get_application(name=app_name)
        
        if not app:
            return {'success': False, 'error': 'Application not found'}
        
        # Check if service already exists for this app/env
        existing = self.get_service_for_app(app_name, service_type, environment)
        if existing:
            return {
                'success': False, 
                'error': f'Service {service_type} already exists for {app_name} ({environment})'
            }
        
        # Generate base config
        config = generate_service_config(service_type, app_name, environment)
        if not config:
            return {'success': False, 'error': f'Unknown service type: {service_type}'}
        
        # Apply custom config
        if custom_config:
            validation = validate_service_config(service_type, custom_config)
            if not validation['valid']:
                return {'success': False, 'errors': validation['errors']}
            
            for key in ['memory_limit', 'cpu_limit', 'port']:
                if key in custom_config:
                    config[key] = custom_config[key]
        
        # Allocate port
        allocated_port = self._allocate_port(service_type, environment, config.get('port'))
        config['port'] = allocated_port
        
        # Set server
        config['server_ip'] = self.server_ip
        config['server_name'] = self._get_server_name(self.server_ip)
        
        # Store in database
        service_id = self._store_service(app['id'], config)
        
        # Deploy service
        result = self._deploy_service(config, service_id)
        
        if result['success']:
            # Update service status
            self._update_service_status(service_id, 'running', result.get('container_id'))
            
            return {
                'success': True,
                'service_id': service_id,
                'config': config,
                'connection_string': get_connection_string(service_type, config, self.server_ip),
                'container_id': result.get('container_id'),
                'message': f'Service {service_type} created successfully'
            }
        else:
            # Remove from database on failure
            self._remove_service(service_id)
            
            return {
                'success': False,
                'error': result.get('error', 'Failed to deploy service'),
                'service_id': service_id
            }
    
    def delete_service(self, service_id: str, remove_data: bool = False) -> Dict[str, Any]:
        """
        Delete a service.
        
        Args:
            service_id: Service ID
            remove_data: Whether to remove data volumes
            
        Returns:
            Dict with success status
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        # Stop and remove container
        result = self._stop_service(service, remove_data=remove_data)
        
        if result['success']:
            # Remove from database
            self._remove_service(service_id)
            
            return {
                'success': True,
                'message': f"Service {service['type']} deleted successfully"
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Failed to stop service')
            }
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get service details.
        
        Args:
            service_id: Service ID
            
        Returns:
            Service dict or None
        """
        service = self._get_service(service_id)
        if not service:
            return None
        
        # Get live status
        status = self._check_container_status(service)
        service['container_status'] = status
        
        # Add connection string
        template = get_service_template(service['type'])
        if template:
            service['connection_string'] = get_connection_string(
                service['type'], 
                service, 
                service.get('server_ip', 'localhost')
            )
        
        return service
    
    def get_services_for_app(self, app_name: str, environment: str = None) -> List[Dict[str, Any]]:
        """
        Get all services for an application.
        
        Args:
            app_name: Application name
            environment: Optional environment filter
            
        Returns:
            List of service dicts
        """
        if not PAAS_DB_AVAILABLE:
            return []
        
        app = paas_db.get_application(name=app_name)
        if not app:
            return []
        
        services = self._get_services_by_app_id(app['id'], environment)
        
        # Enrich with live status
        for service in services:
            status = self._check_container_status(service)
            service['container_status'] = status
            service['connection_string'] = get_connection_string(
                service['type'],
                service,
                service.get('server_ip', 'localhost')
            )
        
        return services
    
    def get_service_for_app(self, app_name: str, service_type: str, environment: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific service for an application.
        
        Args:
            app_name: Application name
            service_type: Service type
            environment: Environment
            
        Returns:
            Service dict or None
        """
        services = self.get_services_for_app(app_name, environment)
        for service in services:
            if service['type'] == service_type:
                return service
        return None
    
    def restart_service(self, service_id: str) -> Dict[str, Any]:
        """
        Restart a service.
        
        Args:
            service_id: Service ID
            
        Returns:
            Dict with success status
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        result = self._restart_container(service)
        
        if result['success']:
            self._update_service_status(service_id, 'running')
        
        return result
    
    def stop_service(self, service_id: str) -> Dict[str, Any]:
        """
        Stop a service.
        
        Args:
            service_id: Service ID
            
        Returns:
            Dict with success status
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        result = self._stop_container(service)
        
        if result['success']:
            self._update_service_status(service_id, 'stopped')
        
        return result
    
    def start_service(self, service_id: str) -> Dict[str, Any]:
        """
        Start a stopped service.
        
        Args:
            service_id: Service ID
            
        Returns:
            Dict with success status
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        result = self._start_container(service)
        
        if result['success']:
            self._update_service_status(service_id, 'running')
        
        return result
    
    def backup_service(self, service_id: str) -> Dict[str, Any]:
        """
        Backup a service.
        
        Args:
            service_id: Service ID
            
        Returns:
            Dict with success status and backup details
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        template = get_service_template(service['type'])
        if not template or not template.get('backup'):
            return {'success': False, 'error': 'Backup not supported for this service'}
        
        result = self._execute_backup(service, template)
        
        if result['success']:
            self._record_backup(service_id, result)
        
        return result
    
    def get_service_logs(self, service_id: str, lines: int = 100) -> Dict[str, Any]:
        """
        Get service logs.
        
        Args:
            service_id: Service ID
            lines: Number of lines to retrieve
            
        Returns:
            Dict with logs
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        return self._get_container_logs(service, lines)
    
    def get_service_metrics(self, service_id: str) -> Dict[str, Any]:
        """
        Get service resource metrics.
        
        Args:
            service_id: Service ID
            
        Returns:
            Dict with CPU, memory, network metrics
        """
        service = self._get_service(service_id)
        if not service:
            return {'success': False, 'error': 'Service not found'}
        
        return self._get_container_metrics(service)
    
    # =========================================================================
    # Port Allocation
    # =========================================================================
    
    def _allocate_port(self, service_type: str, environment: str, 
                       requested_port: int = None) -> int:
        """
        Allocate next available port for service type.
        
        Args:
            service_type: Service type
            environment: Environment
            requested_port: Optional specific port request
            
        Returns:
            Allocated port number
        """
        template = get_service_template(service_type)
        if not template:
            raise ValueError(f"Unknown service type: {service_type}")
        
        base_port, end_port = template['port_range']
        
        # If requested port is valid, use it
        if requested_port and base_port <= requested_port <= end_port:
            # Check if port is in use
            used_ports = self._get_used_ports()
            if requested_port not in used_ports:
                return requested_port
        
        # Find next available port
        used_ports = self._get_used_ports()
        
        for port in range(base_port, end_port + 1):
            if port not in used_ports:
                return port
        
        raise RuntimeError(f"No available ports for {service_type}")
    
    def _get_used_ports(self) -> set:
        """Get set of all used ports."""
        used = set()
        
        if PAAS_DB_AVAILABLE:
            try:
                services = paas_db.get_all_services()
                for s in services:
                    if s.get('port'):
                        used.add(s['port'])
            except Exception:
                pass
        
        return used
    
    # =========================================================================
    # Docker Operations
    # =========================================================================
    
    def _deploy_service(self, config: Dict[str, Any], service_id: str) -> Dict[str, Any]:
        """
        Deploy service as Docker container.
        
        Args:
            config: Service configuration
            service_id: Service ID
            
        Returns:
            Dict with success status and container ID
        """
        template = get_service_template(config['type'])
        if not template:
            return {'success': False, 'error': 'Unknown service type'}
        
        container_name = f"{config['app_name']}-{config['type']}-{config['environment']}"
        server_ip = config.get('server_ip', self.server_ip)
        
        # Build docker run command
        cmd = ['docker', 'run', '-d',
               '--name', container_name,
               '--restart', 'unless-stopped',
               '-p', f"{config['port']}:{template['port']}",
               '-m', config['memory_limit'],
               '--cpus', str(config['cpu_limit']),
               '--label', f'service.id={service_id}',
               '--label', f'service.type={config["type"]}',
               '--label', f'service.app={config["app_name"]}',
               '--label', f'service.env={config["environment"]}']
        
        # Add additional port mappings (e.g., management ports)
        if template.get('management_port'):
            mgmt_port = config['port'] + 10000
            cmd.extend(['-p', f"{mgmt_port}:{template['management_port']}"])
        
        if template.get('console_port'):
            console_port = config['port'] + 1
            cmd.extend(['-p', f"{console_port}:{template['console_port']}"])
        
        # Add environment variables
        env_vars = get_environment_variables(config['type'], config)
        for key, value in env_vars.items():
            cmd.extend(['-e', f"{key}={value}"])
        
        # Add volumes
        for vol in config.get('volumes', []):
            host_path = vol['host']
            cmd.extend(['-v', f"{host_path}:{vol['container']}"])
        
        # Add image
        cmd.append(template['docker_image'])
        
        # Add command if specified
        if template.get('command'):
            cmd.extend(['sh', '-c', template['command']])
        
        # Execute via SSH
        result = self._ssh_command(server_ip, cmd)
        
        if result['success']:
            container_id = result.get('stdout', '').strip()
            return {'success': True, 'container_id': container_id}
        else:
            return {'success': False, 'error': result.get('stderr', 'Unknown error')}
    
    def _stop_service(self, service: Dict[str, Any], remove_data: bool = False) -> Dict[str, Any]:
        """Stop and remove a service container."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        
        # Stop container
        self._ssh_command(server_ip, ['docker', 'stop', container_name], ignore_errors=True)
        
        # Remove container
        self._ssh_command(server_ip, ['docker', 'rm', container_name], ignore_errors=True)
        
        # Remove data volumes if requested
        if remove_data:
            credentials = service.get('credentials', {})
            volumes = service.get('volumes', [])
            for vol in volumes:
                host_path = vol.get('host', '')
                if host_path:
                    self._ssh_command(server_ip, ['rm', '-rf', host_path], ignore_errors=True)
        
        return {'success': True}
    
    def _stop_container(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Stop a container without removing it."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        result = self._ssh_command(server_ip, ['docker', 'stop', container_name], ignore_errors=True)
        
        return {'success': result['success']}
    
    def _start_container(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Start a stopped container."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        result = self._ssh_command(server_ip, ['docker', 'start', container_name], ignore_errors=True)
        
        return {'success': result['success']}
    
    def _restart_container(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Restart a container."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        result = self._ssh_command(server_ip, ['docker', 'restart', container_name])
        
        return {'success': result['success']}
    
    def _check_container_status(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Check container status."""
        container_name = service.get('container_name')
        if not container_name:
            return {'status': 'not_created'}
        
        server_ip = service.get('server_ip', self.server_ip)
        result = self._ssh_command(
            server_ip, 
            ['docker', 'inspect', '--format', '{{.State.Status}}', container_name],
            ignore_errors=True
        )
        
        if result['success']:
            status = result.get('stdout', '').strip()
            return {
                'status': status,
                'running': status == 'running'
            }
        
        return {'status': 'not_found', 'running': False}
    
    def _get_container_logs(self, service: Dict[str, Any], lines: int = 100) -> Dict[str, Any]:
        """Get container logs."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        result = self._ssh_command(
            server_ip, 
            ['docker', 'logs', '--tail', str(lines), container_name],
            ignore_errors=True
        )
        
        return {
            'success': result['success'],
            'logs': result.get('stdout', '') + result.get('stderr', '')
        }
    
    def _get_container_metrics(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Get container resource metrics."""
        container_name = service.get('container_name')
        if not container_name:
            return {'success': False, 'error': 'No container name'}
        
        server_ip = service.get('server_ip', self.server_ip)
        
        # Get stats
        result = self._ssh_command(
            server_ip,
            ['docker', 'stats', '--no-stream', '--format', 
             '{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}', container_name],
            ignore_errors=True
        )
        
        if result['success']:
            output = result.get('stdout', '').strip()
            parts = output.split('|')
            
            if len(parts) >= 3:
                return {
                    'success': True,
                    'cpu_percent': parts[0],
                    'memory_usage': parts[1],
                    'network_io': parts[2]
                }
        
        return {'success': False, 'error': 'Could not get metrics'}
    
    def _execute_backup(self, service: Dict[str, Any], template: Dict[str, Any]) -> Dict[str, Any]:
        """Execute service backup."""
        backup_config = template.get('backup', {})
        command = backup_config.get('command')
        
        if not command:
            return {'success': False, 'error': 'No backup command defined'}
        
        # Build backup command with credentials
        credentials = service.get('credentials', {})
        for key, value in credentials.items():
            command = command.replace('{' + key + '}', str(value))
        
        container_name = service.get('container_name')
        server_ip = service.get('server_ip', self.server_ip)
        
        # Execute backup in container
        result = self._ssh_command(
            server_ip,
            ['docker', 'exec', container_name, 'sh', '-c', command],
            timeout=300
        )
        
        backup_path = backup_config.get('path', '')
        if '{app_name}' in backup_path:
            backup_path = backup_path.replace('{app_name}', service.get('app_name', ''))
        
        return {
            'success': result['success'],
            'backup_path': backup_path,
            'timestamp': datetime.utcnow().isoformat(),
            'output': result.get('stdout', '')
        }
    
    # =========================================================================
    # SSH Commands
    # =========================================================================
    
    def _ssh_command(self, server_ip: str, command: List[str], 
                     timeout: int = 60, ignore_errors: bool = False) -> Dict[str, Any]:
        """
        Execute command on remote server via SSH.
        
        Args:
            server_ip: Server IP address
            command: Command list to execute
            timeout: Command timeout in seconds
            ignore_errors: Don't fail on non-zero exit
            
        Returns:
            Dict with success, stdout, stderr
        """
        cmd_str = ' '.join(f'"{arg}"' if ' ' in arg else arg for arg in command)
        ssh_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
                   f'root@{server_ip}', cmd_str]
        
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            success = result.returncode == 0 or ignore_errors
            
            return {
                'success': success,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_server_name(self, server_ip: str) -> str:
        """Get server name from IP."""
        for server in self.app_servers:
            if server['ip'] == server_ip:
                return server['name']
        return server_ip
    
    # =========================================================================
    # Database Operations
    # =========================================================================
    
    def _store_service(self, app_id: str, config: Dict[str, Any]) -> str:
        """Store service in database."""
        if not PAAS_DB_AVAILABLE:
            return None
        
        service_id = paas_db.generate_id()
        
        service_data = {
            'id': service_id,
            'app_id': app_id,
            'type': config['type'],
            'environment': config['environment'],
            'port': config['port'],
            'server_ip': config.get('server_ip'),
            'server_name': config.get('server_name'),
            'container_name': f"{config['app_name']}-{config['type']}-{config['environment']}",
            'container_id': None,
            'credentials_encrypted': paas_db.encrypt_value(json.dumps(config.get('credentials', {}))),
            'volumes_json': json.dumps(config.get('volumes', [])),
            'memory_limit': config.get('memory_limit'),
            'cpu_limit': config.get('cpu_limit'),
            'status': 'pending',
            'created_at': datetime.utcnow().isoformat()
        }
        
        paas_db.create_service(service_data)
        
        return service_id
    
    def _get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get service from database."""
        if not PAAS_DB_AVAILABLE:
            return None
        
        service = paas_db.get_service(service_id)
        if not service:
            return None
        
        # Decrypt credentials
        if service.get('credentials_encrypted'):
            try:
                service['credentials'] = json.loads(
                    paas_db.decrypt_value(service['credentials_encrypted'])
                )
            except Exception:
                service['credentials'] = {}
        
        # Parse volumes
        if service.get('volumes_json'):
            try:
                service['volumes'] = json.loads(service['volumes_json'])
            except Exception:
                service['volumes'] = []
        
        return service
    
    def _get_services_by_app_id(self, app_id: str, environment: str = None) -> List[Dict[str, Any]]:
        """Get services for an app from database."""
        if not PAAS_DB_AVAILABLE:
            return []
        
        services = paas_db.get_services_for_app(app_id, environment)
        
        # Decrypt credentials and parse JSON
        for service in services:
            if service.get('credentials_encrypted'):
                try:
                    service['credentials'] = json.loads(
                        paas_db.decrypt_value(service['credentials_encrypted'])
                    )
                except Exception:
                    service['credentials'] = {}
            
            if service.get('volumes_json'):
                try:
                    service['volumes'] = json.loads(service['volumes_json'])
                except Exception:
                    service['volumes'] = []
        
        return services
    
    def _remove_service(self, service_id: str) -> bool:
        """Remove service from database."""
        if not PAAS_DB_AVAILABLE:
            return False
        
        return paas_db.delete_service(service_id)
    
    def _update_service_status(self, service_id: str, status: str, 
                                container_id: str = None) -> bool:
        """Update service status."""
        if not PAAS_DB_AVAILABLE:
            return False
        
        updates = {'status': status}
        if container_id:
            updates['container_id'] = container_id
        
        return paas_db.update_service(service_id, updates)
    
    def _record_backup(self, service_id: str, result: Dict[str, Any]) -> bool:
        """Record backup in database."""
        if not PAAS_DB_AVAILABLE:
            return False
        
        # Store backup metadata
        backup_data = {
            'service_id': service_id,
            'timestamp': result.get('timestamp'),
            'backup_path': result.get('backup_path'),
            'success': result.get('success')
        }
        
        return paas_db.record_service_backup(backup_data)


# Convenience function for API use
def get_service_manager(server_ip: str = None) -> ServiceManager:
    """Get a ServiceManager instance."""
    return ServiceManager(server_ip=server_ip)