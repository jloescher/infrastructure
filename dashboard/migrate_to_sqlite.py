#!/usr/bin/env python3
"""
Migration script to convert YAML configuration files to SQLite database.

This script migrates:
- applications.yml -> applications table
- domains (from applications) -> domains table
- secrets (SOPS encrypted) -> secrets table
- servers (from inventory) -> servers table
"""

import os
import sys
import yaml
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    init_database, get_db, generate_id,
    create_application, create_domain, create_secret, upsert_server,
    encrypt_value
)


def load_yaml_file(filepath: str) -> dict:
    """Load a YAML file safely."""
    if not os.path.exists(filepath):
        return {}
    
    with open(filepath, 'r') as f:
        try:
            return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}


def migrate_applications(applications_path: str) -> dict:
    """Migrate applications.yml to SQLite."""
    stats = {'created': 0, 'updated': 0, 'errors': []}
    
    if not os.path.exists(applications_path):
        print(f"Applications file not found: {applications_path}")
        return stats
    
    data = load_yaml_file(applications_path)
    applications = data.get('applications', {})
    
    print(f"Migrating {len(applications)} applications...")
    
    for app_name, app_data in applications.items():
        try:
            # Create application
            app_id = create_application({
                'name': app_name,
                'display_name': app_data.get('name', app_name),
                'description': app_data.get('description', ''),
                'framework': app_data.get('framework', 'laravel'),
                'repository': app_data.get('git_repo'),
                'production_branch': app_data.get('production_branch', 'main'),
                'staging_branch': app_data.get('staging_branch', 'staging'),
                'staging_env': app_data.get('staging_env', True),
                'target_servers': app_data.get('target_servers', []),
                'port': app_data.get('port'),
                'redis_enabled': app_data.get('redis_enabled', False),
                'redis_db': app_data.get('redis_db'),
            })
            
            # Create domains
            for domain_data in app_data.get('domains', []):
                create_domain({
                    'app_id': app_id,
                    'domain': domain_data.get('name') or domain_data.get('domain'),
                    'environment': domain_data.get('type', 'production'),
                    'is_www': domain_data.get('www_redirect', False),
                    'dns_label': domain_data.get('dns_label', '@'),
                    'ssl_enabled': domain_data.get('ssl_enabled', True),
                    'password': domain_data.get('password'),
                })
            
            # Create secrets from database config
            if app_data.get('db_user') and app_data.get('db_user_password'):
                create_secret(app_id, 'DB_USERNAME', app_data['db_user'], 'production')
                create_secret(app_id, 'DB_PASSWORD', app_data['db_user_password'], 'production')
            
            if app_data.get('db_admin') and app_data.get('db_admin_password'):
                create_secret(app_id, 'DB_ADMIN_USERNAME', app_data['db_admin'], 'production')
                create_secret(app_id, 'DB_ADMIN_PASSWORD', app_data['db_admin_password'], 'production')
            
            if app_data.get('database'):
                create_secret(app_id, 'DB_DATABASE', app_data['database'], 'production')
            
            # Staging secrets
            if app_data.get('staging_db_user') and app_data.get('staging_db_user_password'):
                create_secret(app_id, 'DB_USERNAME', app_data['staging_db_user'], 'staging')
                create_secret(app_id, 'DB_PASSWORD', app_data['staging_db_user_password'], 'staging')
            
            if app_data.get('staging_db_admin') and app_data.get('staging_db_admin_password'):
                create_secret(app_id, 'DB_ADMIN_USERNAME', app_data['staging_db_admin'], 'staging')
                create_secret(app_id, 'DB_ADMIN_PASSWORD', app_data['staging_db_admin_password'], 'staging')
            
            if app_data.get('staging_database'):
                create_secret(app_id, 'DB_DATABASE', app_data['staging_database'], 'staging')
            
            stats['created'] += 1
            print(f"  ✓ {app_name}")
            
        except Exception as e:
            stats['errors'].append(f"{app_name}: {str(e)}")
            print(f"  ✗ {app_name}: {str(e)}")
    
    return stats


