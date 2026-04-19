"""
Service templates for add-on services.

Each service template defines:
- Docker image
- Port configuration
- Environment variables
- Health check
- Volume mounts
- Backup strategy
"""

import secrets
import string
from typing import Dict, List, Optional, Any


SERVICE_TEMPLATES = {
    'meilisearch': {
        'name': 'Meilisearch',
        'description': 'Search engine for fast, relevant search',
        'docker_image': 'getmeili/meilisearch:latest',
        'port': 7700,
        'port_range': (7700, 7799),
        'environment': {
            'MEILI_MASTER_KEY': '{api_key}',
            'MEILI_ENV': 'production'
        },
        'volumes': [
            {'container': '/meili_data', 'host': '/var/lib/meilisearch/{app_name}'}
        ],
        'health_check': {
            'type': 'http',
            'endpoint': '/health',
            'expected_status': 200
        },
        'connection_template': 'http://{host}:{port}',
        'backup': {
            'command': None,  # Use dump API
            'path': '/var/lib/meilisearch/{app_name}/dumps'
        },
        'memory_limit': '512M',
        'cpu_limit': 1.0,
        'icon': '🔍',
        'category': 'search'
    },
    
    'minio': {
        'name': 'MinIO',
        'description': 'S3-compatible object storage',
        'docker_image': 'minio/minio:latest',
        'port': 9000,
        'console_port': 9001,
        'port_range': (9000, 9099),
        'command': 'server /data --console-address ":9001"',
        'environment': {
            'MINIO_ROOT_USER': '{access_key}',
            'MINIO_ROOT_PASSWORD': '{secret_key}'
        },
        'volumes': [
            {'container': '/data', 'host': '/var/lib/minio/{app_name}'}
        ],
        'health_check': {
            'type': 'http',
            'endpoint': '/minio/health/live',
            'expected_status': 200
        },
        'connection_template': 'http://{access_key}:{secret_key}@{host}:{port}',
        'backup': {
            'command': 'mc mirror local/{bucket} /backup/{bucket}',
            'path': '/var/lib/minio/{app_name}'
        },
        'memory_limit': '1G',
        'cpu_limit': 1.0,
        'icon': '🪣',
        'category': 'storage'
    },
    
    'rabbitmq': {
        'name': 'RabbitMQ',
        'description': 'Message broker for async processing',
        'docker_image': 'rabbitmq:3-management',
        'port': 5672,
        'management_port': 15672,
        'port_range': (5672, 5699),
        'environment': {
            'RABBITMQ_DEFAULT_USER': '{username}',
            'RABBITMQ_DEFAULT_PASS': '{password}'
        },
        'volumes': [
            {'container': '/var/lib/rabbitmq', 'host': '/var/lib/rabbitmq/{app_name}'}
        ],
        'health_check': {
            'type': 'http',
            'endpoint': '/api/overview',
            'port_offset': 10000,  # Management port = service port + 10000
            'expected_status': 200
        },
        'connection_template': 'amqp://{username}:{password}@{host}:{port}',
        'backup': {
            'command': 'rabbitmqctl export /backup/definitions.json',
            'path': '/var/lib/rabbitmq/{app_name}'
        },
        'memory_limit': '512M',
        'cpu_limit': 1.0,
        'icon': '🐰',
        'category': 'messaging'
    },
    
    'postgresql': {
        'name': 'PostgreSQL',
        'description': 'Additional PostgreSQL database',
        'docker_image': 'postgres:16-alpine',
        'port': 5432,
        'port_range': (5433, 5499),
        'environment': {
            'POSTGRES_DB': '{db_name}',
            'POSTGRES_USER': '{username}',
            'POSTGRES_PASSWORD': '{password}'
        },
        'volumes': [
            {'container': '/var/lib/postgresql/data', 'host': '/var/lib/postgresql/{app_name}'}
        ],
        'health_check': {
            'type': 'command',
            'command': 'pg_isready -U {username}',
            'expected': 'accepting connections'
        },
        'connection_template': 'postgresql://{username}:{password}@{host}:{port}/{db_name}',
        'backup': {
            'command': 'pg_dump -U {username} {db_name} | gzip > /backup/{db_name}.sql.gz',
            'path': '/var/lib/postgresql/{app_name}'
        },
        'memory_limit': '512M',
        'cpu_limit': 1.0,
        'icon': '🐘',
        'category': 'database'
    },
    
    'elasticsearch': {
        'name': 'Elasticsearch',
        'description': 'Search and analytics engine',
        'docker_image': 'docker.elastic.co/elasticsearch/elasticsearch:8.11.0',
        'port': 9200,
        'port_range': (9200, 9299),
        'environment': {
            'discovery.type': 'single-node',
            'xpack.security.enabled': 'false',
            'ES_JAVA_OPTS': '-Xms512m -Xmx512m'
        },
        'volumes': [
            {'container': '/usr/share/elasticsearch/data', 'host': '/var/lib/elasticsearch/{app_name}'}
        ],
        'health_check': {
            'type': 'http',
            'endpoint': '/_cluster/health',
            'expected_status': 200
        },
        'connection_template': 'http://{host}:{port}',
        'backup': {
            'command': None,  # Use snapshot API
            'path': '/var/lib/elasticsearch/{app_name}/snapshots'
        },
        'memory_limit': '1G',
        'cpu_limit': 2.0,
        'icon': '🔎',
        'category': 'search'
    },
    
    'mongodb': {
        'name': 'MongoDB',
        'description': 'NoSQL document database',
        'docker_image': 'mongo:7',
        'port': 27017,
        'port_range': (27017, 27099),
        'environment': {
            'MONGO_INITDB_ROOT_USERNAME': '{username}',
            'MONGO_INITDB_ROOT_PASSWORD': '{password}'
        },
        'volumes': [
            {'container': '/data/db', 'host': '/var/lib/mongodb/{app_name}'}
        ],
        'health_check': {
            'type': 'command',
            'command': 'mongosh --eval "db.adminCommand(\'ping\')"',
            'expected': 'ok'
        },
        'connection_template': 'mongodb://{username}:{password}@{host}:{port}',
        'backup': {
            'command': 'mongodump --archive=/backup/{db_name}.archive',
            'path': '/var/lib/mongodb/{app_name}'
        },
        'memory_limit': '512M',
        'cpu_limit': 1.0,
        'icon': '🍃',
        'category': 'database'
    },
    
    'valkey': {
        'name': 'Valkey',
        'description': 'Redis-compatible in-memory data store',
        'docker_image': 'valkey/valkey:7-alpine',
        'port': 6379,
        'port_range': (16379, 16499),
        'environment': {
            'VALKEY_PASSWORD': '{password}'
        },
        'volumes': [
            {'container': '/data', 'host': '/var/lib/valkey/{app_name}'}
        ],
        'health_check': {
            'type': 'command',
            'command': 'valkey-cli -a {password} ping',
            'expected': 'PONG'
        },
        'connection_template': 'redis://:{password}@{host}:{port}',
        'backup': {
            'command': 'valkey-cli -a {password} BGSAVE',
            'path': '/var/lib/valkey/{app_name}/dump.rdb'
        },
        'memory_limit': '256M',
        'cpu_limit': 0.5,
        'icon': '🗝️',
        'category': 'caching'
    }
}


