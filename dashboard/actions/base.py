"""
Base Action Class for PaaS Operations.

This module provides the foundation for all action classes with:
- Validation before execution
- Progress tracking
- Error handling
- Rollback support
- Pre/post execution hooks
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime
import traceback
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """
    Result of an action execution.
    
    Attributes:
        success: Whether the action succeeded
        message: Human-readable result message
        data: Optional data returned by the action
        error: Error message if action failed
        steps: List of step records during execution
        started_at: When the action started
        finished_at: When the action finished
        duration_seconds: Total execution time
    """
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    steps: List[Dict] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'message': self.message,
            'data': self.data,
            'error': self.error,
            'steps': self.steps,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'duration_seconds': self.duration_seconds
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict())


class BaseAction:
    """
    Base class for all actions with common patterns.
    
    Actions are the primary way to perform operations in the PaaS.
    They provide:
    - Validation before execution
    - Progress tracking with WebSocket updates
    - Structured error handling
    - Rollback support
    - Pre/post execution hooks
    
    Subclasses must implement:
    - _execute(): The main action logic
    
    Subclasses can override:
    - validate(): Return list of validation errors
    - pre_execute(): Called before execute(), return False to abort
    - post_execute(): Called after execute()
    - rollback(): Provide rollback logic
    
    Example:
        class MyAction(BaseAction):
            action_type = "my_action"
            
            def __init__(self, param: str):
                super().__init__()
                self.param = param
            
            def validate(self) -> List[str]:
                errors = []
                if not self.param:
                    errors.append("param is required")
                return errors
            
            def _execute(self) -> ActionResult:
                self.add_step("step1", "running", "Doing something")
                # ... do work ...
                self.add_step("step1", "success", "Done")
                
                return ActionResult(
                    success=True,
                    message="Action completed",
                    data={"result": "value"}
                )
    """
    
    action_type: str = "base"
    
    def __init__(self, deployment_id: str = None, emit_progress: bool = True):
        """
        Initialize the action.
        
        Args:
            deployment_id: Optional deployment ID for progress tracking
            emit_progress: Whether to emit WebSocket progress updates
        """
        self.deployment_id = deployment_id
        self.emit_progress = emit_progress
        self.steps: List[Dict] = []
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self._rollback_data: Dict[str, Any] = {}
    
    def validate(self) -> List[str]:
        """
        Validate action parameters before execution.
        
        Returns:
            List of validation error messages. Empty list = valid.
        
        Override this method to add custom validation.
        """
        return []
    
    def pre_execute(self) -> bool:
        """
        Called before execute(). Return False to abort.
        
        Override this method to add pre-execution logic like:
        - Creating database records
        - Acquiring locks
        - Checking prerequisites
        
        Returns:
            True to proceed with execution, False to abort.
        """
        self.started_at = datetime.utcnow()
        return True
    
    def post_execute(self, result: ActionResult) -> None:
        """
        Called after execute(), regardless of success/failure.
        
        Override this method to add post-execution logic like:
        - Updating database records
        - Sending notifications
        - Cleaning up resources
        
        Args:
            result: The action result
        """
        self.finished_at = datetime.utcnow()
        if self.started_at:
            result.started_at = self.started_at
            result.finished_at = self.finished_at
            result.duration_seconds = (self.finished_at - self.started_at).total_seconds()
        result.steps = self.steps
    
    def _execute(self) -> ActionResult:
        """
        Main action logic. Override this method in subclasses.
        
        Returns:
            ActionResult with success/failure status
        """
        raise NotImplementedError("Subclasses must implement _execute()")
    
    def execute(self) -> ActionResult:
        """
        Main execution method with error handling.
        
        This method:
        1. Validates parameters
        2. Calls pre_execute()
        3. Executes the action
        4. Handles exceptions
        5. Calls post_execute()
        
        Returns:
            ActionResult with execution outcome
        """
        # 1. Validate
        errors = self.validate()
        if errors:
            result = ActionResult(
                success=False,
                message="Validation failed",
                error="; ".join(errors)
            )
            self.post_execute(result)
            return result
        
        # 2. Pre-execute
        if not self.pre_execute():
            result = ActionResult(
                success=False,
                message="Pre-execution check failed"
            )
            self.post_execute(result)
            return result
        
        # 3. Execute
        try:
            result = self._execute()
        except Exception as e:
            logger.exception(f"Action {self.action_type} failed with exception")
            result = ActionResult(
                success=False,
                message=f"Action failed: {str(e)}",
                error=traceback.format_exc()
            )
        
        # 4. Post-execute
        self.post_execute(result)
        
        return result
    
    def add_step(self, name: str, status: str, output: str = None,
                 server: str = None, duration: float = None) -> Dict:
        """
        Track a step in the action.
        
        This method:
        - Records the step for history
        - Emits a progress update via WebSocket
        - Returns the step dictionary
        
        Args:
            name: Step name (e.g., 'git_fetch', 'install_deps')
            status: Step status ('running', 'success', 'failed', 'skipped')
            output: Optional output message
            server: Optional server name
            duration: Optional duration in seconds
            
        Returns:
            Step dictionary
        """
        step = {
            'name': name,
            'status': status,
            'output': output,
            'server': server,
            'duration': duration,
            'timestamp': datetime.utcnow().isoformat()
        }
        self.steps.append(step)
        
        # Emit progress update
        if self.emit_progress and self.deployment_id:
            self._emit_step_progress(step)
        
        logger.debug(f"Action {self.action_type} step {name}: {status}")
        
        return step
    
    def _emit_step_progress(self, step: Dict) -> None:
        """
        Emit a step progress update via WebSocket.
        
        Args:
            step: Step dictionary
        """
        try:
            from websocket import emit_progress
            emit_progress(self.deployment_id, 'action_step', {
                'action_type': self.action_type,
                'step': step
            })
        except ImportError:
            logger.warning("WebSocket module not available for progress emission")
        except Exception as e:
            logger.warning(f"Failed to emit progress: {e}")
    
    def store_rollback_data(self, key: str, value: Any) -> None:
        """
        Store data for rollback support.
        
        Call this during execution to save state that can be used
        by rollback() if the action needs to be rolled back.
        
        Args:
            key: Data key
            value: Data value (must be JSON-serializable)
        """
        self._rollback_data[key] = value
    
    def get_rollback_data(self, key: str, default: Any = None) -> Any:
        """
        Get stored rollback data.
        
        Args:
            key: Data key
            default: Default value if key not found
            
        Returns:
            Stored value or default
        """
        return self._rollback_data.get(key, default)
    
    def rollback(self) -> ActionResult:
        """
        Rollback the action.
        
        Override this method to provide rollback logic.
        The base implementation returns a message indicating
        no rollback is defined.
        
        Returns:
            ActionResult with rollback outcome
        """
        return ActionResult(
            success=True,
            message="No rollback defined for this action",
            steps=self.steps
        )
    
    def execute_with_rollback(self) -> ActionResult:
        """
        Execute the action and rollback on failure.
        
        This method:
        1. Executes the action
        2. If it fails, calls rollback()
        3. Returns the appropriate result
        
        Returns:
            ActionResult with execution outcome
        """
        result = self.execute()
        
        if not result.success:
            logger.info(f"Action {self.action_type} failed, attempting rollback")
            rollback_result = self.rollback()
            
            result.data = result.data or {}
            result.data['rollback'] = rollback_result.to_dict()
            result.message += f" (Rollback: {rollback_result.message})"
        
        return result


class ActionChain:
    """
    Execute multiple actions in sequence.
    
    If any action fails, the chain stops and returns failure.
    Optionally, can rollback all completed actions on failure.
    
    Example:
        chain = ActionChain(rollback_on_failure=True)
        chain.add(DeployAction('app1', 'production', 'main'))
        chain.add(DeployAction('app2', 'production', 'main'))
        
        result = chain.execute()
    """
    
    def __init__(self, rollback_on_failure: bool = False):
        """
        Initialize the action chain.
        
        Args:
            rollback_on_failure: If True, rollback all completed actions on failure
        """
        self.actions: List[BaseAction] = []
        self.rollback_on_failure = rollback_on_failure
        self.results: List[ActionResult] = []
    
    def add(self, action: BaseAction) -> 'ActionChain':
        """
        Add an action to the chain.
        
        Args:
            action: Action to add
            
        Returns:
            Self for chaining
        """
        self.actions.append(action)
        return self
    
    def execute(self) -> ActionResult:
        """
        Execute all actions in sequence.
        
        Returns:
            Combined ActionResult
        """
        self.results = []
        completed_actions = []
        
        for action in self.actions:
            result = action.execute()
            self.results.append(result)
            
            if result.success:
                completed_actions.append(action)
            else:
                # Action failed
                if self.rollback_on_failure:
                    # Rollback completed actions in reverse order
                    for rollback_action in reversed(completed_actions):
                        rollback_result = rollback_action.rollback()
                        result.data = result.data or {}
                        result.data.setdefault('rollbacks', []).append(
                            rollback_result.to_dict()
                        )
                
                # Return combined failure result
                return ActionResult(
                    success=False,
                    message=f"Action chain failed at {action.action_type}",
                    error=result.error,
                    data={
                        'results': [r.to_dict() for r in self.results],
                        'failed_action': action.action_type
                    },
                    steps=[s for r in self.results for s in r.steps]
                )
        
        # All actions succeeded
        return ActionResult(
            success=True,
            message=f"Action chain completed: {len(self.actions)} actions",
            data={
                'results': [r.to_dict() for r in self.results]
            },
            steps=[s for r in self.results for s in r.steps]
        )


class ParallelActionGroup:
    """
    Execute multiple actions in parallel.
    
    All actions are executed simultaneously. Results are collected
    and combined.
    
    Example:
        group = ParallelActionGroup()
        group.add(DeployAction('app1', 'production', 'main'))
        group.add(DeployAction('app2', 'production', 'main'))
        
        result = group.execute()
    """
    
    def __init__(self, stop_on_failure: bool = False):
        """
        Initialize the parallel action group.
        
        Args:
            stop_on_failure: Not applicable for parallel execution,
                           actions run simultaneously
        """
        self.actions: List[BaseAction] = []
        self.stop_on_failure = stop_on_failure
    
    def add(self, action: BaseAction) -> 'ParallelActionGroup':
        """
        Add an action to the group.
        
        Args:
            action: Action to add
            
        Returns:
            Self for chaining
        """
        self.actions.append(action)
        return self
    
    def execute(self) -> ActionResult:
        """
        Execute all actions in parallel.
        
        Returns:
            Combined ActionResult
        """
        import concurrent.futures
        
        results: List[ActionResult] = []
        errors: List[str] = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(self.actions)) as executor:
            future_to_action = {
                executor.submit(action.execute): action
                for action in self.actions
            }
            
            for future in concurrent.futures.as_completed(future_to_action):
                action = future_to_action[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    error_result = ActionResult(
                        success=False,
                        message=f"Action {action.action_type} raised exception",
                        error=str(e)
                    )
                    results.append(error_result)
                    errors.append(f"{action.action_type}: {str(e)}")
        
        # Combine results
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        
        return ActionResult(
            success=failure_count == 0,
            message=f"Parallel execution: {success_count} succeeded, {failure_count} failed",
            error="; ".join(errors) if errors else None,
            data={
                'results': [r.to_dict() for r in results],
                'success_count': success_count,
                'failure_count': failure_count
            },
            steps=[s for r in results for s in r.steps]
        )