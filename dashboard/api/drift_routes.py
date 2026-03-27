"""
API routes for drift detection.

Endpoints:
- GET /api/drift/results - Get current drift results
- POST /api/drift/check - Run drift check
- GET /api/drift/history - Get drift history
- GET /api/drift/trend - Get drift trend
- GET /api/drift/summary - Get drift summary
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Blueprint, jsonify, request

from services.drift.reporter import DriftReporter
from services.drift.detector import DriftDetector, check_drift_for_server
import database as db


drift_bp = Blueprint('drift', __name__, url_prefix='/api/drift')


@drift_bp.route('/check', methods=['POST'])
def api_drift_check():
    """
    Run drift detection check.
    
    Query params:
    - server: Specific server name (optional)
    
    Returns:
        JSON with check results
    """
    try:
        server_name = request.args.get('server')
        
        if server_name:
            # Check specific server
            results = check_drift_for_server(server_name)
            return jsonify({
                'success': True,
                'server': server_name,
                'drifts': [r.to_dict() for r in results],
                'count': len(results),
                'checked_at': datetime.utcnow().isoformat()
            })
        else:
            # Check all servers
            reporter = DriftReporter()
            report = reporter.check_all_servers()
            
            return jsonify({
                'success': True,
                'report': report
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/results', methods=['GET'])
def api_drift_results():
    """
    Get current drift results.
    
    Query params:
    - server: Filter by server name (optional)
    - service: Filter by service name (optional)
    - severity: Filter by severity (optional)
    
    Returns:
        JSON with current drift results
    """
    try:
        server = request.args.get('server')
        service = request.args.get('service')
        severity = request.args.get('severity')
        
        reporter = DriftReporter()
        
        if server:
            results = reporter.get_drift_by_server(server)
        elif service:
            results = reporter.get_drift_by_service(service)
        else:
            results = reporter.get_current_drifts()
        
        # Filter by severity if specified
        if severity:
            results = [r for r in results if r['severity'] == severity]
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/history', methods=['GET'])
def api_drift_history():
    """
    Get drift history.
    
    Query params:
    - days: Number of days to look back (default: 7)
    
    Returns:
        JSON with historical drift checks
    """
    try:
        days = int(request.args.get('days', 7))
        
        reporter = DriftReporter()
        history = reporter.get_drift_history(days)
        
        return jsonify({
            'success': True,
            'history': history,
            'count': len(history)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/trend', methods=['GET'])
def api_drift_trend():
    """
    Get drift trend over time.
    
    Query params:
    - days: Number of days to analyze (default: 30)
    
    Returns:
        JSON with trend data
    """
    try:
        days = int(request.args.get('days', 30))
        
        reporter = DriftReporter()
        trend = reporter.get_drift_trend(days)
        
        return jsonify({
            'success': True,
            'trend': trend
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/summary', methods=['GET'])
def api_drift_summary():
    """
    Get drift summary.
    
    Returns:
        JSON with summary statistics
    """
    try:
        reporter = DriftReporter()
        summary = reporter.get_drift_summary()
        
        return jsonify({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/clear', methods=['POST'])
def api_drift_clear():
    """
    Clear current drift results.
    
    This is typically done after resolving drifts.
    
    Returns:
        JSON with result
    """
    try:
        reporter = DriftReporter()
        cleared = reporter.clear_resolved_drifts()
        
        return jsonify({
            'success': True,
            'cleared': cleared,
            'message': f'Cleared {cleared} drift records'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@drift_bp.route('/config/<server_name>/<service>', methods=['GET'])
def api_get_expected_config(server_name, service):
    """
    Get expected configuration for a server and service.
    
    Args:
        server_name: Server name
        service: Service name
        
    Returns:
        JSON with expected configuration
    """
    try:
        from services.drift.configurations import get_expected_config
        
        config = get_expected_config(server_name, service)
        
        if not config:
            return jsonify({
                'success': False,
                'error': f'No configuration found for {server_name}/{service}'
            }), 404
        
        return jsonify({
            'success': True,
            'server': server_name,
            'service': service,
            'config': config
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def register_drift_routes(app):
    """Register drift routes with the Flask app."""
    app.register_blueprint(drift_bp)
    
    # Add drift dashboard page route
    @app.route('/drift')
    def drift_dashboard():
        """Drift detection dashboard."""
        from flask import render_template
        return render_template('drift.html')