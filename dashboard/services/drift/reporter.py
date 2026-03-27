"""
Generate drift reports and alerts.

Collects drift results, stores history, and sends notifications.
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from services.drift.detector import DriftDetector, DriftResult
from services.notifications import NotificationService
import database as db


class DriftReporter:
    """
    Generate drift reports and handle alerting.
    
    Manages:
    - Drift detection execution
    - Result storage in database
    - Historical tracking
    - Alert notifications
    """
    
    def __init__(self):
        self.detector = DriftDetector()
    
    def check_all_servers(self) -> Dict[str, Any]:
        """
        Check all servers for drift and generate report.
        
        Returns:
            Dictionary with complete drift report
        """
        # Run detection
        results = self.detector.check_all_servers()
        
        # Store results
        self._store_results(results)
        
        # Store history
        self._store_history(results)
        
        # Send alerts if critical drift found
        if results['critical'] > 0:
            self._send_alert(results)
        
        return results
    
    def _store_results(self, results: Dict[str, Any]) -> None:
        """
        Store current drift results in database.
        
        Replaces previous results with current state.
        """
        with db.get_db() as conn:
            # Clear previous results
            conn.execute('DELETE FROM drift_results')
            
            # Insert new results
            for server, drifts in results.get('by_server', {}).items():
                for drift in drifts:
                    conn.execute('''
                        INSERT INTO drift_results 
                        (server, server_ip, service, config_key, expected, actual, 
                         severity, description, checked_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        drift['server'],
                        drift['server_ip'],
                        drift['service'],
                        drift['key'],
                        drift['expected'],
                        drift['actual'],
                        drift['severity'],
                        drift['description'],
                        drift['timestamp']
                    ))
            
            conn.commit()
    
    def _store_history(self, results: Dict[str, Any]) -> None:
        """
        Store drift check history.
        
        Maintains historical record for trend analysis.
        """
        with db.get_db() as conn:
            conn.execute('''
                INSERT INTO drift_history 
                (report_json, total_drifts, critical_count, warning_count, checked_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                json.dumps(results),
                results['total_drifts'],
                results['critical'],
                results['warning'],
                results['checked_at']
            ))
            conn.commit()
    
    def _send_alert(self, report: Dict[str, Any]) -> None:
        """
        Send drift alert notification.
        
        Args:
            report: Drift report dictionary
        """
        # Build alert message
        critical_items = []
        warning_items = []
        
        for server, drifts in report.get('by_server', {}).items():
            for drift in drifts:
                item = f"- {drift['service']}.{drift['key']}: {drift['actual']} (expected: {drift['expected']})"
                if drift['severity'] == 'critical':
                    critical_items.append(f"{server}: {item}")
                else:
                    warning_items.append(f"{server}: {item}")
        
        message = f"""
⚠️ Configuration Drift Detected

Critical drifts: {report['critical']}
Warning drifts: {report['warning']}

Servers affected: {len(report['by_server'])}

