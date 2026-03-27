"""
Unit Tests for Action Pattern.

This module provides test cases for all action classes demonstrating:
- How to test actions in isolation
- How to mock external dependencies
- How to verify action behavior

Run tests with:
    python -m pytest dashboard/tests/test_actions.py -v

Or with unittest:
    python -m unittest dashboard.tests.test_actions -v
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import json

# Import actions
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base import BaseAction, ActionResult, ActionChain, ParallelActionGroup
from actions.deploy import DeployAction, deploy_application
from actions.rollback import RollbackAction, rollback_deployment
from actions.provision import ProvisionAction, provision_domain
from actions.backup import BackupAction, RestoreAction, create_backup, restore_backup


class TestActionResult(unittest.TestCase):
    """Test ActionResult dataclass."""
    
    def test_success_result(self):
        """Test creating a successful result."""
        result = ActionResult(
            success=True,
            message="Operation completed",
            data={'key': 'value'}
        )
        
        self.assertTrue(result.success)
        self.assertEqual(result.message, "Operation completed")
        self.assertEqual(result.data['key'], 'value')
        self.assertIsNone(result.error)
    
    def test_failure_result(self):
        """Test creating a failure result."""
        result = ActionResult(
            success=False,
            message="Operation failed",
            error="Something went wrong"
        )
        
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Something went wrong")
    
    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = ActionResult(
            success=True,
            message="Test",
            data={'foo': 'bar'},
            steps=[{'name': 'step1', 'status': 'success'}]
        )
        
        result_dict = result.to_dict()
        
        self.assertIsInstance(result_dict, dict)
        self.assertTrue(result_dict['success'])
        self.assertEqual(result_dict['data']['foo'], 'bar')
        self.assertEqual(len(result_dict['steps']), 1)
    
    def test_to_json(self):
        """Test converting result to JSON."""
        result = ActionResult(
            success=True,
            message="Test"
        )
        
        json_str = result.to_json()
        
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertTrue(parsed['success'])


class TestBaseAction(unittest.TestCase):
    """Test BaseAction class."""
    
    def test_validation_failure(self):
        """Test that validation failure returns error result."""
        class ValidatedAction(BaseAction):
            action_type = "validated"
            
            def validate(self):
                return ["Validation error 1", "Validation error 2"]
            
            def _execute(self):
                return ActionResult(success=True, message="Should not reach")
        
        action = ValidatedAction()
        result = action.execute()
        
        self.assertFalse(result.success)
        self.assertIn("Validation error 1", result.error)
        self.assertIn("Validation error 2", result.error)
    
    def test_pre_execute_abort(self):
        """Test that pre_execute returning False aborts execution."""
        class AbortAction(BaseAction):
            action_type = "abort"
            
            def pre_execute(self):
                return False
            
            def _execute(self):
                return ActionResult(success=True, message="Should not reach")
        
        action = AbortAction()
        result = action.execute()
        
        self.assertFalse(result.success)
        self.assertEqual(result.message, "Pre-execution check failed")
    
    def test_exception_handling(self):
        """Test that exceptions are caught and returned as errors."""
        class ExceptionAction(BaseAction):
            action_type = "exception"
            
            def _execute(self):
                raise ValueError("Test exception")
        
        action = ExceptionAction()
        result = action.execute()
        
        self.assertFalse(result.success)
        self.assertIn("Test exception", result.message)
        self.assertIn("ValueError: Test exception", result.error)
    
    def test_step_tracking(self):
        """Test that steps are tracked correctly."""
        class StepAction(BaseAction):
            action_type = "step"
            
            def _execute(self):
                self.add_step("step1", "running")
                self.add_step("step1", "success", "Output here")
                self.add_step("step2", "running")
                self.add_step("step2", "failed", "Error here")
                
                return ActionResult(success=False, message="Done")
        
        action = StepAction(emit_progress=False)
        result = action.execute()
        
        self.assertEqual(len(result.steps), 4)
        self.assertEqual(result.steps[0]['name'], 'step1')
        self.assertEqual(result.steps[0]['status'], 'running')
        self.assertEqual(result.steps[1]['status'], 'success')
        self.assertEqual(result.steps[1]['output'], 'Output here')
    
    def test_rollback_data(self):
        """Test storing and retrieving rollback data."""
        action = BaseAction()
        
        action.store_rollback_data('key1', 'value1')
        action.store_rollback_data('key2', {'nested': 'data'})
        
        self.assertEqual(action.get_rollback_data('key1'), 'value1')
        self.assertEqual(action.get_rollback_data('key2')['nested'], 'data')
        self.assertIsNone(action.get_rollback_data('nonexistent'))
        self.assertEqual(action.get_rollback_data('nonexistent', 'default'), 'default')
    
    def test_execute_with_rollback(self):
        """Test execute_with_rollback calls rollback on failure."""
        class RollbackAction(BaseAction):
            action_type = "with_rollback"
            
            def _execute(self):
                self.store_rollback_data('called', True)
                return ActionResult(success=False, message="Failed")
            
            def rollback(self):
                return ActionResult(
                    success=True,
                    message="Rollback completed"
                )
        
        action = RollbackAction()
        result = action.execute_with_rollback()
        
        self.assertFalse(result.success)
        self.assertIn('Rollback completed', result.message)
        self.assertIsNotNone(result.data)
        self.assertTrue(result.data['rollback']['success'])


class TestActionChain(unittest.TestCase):
    """Test ActionChain class."""
    
    def test_successful_chain(self):
        """Test chain with all successful actions."""
        class SuccessAction(BaseAction):
            action_type = "success"
            def _execute(self):
                return ActionResult(success=True, message="OK")
        
        chain = ActionChain()
        chain.add(SuccessAction()).add(SuccessAction()).add(SuccessAction())
        
        result = chain.execute()
        
        self.assertTrue(result.success)
        self.assertEqual(len(chain.results), 3)
    
    def test_chain_stops_on_failure(self):
        """Test that chain stops on first failure."""
        class SuccessAction(BaseAction):
            action_type = "success"
            def _execute(self):
                return ActionResult(success=True, message="OK")
        
        class FailAction(BaseAction):
            action_type = "fail"
            def _execute(self):
                return ActionResult(success=False, message="Failed")
        
        chain = ActionChain()
        chain.add(SuccessAction()).add(FailAction()).add(SuccessAction())
        
        result = chain.execute()
        
        self.assertFalse(result.success)
        self.assertEqual(len(chain.results), 2)  # Stopped after failure
    
    def test_chain_rollback_on_failure(self):
        """Test that chain rolls back completed actions on failure."""
        rollback_called = []
        
        class SuccessAction(BaseAction):
            action_type = "success"
            def _execute(self):
                return ActionResult(success=True, message="OK")
            def rollback(self):
                rollback_called.append(self.action_type)
                return ActionResult(success=True, message="Rolled back")
        
        class FailAction(BaseAction):
            action_type = "fail"
            def _execute(self):
                return ActionResult(success=False, message="Failed")
        
        chain = ActionChain(rollback_on_failure=True)
        chain.add(SuccessAction()).add(SuccessAction()).add(FailAction())
        
        result = chain.execute()
        
        self.assertFalse(result.success)
        self.assertEqual(len(rollback_called), 2)  # Both success actions rolled back


class TestParallelActionGroup(unittest.TestCase):
    """Test ParallelActionGroup class."""
    
    def test_parallel_execution(self):
        """Test that actions execute in parallel."""
        import time
        
        class SlowAction(BaseAction):
            action_type = "slow"
            def _execute(self):
                time.sleep(0.1)
                return ActionResult(success=True, message="OK")
        
        group = ParallelActionGroup()
        group.add(SlowAction()).add(SlowAction()).add(SlowAction())
        
        start = datetime.utcnow()
        result = group.execute()
        duration = (datetime.utcnow() - start).total_seconds()
        
        # Should take ~0.1s if parallel, ~0.3s if sequential
        self.assertTrue(result.success)
        self.assertLess(duration, 0.3)
    
    def test_partial_failure(self):
        """Test handling of partial failures."""
        class SuccessAction(BaseAction):
            action_type = "success"
            def _execute(self):
                return ActionResult(success=True, message="OK")
        
        class FailAction(BaseAction):
            action_type = "fail"
            def _execute(self):
                return ActionResult(success=False, message="Failed")
        
        group = ParallelActionGroup()
        group.add(SuccessAction()).add(FailAction()).add(SuccessAction())
        
        result = group.execute()
        
        self.assertFalse(result.success)
        self.assertEqual(result.data['success_count'], 2)
        self.assertEqual(result.data['failure_count'], 1)


class TestDeployAction(unittest.TestCase):
    """Test DeployAction class."""
    
    @patch('actions.deploy.paas_db')
    @patch('actions.deploy.get_ssh_pool')
    @patch('actions.deploy.execute_pre_deploy_hooks')
    @patch('actions.deploy.execute_post_deploy_hooks')
    def test_deploy_validation_app_not_found(self, mock_post_hooks, mock_pre_hooks, 
                                              mock_ssh_pool, mock_db):
        """Test validation fails when app not found."""
        mock_db.get_application.return_value = None
        
        action = DeployAction(
            app_name='nonexistent',
            environment='production',
            branch='main'
        )
        
        result = action.execute()
        
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)
    
    @patch('actions.deploy.paas_db')
    def test_deploy_validation_no_servers(self, mock_db):
        """Test validation fails when no servers configured."""
        mock_db.get_application.return_value = {
            'id': 'app1',
            'name': 'testapp',
            'target_servers': []
        }
        
        action = DeployAction(
            app_name='testapp',
            environment='production',
            branch='main'
        )
        
        errors = action.validate()
        
        self.assertIn("No target servers", errors[0])
    
    @patch('actions.deploy.paas_db')
    @patch('actions.deploy.get_ssh_pool')
    @patch('actions.deploy.execute_pre_deploy_hooks')
    @patch('actions.deploy.execute_post_deploy_hooks')
    def test_successful_deploy(self, mock_post_hooks, mock_pre_hooks, 
                                mock_ssh_pool, mock_db):
        """Test successful deployment flow."""
        # Setup mocks
        mock_db.get_application.return_value = {
            'id': 'app1',
            'name': 'testapp',
            'framework': 'laravel',
            'port': 8100,
            'target_servers': ['server1']
        }
        mock_db.list_servers.return_value = [
            {'name': 'server1', 'ip': '10.0.0.1', 'role': 'app primary'}
        ]
        mock_db.create_deployment.return_value = 'dep1'
        mock_db.get_deployment_steps.return_value = []
        
        mock_ssh_conn = MagicMock()
        mock_ssh_conn.exec_command.return_value = (
            MagicMock(),
            MagicMock(read=MagicMock(return_value=b'OK')),
            MagicMock(read=MagicMock(return_value=b''))
        )
        mock_ssh_conn.exec_command.return_value[1].channel.recv_exit_status.return_value = 0
        
        mock_pool = MagicMock()
        mock_pool.get_connection.return_value = mock_ssh_conn
        mock_ssh_pool.return_value = mock_pool
        
        mock_pre_hooks.return_value = {'success': True, 'hooks_executed': 0}
        mock_post_hooks.return_value = {'success': True, 'hooks_executed': 0}
        
        action = DeployAction(
            app_name='testapp',
            environment='production',
            branch='main',
            emit_progress=False
        )
        
        result = action.execute()
        
        self.assertTrue(result.success)
        mock_db.update_deployment.assert_called()


class TestRollbackAction(unittest.TestCase):
    """Test RollbackAction class."""
    
    @patch('actions.rollback.paas_db')
    def test_rollback_validation_deployment_not_found(self, mock_db):
        """Test validation fails when deployment not found."""
        mock_db.get_deployment.return_value = None
        
        action = RollbackAction(deployment_id='nonexistent')
        
        errors = action.validate()
        
        self.assertIn("not found", errors[0])
    
    @patch('actions.rollback.paas_db')
    def test_rollback_no_previous_deployment(self, mock_db):
        """Test validation fails when no previous deployment exists."""
        mock_db.get_deployment.return_value = {
            'id': 'dep1',
            'app_id': 'app1',
            'environment': 'production',
            'branch': 'main'
        }
        mock_db.get_application.return_value = {'id': 'app1', 'name': 'testapp'}
        mock_db.get_rollback_target.return_value = None
        
        action = RollbackAction(deployment_id='dep1')
        
        errors = action.validate()
        
        self.assertIn("No previous deployment", errors[0])


class TestBackupAction(unittest.TestCase):
    """Test BackupAction class."""
    
    @patch('actions.backup.paas_db')
    def test_backup_validation_invalid_type(self, mock_db):
        """Test validation fails with invalid backup type."""
        mock_db.list_servers.return_value = [
            {'name': 'db1', 'ip': '10.0.0.1', 'role': 'database'}
        ]
        
        action = BackupAction(
            db_name='testdb',
            backup_type='invalid'
        )
        
        errors = action.validate()
        
        self.assertIn("Invalid backup type", errors[0])
    
    @patch('actions.backup.paas_db')
    def test_backup_validation_no_database_server(self, mock_db):
        """Test validation fails when no database server found."""
        mock_db.list_servers.return_value = []
        
        action = BackupAction(db_name='testdb')
        
        errors = action.validate()
        
        self.assertIn("No database server", errors[0])


class TestProvisionAction(unittest.TestCase):
    """Test ProvisionAction class."""
    
    @patch('actions.provision.paas_db')
    def test_provision_validation_domain_not_found(self, mock_db):
        """Test validation fails when domain not found."""
        mock_db.get_domain.return_value = None
        
        action = ProvisionAction(domain_id='nonexistent')
        
        errors = action.validate()
        
        self.assertIn("not found", errors[0])
    
    @patch('actions.provision.paas_db')
    @patch.dict(os.environ, {}, clear=True)
    def test_provision_validation_no_cloudflare_token(self, mock_db):
        """Test validation fails without Cloudflare token."""
        mock_db.get_domain.return_value = {
            'id': 'dom1',
            'domain': 'example.com',
            'app_id': 'app1',
            'environment': 'production'
        }
        mock_db.get_application.return_value = {'id': 'app1', 'name': 'testapp'}
        
        action = ProvisionAction(domain_id='dom1')
        
        errors = action.validate()
        
        self.assertIn("CLOUDFLARE_API_TOKEN", errors[0])


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""
    
    @patch('actions.deploy.DeployAction')
    def test_deploy_application(self, mock_action_class):
        """Test deploy_application convenience function."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = ActionResult(success=True, message="OK")
        mock_action_class.return_value = mock_instance
        
        result = deploy_application('myapp', 'production', 'main')
        
        self.assertTrue(result.success)
        mock_action_class.assert_called_once_with(
            app_name='myapp',
            environment='production',
            branch='main',
            commit=None
        )
    
    @patch('actions.rollback.RollbackAction')
    def test_rollback_deployment(self, mock_action_class):
        """Test rollback_deployment convenience function."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = ActionResult(success=True, message="OK")
        mock_action_class.return_value = mock_instance
        
        result = rollback_deployment(deployment_id='dep1')
        
        self.assertTrue(result.success)
    
    @patch('actions.backup.BackupAction')
    def test_create_backup(self, mock_action_class):
        """Test create_backup convenience function."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = ActionResult(success=True, message="OK")
        mock_action_class.return_value = mock_instance
        
        result = create_backup('mydb', 'full')
        
        self.assertTrue(result.success)
    
    @patch('actions.provision.ProvisionAction')
    def test_provision_domain(self, mock_action_class):
        """Test provision_domain convenience function."""
        mock_instance = MagicMock()
        mock_instance.execute.return_value = ActionResult(success=True, message="OK")
        mock_action_class.return_value = mock_instance
        
        result = provision_domain(domain_id='dom1')
        
        self.assertTrue(result.success)


if __name__ == '__main__':
    unittest.main()