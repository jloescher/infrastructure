"""
Expected configurations for each service type.

These define the baseline configuration that servers should maintain.
"""

from typing import Dict, Any

# Expected configurations by service type
EXPECTED_CONFIGURATIONS = {
    'postgresql': {
        'max_connections': 200,
        'shared_buffers': '256MB',
        'effective_cache_size': '768MB',
        'work_mem': '4MB',
        'maintenance_work_mem': '64MB',
        'checkpoint_completion_target': 0.9,
        'wal_buffers': '16MB',
        'default_statistics_target': 100,
        'random_page_cost': 1.1,
        'effective_io_concurrency': 200,
    },
    'haproxy': {
        'maxconn': 4096,
        'timeout_connect': '5s',
        'timeout_client': '50s',
        'timeout_server': '50s',
    },
    'system': {
        'vm.swappiness': 10,
        'vm.dirty_ratio': 15,
        'vm.dirty_background_ratio': 5,
        'net.core.somaxconn': 65535,
        'net.ipv4.tcp_max_syn_backlog': 65535,
    }
}

# Server-specific overrides based on role and capacity
SERVER_CONFIG_OVERRIDES = {
    're-db': {
        'system': {
            'vm.swappiness': 5,  # Less swapping for database server
        }
    },
    're-node-02': {},
    'router-01': {
        'haproxy': {
            'maxconn': 8192,
        },
        'system': {
            'net.core.somaxconn': 131072,
            'net.ipv4.tcp_max_syn_backlog': 131072,
        }
    },
    'router-02': {
        'haproxy': {
            'maxconn': 8192,
        },
        'system': {
            'net.core.somaxconn': 131072,
            'net.ipv4.tcp_max_syn_backlog': 131072,
        }
    },
    're-node-01': {
        'postgresql': {
            'max_connections': 300,
            'shared_buffers': '512MB',
            'effective_cache_size': '1536MB',
        },
        'system': {
            'vm.swappiness': 5,
        }
    },
    're-node-03': {
        'postgresql': {
            'max_connections': 300,
            'shared_buffers': '512MB',
            'effective_cache_size': '1536MB',
        },
        'system': {
            'vm.swappiness': 5,
        }
    },
    're-node-04': {
        'postgresql': {
            'max_connections': 300,
            'shared_buffers': '512MB',
            'effective_cache_size': '1536MB',
        },
        'system': {
            'vm.swappiness': 5,
        }
    }
}

# Services to check per server role
ROLE_SERVICES = {
    'app': ['system'],
    'database': ['postgresql', 'system'],
    'router': ['haproxy', 'system'],
    'monitoring': ['haproxy', 'system'],
}

# Configuration keys that are critical (require immediate attention)
CRITICAL_KEYS = {
    'postgresql': ['max_connections', 'shared_buffers', 'work_mem'],
    'haproxy': ['maxconn'],
    'system': ['vm.swappiness', 'net.core.somaxconn'],
}

# Configuration keys that are informational (nice to know)
INFO_KEYS = {
    'postgresql': ['default_statistics_target'],
    'system': ['vm.dirty_ratio', 'vm.dirty_background_ratio'],
}


def get_expected_config(server_name: str, service: str) -> Dict[str, Any]:
    """
    Get expected configuration for a server and service.
    
    Args:
        server_name: Server name (e.g., 're-db', 'router-01')
        service: Service name (e.g., 'postgresql')
        
    Returns:
        Dictionary of expected configuration values
    """
    # Start with base configuration
    base_config = EXPECTED_CONFIGURATIONS.get(service, {}).copy()
    
    # Apply server-specific overrides
    overrides = SERVER_CONFIG_OVERRIDES.get(server_name, {}).get(service, {})
    base_config.update(overrides)
    
    return base_config


def get_services_for_role(role: str) -> list:
    """
    Get list of services to check for a given server role.
    
    Args:
        role: Server role (app, database, router, monitoring)
        
    Returns:
        List of service names
    """
    return ROLE_SERVICES.get(role, ['system'])


def get_severity(service: str, key: str) -> str:
    """
    Determine severity level for a configuration drift.
    
    Args:
        service: Service name
        key: Configuration key
        
    Returns:
        Severity level: 'critical', 'warning', or 'info'
    """
    if key in CRITICAL_KEYS.get(service, []):
        return 'critical'
    elif key in INFO_KEYS.get(service, []):
        return 'info'
    return 'warning'


def get_drift_description(service: str, key: str, expected: Any, actual: Any) -> str:
    """
    Generate a human-readable description of the drift.
    
    Args:
        service: Service name
        key: Configuration key
        expected: Expected value
        actual: Actual value
        
    Returns:
        Human-readable description
    """
    descriptions = {
        ('postgresql', 'max_connections'): 'Max connections affects database concurrency',
        ('postgresql', 'shared_buffers'): 'Shared buffers affects database performance',
        ('haproxy', 'maxconn'): 'Max connections affects load balancer capacity',
        ('system', 'vm.swappiness'): 'Swappiness affects memory management behavior',
        ('system', 'net.core.somaxconn'): 'Socket max connections affects connection queue',
    }
    
    base_desc = descriptions.get((service, key), 'Configuration value differs from expected baseline')
    
    return f"{base_desc}. Expected: {expected}, Actual: {actual}"