"""
        
        if critical_items:
            message += "Critical Issues:\n" + "\n".join(critical_items[:5]) + "\n\n"
        
        if warning_items:
            message += "Warnings:\n" + "\n".join(warning_items[:5]) + "\n\n"
        
        message += "Check the dashboard for full details."
        
        # Send notification
        try:
            # Store as setting for dashboard display
            db.set_setting('last_drift_alert', {
                'message': message,
                'critical': report['critical'],
                'warning': report['warning'],
                'checked_at': report['checked_at']
            })
            
            # Send via notification service
            NotificationService.send_webhook_notification(
                db.get_setting('notification_webhook', default=''),
                {
                    'event': 'drift_detected',
                    'timestamp': datetime.utcnow().isoformat(),
                    'data': {
                        'critical': report['critical'],
                        'warning': report['warning'],
                        'servers': list(report.get('by_server', {}).keys()),
                        'message': message
                    }
                }
            )
        except Exception as e:
            print(f"Failed to send drift alert: {e}")
    
    def get_current_drifts(self) -> List[Dict[str, Any]]:
        """
        Get current drift results from database.
        
        Returns:
            List of current drift records
        """
        with db.get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM drift_results 
                ORDER BY severity, server, service
            ''').fetchall()
            
            return [dict(row) for row in rows]
    
    def get_drift_by_server(self, server_name: str) -> List[Dict[str, Any]]:
        """
        Get drifts for a specific server.
        
        Args:
            server_name: Server name
            
        Returns:
            List of drift records for the server
        """
        with db.get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM drift_results 
                WHERE server = ?
                ORDER BY severity, service
            ''', (server_name,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_drift_by_service(self, service: str) -> List[Dict[str, Any]]:
        """
        Get drifts for a specific service.
        
        Args:
            service: Service name
            
        Returns:
            List of drift records for the service
        """
        with db.get_db() as conn:
            rows = conn.execute('''
                SELECT * FROM drift_results 
                WHERE service = ?
                ORDER BY severity, server
            ''', (service,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_drift_history(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get drift history for the past N days.
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of historical drift check records
        """
        with db.get_db() as conn:
            rows = conn.execute('''
                SELECT id, total_drifts, critical_count, warning_count, checked_at
                FROM drift_history
                WHERE checked_at >= datetime('now', ?)
                ORDER BY checked_at DESC
            ''', (f'-{days} days',)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_drift_trend(self, days: int = 30) -> Dict[str, Any]:
        """
        Get drift trend over time.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dictionary with trend data
        """
        history = self.get_drift_history(days)
        
        if not history:
            return {
                'trend': 'unknown',
                'data': [],
                'summary': 'No historical data available'
            }
        
        # Calculate trend
        if len(history) >= 2:
            recent = history[:5]
            older = history[5:10] if len(history) > 5 else history
            
            recent_avg = sum(h['total_drifts'] for h in recent) / len(recent)
            older_avg = sum(h['total_drifts'] for h in older) / len(older) if older else recent_avg
            
            if recent_avg > older_avg * 1.2:
                trend = 'increasing'
            elif recent_avg < older_avg * 0.8:
                trend = 'decreasing'
            else:
                trend = 'stable'
        else:
            trend = 'insufficient_data'
        
        # Format data for charts
        data = [
            {
                'date': h['checked_at'][:10],  # YYYY-MM-DD
                'total': h['total_drifts'],
                'critical': h['critical_count'],
                'warning': h['warning_count']
            }
            for h in reversed(history)
        ]
        
        return {
            'trend': trend,
            'data': data,
            'summary': f"Drift is {trend}. {history[0]['total_drifts']} drifts in last check."
        }
    
    def get_drift_summary(self) -> Dict[str, Any]:
        """
        Get summary of current drift state.
        
        Returns:
            Dictionary with summary statistics
        """
        current = self.get_current_drifts()
        
        if not current:
            return {
                'has_drift': False,
                'total': 0,
                'critical': 0,
                'warning': 0,
                'info': 0,
                'servers': [],
                'services': []
            }
        
        servers = list(set(d['server'] for d in current))
        services = list(set(d['service'] for d in current))
        
        return {
            'has_drift': True,
            'total': len(current),
            'critical': sum(1 for d in current if d['severity'] == 'critical'),
            'warning': sum(1 for d in current if d['severity'] == 'warning'),
            'info': sum(1 for d in current if d['severity'] == 'info'),
            'servers': servers,
            'services': services,
            'last_checked': current[0]['checked_at'] if current else None
        }
    
    def clear_resolved_drifts(self) -> int:
        """
        Clear drift records that have been resolved.
        
        This is typically done after running remediation.
        
        Returns:
            Number of records cleared
        """
        with db.get_db() as conn:
            cursor = conn.execute('DELETE FROM drift_results')
            conn.commit()
            return cursor.rowcount


def check_and_report() -> Dict[str, Any]:
    """
    Convenience function to check and report drift.
    
    Returns:
        Drift report dictionary
    """
    reporter = DriftReporter()
    return reporter.check_all_servers()


def get_drift_summary() -> Dict[str, Any]:
    """
    Convenience function to get drift summary.
    
    Returns:
        Drift summary dictionary
    """
    reporter = DriftReporter()
    return reporter.get_drift_summary()