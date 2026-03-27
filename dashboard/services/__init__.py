"""
Services module for PaaS deployment enhancements.

This module provides:
- Framework detection and configuration
- Blue-green deployment management
- Deployment hooks execution
- Notification services
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
    # Optional services
    "BlueGreenDeploy",
    "HookExecutor",
    "NotificationService",
]