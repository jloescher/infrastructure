"""
SQLite database module for PaaS internal state.

This module manages the PaaS's own configuration and state using SQLite,
making the PaaS portable and deployable anywhere.
"""

import sqlite3
import json
import os
import hashlib
import secrets
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64


DATABASE_PATH = os.environ.get('PAAS_DATABASE_PATH', '/data/paas.db')
ENCRYPTION_KEY_PATH = os.environ.get('PAAS_KEY_PATH', '/data/vault.key')


def get_encryption_key() -> bytes:
    """Get or create the encryption key for secrets."""
    key_path = ENCRYPTION_KEY_PATH
    
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return f.read()
    
    key = AESGCM.generate_key(bit_length=256)
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, 'wb') as f:
        f.write(key)
    os.chmod(key_path, 0o600)
    return key


def encrypt_value(plaintext: str) -> str:
    """Encrypt a value using AES-256-GCM."""
    if not plaintext:
        return ''
    
    key = get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a value using AES-256-GCM."""
    if not encrypted:
        return ''
    
    try:
        key = get_encryption_key()
        aesgcm = AESGCM(key)
        data = base64.b64decode(encrypted)
        nonce = data[:12]
        ciphertext = data[12:]
        return aesgcm.decrypt(nonce, ciphertext, None).decode()
    except Exception:
        return ''


@contextmanager
def get_db():
    """Get database connection with context manager."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Initialize database schema."""
    with get_db() as conn:
        conn.executescript('''
            -- Applications table
            CREATE TABLE IF NOT EXISTS applications (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT,
                description TEXT,
                framework TEXT DEFAULT 'laravel',
                repository TEXT,
                production_branch TEXT DEFAULT 'main',
                staging_branch TEXT DEFAULT 'staging',
                create_staging INTEGER DEFAULT 1,
                target_servers TEXT,
                port INTEGER,
                redis_enabled INTEGER DEFAULT 0,
                redis_db INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Domains table
            CREATE TABLE IF NOT EXISTS domains (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                environment TEXT CHECK(environment IN ('production', 'staging')),
                is_www INTEGER DEFAULT 0,
                dns_label TEXT DEFAULT '@',
                ssl_enabled INTEGER DEFAULT 1,
                ssl_expires_at TEXT,
                provisioned INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                password TEXT,
                error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE,
                UNIQUE(domain, environment)
            );
            
            -- Secrets table
            CREATE TABLE IF NOT EXISTS secrets (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value_encrypted TEXT,
                scope TEXT DEFAULT 'shared' CHECK(scope IN ('shared', 'production', 'staging')),
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE,
                UNIQUE(app_id, key, scope)
            );
            
            -- Databases table (for app databases managed by PaaS)
            CREATE TABLE IF NOT EXISTS databases (
                id TEXT PRIMARY KEY,
                app_id TEXT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                owner TEXT,
                environment TEXT CHECK(environment IN ('production', 'staging')),
                user_name TEXT,
                user_password_encrypted TEXT,
                admin_name TEXT,
                admin_password_encrypted TEXT,
                pool_size INTEGER DEFAULT 20,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE SET NULL
            );
            
            -- Servers table
            CREATE TABLE IF NOT EXISTS servers (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                ip TEXT NOT NULL,
                public_ip TEXT,
                role TEXT CHECK(role IN ('app', 'database', 'router', 'monitoring')),
                specs_json TEXT,
                status TEXT DEFAULT 'unknown',
                last_check_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Deployments table
            CREATE TABLE IF NOT EXISTS deployments (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                environment TEXT NOT NULL,
                commit TEXT,
                branch TEXT,
                status TEXT DEFAULT 'pending',
                results_json TEXT,
                logs TEXT,
                deployed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE
            );
            
            -- Deployment steps table (for progress tracking)
            CREATE TABLE IF NOT EXISTS deployment_steps (
                id TEXT PRIMARY KEY,
                deployment_id TEXT NOT NULL,
                server TEXT NOT NULL,
                step TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                output TEXT,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE CASCADE
            );
            
            -- Config sync status table
            CREATE TABLE IF NOT EXISTS sync_status (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_sync_at TEXT,
                last_sync_status TEXT,
                gist_id TEXT,
                gist_url TEXT,
                gist_version TEXT,
                auto_sync_enabled INTEGER DEFAULT 1
            );
            
            -- Sync history table
            CREATE TABLE IF NOT EXISTS sync_history (
                id TEXT PRIMARY KEY,
                direction TEXT CHECK(direction IN ('export', 'import', 'gist_sync')),
                status TEXT,
                gist_id TEXT,
                gist_version TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Settings table
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_domains_app ON domains(app_id);
            CREATE INDEX IF NOT EXISTS idx_secrets_app ON secrets(app_id);
            CREATE INDEX IF NOT EXISTS idx_deployments_app ON deployments(app_id);
            CREATE INDEX IF NOT EXISTS idx_deployment_steps_deployment ON deployment_steps(deployment_id);
            
            -- Initialize sync_status
            INSERT OR IGNORE INTO sync_status (id, auto_sync_enabled) VALUES (1, 1);
        ''')
        conn.commit()


