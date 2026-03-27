"""
API routes for add-on services management.

Phase 3 endpoints for:
- Service templates listing
- Service CRUD operations
- Service lifecycle management (start/stop/restart)
- Service backup
"""

from flask import Blueprint, request, jsonify, g

try:
    from services import (
        list_service_templates,
        get_services_by_category,
        get_service_manager,
        ServiceManager
    )
    SERVICES_AVAILABLE = True
except ImportError:
    SERVICES_AVAILABLE = False

try:
    import database as paas_db
    PAAS_DB_AVAILABLE = True
except ImportError:
    PAAS_DB_AVAILABLE = False

# Create blueprint
services_bp = Blueprint('services', __name__, url_prefix='/api')


# =============================================================================
# Service Templates
# =============================================================================

@services_bp.route('/services/templates', methods=['GET'])
def api_service_templates():
    """
    List available service templates.
    
    Returns:
        JSON with list of available service templates
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    templates = list_service_templates()
    
    return jsonify({
        'success': True,
        'templates': templates
    })


@services_bp.route('/services/templates/categories', methods=['GET'])
def api_service_categories():
    """
    List services grouped by category.
    
    Returns:
        JSON with services grouped by category
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    categories = get_services_by_category()
    
    return jsonify({
        'success': True,
        'categories': categories
    })


# =============================================================================
# Application Services CRUD
# =============================================================================

@services_bp.route('/apps/<app_name>/services', methods=['GET', 'POST'])
def api_app_services(app_name):
    """
    List or create services for an application.
    
    GET: List all services for an app
    POST: Create a new service
    
    POST body:
        {
            "type": "redis",
            "environment": "production",
            "config": {
                "memory_limit": "512M",
                "cpu_limit": 1.0
            }
        }
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    
    if request.method == 'POST':
        data = request.json or {}
        
        service_type = data.get('type')
        environment = data.get('environment', 'production')
        custom_config = data.get('config')
        
        if not service_type:
            return jsonify({'success': False, 'error': 'Service type required'}), 400
        
        result = manager.create_service(
            app_name=app_name,
            service_type=service_type,
            environment=environment,
            custom_config=custom_config
        )
        
        status_code = 201 if result.get('success') else 400
        return jsonify(result), status_code
    
    # GET - list services
    environment = request.args.get('environment')
    services = manager.get_services_for_app(app_name, environment)
    
    return jsonify({
        'success': True,
        'app_name': app_name,
        'services': services
    })


@services_bp.route('/services/<service_id>', methods=['GET', 'DELETE'])
def api_service(service_id):
    """
    Get or delete a service.
    
    GET: Get service details
    DELETE: Delete a service
        
    Query params (DELETE):
        - remove_data: bool - Whether to remove data volumes
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    
    if request.method == 'DELETE':
        remove_data = request.args.get('remove_data', 'false').lower() == 'true'
        result = manager.delete_service(service_id, remove_data=remove_data)
        
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code
    
    # GET
    service = manager.get_service(service_id)
    
    if not service:
        return jsonify({'success': False, 'error': 'Service not found'}), 404
    
    return jsonify({
        'success': True,
        'service': service
    })


# =============================================================================
# Service Lifecycle
# =============================================================================

@services_bp.route('/services/<service_id>/start', methods=['POST'])
def api_service_start(service_id):
    """
    Start a stopped service.
    
    Returns:
        JSON with success status
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    result = manager.start_service(service_id)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@services_bp.route('/services/<service_id>/stop', methods=['POST'])
def api_service_stop(service_id):
    """
    Stop a running service.
    
    Returns:
        JSON with success status
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    result = manager.stop_service(service_id)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@services_bp.route('/services/<service_id>/restart', methods=['POST'])
def api_service_restart(service_id):
    """
    Restart a service.
    
    Returns:
        JSON with success status
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    result = manager.restart_service(service_id)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


# =============================================================================
# Service Backup
# =============================================================================

@services_bp.route('/services/<service_id>/backup', methods=['POST'])
def api_service_backup(service_id):
    """
    Backup a service.
    
    Returns:
        JSON with backup details
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    result = manager.backup_service(service_id)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@services_bp.route('/services/<service_id>/backups', methods=['GET'])
def api_service_backups(service_id):
    """
    Get backup history for a service.
    
    Returns:
        JSON with list of backups
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    limit = request.args.get('limit', 10, type=int)
    backups = paas_db.get_service_backups(service_id, limit)
    
    return jsonify({
        'success': True,
        'service_id': service_id,
        'backups': backups
    })


# =============================================================================
# Service Logs & Metrics
# =============================================================================

@services_bp.route('/services/<service_id>/logs', methods=['GET'])
def api_service_logs(service_id):
    """
    Get service logs.
    
    Query params:
        - lines: int - Number of lines to retrieve (default: 100)
    
    Returns:
        JSON with logs
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    lines = request.args.get('lines', 100, type=int)
    result = manager.get_service_logs(service_id, lines)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


@services_bp.route('/services/<service_id>/metrics', methods=['GET'])
def api_service_metrics(service_id):
    """
    Get service resource metrics.
    
    Returns:
        JSON with CPU, memory, network metrics
    """
    if not SERVICES_AVAILABLE:
        return jsonify({'success': False, 'error': 'Services module not available'}), 500
    
    manager = get_service_manager()
    result = manager.get_service_metrics(service_id)
    
    status_code = 200 if result.get('success') else 400
    return jsonify(result), status_code


# =============================================================================
# All Services
# =============================================================================

@services_bp.route('/services', methods=['GET'])
def api_all_services():
    """
    List all services across all applications.
    
    Query params:
        - type: Filter by service type
        - environment: Filter by environment
    
    Returns:
        JSON with list of all services
    """
    if not PAAS_DB_AVAILABLE:
        return jsonify({'success': False, 'error': 'Database not available'}), 500
    
    service_type = request.args.get('type')
    environment = request.args.get('environment')
    
    if service_type:
        services = paas_db.get_services_by_type(service_type)
    else:
        services = paas_db.get_all_services()
    
    # Filter by environment if specified
    if environment:
        services = [s for s in services if s.get('environment') == environment]
    
    # Decrypt credentials for each service
    for service in services:
        if service.get('credentials_encrypted'):
            try:
                import json
                service['credentials'] = json.loads(
                    paas_db.decrypt_value(service['credentials_encrypted'])
                )
            except Exception:
                service['credentials'] = {}
        
        if service.get('volumes_json'):
            try:
                service['volumes'] = json.loads(service['volumes_json'])
            except Exception:
                service['volumes'] = []
    
    return jsonify({
        'success': True,
        'services': services
    })


def register_services_routes(app):
    """
    Register services blueprint with the Flask app.
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(services_bp)