def migrate_servers(inventory_path: str) -> dict:
    """Migrate server inventory to SQLite."""
    stats = {'created': 0, 'updated': 0, 'errors': []}
    
    if not os.path.exists(inventory_path):
        print(f"Inventory file not found: {inventory_path}")
        return stats
    
    data = load_yaml_file(inventory_path)
    all_hosts = {}
    
    # Collect all hosts from all groups
    for group_name, group_data in data.get('all', {}).get('children', {}).items():
        hosts = group_data.get('hosts', {})
        for host_name, host_vars in hosts.items():
            role = 'app'
            if 'db' in group_name.lower() or 'postgres' in group_name.lower():
                role = 'database'
            elif 'router' in group_name.lower() or 'haproxy' in group_name.lower():
                role = 'router'
            elif 'monitor' in group_name.lower():
                role = 'monitoring'
            
            all_hosts[host_name] = {
                'name': host_name,
                'ip': host_vars.get('ansible_host', host_vars.get('ip')),
                'public_ip': host_vars.get('public_ip'),
                'role': role,
                'specs': {
                    'vcpus': host_vars.get('vcpus'),
                    'memory_gb': host_vars.get('memory_gb'),
                    'disk_gb': host_vars.get('disk_gb'),
                    'region': host_vars.get('region'),
                }
            }
    
    print(f"Migrating {len(all_hosts)} servers...")
    
    for server_data in all_hosts.values():
        try:
            upsert_server(server_data)
            stats['created'] += 1
            print(f"  ✓ {server_data['name']}")
        except Exception as e:
            stats['errors'].append(f"{server_data['name']}: {str(e)}")
            print(f"  ✗ {server_data['name']}: {str(e)}")
    
    return stats


def migrate_databases(databases_path: str) -> dict:
    """Migrate databases.yml to SQLite."""
    stats = {'created': 0, 'updated': 0, 'errors': []}
    
    if not os.path.exists(databases_path):
        print(f"Databases file not found: {databases_path}")
        return stats
    
    data = load_yaml_file(databases_path)
    databases = data.get('databases', {})
    
    print(f"Migrating {len(databases)} databases...")
    
    with get_db() as conn:
        for db_name, db_data in databases.items():
            try:
                db_id = generate_id()
                now = datetime.utcnow().isoformat()
                
                conn.execute('''
                    INSERT OR REPLACE INTO databases (id, name, description, owner, environment,
                        user_name, user_password_encrypted, admin_name, admin_password_encrypted, pool_size)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    db_id,
                    db_name,
                    db_data.get('description', ''),
                    db_data.get('owner'),
                    'production',
                    db_data.get('user_name') or (db_data.get('users', [{}])[0].get('name') if db_data.get('users') else None),
                    encrypt_value(db_data.get('user_password') or (db_data.get('users', [{}])[0].get('password') if db_data.get('users') else '')),
                    db_data.get('admin_name') or (db_data.get('users', [{}, {}])[1].get('name') if len(db_data.get('users', [])) > 1 else None),
                    encrypt_value(db_data.get('admin_password') or (db_data.get('users', [{}, {}])[1].get('password') if len(db_data.get('users', [])) > 1 else '')),
                    db_data.get('pgbouncer_pool_size', 20),
                ))
                
                stats['created'] += 1
                print(f"  ✓ {db_name}")
                
            except Exception as e:
                stats['errors'].append(f"{db_name}: {str(e)}")
                print(f"  ✗ {db_name}: {str(e)}")
        
        conn.commit()
    
    return stats


def main():
    """Run all migrations."""
    print("=" * 60)
    print("PaaS Configuration Migration")
    print("=" * 60)
    print()
    
    # Initialize database
    print("Initializing SQLite database...")
    init_database()
    print("  ✓ Database initialized")
    print()
    
    # Determine paths
    script_dir = Path(__file__).parent
    config_dir = script_dir.parent / 'config'
    
    # Check for config files
    applications_path = config_dir / 'applications.yml'
    inventory_path = script_dir.parent.parent / 'ansible' / 'inventory' / 'hosts.yml'
    databases_path = config_dir / 'databases.yml'
    
    # Run migrations
    app_stats = migrate_applications(str(applications_path))
    print()
    
    server_stats = migrate_servers(str(inventory_path))
    print()
    
    db_stats = migrate_databases(str(databases_path))
    print()
    
    # Print summary
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"Applications: {app_stats['created']} created, {len(app_stats['errors'])} errors")
    print(f"Servers: {server_stats['created']} created, {len(server_stats['errors'])} errors")
    print(f"Databases: {db_stats['created']} created, {len(db_stats['errors'])} errors")
    print()
    
    all_errors = app_stats['errors'] + server_stats['errors'] + db_stats['errors']
    if all_errors:
        print("Errors:")
        for error in all_errors:
            print(f"  - {error}")
    else:
        print("✓ All migrations completed successfully")
    
    return 0 if not all_errors else 1


if __name__ == '__main__':
    from datetime import datetime
    sys.exit(main())