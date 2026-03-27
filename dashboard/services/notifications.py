"""
Deployment notification service.

Sends notifications via multiple channels:
- Slack webhooks
- Email (SMTP)
- Generic webhooks

Configuration is stored in database settings.
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional, List

import requests

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


class NotificationService:
    """
    Send deployment notifications via multiple channels.
    
    Configuration stored in database settings:
    - notification_slack_webhook: Slack webhook URL
    - notification_email: Email address for notifications
    - notification_webhook: Generic webhook URL
    - notification_smtp_host: SMTP server host
    - notification_smtp_port: SMTP server port
    - notification_smtp_user: SMTP username
    - notification_smtp_pass: SMTP password (encrypted)
    - notification_smtp_from: From email address
    - notification_enabled: Master enable/disable flag
    """
    
    # Emoji for different statuses
    STATUS_EMOJI = {
        'started': '🚀',
        'success': '✅',
        'failed': '❌',
        'rollback': '↩️',
        'scheduled': '⏰'
    }
    
    # Colors for Slack attachments
    STATUS_COLORS = {
        'started': '#36a64f',  # Green
        'success': '#36a64f',  # Green
        'failed': '#dc3545',   # Red
        'rollback': '#ffc107', # Yellow
        'scheduled': '#17a2b8' # Blue
    }
    
    @classmethod
    def notify_deployment_start(cls, app_name: str, environment: str, 
                                branch: str, commit: str = None,
                                deployment_id: str = None,
                                scheduled: bool = False) -> Dict[str, Any]:
        """
        Notify that a deployment has started.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            branch: Git branch being deployed
            commit: Commit hash (optional)
            deployment_id: Deployment ID
            scheduled: Whether this is a scheduled deployment
            
        Returns:
            Dict with notification results
        """
        status = 'scheduled' if scheduled else 'started'
        
        message = cls._build_deployment_message(
            app_name=app_name,
            environment=environment,
            branch=branch,
            commit=commit,
            deployment_id=deployment_id,
            status=status,
            title=f"{cls.STATUS_EMOJI[status]} Deployment {status.title()}"
        )
        
        return cls._send_notifications(message, 'deployment_start')
    
    @classmethod
    def notify_deployment_success(cls, app_name: str, environment: str,
                                  branch: str, commit: str = None,
                                  deployment_id: str = None,
                                  duration: int = None,
                                  slots: Dict = None) -> Dict[str, Any]:
        """
        Notify that a deployment succeeded.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            branch: Git branch deployed
            commit: Commit hash (optional)
            deployment_id: Deployment ID
            duration: Duration in seconds
            slots: Blue-green slot info (optional)
            
        Returns:
            Dict with notification results
        """
        title = f"{cls.STATUS_EMOJI['success']} Deployment Successful"
        
        message = cls._build_deployment_message(
            app_name=app_name,
            environment=environment,
            branch=branch,
            commit=commit,
            deployment_id=deployment_id,
            status='success',
            duration=duration,
            slots=slots,
            title=title
        )
        
        return cls._send_notifications(message, 'deployment_success')
    
    @classmethod
    def notify_deployment_failed(cls, app_name: str, environment: str,
                                 branch: str, error: str,
                                 commit: str = None,
                                 deployment_id: str = None,
                                 rollback_recommended: bool = False) -> Dict[str, Any]:
        """
        Notify that a deployment failed.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            branch: Git branch
            error: Error message
            commit: Commit hash (optional)
            deployment_id: Deployment ID
            rollback_recommended: Whether rollback is recommended
            
        Returns:
            Dict with notification results
        """
        title = f"{cls.STATUS_EMOJI['failed']} Deployment Failed"
        
        message = cls._build_deployment_message(
            app_name=app_name,
            environment=environment,
            branch=branch,
            commit=commit,
            deployment_id=deployment_id,
            status='failed',
            error=error,
            rollback_recommended=rollback_recommended,
            title=title
        )
        
        return cls._send_notifications(message, 'deployment_failed')
    
    @classmethod
    def notify_rollback(cls, app_name: str, environment: str,
                        previous_commit: str = None,
                        new_commit: str = None,
                        reason: str = None) -> Dict[str, Any]:
        """
        Notify that a rollback occurred.
        
        Args:
            app_name: Application name
            environment: 'production' or 'staging'
            previous_commit: Commit rolled back from
            new_commit: Commit rolled back to
            reason: Reason for rollback
            
        Returns:
            Dict with notification results
        """
        title = f"{cls.STATUS_EMOJI['rollback']} Deployment Rolled Back"
        
        message = {
            'title': title,
            'app_name': app_name,
            'environment': environment,
            'previous_commit': previous_commit,
            'new_commit': new_commit,
            'reason': reason,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return cls._send_notifications(message, 'deployment_rollback')
    
    @classmethod
    def send_slack_notification(cls, webhook_url: str, message: Dict) -> Dict[str, Any]:
        """
        Send notification to Slack.
        
        Args:
            webhook_url: Slack webhook URL
            message: Message dict with 'title', 'app_name', etc.
            
        Returns:
            Dict with 'success' and any error
        """
        if not webhook_url:
            return {'success': False, 'error': 'No webhook URL configured'}
        
        try:
            # Build Slack message format
            status = message.get('status', 'started')
            color = cls.STATUS_COLORS.get(status, '#808080')
            
            slack_payload = {
                'attachments': [{
                    'color': color,
                    'title': message.get('title', 'Deployment Notification'),
                    'fields': [],
                    'footer': 'Quantyra PaaS',
                    'ts': int(datetime.utcnow().timestamp())
                }]
            }
            
            # Add fields
            fields = [
                ('Application', message.get('app_name'), True),
                ('Environment', message.get('environment', 'production').title(), True),
                ('Branch', message.get('branch'), True),
            ]
            
            if message.get('commit'):
                fields.append(('Commit', message.get('commit')[:8], True))
            
            if message.get('duration'):
                duration_str = cls._format_duration(message['duration'])
                fields.append(('Duration', duration_str, True))
            
            if message.get('error'):
                fields.append(('Error', f"```{message['error'][:500]}```", False))
            
            if message.get('rollback_recommended'):
                fields.append(('Action', 'Rollback recommended', False))
            
            if message.get('slots'):
                slot_info = message['slots']
                fields.append(('Deployed to', slot_info.get('slot', 'unknown'), True))
            
            for name, value, short in fields:
                if value:
                    slack_payload['attachments'][0]['fields'].append({
                        'title': name,
                        'value': str(value),
                        'short': short
                    })
            
            response = requests.post(
                webhook_url,
                json=slack_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                return {'success': True}
            else:
                return {
                    'success': False,
                    'error': f'Slack returned {response.status_code}: {response.text}'
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def send_email_notification(cls, to: str, subject: str, 
                                body: str, html_body: str = None) -> Dict[str, Any]:
        """
        Send email notification via configured SMTP.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: HTML body (optional)
            
        Returns:
            Dict with 'success' and any error
        """
        if not to:
            return {'success': False, 'error': 'No email address configured'}
        
        # Get SMTP settings
        smtp_host = db.get_setting('notification_smtp_host', default='localhost')
        smtp_port = db.get_setting('notification_smtp_port', default=25)
        smtp_user = db.get_setting('notification_smtp_user', default='')
        smtp_pass = db.get_setting('notification_smtp_pass', default='')
        smtp_from = db.get_setting('notification_smtp_from', default='noreply@quantyra.io')
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = smtp_from
            msg['To'] = to
            
            msg.attach(MIMEText(body, 'plain'))
            
            if html_body:
                msg.attach(MIMEText(html_body, 'html'))
            
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                if smtp_user and smtp_pass:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                
                server.sendmail(smtp_from, [to], msg.as_string())
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def send_webhook_notification(cls, url: str, payload: Dict) -> Dict[str, Any]:
        """
        Send notification to a generic webhook.
        
        Args:
            url: Webhook URL
            payload: Payload to send
            
        Returns:
            Dict with 'success' and any error
        """
        if not url:
            return {'success': False, 'error': 'No webhook URL configured'}
        
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Quantyra-PaaS/1.0'
                },
                timeout=10
            )
            
            if 200 <= response.status_code < 300:
                return {'success': True, 'status_code': response.status_code}
            else:
                return {
                    'success': False,
                    'error': f'Webhook returned {response.status_code}',
                    'response': response.text[:500]
                }
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def _send_notifications(cls, message: Dict, event_type: str) -> Dict[str, Any]:
        """
        Send notifications to all configured channels.
        
        Args:
            message: Message dict
            event_type: Event type (deployment_start, etc.)
            
        Returns:
            Dict with results for each channel
        """
        # Check if notifications are enabled
        enabled = db.get_setting('notification_enabled', default=True)
        if not enabled:
            return {'success': True, 'message': 'Notifications disabled'}
        
        results = {
            'event_type': event_type,
            'channels': {}
        }
        
        # Slack
        slack_webhook = db.get_setting('notification_slack_webhook', default='')
        if slack_webhook:
            results['channels']['slack'] = cls.send_slack_notification(
                slack_webhook, message
            )
        
        # Email
        email_to = db.get_setting('notification_email', default='')
        if email_to:
            subject = f"[PaaS] {message.get('title', 'Deployment Notification')}"
            body = cls._build_email_body(message)
            html_body = cls._build_email_html(message)
            
            results['channels']['email'] = cls.send_email_notification(
                email_to, subject, body, html_body
            )
        
        # Generic webhook
        webhook_url = db.get_setting('notification_webhook', default='')
        if webhook_url:
            webhook_payload = {
                'event': event_type,
                'timestamp': datetime.utcnow().isoformat(),
                'data': message
            }
            
            results['channels']['webhook'] = cls.send_webhook_notification(
                webhook_url, webhook_payload
            )
        
        # Determine overall success
        results['success'] = all(
            r.get('success', False) for r in results['channels'].values()
        ) if results['channels'] else True
        
        return results
    
    @classmethod
    def _build_deployment_message(cls, **kwargs) -> Dict:
        """Build a deployment message dict."""
        message = {
            'timestamp': datetime.utcnow().isoformat()
        }
        message.update(kwargs)
        return message
    
    @classmethod
    def _format_duration(cls, seconds: int) -> str:
        """Format duration in human-readable format."""
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
        elif seconds >= 60:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m {secs}s"
        else:
            return f"{seconds}s"
    
    @classmethod
    def _build_email_body(cls, message: Dict) -> str:
        """Build plain text email body."""
        lines = [
            message.get('title', 'Deployment Notification'),
            '=' * 50,
            '',
            f"Application: {message.get('app_name', 'Unknown')}",
            f"Environment: {message.get('environment', 'production').title()}",
            f"Branch: {message.get('branch', 'Unknown')}",
        ]
        
        if message.get('commit'):
            lines.append(f"Commit: {message['commit']}")
        
        if message.get('duration'):
            lines.append(f"Duration: {cls._format_duration(message['duration'])}")
        
        if message.get('error'):
            lines.extend([
                '',
                'Error:',
                message['error']
            ])
        
        if message.get('rollback_recommended'):
            lines.append('')
            lines.append('⚠️ Rollback is recommended.')
        
        lines.extend([
            '',
            f"Timestamp: {message.get('timestamp', datetime.utcnow().isoformat())}",
            '',
            '--',
            'Quantyra PaaS'
        ])
        
        return '\n'.join(lines)
    
    @classmethod
    def _build_email_html(cls, message: Dict) -> str:
        """Build HTML email body."""
        status = message.get('status', 'started')
        color = cls.STATUS_COLORS.get(status, '#808080')
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background-color: {color}; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0;">{message.get('title', 'Deployment Notification')}</h1>
            </div>
            <div style="padding: 20px; border: 1px solid #ddd;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>Application:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">{message.get('app_name', 'Unknown')}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>Environment:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">{message.get('environment', 'production').title()}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>Branch:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">{message.get('branch', 'Unknown')}</td>
                    </tr>
        """
        
        if message.get('commit'):
            html += f"""
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>Commit:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><code>{message['commit'][:8]}</code></td>
                    </tr>
            """
        
        if message.get('duration'):
            html += f"""
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;"><strong>Duration:</strong></td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">{cls._format_duration(message['duration'])}</td>
                    </tr>
            """
        
        html += """
                </table>
        """
        
        if message.get('error'):
            html += f"""
                <div style="margin-top: 20px; padding: 15px; background-color: #f8d7da; border-radius: 5px;">
                    <strong>Error:</strong><br>
                    <pre style="margin: 10px 0 0 0; white-space: pre-wrap;">{message['error']}</pre>
                </div>
            """
        
        html += f"""
            </div>
            <div style="padding: 10px; text-align: center; color: #666; font-size: 12px;">
                Quantyra PaaS • {message.get('timestamp', datetime.utcnow().isoformat())}
            </div>
        </body>
        </html>
        """
        