def generate_id() -> str:
    """Generate a unique ID."""
    return secrets.token_urlsafe(16)


# Application CRUD operations

def create_application(app_data: Dict[str, Any]) -> str:
    """Create a new application."""
    app_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO applications (id, name, display_name, description, framework,
                repository, production_branch, staging_branch, create_staging,
                target_servers, port, redis_enabled, redis_db, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            app_id,
            app_data.get('name'),
            app_data.get('display_name', app_data.get('name')),
            app_data.get('description', ''),
            app_data.get('framework', 'laravel'),
            app_data.get('repository', app_data.get('git_repo')),
            app_data.get('production_branch', 'main'),
            app_data.get('staging_branch', 'staging'),
            1 if app_data.get('staging_env', app_data.get('create_staging', True)) else 0,
            json.dumps(app_data.get('target_servers', [])),
            app_data.get('port'),
            1 if app_data.get('redis_enabled') else 0,
            app_data.get('redis_db'),
            now,
            now
        ))
        conn.commit()
    
    return app_id


def get_application(app_id: str = None, name: str = None) -> Optional[Dict[str, Any]]:
    """Get an application by ID or name."""
    with get_db() as conn:
        if app_id:
            row = conn.execute('SELECT * FROM applications WHERE id = ?', (app_id,)).fetchone()
        elif name:
            row = conn.execute('SELECT * FROM applications WHERE name = ?', (name,)).fetchone()
        else:
            return None
        
        if row:
            app = dict(row)
            app['target_servers'] = json.loads(app['target_servers'] or '[]')
            return app
    return None


def list_applications() -> List[Dict[str, Any]]:
    """List all applications."""
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM applications ORDER BY name').fetchall()
        apps = []
        for row in rows:
            app = dict(row)
            app['target_servers'] = json.loads(app['target_servers'] or '[]')
            apps.append(app)
    return apps


def update_application(app_id: str, updates: Dict[str, Any]) -> bool:
    """Update an application."""
    updates['updated_at'] = datetime.utcnow().isoformat()
    
    if 'target_servers' in updates:
        updates['target_servers'] = json.dumps(updates['target_servers'])
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [app_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE applications SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def delete_application(app_id: str) -> bool:
    """Delete an application and all related data."""
    with get_db() as conn:
        conn.execute('DELETE FROM applications WHERE id = ?', (app_id,))
        conn.commit()
    return True


# Domain CRUD operations

def create_domain(domain_data: Dict[str, Any]) -> str:
    """Create a new domain."""
    domain_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO domains (id, app_id, domain, environment, is_www, dns_label,
                ssl_enabled, password, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            domain_id,
            domain_data.get('app_id'),
            domain_data.get('domain') or domain_data.get('name'),
            domain_data.get('environment', 'production'),
            1 if domain_data.get('is_www') or domain_data.get('www_redirect') else 0,
            domain_data.get('dns_label', '@'),
            1 if domain_data.get('ssl_enabled', True) else 0,
            domain_data.get('password'),
            now,
            now
        ))
        conn.commit()
    
    return domain_id


