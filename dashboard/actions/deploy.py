"""
Deploy Action for PaaS.

This module provides the DeployAction class for deploying applications
to target servers with:
- Framework-specific commands
- Multi-server deployment
- Progress tracking
- Rollback support
- Hook execution
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base import BaseAction, ActionResult
from services.framework import get_framework_config, get_health_check_config
from services.hooks import execute_pre_deploy_hooks, execute_post_deploy_hooks
from websocket.performance import get_ssh_pool
import database as paas_db


class DeployAction(BaseAction):
    """
    Deploy an application to target servers.
    
    This action handles the complete deployment workflow:
    1. Validate application and environment
    2. Execute pre-deploy hooks
    3. Deploy to each server (primary first)
    4. Execute post-deploy hooks
    5. Update deployment status
    
    Supports all PaaS frameworks:
    - Laravel (PHP with nginx + PHP-FPM)
    - Next.js (Node.js with systemd)
    - SvelteKit (Node.js with systemd)
    - Python (Flask/Django with Gunicorn)
    - Go (Binary with systemd)
    
    Example:
        action = DeployAction(
            app_name='myapp',
            environment='production',
            branch='main',
            commit='abc123'
        )
        
        result = action.execute()
        
        if result.success:
            print(f"Deployed to {len(result.data['success'])} servers")
        else:
            print(f"Deployment failed: {result.error}")
    """
    
    action_type = "deploy"
    
    # Deployment step definitions with progress weights
    DEPLOYMENT_STEPS = [
        ('git_fetch', 'Fetch latest code', 5),
        ('git_pull', 'Pull changes', 10),
        ('install_deps', 'Install dependencies', 30),
        ('build_assets', 'Build assets', 15),
        ('run_migrations', 'Run migrations', 10),
        ('clear_cache', 'Clear cache', 5),
        ('restart_services', 'Restart services', 15),
        ('health_check', 'Health check', 10),
    ]
    
    def __init__(self, app_name: str, environment: str, branch: str,
                 commit: str = None, deployment_id: str = None,
                 emit_progress: bool = True, skip_hooks: bool = False):
        """
        Initialize the deploy action.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            branch: Git branch to deploy
            commit: Specific commit hash (optional)
            deployment_id: Existing deployment ID (optional)
            emit_progress: Whether to emit WebSocket progress
            skip_hooks: Whether to skip pre/post deploy hooks
        """
        super().__init__(deployment_id=deployment_id, emit_progress=emit_progress)
        self.app_name = app_name
        self.environment = environment
        self.branch = branch
        self.commit = commit
        self.skip_hooks = skip_hooks
        
        # Populated during execution
        self.app: Optional[Dict[str, Any]] = None
        self.servers: List[Dict[str, Any]] = []
        self.framework: str = 'laravel'
        self.app_path: str = ''
        self.port: int = 8100
    
    def validate(self) -> List[str]:
        """
        Validate deployment parameters.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Check app exists
        self.app = paas_db.get_application(name=self.app_name)
        if not self.app:
            errors.append(f"Application '{self.app_name}' not found")
            return errors
        
        # Check target servers
        target_servers = self.app.get('target_servers', [])
        if not target_servers:
            errors.append("No target servers configured for application")
        
        # Validate environment
        if self.environment not in ['production', 'staging']:
            errors.append(f"Invalid environment: {self.environment}. Must be 'production' or 'staging'")
        
        # Validate branch
        if not self.branch:
            errors.append("Branch is required")
        
        return errors
    
    def pre_execute(self) -> bool:
        """
        Prepare for deployment.
        
        Creates deployment record and updates status to 'running'.
        
        Returns:
            True to proceed with deployment
        """
        if not super().pre_execute():
            return False
        
        # Store application details
        self.framework = self.app.get('framework', 'laravel')
        self.port = self.app.get('port', 8100)
        self.app_path = f"/var/www/{self.app_name}"
        
        # Get target servers
        all_servers = paas_db.list_servers()
        target_names = self.app.get('target_servers', [])
        self.servers = [s for s in all_servers if s['name'] in target_names]
        
        # Sort: primary first
        self.servers.sort(
            key=lambda s: 0 if 'primary' in s.get('role', '').lower() else 1
        )
        
        # Create deployment record if not provided
        if not self.deployment_id:
            self.deployment_id = paas_db.create_deployment(
                self.app['id'], self.environment, self.branch, self.commit
            )
        
        # Update deployment status
        paas_db.update_deployment(self.deployment_id, {'status': 'running'})
        
        # Create deployment steps for tracking
        for server in self.servers:
            for step_name, _, _ in self.DEPLOYMENT_STEPS:
                paas_db.create_deployment_step(
                    self.deployment_id, server['name'], step_name
                )
        
        # Store rollback data
        self.store_rollback_data('app_id', self.app['id'])
        self.store_rollback_data('environment', self.environment)
        self.store_rollback_data('previous_deployment', 
            paas_db.get_last_successful_deployment(self.app['id'], self.environment)
        )
        
        return True
    
    def _execute(self) -> ActionResult:
        """
        Execute the deployment.
        
        Returns:
            ActionResult with deployment outcome
        """
        config = get_framework_config(self.framework)
        results = {
            'servers': {},
            'success': [],
            'errors': [],
            'hooks': {}
        }
        
        # Execute pre-deploy hooks
        if not self.skip_hooks:
            self.add_step('pre_deploy_hooks', 'running', 
                         f"Running pre-deploy hooks for {self.app_name}")
            
            hook_result = execute_pre_deploy_hooks(
                app_id=self.app['id'],
                environment=self.environment,
                servers=self.servers,
                deployment_id=self.deployment_id
            )
            
            results['hooks']['pre_deploy'] = hook_result
            
            if not hook_result['success']:
                self.add_step('pre_deploy_hooks', 'failed', 
                             hook_result.get('message', 'Pre-deploy hooks failed'))
                
                paas_db.update_deployment(self.deployment_id, {
                    'status': 'failed',
                    'results_json': json.dumps(results),
                    'finished_at': datetime.utcnow().isoformat()
                })
                
                return ActionResult(
                    success=False,
                    message="Pre-deploy hooks failed",
                    error=hook_result.get('message'),
                    data=results
                )
            
            self.add_step('pre_deploy_hooks', 'success', 
                         f"Completed {hook_result['hooks_executed']} hooks")
        
        # Deploy to each server
        for server in self.servers:
            server_result = self._deploy_to_server(server, config)
            results['servers'][server['name']] = server_result
            
            if server_result['success']:
                results['success'].append(server['name'])
            else:
                results['errors'].append(
                    f"{server['name']}: {server_result.get('error')}"
                )
                
                # Stop if primary fails
                if 'primary' in server.get('role', '').lower():
                    self.add_step('abort', 'failed',
                                 f"Primary server {server['name']} failed, aborting")
                    break
        
        # Determine overall success
        success = len(results['errors']) == 0
        
        # Execute post-deploy hooks (only if deployment succeeded)
        if success and not self.skip_hooks:
            self.add_step('post_deploy_hooks', 'running',
                         f"Running post-deploy hooks for {self.app_name}")
            
            hook_result = execute_post_deploy_hooks(
                app_id=self.app['id'],
                environment=self.environment,
                servers=self.servers,
                deployment_id=self.deployment_id
            )
            
            results['hooks']['post_deploy'] = hook_result
            self.add_step('post_deploy_hooks', 'success',
                         f"Completed {hook_result['hooks_executed']} hooks")
        
        # Update deployment status
        paas_db.update_deployment(self.deployment_id, {
            'status': 'success' if success else 'failed',
            'results_json': json.dumps(results),
            'finished_at': datetime.utcnow().isoformat()
        })
        
        return ActionResult(
            success=success,
            message=f"Deployed to {len(results['success'])}/{len(self.servers)} servers",
            data=results,
            error="; ".join(results['errors']) if results['errors'] else None
        )
    
    def _deploy_to_server(self, server: Dict, config: Dict) -> Dict:
        """
        Deploy to a single server.
        
        Args:
            server: Server dictionary with 'name' and 'ip'
            config: Framework configuration
            
        Returns:
            Dictionary with deployment result
        """
        pool = get_ssh_pool()
        conn = pool.get_connection(server['ip'])
        
        if not conn:
            return {'success': False, 'error': 'Could not connect to server'}
        
        server_name = server['name']
        result = {'steps': [], 'success': True}
        
        try:
            for step_name, step_desc, _ in self.DEPLOYMENT_STEPS:
                self.add_step(step_name, 'running', server=server_name)
                
                # Update step in database
                steps = paas_db.get_deployment_steps(self.deployment_id)
                for s in steps:
                    if s['server'] == server_name and s['step'] == step_name:
                        paas_db.update_deployment_step(
                            s['id'],
                            status='running',
                            started_at=datetime.utcnow().isoformat()
                        )
                        break
                
                cmd = self._get_step_command(step_name, config)
                
                if not cmd:
                    # Skip this step for this framework
                    self.add_step(step_name, 'skipped', server=server_name)
                    result['steps'].append({'name': step_name, 'status': 'skipped'})
                    
                    for s in steps:
                        if s['server'] == server_name and s['step'] == step_name:
                            paas_db.update_deployment_step(s['id'], status='skipped')
                            break
                    continue
                
                # Execute command
                start_time = datetime.utcnow()
                stdin, stdout, stderr = conn.exec_command(cmd, timeout=300)
                exit_code = stdout.channel.recv_exit_status()
                duration = (datetime.utcnow() - start_time).total_seconds()
                
                output = stdout.read().decode('utf-8', errors='replace')[:2000]
                error = stderr.read().decode('utf-8', errors='replace')[:2000]
                
                if exit_code != 0:
                    self.add_step(step_name, 'failed', 
                                 error[:200] if error else 'Command failed',
                                 server=server_name, duration=duration)
                    
                    result['success'] = False
                    result['error'] = f"{step_name} failed: {error[:200] if error else 'Unknown error'}"
                    result['steps'].append({
                        'name': step_name, 
                        'status': 'failed', 
                        'error': error[:500]
                    })
                    
                    # Update step in database
                    for s in steps:
                        if s['server'] == server_name and s['step'] == step_name:
                            paas_db.update_deployment_step(
                                s['id'],
                                status='failed',
                                output=error[:500],
                                finished_at=datetime.utcnow().isoformat()
                            )
                            break
                    
                    break
                else:
                    self.add_step(step_name, 'success',
                                 output[:200] if output else 'OK',
                                 server=server_name, duration=duration)
                    
                    result['steps'].append({
                        'name': step_name,
                        'status': 'success',
                        'output': output[:500]
                    })
                    
                    # Update step in database
                    for s in steps:
                        if s['server'] == server_name and s['step'] == step_name:
                            paas_db.update_deployment_step(
                                s['id'],
                                status='success',
                                output=output[:500],
                                finished_at=datetime.utcnow().isoformat()
                            )
                            break
        
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            self.add_step('error', 'failed', str(e), server=server_name)
        
        finally:
            pool.release_connection(conn)
        
        return result
    
    def _get_step_command(self, step: str, config: Dict) -> Optional[str]:
        """
        Get the command for a deployment step.
        
        Args:
            step: Step name (e.g., 'git_fetch', 'install_deps')
            config: Framework configuration
            
        Returns:
            Command string or None if step should be skipped
        """
        cd = f'cd {self.app_path}'
        
        if step == 'git_fetch':
            return f'{cd} && git fetch origin'
        
        if step == 'git_pull':
            cmd = f'{cd} && git checkout {self.branch} && git pull origin {self.branch}'
            if self.commit:
                cmd += f' && git checkout {self.commit}'
            return cmd
        
        if step == 'install_deps':
            cmd = config.get('install_cmd')
            if cmd:
                return f'{cd} && {cmd}'
            return None
        
        if step == 'build_assets':
            cmd = config.get('build_cmd')
            if cmd:
                # Replace placeholders
                cmd = cmd.replace('{app_name}', self.app_name)
                cmd = cmd.replace('{port}', str(self.port))
                return f'{cd} && {cmd}'
            return None
        
        if step == 'run_migrations':
            cmd = config.get('migrate_cmd')
            if cmd:
                return f'{cd} && {cmd}'
            return None
        
        if step == 'clear_cache':
            # Only Laravel has cache clearing
            if self.framework == 'laravel':
                return f'{cd} && php artisan cache:clear && php artisan config:clear && php artisan view:clear'
            return None
        
        if step == 'restart_services':
            runtime = config.get('runtime', '')
            
            if 'php-fpm' in runtime:
                return 'sudo systemctl reload php8.5-fpm && sudo systemctl reload nginx'
            elif 'systemd' in runtime:
                return f'sudo systemctl restart {self.app_name}'
            return None
        
        if step == 'health_check':
            health_config = get_health_check_config(self.framework, self.port)
            port = health_config['port']
            path = health_config['path']
            return f'curl -sf http://localhost:{port}{path} || exit 1'
        
        return None
    
    def rollback(self) -> ActionResult:
        """
        Rollback the deployment.
        
        This method triggers a rollback to the previous successful deployment.
        
        Returns:
            ActionResult with rollback outcome
        """
        previous = self.get_rollback_data('previous_deployment')
        
        if not previous:
            return ActionResult(
                success=False,
                message="No previous deployment to rollback to"
            )
        
        # Execute rollback as a new deployment
        rollback_action = RollbackAction(
            deployment_id=self.deployment_id,
            target_commit=previous.get('commit')
        )
        
        return rollback_action.execute()


# Convenience function for quick deployments
def deploy_application(app_name: str, environment: str, branch: str,
                       commit: str = None) -> ActionResult:
    """
    Deploy an application with default settings.
    
    Args:
        app_name: Application name
        environment: 'production' or 'staging'
        branch: Git branch
        commit: Optional specific commit
        
    Returns:
        ActionResult with deployment outcome
    """
    action = DeployAction(
        app_name=app_name,
        environment=environment,
        branch=branch,
        commit=commit
    )
    return action.execute()