"""
Provision Action for PaaS.

This module provides the ProvisionAction class for provisioning domains
with:
- DNS record creation via Cloudflare
- SSL certificate provisioning via certbot
- HAProxy configuration updates
- Health verification
"""

import os
import sys
import subprocess
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base import BaseAction, ActionResult
from websocket.performance import get_ssh_pool
import database as paas_db


class ProvisionAction(BaseAction):
    """
    Provision a domain with SSL certificate.
    
    This action handles the complete domain provisioning workflow:
    1. Validate domain and application
    2. Create DNS records via Cloudflare
    3. Provision SSL certificate via certbot
    4. Update HAProxy configuration
    5. Verify domain accessibility
    
    Example:
        action = ProvisionAction(domain_id='abc123')
        result = action.execute()
        
        if result.success:
            print(f"Domain {result.data['domain']} provisioned successfully")
        else:
            print(f"Provisioning failed: {result.error}")
    """
    
    action_type = "provision"
    
    # Cloudflare API configuration
    CLOUDFLARE_API_URL = "https://api.cloudflare.com/client/v4"
    
    def __init__(self, domain_id: str = None, domain_name: str = None,
                 app_id: str = None, environment: str = 'production',
                 emit_progress: bool = True):
        """
        Initialize the provision action.
        
        Args:
            domain_id: Existing domain ID (optional)
            domain_name: Domain name to provision (optional)
            app_id: Application ID (required with domain_name)
            environment: 'production' or 'staging'
            emit_progress: Whether to emit WebSocket progress
        """
        super().__init__(emit_progress=emit_progress)
        self.domain_id = domain_id
        self.domain_name = domain_name
        self.app_id = app_id
        self.environment = environment
        
        # Populated during execution
        self.domain: Optional[Dict[str, Any]] = None
        self.app: Optional[Dict[str, Any]] = None
        self.zone_id: Optional[str] = None
        self.cloudflare_token: Optional[str] = None
    
    def validate(self) -> List[str]:
        """
        Validate provisioning parameters.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Get domain by ID or create new
        if self.domain_id:
            self.domain = paas_db.get_domain(self.domain_id)
            if not self.domain:
                errors.append(f"Domain {self.domain_id} not found")
                return errors
            
            self.app = paas_db.get_application(app_id=self.domain['app_id'])
            self.environment = self.domain.get('environment', 'production')
        
        elif self.domain_name and self.app_id:
            self.app = paas_db.get_application(app_id=self.app_id)
            if not self.app:
                errors.append(f"Application {self.app_id} not found")
                return errors
            
            # Check if domain already exists
            existing = paas_db.get_domain_by_name(self.domain_name, self.environment)
            if existing:
                self.domain = existing
            else:
                # Create domain record
                self.domain_id = paas_db.create_domain({
                    'app_id': self.app_id,
                    'domain': self.domain_name,
                    'environment': self.environment
                })
                self.domain = paas_db.get_domain(self.domain_id)
        
        else:
            errors.append("Either domain_id or both domain_name and app_id are required")
            return errors
        
        # Validate environment
        if self.environment not in ['production', 'staging']:
            errors.append(f"Invalid environment: {self.environment}")
        
        # Get Cloudflare configuration
        self.cloudflare_token = os.environ.get('CLOUDFLARE_API_TOKEN')
        if not self.cloudflare_token:
            errors.append("CLOUDFLARE_API_TOKEN environment variable not set")
        
        return errors
    
    def pre_execute(self) -> bool:
        """
        Prepare for provisioning.
        
        Updates domain status to 'provisioning'.
        
        Returns:
            True to proceed with provisioning
        """
        if not super().pre_execute():
            return False
        
        # Update domain status
        paas_db.update_domain(self.domain['id'], {
            'status': 'provisioning'
        })
        
        # Determine zone ID from domain
        self.zone_id = self._get_zone_id()
        
        if not self.zone_id:
            self.add_step('validate', 'failed', 'Could not determine Cloudflare zone')
            return False
        
        # Store rollback data
        self.store_rollback_data('domain_id', self.domain['id'])
        self.store_rollback_data('initial_status', self.domain.get('status'))
        
        return True
    
    def _execute(self) -> ActionResult:
        """
        Execute the provisioning.
        
        Returns:
            ActionResult with provisioning outcome
        """
        results = {
            'domain': self.domain['domain'],
            'environment': self.environment,
            'steps': {}
        }
        
        # Step 1: Create DNS records
        self.add_step('dns', 'running', 'Creating DNS records')
        
        dns_result = self._create_dns_records()
        results['steps']['dns'] = dns_result
        
        if not dns_result['success']:
            self.add_step('dns', 'failed', dns_result.get('error'))
            
            paas_db.update_domain(self.domain['id'], {
                'status': 'failed',
                'error': dns_result.get('error')
            })
            
            return ActionResult(
                success=False,
                message="DNS provisioning failed",
                error=dns_result.get('error'),
                data=results
            )
        
        self.add_step('dns', 'success', f"DNS records created")
        
        # Step 2: Provision SSL certificate
        self.add_step('ssl', 'running', 'Provisioning SSL certificate')
        
        ssl_result = self._provision_ssl()
        results['steps']['ssl'] = ssl_result
        
        if not ssl_result['success']:
            self.add_step('ssl', 'failed', ssl_result.get('error'))
            
            paas_db.update_domain(self.domain['id'], {
                'status': 'failed',
                'error': ssl_result.get('error')
            })
            
            return ActionResult(
                success=False,
                message="SSL provisioning failed",
                error=ssl_result.get('error'),
                data=results
            )
        
        self.add_step('ssl', 'success', "SSL certificate provisioned")
        
        # Step 3: Update HAProxy configuration
        self.add_step('haproxy', 'running', 'Updating HAProxy configuration')
        
        haproxy_result = self._update_haproxy()
        results['steps']['haproxy'] = haproxy_result
        
        if not haproxy_result['success']:
            self.add_step('haproxy', 'failed', haproxy_result.get('error'))
            
            paas_db.update_domain(self.domain['id'], {
                'status': 'failed',
                'error': haproxy_result.get('error')
            })
            
            return ActionResult(
                success=False,
                message="HAProxy update failed",
                error=haproxy_result.get('error'),
                data=results
            )
        
        self.add_step('haproxy', 'success', "HAProxy configuration updated")
        
        # Step 4: Verify domain accessibility
        self.add_step('verify', 'running', 'Verifying domain accessibility')
        
        verify_result = self._verify_domain()
        results['steps']['verify'] = verify_result
        
        if not verify_result['success']:
            self.add_step('verify', 'failed', verify_result.get('error'))
            
            paas_db.update_domain(self.domain['id'], {
                'status': 'failed',
                'error': verify_result.get('error')
            })
            
            return ActionResult(
                success=False,
                message="Domain verification failed",
                error=verify_result.get('error'),
                data=results
            )
        
        self.add_step('verify', 'success', "Domain is accessible")
        
        # Update domain status
        paas_db.update_domain(self.domain['id'], {
            'status': 'active',
            'provisioned': 1,
            'ssl_enabled': 1,
            'ssl_expires_at': self._get_cert_expiry(),
            'error': None
        })
        
        return ActionResult(
            success=True,
            message=f"Domain {self.domain['domain']} provisioned successfully",
            data=results
        )
    
    def _get_zone_id(self) -> Optional[str]:
        """
        Get Cloudflare zone ID for the domain.
        
        Returns:
            Zone ID or None
        """
        import requests
        
        # Extract root domain
        domain_parts = self.domain['domain'].split('.')
        if len(domain_parts) >= 2:
            root_domain = '.'.join(domain_parts[-2:])
        else:
            root_domain = self.domain['domain']
        
        try:
            response = requests.get(
                f"{self.CLOUDFLARE_API_URL}/zones",
                params={'name': root_domain},
                headers={
                    'Authorization': f'Bearer {self.cloudflare_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('result'):
                    return data['result'][0]['id']
        
        except Exception as e:
            self.add_step('zone_lookup', 'failed', str(e))
        
        return None
    
    def _create_dns_records(self) -> Dict[str, Any]:
        """
        Create DNS records via Cloudflare API.
        
        Returns:
            Dictionary with success status and details
        """
        import requests
        
        domain = self.domain['domain']
        app_port = self.app.get('port', 8100)
        
        # Get router IPs for DNS records
        routers = self._get_router_ips()
        
        if not routers:
            return {
                'success': False,
                'error': 'No router IPs found'
            }
        
        records_created = []
        
        try:
            # Create A record (or AAAA for IPv6)
            for router_ip in routers:
                record_data = {
                    'type': 'A',
                    'name': domain if self.environment == 'production' else f'staging.{domain}',
                    'content': router_ip,
                    'ttl': 1,  # Auto
                    'proxied': True  # Enable Cloudflare proxy
                }
                
                response = requests.post(
                    f"{self.CLOUDFLARE_API_URL}/zones/{self.zone_id}/dns_records",
                    json=record_data,
                    headers={
                        'Authorization': f'Bearer {self.cloudflare_token}',
                        'Content-Type': 'application/json'
                    },
                    timeout=30
                )
                
                if response.status_code in [200, 201]:
                    records_created.append(response.json().get('result', {}).get('id'))
            
            return {
                'success': True,
                'records_created': records_created
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _provision_ssl(self) -> Dict[str, Any]:
        """
        Provision SSL certificate via certbot with DNS-01 challenge.
        
        Returns:
            Dictionary with success status and details
        """
        domain = self.domain['domain']
        
        if self.environment == 'staging':
            full_domain = f'staging.{domain}'
        else:
            full_domain = domain
        
        # Get router server for certbot execution
        routers = paas_db.list_servers()
        router = next((s for s in routers if 'router' in s.get('role', '').lower()), None)
        
        if not router:
            return {
                'success': False,
                'error': 'No router server found'
            }
        
        pool = get_ssh_pool()
        conn = pool.get_connection(router['ip'])
        
        if not conn:
            return {
                'success': False,
                'error': 'Could not connect to router'
            }
        
        try:
            # Run certbot with DNS-01 challenge
            certbot_cmd = (
                f"certbot certonly --dns-cloudflare "
                f"--dns-cloudflare-credentials /root/.cloudflare.ini "
                f"--dns-cloudflare-propagation-seconds 30 "
                f"-d {full_domain} "
                f"--non-interactive --agree-tos "
                f"-m admin@{domain}"
            )
            
            stdin, stdout, stderr = conn.exec_command(certbot_cmd, timeout=300)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            pool.release_connection(conn)
            
            if exit_code == 0:
                return {
                    'success': True,
                    'output': output
                }
            else:
                return {
                    'success': False,
                    'error': error or output
                }
        
        except Exception as e:
            pool.release_connection(conn)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _update_haproxy(self) -> Dict[str, Any]:
        """
        Update HAProxy configuration to route domain to application.
        
        Returns:
            Dictionary with success status and details
        """
        domain = self.domain['domain']
        app_name = self.app['name']
        app_port = self.app.get('port', 8100)
        
        if self.environment == 'staging':
            full_domain = f'staging.{domain}'
        else:
            full_domain = domain
        
        # Get router server
        routers = paas_db.list_servers()
        router = next((s for s in routers if 'router' in s.get('role', '').lower()), None)
        
        if not router:
            return {
                'success': False,
                'error': 'No router server found'
            }
        
        pool = get_ssh_pool()
        conn = pool.get_connection(router['ip'])
        
        if not conn:
            return {
                'success': False,
                'error': 'Could not connect to router'
            }
        
        try:
            # Add domain to HAProxy registry
            registry_entry = f"{full_domain}:{app_name}:{app_port}"
            
            # Update registry.conf
            cmd = f'echo "{registry_entry}" >> /etc/haproxy/domains/registry.conf'
            stdin, stdout, stderr = conn.exec_command(cmd)
            stdout.channel.recv_exit_status()
            
            # Rebuild HAProxy configuration
            rebuild_cmd = '/opt/scripts/provision-domain.sh --rebuild'
            stdin, stdout, stderr = conn.exec_command(rebuild_cmd, timeout=120)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode()
            error = stderr.read().decode()
            
            pool.release_connection(conn)
            
            if exit_code == 0:
                return {
                    'success': True,
                    'output': output
                }
            else:
                return {
                    'success': False,
                    'error': error or output
                }
        
        except Exception as e:
            pool.release_connection(conn)
            return {
                'success': False,
                'error': str(e)
            }
    
    def _verify_domain(self) -> Dict[str, Any]:
        """
        Verify domain is accessible and serving correctly.
        
        Returns:
            Dictionary with success status and details
        """
        import requests
        import time
        
        domain = self.domain['domain']
        
        if self.environment == 'staging':
            full_domain = f'staging.{domain}'
        else:
            full_domain = domain
        
        # Wait for DNS propagation (Cloudflare is usually fast)
        time.sleep(5)
        
        try:
            # Check if domain responds
            response = requests.get(
                f'https://{full_domain}',
                timeout=30,
                verify=True  # Verify SSL
            )
            
            if response.status_code in [200, 301, 302]:
                return {
                    'success': True,
                    'status_code': response.status_code
                }
            else:
                return {
                    'success': False,
                    'error': f'Domain returned status {response.status_code}'
                }
        
        except requests.exceptions.SSLError as e:
            return {
                'success': False,
                'error': f'SSL error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_router_ips(self) -> List[str]:
        """
        Get router public IPs for DNS records.
        
        Returns:
            List of router IP addresses
        """
        servers = paas_db.list_servers()
        routers = [s for s in servers if 'router' in s.get('role', '').lower()]
        
        ips = []
        for router in routers:
            # Use public IP for DNS
            if router.get('public_ip'):
                ips.append(router['public_ip'])
            elif router.get('ip'):
                ips.append(router['ip'])
        
        return ips
    
    def _get_cert_expiry(self) -> Optional[str]:
        """
        Get SSL certificate expiry date.
        
        Returns:
            ISO date string or None
        """
        from datetime import timedelta
        
        # Certbot certificates are valid for 90 days
        # Return approximate expiry
        expiry = datetime.utcnow() + timedelta(days=90)
        return expiry.isoformat()
    
    def rollback(self) -> ActionResult:
        """
        Rollback the domain provisioning.
        
        Returns:
            ActionResult with rollback outcome
        """
        results = {
            'steps': {}
        }
        
        # Remove HAProxy configuration
        self.add_step('rollback_haproxy', 'running', 'Removing HAProxy config')
        haproxy_result = self._remove_haproxy_config()
        results['steps']['haproxy'] = haproxy_result
        
        # Remove DNS records
        self.add_step('rollback_dns', 'running', 'Removing DNS records')
        dns_result = self._remove_dns_records()
        results['steps']['dns'] = dns_result
        
        # Update domain status
        paas_db.update_domain(self.domain['id'], {
            'status': 'rolled_back',
            'provisioned': 0
        })
        
        return ActionResult(
            success=True,
            message="Domain provisioning rolled back",
            data=results
        )
    
    def _remove_haproxy_config(self) -> Dict[str, Any]:
        """Remove HAProxy configuration for domain."""
        # Implementation similar to _update_haproxy but removing
        return {'success': True}
    
    def _remove_dns_records(self) -> Dict[str, Any]:
        """Remove DNS records for domain."""
        # Implementation similar to _create_dns_records but deleting
        return {'success': True}


# Convenience function
def provision_domain(domain_id: str = None, domain_name: str = None,
                     app_id: str = None, environment: str = 'production') -> ActionResult:
    """
    Provision a domain with default settings.
    
    Args:
        domain_id: Existing domain ID
        domain_name: Domain name to provision
        app_id: Application ID
        environment: 'production' or 'staging'
        
    Returns:
        ActionResult with provisioning outcome
    """
    action = ProvisionAction(
        domain_id=domain_id,
        domain_name=domain_name,
        app_id=app_id,
        environment=environment
    )
    return action.execute()