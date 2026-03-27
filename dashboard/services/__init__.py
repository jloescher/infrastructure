"""
Services module for PaaS deployment enhancements.

This module provides:
- Framework detection and configuration
- Blue-green deployment management
- Deployment hooks execution
- Notification services
- Add-on service management (Phase 3)
"""

from .framework import (
    FRAMEWORK_CONFIGS,
    FRAMEWORK_PORT_RANGES,
    detect_framework,
    get_framework_config,
    get_framework_port,
    get_all_frameworks,
    validate_framework,
    FrameworkDetectionError,
)

# Phase 3: Add-on Services
from .templates import (
    SERVICE_TEMPLATES,
    get_service_template,
    list_service_templates,
    get_services_by_category,
    generate_service_config,
    validate_service_config,
    get_connection_string,
    get_environment_variables,
)

# Optional imports for services that may not be implemented yet
try:
    from .bluegreen import BlueGreenDeploy
except ImportError:
    BlueGreenDeploy = None

try:
    from .hooks import HookExecutor
except ImportError:
    HookExecutor = None

try:
    from .notifications import NotificationService
except ImportError:
    NotificationService = None

try:
    from .service_manager import ServiceManager, get_service_manager
except ImportError:
    ServiceManager = None
    get_service_manager = None

__all__ = [
    # Framework services
    "FRAMEWORK_CONFIGS",
    "FRAMEWORK_PORT_RANGES",
    "detect_framework",
    "get_framework_config",
    "get_framework_port",
    "get_all_frameworks",
    "validate_framework",
    "FrameworkDetectionError",
    # Phase 3: Add-on Services
    "SERVICE_TEMPLATES",
    "get_service_template",
    "list_service_templates",
    "get_services_by_category",
    "generate_service_config",
    "validate_service_config",
    "get_connection_string",
    "get_environment_variables",
    "ServiceManager",
    "get_service_manager",
    # Optional services
    "BlueGreenDeploy",
    "HookExecutor",
    "NotificationService",
]