def get_service_template(service_type: str) -> Optional[Dict[str, Any]]:
    """
    Get service template configuration.
    
    Args:
        service_type: Service type identifier (e.g., 'redis', 'meilisearch')
        
    Returns:
        Service template dict or None if not found
    """
    return SERVICE_TEMPLATES.get(service_type)


def list_service_templates() -> List[Dict[str, Any]]:
    """
    List all available service templates.
    
    Returns:
        List of service template summaries
    """
    return [
        {
            'type': key,
            'name': template['name'],
            'description': template['description'],
            'port': template['port'],
            'icon': template.get('icon', '📦'),
            'category': template.get('category', 'other'),
            'memory_limit': template.get('memory_limit', '256M'),
            'cpu_limit': template.get('cpu_limit', 0.5)
        }
        for key, template in SERVICE_TEMPLATES.items()
    ]


def get_services_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get services grouped by category.
    
    Returns:
        Dict mapping category to list of services
    """
    categories = {}
    for key, template in SERVICE_TEMPLATES.items():
        category = template.get('category', 'other')
        if category not in categories:
            categories[category] = []
        categories[category].append({
            'type': key,
            'name': template['name'],
            'description': template['description'],
            'icon': template.get('icon', '📦'),
            'memory_limit': template.get('memory_limit', '256M')
        })
    return categories


def generate_password(length: int = 32) -> str:
    """Generate a random password."""
    chars = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_api_key(length: int = 32) -> str:
    """Generate a random API key."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


