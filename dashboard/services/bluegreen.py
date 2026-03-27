"""
Blue-green deployment manager.

Maintains two deployment slots (blue/green) and switches traffic
between them after successful deployment.

Directory structure:
    /var/www/
    ├── myapp-blue/      # Blue slot
    ├── myapp-green/     # Green slot
    └── myapp -> myapp-blue  # Symlink to active slot

HAProxy routing:
    - Traffic routes to the symlink target
    - Switching traffic = updating symlink + reloading HAProxy
"""

import os
import json
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional, List

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


class BlueGreenDeploy:
    """
    Blue-green deployment manager.
    
    Maintains two deployment slots (blue/green) and switches traffic
    between them after successful deployment.
    """
    
    SLOTS = ['blue', 'green']
    
    # HAProxy routers
    ROUTERS = [
        {"name": "router-01", "ip": "100.102.220.16"},
        {"name": "router-02", "ip": "100.116.175.9"}
    ]
    
    @classmethod
    def get_current_slot(cls, app_name: str, environment: str) -> str:
        """
        Get the currently active slot for an app/environment.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            
        Returns:
            'blue' or 'green'
        """
        # Check the slot state in database
        app = db.get_application(name=app_name)
        if not app:
            return 'blue'  # Default to blue
        
        # Get slot state from app settings
        slot_key = f'bluegreen_{environment}_slot'
        slot = db.get_setting(slot_key, default='blue')
        
        # Verify symlink matches (if not, sync)
        app_id = app['id']
        expected_path = f'/var/www/{app_name}-{slot}'
        actual_link = cls._get_symlink_target(app_name, environment)
        
        if actual_link and actual_link != expected_path:
            # Symlink doesn't match DB state, update DB
            db.set_setting(slot_key, actual_link.split('-')[-1])
            return actual_link.split('-')[-1]
        
        return slot
    
    @classmethod
    def get_target_slot(cls, app_name: str, environment: str) -> str:
        """
        Get the inactive slot to deploy to.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            
        Returns:
            The inactive slot ('blue' or 'green')
        """
        current = cls.get_current_slot(app_name, environment)
        return 'green' if current == 'blue' else 'blue'
    
    @classmethod
    def deploy_to_slot(cls, app_name: str, slot: str, branch: str, 
                       environment: str, servers: List[Dict],
                       deployment_id: str = None) -> Dict[str, Any]:
        """
        Deploy to a specific slot.
        
        Args:
            app_name: Application name
            slot: 'blue' or 'green'
            branch: Git branch to deploy
            environment: 'production' or 'staging'
            servers: List of server dicts with 'name' and 'ip'
            deployment_id: Optional deployment ID for tracking
            
        Returns:
            Dict with 'success', 'slot', 'path', and any errors
        """
        if slot not in cls.SLOTS:
            return {'success': False, 'error': f'Invalid slot: {slot}'}
        
        slot_path = f'/var/www/{app_name}-{slot}'
        results = {'success': True, 'slot': slot, 'path': slot_path, 'servers': {}}
        
        for server in servers:
            server_name = server['name']
            server_ip = server['ip']
            
            try:
                # Ensure slot directory exists
                result = cls._run_ssh(server_ip, f'mkdir -p {slot_path}')
                
                # Clone or update repository
                clone_result = cls._deploy_code(server_ip, slot_path, app_name, branch)
                
                if not clone_result['success']:
                    results['success'] = False
                    results['servers'][server_name] = {
                        'success': False,
                        'error': clone_result.get('error')
                    }
                    continue
                
                results['servers'][server_name] = {
                    'success': True,
                    'path': slot_path
                }
                
            except Exception as e:
                results['success'] = False
                results['servers'][server_name] = {
                    'success': False,
                    'error': str(e)
                }
        
        # Store deployment slot info
        if results['success'] and deployment_id:
            db.update_deployment(deployment_id, {
                'slot': slot,
                'slot_path': slot_path
            })
        
        return results
    
    @classmethod
    def switch_traffic(cls, app_name: str, environment: str, 
                       target_slot: str = None) -> Dict[str, Any]:
        """
        Switch HAProxy traffic to the other slot.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            target_slot: Specific slot to switch to (optional, defaults to inactive)
            
        Returns:
            Dict with 'success', 'previous_slot', 'new_slot', and any errors
        """
        current_slot = cls.get_current_slot(app_name, environment)
        
        if target_slot:
            if target_slot not in cls.SLOTS:
                return {'success': False, 'error': f'Invalid slot: {target_slot}'}
            new_slot = target_slot
        else:
            new_slot = cls.get_target_slot(app_name, environment)
        
        if current_slot == new_slot:
            return {
                'success': True,
                'previous_slot': current_slot,
                'new_slot': new_slot,
                'message': 'Already on target slot, no switch needed'
            }
        
        results = {
            'success': True,
            'previous_slot': current_slot,
            'new_slot': new_slot,
            'routers': {}
        }
        
        # Get app info for port
        app = db.get_application(name=app_name)
        port = app.get('port', 8100) if app else 8100
        if environment == 'staging':
            port = port + 1100
        
        # Update symlink on all app servers
        servers = db.list_servers()
        app_servers = [s for s in servers if s.get('role') == 'app']
        
        for server in app_servers:
            server_ip = server['ip']
            server_name = server['name']
            
            try:
                # Atomic symlink switch
                new_path = f'/var/www/{app_name}-{new_slot}'
                temp_link = f'/var/www/{app_name}-temp'
                final_link = f'/var/www/{app_name}'
                
                # Create new symlink atomically
                result = cls._run_ssh(
                    server_ip,
                    f'ln -sfn {new_path} {temp_link} && mv -Tf {temp_link} {final_link}'
                )
                
                if result['success']:
                    results['routers'][server_name] = {
                        'success': True,
                        'action': 'symlink_updated',
                        'path': new_path
                    }
                else:
                    results['routers'][server_name] = {
                        'success': False,
                        'error': result.get('error', 'Failed to update symlink')
                    }
                    results['success'] = False
                    
            except Exception as e:
                results['routers'][server_name] = {
                    'success': False,
                    'error': str(e)
                }
                results['success'] = False
        
        # Update HAProxy backend on routers if needed
        # (In this architecture, HAProxy routes by Host header, so no backend change needed)
        # Just reload nginx on app servers
        for server in app_servers:
            server_ip = server['ip']
            cls._run_ssh(server_ip, 'sudo systemctl reload nginx')
        
        # Update database state
        if results['success']:
            slot_key = f'bluegreen_{environment}_slot'
            db.set_setting(slot_key, new_slot)
            
            # Log the switch
            switch_key = f'bluegreen_{app_name}_{environment}_last_switch'
            db.set_setting(switch_key, {
                'previous_slot': current_slot,
                'new_slot': new_slot,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        return results
    
    @classmethod
    def rollback_slot(cls, app_name: str, environment: str) -> Dict[str, Any]:
        """
        Switch back to the previous slot.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            
        Returns:
            Dict with 'success', 'previous_slot', 'new_slot', and any errors
        """
        current_slot = cls.get_current_slot(app_name, environment)
        previous_slot = 'green' if current_slot == 'blue' else 'blue'
        
        # Verify previous slot has valid deployment
        app = db.get_application(name=app_name)
        servers = db.list_servers()
        app_servers = [s for s in servers if s.get('role') == 'app']
        
        for server in app_servers:
            previous_path = f'/var/www/{app_name}-{previous_slot}'
            result = cls._run_ssh(server['ip'], f'test -d {previous_path}')
            if not result['success']:
                return {
                    'success': False,
                    'error': f'Previous slot {previous_slot} does not exist on {server["name"]}'
                }
        
        return cls.switch_traffic(app_name, environment, previous_slot)
    
    @classmethod
    def get_status(cls, app_name: str, environment: str) -> Dict[str, Any]:
        """
        Get blue-green deployment status for an app.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            
        Returns:
            Dict with current slot, target slot, and deployment info
        """
        current_slot = cls.get_current_slot(app_name, environment)
        target_slot = cls.get_target_slot(app_name, environment)
        
        app = db.get_application(name=app_name)
        servers = db.list_servers()
        app_servers = [s for s in servers if s.get('role') == 'app']
        
        slot_status = {}
        for slot in cls.SLOTS:
            slot_status[slot] = {
                'path': f'/var/www/{app_name}-{slot}',
                'servers': {}
            }
            
            for server in app_servers:
                server_ip = server['ip']
                server_name = server['name']
                slot_path = f'/var/www/{app_name}-{slot}'
                
                # Check if slot exists and get commit info
                result = cls._run_ssh(
                    server_ip,
                    f'if [ -d {slot_path} ]; then cd {slot_path} && git rev-parse HEAD 2>/dev/null || echo "not_a_git_repo"; else echo "not_found"; fi'
                )
                
                if result['success'] and result['output'].strip() not in ['not_found', 'not_a_git_repo']:
                    slot_status[slot]['servers'][server_name] = {
                        'exists': True,
                        'commit': result['output'].strip()[:8]
                    }
                else:
                    slot_status[slot]['servers'][server_name] = {
                        'exists': False
                    }
        
        # Get last switch info
        switch_key = f'bluegreen_{app_name}_{environment}_last_switch'
        last_switch = db.get_setting(switch_key, default=None)
        
        return {
            'app_name': app_name,
            'environment': environment,
            'current_slot': current_slot,
            'target_slot': target_slot,
            'slot_status': slot_status,
            'last_switch': last_switch
        }
    
    @classmethod
    def _get_symlink_target(cls, app_name: str, environment: str) -> Optional[str]:
        """Get the actual symlink target from first available server."""
        servers = db.list_servers()
        app_servers = [s for s in servers if s.get('role') == 'app']
        
        if not app_servers:
            return None
        
        server_ip = app_servers[0]['ip']
        result = cls._run_ssh(
            server_ip,
            f'readlink /var/www/{app_name} 2>/dev/null || echo ""'
        )
        
        if result['success']:
            return result['output'].strip() or None
        
        return None
    
    @classmethod
    def _deploy_code(cls, server_ip: str, slot_path: str, 
                     app_name: str, branch: str) -> Dict[str, Any]:
        """Deploy code to a slot."""
        # Check if directory exists and is a git repo
        check_result = cls._run_ssh(
            server_ip,
            f'if [ -d {slot_path}/.git ]; then echo "exists"; else echo "not_exists"; fi'
        )
        
        if check_result['output'].strip() == 'exists':
            # Update existing repo
            result = cls._run_ssh(
                server_ip,
                f'cd {slot_path} && git fetch origin && git checkout {branch} && git pull origin {branch}'
            )
        else:
            # Get repository URL from app config
            app = db.get_application(name=app_name)
            repo_url = app.get('repository') if app else None
            
            if not repo_url:
                return {'success': False, 'error': 'No repository configured'}
            
            # Clone new repo
            result = cls._run_ssh(
                server_ip,
                f'rm -rf {slot_path} && git clone -b {branch} {repo_url} {slot_path}'
            )
        
        return {
            'success': result['success'],
            'error': result.get('error')
        }
    
    @classmethod
    def _run_ssh(cls, server_ip: str, command: str, timeout: int = 300) -> Dict[str, Any]:
        """Run SSH command on a server."""
        try:
            ssh_key = os.environ.get('SSH_KEY_PATH', '/root/.ssh/id_vps')
            full_command = [
                'ssh', '-i', ssh_key,
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                f'root@{server_ip}',
                command
            ]
            
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                'success': result.returncode == 0,
                'exit_code': result.returncode,
                'output': result.stdout,
                'error': result.stderr
            }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Command timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Convenience functions for use in deploy tasks
def get_current_slot(app_name: str, environment: str) -> str:
    """Get the currently active slot."""
    return BlueGreenDeploy.get_current_slot(app_name, environment)


def get_target_slot(app_name: str, environment: str) -> str:
    """Get the target slot for deployment."""
    return BlueGreenDeploy.get_target_slot(app_name, environment)


def switch_traffic(app_name: str, environment: str) -> Dict[str, Any]:
    """Switch traffic to the other slot."""
    return BlueGreenDeploy.switch_traffic(app_name, environment)


def rollback_slot(app_name: str, environment: str) -> Dict[str, Any]:
    """Rollback to the previous slot."""
    return BlueGreenDeploy.rollback_slot(app_name, environment)