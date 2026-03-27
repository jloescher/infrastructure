"""
Database migrations for PaaS.

Migrations are named with the pattern: {date}_{description}.py
Example: 20260326_001_add_deployment_indexes.py

To run all pending migrations:
    python -m dashboard.migrations

To run a specific migration:
    python dashboard/migrations/add_deployment_indexes.py
"""

import os
import importlib
import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent


def get_migration_files():
    """Get all migration files sorted by name."""
    migration_pattern = re.compile(r'^\d{8}_\d+_.+\.py$')
    files = []
    
    for f in MIGRATIONS_DIR.iterdir():
        if f.is_file() and migration_pattern.match(f.name):
            files.append(f)
    
    return sorted(files)


def run_pending_migrations():
    """Run all pending migrations."""
    print("Checking for pending migrations...")
    
    migrations = get_migration_files()
    
    if not migrations:
        print("No migration files found.")
        return
    
    for migration_file in migrations:
        module_name = migration_file.stem
        print(f"\nChecking: {module_name}")
        
        # Import and run migration
        spec = importlib.util.spec_from_file_location(module_name, migration_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, 'apply_migration'):
            module.apply_migration()


if __name__ == '__main__':
    run_pending_migrations()