return html
    
    @classmethod
    def send_alert(cls, alert_type: str, message: str, 
                   severity: str = 'warning', details: Dict = None) -> Dict[str, Any]:
        """
        Send a generic alert notification.
        
        Args:
            alert_type: Type of alert (ssl, disk, backup, service, etc.)
            message: Alert message content
            severity: Alert severity (info, warning, critical)
            details: Optional additional details
            
        Returns:
            Dict with notification results
        """
        severity_emoji = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'critical': '🚨',
            'error': '❌'
        }
        
        emoji = severity_emoji.get(severity, '⚠️')
        
        notification_message = {
            'title': f'{emoji} {alert_type.title()} Alert',
            'alert_type': alert_type,
            'severity': severity,
            'message': message,
            'details': details,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        return cls._send_notifications(notification_message, f'alert_{alert_type}')


# Convenience functions
def notify_deployment_start(app_name: str, environment: str, branch: str,
                            commit: str = None, deployment_id: str = None,
                            scheduled: bool = False) -> Dict[str, Any]:
    """Notify deployment started."""
    return NotificationService.notify_deployment_start(
        app_name=app_name,
        environment=environment,
        branch=branch,
        commit=commit,
        deployment_id=deployment_id,
        scheduled=scheduled
    )


def notify_deployment_success(app_name: str, environment: str, branch: str,
                              commit: str = None, deployment_id: str = None,
                              duration: int = None) -> Dict[str, Any]:
    """Notify deployment succeeded."""
    return NotificationService.notify_deployment_success(
        app_name=app_name,
        environment=environment,
        branch=branch,
        commit=commit,
        deployment_id=deployment_id,
        duration=duration
    )


def notify_deployment_failed(app_name: str, environment: str, branch: str,
                             error: str, commit: str = None,
                             deployment_id: str = None,
                             rollback_recommended: bool = False) -> Dict[str, Any]:
    """Notify deployment failed."""
    return NotificationService.notify_deployment_failed(
        app_name=app_name,
        environment=environment,
        branch=branch,
        error=error,
        commit=commit,
        deployment_id=deployment_id,
        rollback_recommended=rollback_recommended
    )


def notify_rollback(app_name: str, environment: str, previous_commit: str = None,
                    new_commit: str = None, reason: str = None) -> Dict[str, Any]:
    """Notify rollback occurred."""
    return NotificationService.notify_rollback(
        app_name=app_name,
        environment=environment,
        previous_commit=previous_commit,
        new_commit=new_commit,
        reason=reason
    )


def send_alert(alert_type: str, message: str, severity: str = 'warning',
               details: Dict = None) -> Dict[str, Any]:
    """
    Send a generic alert notification.
    
    Args:
        alert_type: Type of alert (ssl, disk, backup, service, etc.)
        message: Alert message content
        severity: Alert severity (info, warning, critical)
        details: Optional additional details
        
    Returns:
        Dict with notification results
    """
    return NotificationService.send_alert(
        alert_type=alert_type,
        message=message,
        severity=severity,
        details=details
    )