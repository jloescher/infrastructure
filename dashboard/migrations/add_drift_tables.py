"""
Add drift detection tables to database.

Tables:
- drift_results: Current drift state
- drift_history: Historical drift checks
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import database as db


def migrate():
    """Add drift detection tables."""
    with db.get_db() as conn:
        # Current drift results
        conn.execute('''
            CREATE TABLE IF NOT EXISTS drift_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server TEXT NOT NULL,
                server_ip TEXT NOT NULL,
                service TEXT NOT NULL,
                config_key TEXT NOT NULL,
                expected TEXT,
                actual TEXT,
                severity TEXT DEFAULT 'warning',
                description TEXT,
                checked_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Historical drift checks
        conn.execute('''
            CREATE TABLE IF NOT EXISTS drift_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_json TEXT NOT NULL,
                total_drifts INTEGER DEFAULT 0,
                critical_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                info_count INTEGER DEFAULT 0,
                checked_at TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create indexes
        conn.execute('CREATE INDEX IF NOT EXISTS idx_drift_results_server ON drift_results(server)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_drift_results_service ON drift_results(service)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_drift_results_severity ON drift_results(severity)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_drift_history_checked_at ON drift_history(checked_at)')
        
        conn.commit()
    
    print("✓ Drift detection tables created")


if __name__ == '__main__':
    migrate()