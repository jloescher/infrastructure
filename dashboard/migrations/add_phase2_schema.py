"""
Database migration for Phase 2 deployment enhancements.

Run this script to add the new tables and columns for:
- Deployment hooks
- Hook execution history
- Scheduled deployments
- Blue-green deployment slots
- Notification settings

Usage:
    cd dashboard
    python migrations/add_phase2_schema.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db
from datetime import datetime
import sqlite3


def migrate():
    """Run Phase 2 schema migration."""
    print("Starting Phase 2 schema migration...")
    
    with db.get_db() as conn:
        # Deployment hooks table
        print("  Creating deployment_hooks table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS deployment_hooks (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                hook_type TEXT CHECK(hook_type IN ('pre_deploy', 'post_deploy', 'pre_rollback', 'post_rollback')),
                environment TEXT,
                command TEXT NOT NULL,
                timeout INTEGER DEFAULT 300,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE
            )
        ''')
        
        # Hook executions history
        print("  Creating hook_executions table...")
        conn.execute('''
            CREATE TABLE IF NOT EXISTS hook_executions (
                id TEXT PRIMARY KEY,
                hook_id TEXT NOT NULL,
                deployment_id TEXT,
                success INTEGER NOT NULL,
                servers_json TEXT,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY (hook_id) REFERENCES deployment_hooks(id) ON DELETE CASCADE,
                FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE SET NULL
            )
        ''')
        
        # Add scheduled_at column to deployments
        print("  Adding scheduled_at column to deployments...")
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN scheduled_at TEXT')
            print("    Added scheduled_at column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("    scheduled_at column already exists")
            else:
                raise
        
        # Add is_scheduled column to deployments
        print("  Adding is_scheduled column to deployments...")
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN is_scheduled INTEGER DEFAULT 0')
            print("    Added is_scheduled column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("    is_scheduled column already exists")
            else:
                raise
        
        # Add slot column for blue-green deployments
        print("  Adding slot column to deployments...")
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN slot TEXT')
            print("    Added slot column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("    slot column already exists")
            else:
                raise
        
        # Add slot_path column
        print("  Adding slot_path column to deployments...")
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN slot_path TEXT')
            print("    Added slot_path column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("    slot_path column already exists")
            else:
                raise
        
        # Add deployment_mode column
        print("  Adding deployment_mode column to deployments...")
        try:
            conn.execute("ALTER TABLE deployments ADD COLUMN deployment_mode TEXT DEFAULT 'standard'")
            print("    Added deployment_mode column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("    deployment_mode column already exists")
            else:
                raise
        
        # Create indexes
        print("  Creating indexes...")
        conn.execute('CREATE INDEX IF NOT EXISTS idx_deployment_hooks_app ON deployment_hooks(app_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_hook_executions_hook ON hook_executions(hook_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_hook_executions_deployment ON hook_executions(deployment_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_deployments_scheduled ON deployments(scheduled_at) WHERE status = "scheduled"')
        
        # Initialize notification settings
        print("  Initializing notification settings...")
        notification_settings = [
            ('notification_enabled', 'true'),
            ('notification_slack_webhook', ''),
            ('notification_email', ''),
            ('notification_webhook', ''),
            ('notification_smtp_host', 'localhost'),
            ('notification_smtp_port', '25'),
            ('notification_smtp_user', ''),
            ('notification_smtp_pass', ''),
            ('notification_smtp_from', 'noreply@quantyra.io'),
        ]
        
        for key, value in notification_settings:
            conn.execute('''
                INSERT OR IGNORE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value, datetime.utcnow().isoformat()))
        
        conn.commit()
    
    print("\n✅ Phase 2 schema migration complete!")
    print("\nNew features available:")
    print("  - Deployment hooks (pre_deploy, post_deploy, pre_rollback, post_rollback)")
    print("  - Scheduled deployments")
    print("  - Blue-green deployment mode")
    print("  - Deployment notifications (Slack, email, webhook)")


if __name__ == '__main__':
    migrate()