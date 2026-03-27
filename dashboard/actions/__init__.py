"""
Action Pattern Module for Phase 3 PaaS.

This module provides reusable, testable action classes with:
- Consistent error handling and validation
- Progress tracking and rollback support
- Pre/post execution hooks
- Real-time WebSocket updates

Available Actions:
- DeployAction: Deploy applications to target servers
- RollbackAction: Rollback deployments to previous versions
- ProvisionAction: Provision domains with SSL certificates
- BackupAction: Create database backups

Usage:
    from actions import DeployAction
    
    action = DeployAction(
        app_name='myapp',
        environment='production',
        branch='main'
    )
    
    result = action.execute()
    
    if result.success:
        print(f"Deployed successfully: {result.message}")
    else:
        print(f"Deployment failed: {result.error}")
"""

from actions.base import BaseAction, ActionResult
from actions.deploy import DeployAction
from actions.rollback import RollbackAction
from actions.provision import ProvisionAction
from actions.backup import BackupAction

__all__ = [
    'BaseAction',
    'ActionResult',
    'DeployAction',
    'RollbackAction',
    'ProvisionAction',
    'BackupAction',
]