def generate_service_config(service_type: str, app_name: str, environment: str) -> Optional[Dict[str, Any]]:
    """
    Generate service configuration with random credentials.
    
    Args:
        service_type: Service type identifier
        app_name: Application name
        environment: Environment name (production/staging)
        
    Returns:
        Service configuration dict or None if type not found
    """
    template = get_service_template(service_type)
    if not template:
        return None
    
    config = {
        'type': service_type,
        'app_name': app_name,
        'environment': environment,
        'docker_image': template['docker_image'],
        'port': None,  # Will be allocated
        'memory_limit': template.get('memory_limit', '256M'),
        'cpu_limit': template.get('cpu_limit', 0.5),
        'volumes': [],
        'environment_vars': {},
        'credentials': {},
        'health_check': template.get('health_check', {}),
        'backup': template.get('backup', {}),
        'icon': template.get('icon', '📦'),
        'category': template.get('category', 'other')
    }
    
    # Generate credentials based on service type
    if service_type == 'valkey':
        config['credentials']['password'] = generate_password()
    elif service_type == 'meilisearch':
        config['credentials']['api_key'] = generate_api_key()
    elif service_type == 'minio':
        config['credentials']['access_key'] = generate_api_key(20)
        config['credentials']['secret_key'] = generate_password(40)
    elif service_type == 'rabbitmq':
        config['credentials']['username'] = 'admin'
        config['credentials']['password'] = generate_password()
    elif service_type == 'postgresql':
        safe_name = app_name.replace('-', '_').replace('.', '_')[:20]
        config['credentials']['db_name'] = f"{safe_name}_{environment}"
        config['credentials']['username'] = f"{safe_name}_user"
        config['credentials']['password'] = generate_password()
    elif service_type == 'mongodb':
        config['credentials']['username'] = 'admin'
        config['credentials']['password'] = generate_password()
    elif service_type == 'elasticsearch':
        # Elasticsearch doesn't require credentials in single-node mode
        pass
    
    # Process volumes
    for vol in template.get('volumes', []):
        host_path = vol['host'].format(
            app_name=app_name,
            environment=environment
        )
        config['volumes'].append({
            'container': vol['container'],
            'host': host_path
        })
    
    return config


def validate_service_config(service_type: str, custom_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a custom service configuration.
    
    Args:
        service_type: Service type identifier
        custom_config: Custom configuration overrides
        
    Returns:
        Dict with 'valid' boolean and optional 'errors' list
    """
    template = get_service_template(service_type)
    if not template:
        return {'valid': False, 'errors': [f'Unknown service type: {service_type}']}
    
    errors = []
    
    # Validate memory limit
    if 'memory_limit' in custom_config:
        mem = custom_config['memory_limit']
        if not isinstance(mem, str) or not mem.endswith(('M', 'G', 'K')):
            errors.append('memory_limit must be a string like "256M" or "1G"')
    
    # Validate CPU limit
    if 'cpu_limit' in custom_config:
        cpu = custom_config['cpu_limit']
        if not isinstance(cpu, (int, float)) or cpu <= 0:
            errors.append('cpu_limit must be a positive number')
    
    # Validate port (if manually specified)
    if 'port' in custom_config:
        port = custom_config['port']
        port_range = template.get('port_range', (0, 65535))
        if not isinstance(port, int) or not (port_range[0] <= port <= port_range[1]):
            errors.append(f'port must be between {port_range[0]} and {port_range[1]}')
    
    return {'valid': len(errors) == 0, 'errors': errors}


def get_connection_string(service_type: str, config: Dict[str, Any], host: str = 'localhost') -> str:
    """
    Generate connection string for a service.
    
    Args:
        service_type: Service type identifier
        config: Service configuration with credentials and port
        host: Host address
        
    Returns:
        Connection string
    """
    template = get_service_template(service_type)
    if not template:
        return ''
    
    conn_template = template.get('connection_template', '')
    if not conn_template:
        return ''
    
    port = config.get('port', template['port'])
    creds = config.get('credentials', {})
    
    # Replace placeholders
    conn = conn_template.replace('{host}', host)
    conn = conn.replace('{port}', str(port))
    
    for key, value in creds.items():
        conn = conn.replace('{' + key + '}', str(value))
    
    return conn


def get_environment_variables(service_type: str, config: Dict[str, Any]) -> Dict[str, str]:
    """
    Build environment variables from template and credentials.
    
    Args:
        service_type: Service type identifier
        config: Service configuration with credentials
        
    Returns:
        Dict of environment variable name to value
    """
    template = get_service_template(service_type)
    if not template:
        return {}
    
    env_vars = {}
    creds = config.get('credentials', {})
    
    for key, value in template.get('environment', {}).items():
        # Replace placeholders with credential values
        for cred_key, cred_value in creds.items():
            placeholder = '{' + cred_key + '}'
            if placeholder in value:
                value = value.replace(placeholder, str(cred_value))
        
        # Also replace app_name and environment
        value = value.replace('{app_name}', config.get('app_name', ''))
        value = value.replace('{environment}', config.get('environment', 'production'))
        
        env_vars[key] = value
    
    return env_vars