def get_domains_for_app(app_id: str) -> List[Dict[str, Any]]:
    """Get all domains for an application."""
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM domains WHERE app_id = ? ORDER BY environment, domain', (app_id,)).fetchall()
        return [dict(row) for row in rows]


def update_domain(domain_id: str, updates: Dict[str, Any]) -> bool:
    """Update a domain."""
    updates['updated_at'] = datetime.utcnow().isoformat()
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [domain_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE domains SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def delete_domain(domain_id: str) -> bool:
    """Delete a domain."""
    with get_db() as conn:
        conn.execute('DELETE FROM domains WHERE id = ?', (domain_id,))
        conn.commit()
    return True


# Secret CRUD operations

def create_secret(app_id: str, key: str, value: str, scope: str = 'shared', description: str = '') -> str:
    """Create a new secret."""
    secret_id = generate_id()
    now = datetime.utcnow().isoformat()
    encrypted_value = encrypt_value(value) if value else ''
    
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO secrets (id, app_id, key, value_encrypted, scope, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (secret_id, app_id, key, encrypted_value, scope, description, now, now))
        conn.commit()
    
    return secret_id


def get_secrets_for_app(app_id: str, scope: str = None) -> List[Dict[str, Any]]:
    """Get all secrets for an application."""
    with get_db() as conn:
        if scope:
            rows = conn.execute('SELECT * FROM secrets WHERE app_id = ? AND scope = ?', (app_id, scope)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM secrets WHERE app_id = ? ORDER BY scope, key', (app_id,)).fetchall()
        
        secrets_list = []
        for row in rows:
            secret = dict(row)
            secret['value'] = decrypt_value(secret['value_encrypted'])
            del secret['value_encrypted']
            secrets_list.append(secret)
    
    return secrets_list


def get_secret_value(app_id: str, key: str, scope: str = 'shared') -> Optional[str]:
    """Get a specific secret value."""
    with get_db() as conn:
        row = conn.execute(
            'SELECT value_encrypted FROM secrets WHERE app_id = ? AND key = ? AND scope = ?',
            (app_id, key, scope)
        ).fetchone()
        
        if row:
            return decrypt_value(row['value_encrypted'])
    return None


def delete_secret(secret_id: str = None, app_id: str = None, key: str = None, scope: str = None) -> bool:
    """Delete a secret."""
    with get_db() as conn:
        if secret_id:
            conn.execute('DELETE FROM secrets WHERE id = ?', (secret_id,))
        elif app_id and key and scope:
            conn.execute('DELETE FROM secrets WHERE app_id = ? AND key = ? AND scope = ?', (app_id, key, scope))
        elif app_id:
            conn.execute('DELETE FROM secrets WHERE app_id = ?', (app_id,))
        conn.commit()
    return True


# Deployment operations

def create_deployment(app_id: str, environment: str, branch: str, commit: str = None) -> str:
    """Create a new deployment record."""
    deployment_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO deployments (id, app_id, environment, branch, commit, status, deployed_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        ''', (deployment_id, app_id, environment, branch, commit, now))
        conn.commit()
    
    return deployment_id


def update_deployment(deployment_id: str, updates: Dict[str, Any]) -> bool:
    """Update a deployment."""
    if 'results' in updates:
        updates['results_json'] = json.dumps(updates.pop('results'))
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [deployment_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE deployments SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def get_last_deployment(app_id: str, environment: str = None) -> Optional[Dict[str, Any]]:
    """Get the last deployment for an application."""
    with get_db() as conn:
        if environment:
            row = conn.execute('''
                SELECT * FROM deployments 
                WHERE app_id = ? AND environment = ? 
                ORDER BY deployed_at DESC LIMIT 1
            ''', (app_id, environment)).fetchone()
        else:
            row = conn.execute('''
                SELECT * FROM deployments 
                WHERE app_id = ? 
                ORDER BY deployed_at DESC LIMIT 1
            ''', (app_id,)).fetchone()
        
        if row:
            deployment = dict(row)
            if deployment.get('results_json'):
                deployment['results'] = json.loads(deployment['results_json'])
            return deployment
    return None


# Server operations

def upsert_server(server_data: Dict[str, Any]) -> str:
    """Create or update a server."""
    server_id = server_data.get('id', generate_id())
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO servers (id, name, ip, public_ip, role, specs_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                ip = excluded.ip,
                public_ip = excluded.public_ip,
                role = excluded.role,
                specs_json = excluded.specs_json
        ''', (
            server_id,
            server_data['name'],
            server_data['ip'],
            server_data.get('public_ip'),
            server_data.get('role'),
            json.dumps(server_data.get('specs', {})),
            now
        ))
        conn.commit()
    
    return server_id


def list_servers() -> List[Dict[str, Any]]:
    """List all servers."""
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM servers ORDER BY name').fetchall()
        servers = []
        for row in rows:
            server = dict(row)
            if server.get('specs_json'):
                server['specs'] = json.loads(server['specs_json'])
            del server['specs_json']
            servers.append(server)
    return servers


# Export/Import operations

def export_configuration() -> Dict[str, Any]:
    """Export all configuration to a dictionary."""
    now = datetime.utcnow().isoformat()
    
    config = {
        'version': '1.0',
        'exported_at': now,
        'checksum': '',
        'applications': [],
        'domains': [],
        'secrets': {'_encrypted': True, '_algorithm': 'AES-256-GCM', 'data': []},
        'databases': [],
        'servers': []
    }
    
    with get_db() as conn:
        # Export applications
        app_rows = conn.execute('SELECT * FROM applications ORDER BY name').fetchall()
        for row in app_rows:
            app = dict(row)
            app['target_servers'] = json.loads(app['target_servers'] or '[]')
            config['applications'].append(app)
        
        # Export domains
        domain_rows = conn.execute('SELECT * FROM domains ORDER BY domain').fetchall()
        config['domains'] = [dict(row) for row in domain_rows]
        
        # Export secrets (encrypted)
        secret_rows = conn.execute('SELECT * FROM secrets ORDER BY app_id, scope, key').fetchall()
        for row in secret_rows:
            secret = dict(row)
            config['secrets']['data'].append(secret)
        
        # Export databases
        db_rows = conn.execute('SELECT * FROM databases ORDER BY name').fetchall()
        config['databases'] = [dict(row) for row in db_rows]
        
        # Export servers
        server_rows = conn.execute('SELECT * FROM servers ORDER BY name').fetchall()
        for row in server_rows:
            server = dict(row)
            if server.get('specs_json'):
                server['specs'] = json.loads(server['specs_json'])
            del server['specs_json']
            config['servers'].append(server)
    
    # Calculate checksum
    config_json = json.dumps(config, sort_keys=True)
    config['checksum'] = 'sha256:' + hashlib.sha256(config_json.encode()).hexdigest()
    
    return config


def import_configuration(config: Dict[str, Any], mode: str = 'merge') -> Dict[str, Any]:
    """
    Import configuration from a dictionary.
    
    Args:
        config: Configuration dictionary
        mode: 'merge' (add new, update existing), 'replace' (clear all, then import)
    
    Returns:
        Dictionary with import results
    """
    results = {
        'success': True,
        'applications': {'created': 0, 'updated': 0, 'skipped': 0},
        'domains': {'created': 0, 'updated': 0, 'skipped': 0},
        'secrets': {'created': 0, 'updated': 0, 'skipped': 0},
        'databases': {'created': 0, 'updated': 0, 'skipped': 0},
        'servers': {'created': 0, 'updated': 0, 'skipped': 0},
        'errors': []
    }
    
    # Verify checksum
    if config.get('checksum'):
        expected_checksum = config['checksum']
        config_copy = {k: v for k, v in config.items() if k != 'checksum'}
        actual_checksum = 'sha256:' + hashlib.sha256(json.dumps(config_copy, sort_keys=True).encode()).hexdigest()
        if expected_checksum != actual_checksum:
            return {'success': False, 'errors': ['Checksum mismatch - file may be corrupted']}
    
    with get_db() as conn:
        if mode == 'replace':
            # Clear existing data
            conn.execute('DELETE FROM domains')
            conn.execute('DELETE FROM secrets')
            conn.execute('DELETE FROM databases')
            conn.execute('DELETE FROM applications')
        
        # Import applications
        for app in config.get('applications', []):
            try:
                existing = conn.execute('SELECT id FROM applications WHERE name = ?', (app['name'],)).fetchone()
                
                if existing and mode == 'merge':
                    # Update existing
                    conn.execute('''
                        UPDATE applications SET 
                            display_name = ?, description = ?, framework = ?,
                            repository = ?, production_branch = ?, staging_branch = ?,
                            create_staging = ?, target_servers = ?, port = ?,
                            redis_enabled = ?, redis_db = ?, updated_at = ?
                        WHERE name = ?
                    ''', (
                        app.get('display_name'),
                        app.get('description', ''),
                        app.get('framework', 'laravel'),
                        app.get('repository'),
                        app.get('production_branch', 'main'),
                        app.get('staging_branch', 'staging'),
                        app.get('create_staging', 1),
                        json.dumps(app.get('target_servers', [])),
                        app.get('port'),
                        app.get('redis_enabled', 0),
                        app.get('redis_db'),
                        datetime.utcnow().isoformat(),
                        app['name']
                    ))
                    results['applications']['updated'] += 1
                elif not existing:
                    # Create new
                    conn.execute('''
                        INSERT INTO applications (id, name, display_name, description, framework,
                            repository, production_branch, staging_branch, create_staging,
                            target_servers, port, redis_enabled, redis_db, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        app.get('id', generate_id()),
                        app['name'],
                        app.get('display_name'),
                        app.get('description', ''),
                        app.get('framework', 'laravel'),
                        app.get('repository'),
                        app.get('production_branch', 'main'),
                        app.get('staging_branch', 'staging'),
                        app.get('create_staging', 1),
                        json.dumps(app.get('target_servers', [])),
                        app.get('port'),
                        app.get('redis_enabled', 0),
                        app.get('redis_db'),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat()
                    ))
                    results['applications']['created'] += 1
                else:
                    results['applications']['skipped'] += 1
            except Exception as e:
                results['errors'].append(f"Application {app.get('name')}: {str(e)}")
        
        # Import domains
        app_id_map = {app['name']: app['id'] for app in config.get('applications', [])}
        
        for domain in config.get('domains', []):
            try:
                existing = conn.execute('SELECT id FROM domains WHERE domain = ?', (domain['domain'],)).fetchone()
                
                # Get app_id from name if needed
                app_id = domain.get('app_id')
                if not app_id and domain.get('app_name'):
                    app_id = app_id_map.get(domain['app_name'])
                
                if existing and mode == 'merge':
                    conn.execute('''
                        UPDATE domains SET 
                            app_id = ?, environment = ?, is_www = ?,
                            ssl_enabled = ?, password = ?, updated_at = ?
                        WHERE domain = ?
                    ''', (
                        app_id,
                        domain.get('environment', 'production'),
                        domain.get('is_www', 0),
                        domain.get('ssl_enabled', 1),
                        domain.get('password'),
                        datetime.utcnow().isoformat(),
                        domain['domain']
                    ))
                    results['domains']['updated'] += 1
                elif not existing:
                    conn.execute('''
                        INSERT INTO domains (id, app_id, domain, environment, is_www,
                            dns_label, ssl_enabled, password, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        domain.get('id', generate_id()),
                        app_id,
                        domain['domain'],
                        domain.get('environment', 'production'),
                        domain.get('is_www', 0),
                        domain.get('dns_label', '@'),
                        domain.get('ssl_enabled', 1),
                        domain.get('password'),
                        datetime.utcnow().isoformat(),
                        datetime.utcnow().isoformat()
                    ))
                    results['domains']['created'] += 1
                else:
                    results['domains']['skipped'] += 1
            except Exception as e:
                results['errors'].append(f"Domain {domain.get('domain')}: {str(e)}")
        
        # Import secrets
        secrets_data = config.get('secrets', {})
        if secrets_data.get('data'):
            for secret in secrets_data['data']:
                try:
                    existing = conn.execute('''
                        SELECT id FROM secrets WHERE app_id = ? AND key = ? AND scope = ?
                    ''', (secret['app_id'], secret['key'], secret['scope'])).fetchone()
                    
                    if existing and mode == 'merge':
                        conn.execute('''
                            UPDATE secrets SET value_encrypted = ?, updated_at = ?
                            WHERE app_id = ? AND key = ? AND scope = ?
                        ''', (
                            secret['value_encrypted'],
                            datetime.utcnow().isoformat(),
                            secret['app_id'],
                            secret['key'],
                            secret['scope']
                        ))
                        results['secrets']['updated'] += 1
                    elif not existing:
                        conn.execute('''
                            INSERT INTO secrets (id, app_id, key, value_encrypted, scope, description, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            secret.get('id', generate_id()),
                            secret['app_id'],
                            secret['key'],
                            secret['value_encrypted'],
                            secret['scope'],
                            secret.get('description', ''),
                            datetime.utcnow().isoformat(),
                            datetime.utcnow().isoformat()
                        ))
                        results['secrets']['created'] += 1
                    else:
                        results['secrets']['skipped'] += 1
                except Exception as e:
                    results['errors'].append(f"Secret {secret.get('key')}: {str(e)}")
        
        # Import servers
        for server in config.get('servers', []):
            try:
                existing = conn.execute('SELECT id FROM servers WHERE name = ?', (server['name'],)).fetchone()
                
                if existing and mode == 'merge':
                    conn.execute('''
                        UPDATE servers SET ip = ?, public_ip = ?, role = ?, specs_json = ?
                        WHERE name = ?
                    ''', (
                        server['ip'],
                        server.get('public_ip'),
                        server.get('role'),
                        json.dumps(server.get('specs', {})),
                        server['name']
                    ))
                    results['servers']['updated'] += 1
                elif not existing:
                    conn.execute('''
                        INSERT INTO servers (id, name, ip, public_ip, role, specs_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        server.get('id', generate_id()),
                        server['name'],
                        server['ip'],
                        server.get('public_ip'),
                        server.get('role'),
                        json.dumps(server.get('specs', {})),
                        datetime.utcnow().isoformat()
                    ))
                    results['servers']['created'] += 1
                else:
                    results['servers']['skipped'] += 1
            except Exception as e:
                results['errors'].append(f"Server {server.get('name')}: {str(e)}")
        
        conn.commit()
    
    results['success'] = len(results['errors']) == 0
    return results


# Sync status operations

def get_sync_status() -> Dict[str, Any]:
    """Get the current sync status."""
    with get_db() as conn:
        row = conn.execute('SELECT * FROM sync_status WHERE id = 1').fetchone()
        return dict(row) if row else {'auto_sync_enabled': 1}


def update_sync_status(updates: Dict[str, Any]) -> bool:
    """Update sync status."""
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [1]
    
    with get_db() as conn:
        conn.execute(f'UPDATE sync_status SET {set_clause} WHERE id = 1', values)
        conn.commit()
    
    return True


def record_sync_event(direction: str, status: str, gist_id: str = None, gist_version: str = None, details: str = None) -> str:
    """Record a sync event."""
    event_id = generate_id()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO sync_history (id, direction, status, gist_id, gist_version, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (event_id, direction, status, gist_id, gist_version, details, datetime.utcnow().isoformat()))
        conn.commit()
    
    return event_id


def get_sync_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get sync history."""
    with get_db() as conn:
        rows = conn.execute(
            'SELECT * FROM sync_history ORDER BY created_at DESC LIMIT ?',
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


# Settings operations

def get_setting(key: str, default: Any = None) -> Any:
    """Get a setting value."""
    with get_db() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        if row:
            try:
                return json.loads(row['value'])
            except:
                return row['value']
    return default


def set_setting(key: str, value: Any) -> bool:
    """Set a setting value."""
    value_str = json.dumps(value) if not isinstance(value, str) else value
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value_str, now))
        conn.commit()
    
    return True


# Initialize database on import
if os.path.exists(os.path.dirname(DATABASE_PATH)):
    init_database()