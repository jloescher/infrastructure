"""
Rollback Action for PaaS.

This module provides the RollbackAction class for rolling back
deployments to previous versions with:
- Automatic detection of rollback target
- Hook execution
- Progress tracking
- Full rollback history
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base import BaseAction, ActionResult
from actions.deploy import DeployAction
from services.hooks import execute_pre_rollback_hooks, execute_post_rollback_hooks
import database as paas_db


class RollbackAction(BaseAction):
    """
    Rollback a deployment to a previous version.
    
    This action handles the complete rollback workflow:
    1. Validate the deployment to rollback
    2. Find the previous successful deployment
    3. Execute pre-rollback hooks
    4. Deploy the previous version
    5. Execute post-rollback hooks
    6. Update deployment status
    
    Example:
        # Rollback a specific deployment
        action = RollbackAction(deployment_id='abc123')
        result = action.execute()
        
        # Rollback to a specific commit
        action = RollbackAction(
            deployment_id='abc123',
            target_commit='def456'
        )
        result = action.execute()
    """
    
    action_type = "rollback"
    
    def __init__(self, deployment_id: str = None, target_commit: str = None,
                 app_name: str = None, environment: str = None,
                 emit_progress: bool = True, skip_hooks: bool = False):
        """
        Initialize the rollback action.
        
        Args:
            deployment_id: ID of the failed deployment (optional if app_name provided)
            target_commit: Specific commit to rollback to (optional)
            app_name: Application name (alternative to deployment_id)
            environment: Environment name (required with app_name)
            emit_progress: Whether to emit WebSocket progress
            skip_hooks: Whether to skip pre/post rollback hooks
        """
        super().__init__(deployment_id=deployment_id, emit_progress=emit_progress)
        self.target_commit = target_commit
        self.app_name_param = app_name
        self.environment_param = environment
        self.skip_hooks = skip_hooks
        
        # Populated during execution
        self.deployment: Optional[Dict[str, Any]] = None
        self.app: Optional[Dict[str, Any]] = None
        self.servers: List[Dict[str, Any]] = []
        self.previous_deployment: Optional[Dict[str, Any]] = None
    
    def validate(self) -> List[str]:
        """
        Validate rollback parameters.
        
        Returns:
            List of validation errors
        """
        errors = []
        
        # Get deployment by ID or by app/environment
        if self.deployment_id:
            self.deployment = paas_db.get_deployment(self.deployment_id)
            if not self.deployment:
                errors.append(f"Deployment {self.deployment_id} not found")
                return errors
            
            self.app = paas_db.get_application(app_id=self.deployment['app_id'])
            if not self.app:
                errors.append("Application not found for deployment")
                return errors
        
        elif self.app_name_param and self.environment_param:
            self.app = paas_db.get_application(name=self.app_name_param)
            if not self.app:
                errors.append(f"Application '{self.app_name_param}' not found")
                return errors
            
            # Get the last deployment (current state)
            self.deployment = paas_db.get_last_deployment(
                self.app['id'], self.environment_param
            )
            if not self.deployment:
                errors.append(f"No deployments found for {self.app_name_param} in {self.environment_param}")
                return errors
        
        else:
            errors.append("Either deployment_id or both app_name and environment are required")
            return errors
        
        # Check for previous deployment
        self.previous_deployment = paas_db.get_rollback_target(
            self.app['id'],
            self.deployment['environment']
        )
        
        if not self.previous_deployment and not self.target_commit:
            errors.append("No previous deployment available to rollback to")
        
        return errors
    
    def pre_execute(self) -> bool:
        """
        Prepare for rollback.
        
        Creates rollback deployment record and gets target servers.
        
        Returns:
            True to proceed with rollback
        """
        if not super().pre_execute():
            return False
        
        # Get target servers
        all_servers = paas_db.list_servers()
        target_names = self.app.get('target_servers', [])
        self.servers = [s for s in all_servers if s['name'] in target_names]
        
        # Sort: primary first
        self.servers.sort(
            key=lambda s: 0 if 'primary' in s.get('role', '').lower() else 1
        )
        
        # Create rollback deployment record if using existing deployment ID
        if self.deployment_id:
            self.deployment_id = paas_db.create_rollback_deployment(self.deployment_id)
        
        # Update deployment status
        paas_db.update_deployment(self.deployment_id, {
            'status': 'running',
            'logs': f'Rollback initiated at {datetime.utcnow().isoformat()}'
        })
        
        # Store rollback data
        self.store_rollback_data('original_deployment_id', self.deployment['id'])
        self.store_rollback_data('app_id', self.app['id'])
        self.store_rollback_data('environment', self.deployment['environment'])
        
        return True
    
    def _execute(self) -> ActionResult:
        """
        Execute the rollback.
        
        Returns:
            ActionResult with rollback outcome
        """
        results = {
            'original_deployment': self.deployment.get('id'),
            'rollback_to': None,
            'hooks': {}
        }
        
        # Determine target deployment
        if self.target_commit:
            # Rollback to specific commit
            target = {
                'branch': self.deployment.get('branch', 'main'),
                'commit': self.target_commit
            }
            results['rollback_to'] = f"commit {self.target_commit}"
        else:
            # Rollback to previous deployment
            target = self.previous_deployment
            results['rollback_to'] = f"deployment {target['id']}"
        
        self.add_step('rollback_target', 'success',
                     f"Rolling back to {results['rollback_to']}")
        
        # Execute pre-rollback hooks
        if not self.skip_hooks:
            self.add_step('pre_rollback_hooks', 'running',
                         "Running pre-rollback hooks")
            
            hook_result = execute_pre_rollback_hooks(
                app_id=self.app['id'],
                environment=self.deployment['environment'],
                servers=self.servers,
                deployment_id=self.deployment_id
            )
            
            results['hooks']['pre_rollback'] = hook_result
            
            if not hook_result['success']:
                self.add_step('pre_rollback_hooks', 'failed',
                             hook_result.get('message', 'Pre-rollback hooks failed'))
                
                paas_db.update_deployment(self.deployment_id, {
                    'status': 'failed',
                    'logs': 'Rollback failed: pre-rollback hooks failed',
                    'finished_at': datetime.utcnow().isoformat()
                })
                
                return ActionResult(
                    success=False,
                    message="Pre-rollback hooks failed",
                    error=hook_result.get('message'),
                    data=results
                )
            
            self.add_step('pre_rollback_hooks', 'success',
                         f"Completed {hook_result['hooks_executed']} hooks")
        
        # Execute rollback deployment
        self.add_step('deploy', 'running', "Deploying previous version")
        
        rollback_deploy = DeployAction(
            app_name=self.app['name'],
            environment=self.deployment['environment'],
            branch=target.get('branch', 'main'),
            commit=target.get('commit'),
            deployment_id=self.deployment_id,
            emit_progress=self.emit_progress,
            skip_hooks=True  # Hooks already executed above
        )
        
        deploy_result = rollback_deploy.execute()
        results['deploy'] = deploy_result.to_dict()
        
        if not deploy_result.success:
            paas_db.update_deployment(self.deployment_id, {
                'status': 'failed',
                'finished_at': datetime.utcnow().isoformat()
            })
            
            return ActionResult(
                success=False,
                message="Rollback deployment failed",
                error=deploy_result.error,
                data=results
            )
        
        # Execute post-rollback hooks
        if not self.skip_hooks:
            self.add_step('post_rollback_hooks', 'running',
                         "Running post-rollback hooks")
            
            hook_result = execute_post_rollback_hooks(
                app_id=self.app['id'],
                environment=self.deployment['environment'],
                servers=self.servers,
                deployment_id=self.deployment_id
            )
            
            results['hooks']['post_rollback'] = hook_result
            self.add_step('post_rollback_hooks', 'success',
                         f"Completed {hook_result['hooks_executed']} hooks")
        
        # Update deployment status
        paas_db.update_deployment(self.deployment_id, {
            'status': 'success',
            'logs': f'Rollback completed successfully at {datetime.utcnow().isoformat()}',
            'finished_at': datetime.utcnow().isoformat()
        })
        
        return ActionResult(
            success=True,
            message=f"Rollback completed: deployed {results['rollback_to']}",
            data=results
        )
    
    def rollback(self) -> ActionResult:
        """
        A rollback of a rollback is a redeploy of the original.
        
        Returns:
            ActionResult with re-deploy outcome
        """
        original_id = self.get_rollback_data('original_deployment_id')
        
        if not original_id:
            return ActionResult(
                success=False,
                message="Cannot rollback a rollback without original deployment info"
            )
        
        # Re-deploy the original version
        original = paas_db.get_deployment(original_id)
        
        if not original:
            return ActionResult(
                success=False,
                message="Original deployment not found"
            )
        
        return DeployAction(
            app_name=self.app['name'],
            environment=self.deployment['environment'],
            branch=original.get('branch', 'main'),
            commit=original.get('commit'),
            emit_progress=self.emit_progress
        ).execute()


# Convenience function for quick rollbacks
def rollback_deployment(deployment_id: str = None, 
                        app_name: str = None,
                        environment: str = None,
                        target_commit: str = None) -> ActionResult:
    """
    Rollback a deployment with default settings.
    
    Args:
        deployment_id: ID of deployment to rollback (optional)
        app_name: Application name (alternative to deployment_id)
        environment: Environment name (required with app_name)
        target_commit: Specific commit to rollback to (optional)
        
    Returns:
        ActionResult with rollback outcome
    """
    action = RollbackAction(
        deployment_id=deployment_id,
        app_name=app_name,
        environment=environment,
        target_commit=target_commit
    )
    return action.execute()