"""
Phase 2 API Endpoints for deployment enhancements.

Add these routes to dashboard/app.py to enable:
- Deployment hooks management
- Blue-green deployment
- Deployment scheduling
- Notification settings

Usage:
    # In app.py, add at the end:
    from api.phase2_routes import register_phase2_routes
    register_phase2_routes(app)
"""

from flask import request, jsonify
from datetime import datetime
import json

try:
    import database as db
    from services.bluegreen import BlueGreenDeploy
    from services.hooks import HookExecutor
    from services.notifications import NotificationService
    from tasks.scheduler import schedule_deployment, cancel_scheduled_deployment, get_upcoming_scheduled_deployments
    PHASE2_AVAILABLE = True
except ImportError:
    PHASE2_AVAILABLE = False


def register_phase2_routes(app):
    """Register Phase 2 API routes with the Flask app."""
    
    if not PHASE2_AVAILABLE:
        print("Warning: Phase 2 services not available, skipping route registration")
        return
    
    # ========================================================================
    # Deployment Hooks API
    # ========================================================================
    
    @app.route("/api/apps/<app_name>/hooks", methods=["GET"])
    def api_get_deployment_hooks(app_name):
        """Get all deployment hooks for an application."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        hooks = db.get_deployment_hooks(app['id'], enabled_only=False)
        return jsonify({"hooks": hooks})
    
    @app.route("/api/apps/<app_name>/hooks", methods=["POST"])
    def api_create_deployment_hook(app_name):
        """Create a new deployment hook."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        data = request.get_json() or {}
        
        hook_type = data.get('hook_type')
        command = data.get('command')
        
        if not hook_type or not command:
            return jsonify({"error": "hook_type and command are required"}), 400
        
        if hook_type not in ['pre_deploy', 'post_deploy', 'pre_rollback', 'post_rollback']:
            return jsonify({"error": "Invalid hook_type"}), 400
        
        hook_id = db.create_deployment_hook(
            app_id=app['id'],
            hook_type=hook_type,
            command=command,
            environment=data.get('environment'),
            timeout=data.get('timeout', 300),
            enabled=data.get('enabled', True)
        )
        
        return jsonify({
            "success": True,
            "hook_id": hook_id,
            "message": "Hook created successfully"
        }), 201
    
    @app.route("/api/apps/<app_name>/hooks/<hook_id>", methods=["GET"])
    def api_get_deployment_hook(app_name, hook_id):
        """Get a specific deployment hook."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        with db.get_db() as conn:
            row = conn.execute(
                'SELECT * FROM deployment_hooks WHERE id = ? AND app_id = ?',
                (hook_id, app['id'])
            ).fetchone()
            
            if not row:
                return jsonify({"error": "Hook not found"}), 404
            
            return jsonify({"hook": dict(row)})
    
    @app.route("/api/apps/<app_name>/hooks/<hook_id>", methods=["PUT"])
    def api_update_deployment_hook(app_name, hook_id):
        """Update a deployment hook."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        data = request.get_json() or {}
        
        success = db.update_deployment_hook(hook_id, data)
        
        if success:
            return jsonify({"success": True, "message": "Hook updated"})
        else:
            return jsonify({"error": "Failed to update hook"}), 400
    
    @app.route("/api/apps/<app_name>/hooks/<hook_id>", methods=["DELETE"])
    def api_delete_deployment_hook(app_name, hook_id):
        """Delete a deployment hook."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        success = db.delete_deployment_hook(hook_id)
        
        if success:
            return jsonify({"success": True, "message": "Hook deleted"})
        else:
            return jsonify({"error": "Failed to delete hook"}), 400
    
    @app.route("/api/apps/<app_name>/hooks/<hook_id>/executions", methods=["GET"])
    def api_get_hook_executions(app_name, hook_id):
        """Get execution history for a hook."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        limit = request.args.get('limit', 50, type=int)
        executions = db.get_hook_executions(hook_id=hook_id, limit=limit)
        
        return jsonify({"executions": executions})
    
    # ========================================================================
    # Blue-Green Deployment API
    # ========================================================================
    
    @app.route("/api/apps/<app_name>/blue-green/status", methods=["GET"])
    def api_bluegreen_status(app_name):
        """Get blue-green deployment status for an application."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        environment = request.args.get('environment', 'production')
        
        status = BlueGreenDeploy.get_status(app_name, environment)
        
        return jsonify(status)
    
    @app.route("/api/apps/<app_name>/blue-green/switch", methods=["POST"])
    def api_bluegreen_switch(app_name):
        """Switch traffic to the other slot."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        data = request.get_json() or {}
        environment = data.get('environment', 'production')
        target_slot = data.get('target_slot')
        
        result = BlueGreenDeploy.switch_traffic(app_name, environment, target_slot)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @app.route("/api/apps/<app_name>/blue-green/rollback", methods=["POST"])
    def api_bluegreen_rollback(app_name):
        """Rollback to the previous slot."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        data = request.get_json() or {}
        environment = data.get('environment', 'production')
        
        result = BlueGreenDeploy.rollback_slot(app_name, environment)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    # ========================================================================
    # Deployment Scheduling API
    # ========================================================================
    
    @app.route("/api/apps/<app_name>/deploy-schedule", methods=["POST"])
    def api_schedule_deployment(app_name):
        """Schedule a deployment for future execution."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        data = request.get_json() or {}
        
        environment = data.get('environment', 'production')
        branch = data.get('branch', app.get('production_branch', 'main'))
        scheduled_at = data.get('scheduled_at')
        commit = data.get('commit')
        
        if not scheduled_at:
            return jsonify({"error": "scheduled_at is required"}), 400
        
        # Parse scheduled_at
        try:
            if isinstance(scheduled_at, str):
                scheduled_dt = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            else:
                return jsonify({"error": "Invalid scheduled_at format"}), 400
        except ValueError:
            return jsonify({"error": "Invalid scheduled_at format, use ISO 8601"}), 400
        
        # Schedule the deployment
        result = schedule_deployment(
            app_id=app['id'],
            environment=environment,
            branch=branch,
            scheduled_at=scheduled_dt,
            commit=commit
        )
        
        if result['success']:
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    
    @app.route("/api/apps/<app_name>/deploy-schedule", methods=["GET"])
    def api_get_scheduled_deployments(app_name):
        """Get scheduled deployments for an application."""
        app = db.get_application(name=app_name)
        if not app:
            return jsonify({"error": "Application not found"}), 404
        
        with db.get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM deployments 
                WHERE app_id = ? AND status = 'scheduled'
                ORDER BY scheduled_at ASC
            ''', (app['id'],)).fetchall()
            
            return jsonify({
                "scheduled_deployments": [dict(row) for row in rows]
            })
    
    @app.route("/api/deployments/<deployment_id>/cancel-schedule", methods=["POST"])
    def api_cancel_scheduled_deployment(deployment_id):
        """Cancel a scheduled deployment."""
        result = cancel_scheduled_deployment(deployment_id)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @app.route("/api/deployments/scheduled", methods=["GET"])
    def api_list_all_scheduled_deployments():
        """List all scheduled deployments."""
        hours = request.args.get('hours', 24, type=int)
        deployments = get_upcoming_scheduled_deployments(hours=hours)
        
        return jsonify({
            "scheduled_deployments": deployments
        })
    
    # ========================================================================
    # Notification Settings API
    # ========================================================================
    
    @app.route("/api/settings/notifications", methods=["GET"])
    def api_get_notification_settings():
        """Get notification settings."""
        settings = {
            'enabled': db.get_setting('notification_enabled', default=True),
            'slack_webhook': db.get_setting('notification_slack_webhook', default=''),
            'email': db.get_setting('notification_email', default=''),
            'webhook': db.get_setting('notification_webhook', default=''),
            'smtp_host': db.get_setting('notification_smtp_host', default='localhost'),
            'smtp_port': db.get_setting('notification_smtp_port', default=25),
            'smtp_user': db.get_setting('notification_smtp_user', default=''),
            'smtp_from': db.get_setting('notification_smtp_from', default='noreply@quantyra.io'),
        }
        
        return jsonify(settings)
    
    @app.route("/api/settings/notifications", methods=["POST"])
    def api_update_notification_settings():
        """Update notification settings."""
        data = request.get_json() or {}
        
        # Update each setting
        if 'enabled' in data:
            db.set_setting('notification_enabled', str(data['enabled']).lower())
        if 'slack_webhook' in data:
            db.set_setting('notification_slack_webhook', data['slack_webhook'])
        if 'email' in data:
            db.set_setting('notification_email', data['email'])
        if 'webhook' in data:
            db.set_setting('notification_webhook', data['webhook'])
        if 'smtp_host' in data:
            db.set_setting('notification_smtp_host', data['smtp_host'])
        if 'smtp_port' in data:
            db.set_setting('notification_smtp_port', str(data['smtp_port']))
        if 'smtp_user' in data:
            db.set_setting('notification_smtp_user', data['smtp_user'])
        if 'smtp_pass' in data:
            # Encrypt the password before storing
            from database import encrypt_value
            db.set_setting('notification_smtp_pass', encrypt_value(data['smtp_pass']))
        if 'smtp_from' in data:
            db.set_setting('notification_smtp_from', data['smtp_from'])
        
        return jsonify({
            "success": True,
            "message": "Notification settings updated"
        })
    
    @app.route("/api/settings/notifications/test", methods=["POST"])
    def api_test_notification():
        """Test notification settings by sending a test notification."""
        data = request.get_json() or {}
        channel = data.get('channel', 'slack')
        
        test_message = {
            'title': '🧪 Test Notification',
            'app_name': 'test-app',
            'environment': 'production',
            'branch': 'main',
            'status': 'success',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if channel == 'slack':
            webhook_url = db.get_setting('notification_slack_webhook', default='')
            if not webhook_url:
                return jsonify({"error": "Slack webhook not configured"}), 400
            result = NotificationService.send_slack_notification(webhook_url, test_message)
        
        elif channel == 'email':
            email_to = db.get_setting('notification_email', default='')
            if not email_to:
                return jsonify({"error": "Email not configured"}), 400
            result = NotificationService.send_email_notification(
                email_to,
                '[PaaS] Test Notification',
                'This is a test notification from Quantyra PaaS.',
                '<h1>Test Notification</h1><p>This is a test notification from Quantyra PaaS.</p>'
            )
        
        elif channel == 'webhook':
            webhook_url = db.get_setting('notification_webhook', default='')
            if not webhook_url:
                return jsonify({"error": "Webhook not configured"}), 400
            result = NotificationService.send_webhook_notification(webhook_url, test_message)
        
        else:
            return jsonify({"error": "Invalid channel. Use 'slack', 'email', or 'webhook'"}), 400
        
        if result['success']:
            return jsonify({"success": True, "message": f"Test notification sent via {channel}"})
        else:
            return jsonify({"error": result.get('error', 'Failed to send notification')}), 400
    
    print("✅ Phase 2 API routes registered")