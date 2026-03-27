#!/usr/bin/env python3
"""
Migration: Add deployment indexes for performance.

Run this migration to add indexes for faster deployment queries:
    python dashboard/migrations/add_deployment_indexes.py

This migration is idempotent - safe to run multiple times.
"""

import sqlite3
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import DATABASE_PATH, get_db


MIGRATION_NAME = "add_deployment_indexes"
MIGRATION_VERSION = "20260326_001"


def check_migration_table_exists(conn: sqlite3.Connection) -> bool:
    """Check if migrations table exists."""
    cursor = conn.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='migrations'
    """)
    return cursor.fetchone() is not None


def create_migration_table(conn: sqlite3.Connection):
    """Create migrations tracking table."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            description TEXT
        )
    ''')
    conn.commit()


def is_migration_applied(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a migration has been applied."""
    cursor = conn.execute(
        'SELECT id FROM migrations WHERE name = ?',
        (name,)
    )
    return cursor.fetchone() is not None


def record_migration(conn: sqlite3.Connection, name: str, version: str, description: str = None):
    """Record that a migration has been applied."""
    conn.execute('''
        INSERT INTO migrations (name, version, applied_at, description)
        VALUES (?, ?, ?, ?)
    ''', (name, version, datetime.utcnow().isoformat(), description))
    conn.commit()


def apply_migration():
    """Apply the deployment indexes migration."""
    
    print(f"Applying migration: {MIGRATION_NAME} ({MIGRATION_VERSION})")
    print(f"Database: {DATABASE_PATH}")
    
    # Ensure database directory exists
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    
    with get_db() as conn:
        # Create migrations table if needed
        if not check_migration_table_exists(conn):
            print("  Creating migrations table...")
            create_migration_table(conn)
        
        # Check if already applied
        if is_migration_applied(conn, MIGRATION_NAME):
            print(f"  Migration '{MIGRATION_NAME}' already applied. Skipping.")
            return False
        
        # Apply indexes
        print("  Adding deployment indexes...")
        
        # Index for filtering by app_id and environment
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployments_app_env 
            ON deployments(app_id, environment)
        ''')
        print("    ✓ idx_deployments_app_env")
        
        # Index for filtering by status (for active deployments query)
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployments_status 
            ON deployments(status)
        ''')
        print("    ✓ idx_deployments_status")
        
        # Index for chronological ordering
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployments_deployed_at 
            ON deployments(deployed_at DESC)
        ''')
        print("    ✓ idx_deployments_deployed_at")
        
        # Composite index for history queries (app + env + time)
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployments_app_env_time 
            ON deployments(app_id, environment, deployed_at DESC)
        ''')
        print("    ✓ idx_deployments_app_env_time")
        
        # Index for status + time (active deployments)
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployments_status_time 
            ON deployments(status, deployed_at DESC)
        ''')
        print("    ✓ idx_deployments_status_time")
        
        # Index for deployment_steps by server (for server-specific queries)
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployment_steps_server 
            ON deployment_steps(deployment_id, server)
        ''')
        print("    ✓ idx_deployment_steps_server")
        
        # Index for deployment_steps by step name
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployment_steps_step 
            ON deployment_steps(deployment_id, step)
        ''')
        print("    ✓ idx_deployment_steps_step")
        
        # Index for deployment_steps status
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_deployment_steps_status 
            ON deployment_steps(deployment_id, status)
        ''')
        print("    ✓ idx_deployment_steps_status")
        
        # Record migration
        record_migration(
            conn, 
            MIGRATION_NAME, 
            MIGRATION_VERSION,
            "Add indexes for deployments and deployment_steps tables"
        )
        
        print(f"\n  Migration applied successfully!")
        return True


def verify_migration():
    """Verify that indexes were created correctly."""
    print("\nVerifying indexes...")
    
    with get_db() as conn:
        # Get all indexes
        cursor = conn.execute("""
            SELECT name, tbl_name FROM sqlite_master 
            WHERE type='index' AND sql IS NOT NULL
            ORDER BY tbl_name, name
        """)
        
        indexes = cursor.fetchall()
        
        print("\n  Deployment-related indexes:")
        for name, table in indexes:
            if table in ('deployments', 'deployment_steps'):
                print(f"    - {name} (on {table})")
        
        # Verify index usage with EXPLAIN QUERY PLAN
        print("\n  Query plan verification:")
        
        # Test active deployments query
        cursor = conn.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM deployments WHERE status IN ('pending', 'running')
        """)
        plan = cursor.fetchall()
        print(f"    Active deployments: {'USING INDEX' if any('INDEX' in str(p) for p in plan) else 'FULL SCAN'}")
        
        # Test history query
        cursor = conn.execute("""
            EXPLAIN QUERY PLAN
            SELECT * FROM deployments WHERE app_id = ? AND environment = ? ORDER BY deployed_at DESC
        """, ('test-app', 'production'))
        plan = cursor.fetchall()
        print(f"    History query: {'USING INDEX' if any('INDEX' in str(p) for p in plan) else 'FULL SCAN'}")


def rollback_migration():
    """Rollback the migration (drop indexes)."""
    print(f"Rolling back migration: {MIGRATION_NAME}")
    
    with get_db() as conn:
        if not check_migration_table_exists(conn):
            print("  Migrations table not found. Nothing to rollback.")
            return
        
        if not is_migration_applied(conn, MIGRATION_NAME):
            print("  Migration not applied. Nothing to rollback.")
            return
        
        # Drop indexes (SQLite allows IF EXISTS for DROP INDEX since 3.35.0)
        indexes_to_drop = [
            ('idx_deployments_app_env', 'deployments'),
            ('idx_deployments_status', 'deployments'),
            ('idx_deployments_deployed_at', 'deployments'),
            ('idx_deployments_app_env_time', 'deployments'),
            ('idx_deployments_status_time', 'deployments'),
            ('idx_deployment_steps_server', 'deployment_steps'),
            ('idx_deployment_steps_step', 'deployment_steps'),
            ('idx_deployment_steps_status', 'deployment_steps'),
        ]
        
        for index_name, table in indexes_to_drop:
            try:
                conn.execute(f'DROP INDEX IF EXISTS {index_name}')
                print(f"    ✓ Dropped {index_name}")
            except sqlite3.OperationalError as e:
                print(f"    ! Could not drop {index_name}: {e}")
        
        # Remove migration record
        conn.execute('DELETE FROM migrations WHERE name = ?', (MIGRATION_NAME,))
        conn.commit()
        
        print("  Rollback complete.")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Deployment indexes migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    parser.add_argument('--verify', action='store_true', help='Verify migration status')
    args = parser.parse_args()
    
    if args.rollback:
        rollback_migration()
    elif args.verify:
        verify_migration()
    else:
        applied = apply_migration()
        if applied:
            verify_migration()