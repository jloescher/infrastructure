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
                "commit" TEXT,
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
            
            -- Services table (Phase 3 - add-on services)
            CREATE TABLE IF NOT EXISTS services (
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                type TEXT NOT NULL,
                environment TEXT NOT NULL,
                port INTEGER NOT NULL,
                server_ip TEXT,
                server_name TEXT,
                container_id TEXT,
                container_name TEXT,
                credentials_encrypted TEXT,
                volumes_json TEXT,
                memory_limit TEXT DEFAULT '256M',
                cpu_limit REAL DEFAULT 0.5,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE
            );
            
            -- Service backups table
            CREATE TABLE IF NOT EXISTS service_backups (
                id TEXT PRIMARY KEY,
                service_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                backup_path TEXT,
                success INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
            );
            
            -- Create indexes
            CREATE INDEX IF NOT EXISTS idx_domains_app ON domains(app_id);
            CREATE INDEX IF NOT EXISTS idx_secrets_app ON secrets(app_id);
            CREATE INDEX IF NOT EXISTS idx_deployments_app ON deployments(app_id);
            CREATE INDEX IF NOT EXISTS idx_deployment_steps_deployment ON deployment_steps(deployment_id);
            CREATE INDEX IF NOT EXISTS idx_services_app ON services(app_id);
            CREATE INDEX IF NOT EXISTS idx_services_type ON services(type);
            CREATE INDEX IF NOT EXISTS idx_service_backups_service ON service_backups(service_id);
            
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


def get_domain(domain_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a domain by ID.
    
    Args:
        domain_id: The domain ID
        
    Returns:
        Domain dictionary or None
    """
    with get_db() as conn:
        row = conn.execute('SELECT * FROM domains WHERE id = ?', (domain_id,)).fetchone()
        if row:
            return dict(row)
    return None


def get_domain_by_name(domain: str, environment: str = None) -> Optional[Dict[str, Any]]:
    """
    Get a domain by name and environment.
    
    Args:
        domain: Domain name
        environment: Optional environment filter
        
    Returns:
        Domain dictionary or None
    """
    with get_db() as conn:
        if environment:
            row = conn.execute(
                'SELECT * FROM domains WHERE domain = ? AND environment = ?',
                (domain, environment)
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT * FROM domains WHERE domain = ?',
                (domain,)
            ).fetchone()
        
        if row:
            return dict(row)
    return None


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


def get_server_by_name(server_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a server by name.
    
    Args:
        server_name: Server name
        
    Returns:
        Server dictionary or None if not found
    """
    with get_db() as conn:
        row = conn.execute('SELECT * FROM servers WHERE name = ?', (server_name,)).fetchone()
        
        if row:
            server = dict(row)
            if server.get('specs_json'):
                server['specs'] = json.loads(server['specs_json'])
            del server['specs_json']
            return server
    return None


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


# ============================================================================
# Enhanced Deployment Tracking (Phase 1 PaaS)
# ============================================================================

# Standard deployment step names
DEPLOYMENT_STEPS = [
    'git_fetch',
    'git_pull',
    'install_deps',
    'build_assets',
    'run_migrations',
    'clear_cache',
    'restart_services',
    'health_check'
]

# Deployment status values
DEPLOYMENT_STATUSES = ['pending', 'running', 'success', 'failed', 'cancelled', 'rollback']

# Step status values
STEP_STATUSES = ['pending', 'running', 'success', 'failed', 'skipped']


def create_deployment_step(deployment_id: str, server: str, step: str) -> str:
    """
    Create a new deployment step.
    
    Args:
        deployment_id: The deployment ID
        server: Server name (e.g., 're-db', 're-node-02')
        step: Step name from DEPLOYMENT_STEPS
        
    Returns:
        The step ID
    """
    step_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO deployment_steps (id, deployment_id, server, step, status, started_at)
            VALUES (?, ?, ?, ?, 'pending', ?)
        ''', (step_id, deployment_id, server, step, now))
        conn.commit()
    
    return step_id


def update_deployment_step(step_id: str, status: str, output: str = None, 
                           started_at: str = None, finished_at: str = None) -> bool:
    """
    Update a deployment step's status and details.
    
    Args:
        step_id: The step ID
        status: New status from STEP_STATUSES
        output: Command output or error message
        started_at: ISO timestamp when step started
        finished_at: ISO timestamp when step finished
        
    Returns:
        True if successful
    """
    updates = {'status': status}
    
    if output is not None:
        updates['output'] = output
    if started_at is not None:
        updates['started_at'] = started_at
    if finished_at is not None:
        updates['finished_at'] = finished_at
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [step_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE deployment_steps SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def get_deployment_steps(deployment_id: str) -> List[Dict[str, Any]]:
    """
    Get all steps for a deployment.
    
    Args:
        deployment_id: The deployment ID
        
    Returns:
        List of step dictionaries ordered by step order
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM deployment_steps 
            WHERE deployment_id = ? 
            ORDER BY 
                CASE step 
                    WHEN 'git_fetch' THEN 1
                    WHEN 'git_pull' THEN 2
                    WHEN 'install_deps' THEN 3
                    WHEN 'build_assets' THEN 4
                    WHEN 'run_migrations' THEN 5
                    WHEN 'clear_cache' THEN 6
                    WHEN 'restart_services' THEN 7
                    WHEN 'health_check' THEN 8
                    ELSE 99
                END,
                server
        ''', (deployment_id,)).fetchall()
        return [dict(row) for row in rows]


def get_deployment_progress(deployment_id: str) -> Dict[str, Any]:
    """
    Calculate deployment progress.
    
    Args:
        deployment_id: The deployment ID
        
    Returns:
        Dictionary with progress details:
        - total_steps: Total number of steps
        - completed_steps: Number of completed steps
        - failed_steps: Number of failed steps
        - progress_percent: Overall progress percentage
        - current_step: Current step name (or None if not running)
        - server_status: Per-server status breakdown
    """
    steps = get_deployment_steps(deployment_id)
    
    if not steps:
        return {
            'total_steps': 0,
            'completed_steps': 0,
            'failed_steps': 0,
            'progress_percent': 0,
            'current_step': None,
            'server_status': {}
        }
    
    total_steps = len(steps)
    completed_steps = sum(1 for s in steps if s['status'] == 'success')
    failed_steps = sum(1 for s in steps if s['status'] == 'failed')
    skipped_steps = sum(1 for s in steps if s['status'] == 'skipped')
    
    # Calculate progress (completed + skipped out of total)
    progress_percent = round(((completed_steps + skipped_steps) / total_steps) * 100, 1) if total_steps > 0 else 0
    
    # Find current running step
    running_step = next((s for s in steps if s['status'] == 'running'), None)
    current_step = running_step['step'] if running_step else None
    
    # Per-server status
    servers = {}
    for step in steps:
        server = step['server']
        if server not in servers:
            servers[server] = {
                'total': 0,
                'completed': 0,
                'failed': 0,
                'running': 0,
                'current_step': None
            }
        servers[server]['total'] += 1
        if step['status'] == 'success':
            servers[server]['completed'] += 1
        elif step['status'] == 'failed':
            servers[server]['failed'] += 1
        elif step['status'] == 'running':
            servers[server]['running'] += 1
            servers[server]['current_step'] = step['step']
    
    # Add per-server progress percent
    for server in servers:
        s = servers[server]
        s['progress_percent'] = round((s['completed'] / s['total']) * 100, 1) if s['total'] > 0 else 0
    
    return {
        'total_steps': total_steps,
        'completed_steps': completed_steps,
        'failed_steps': failed_steps,
        'skipped_steps': skipped_steps,
        'progress_percent': progress_percent,
        'current_step': current_step,
        'server_status': servers
    }


def get_active_deployments() -> List[Dict[str, Any]]:
    """
    Get all deployments with status 'pending' or 'running'.
    
    Returns:
        List of active deployment dictionaries with app info
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.status IN ('pending', 'running')
            ORDER BY d.deployed_at DESC
        ''').fetchall()
        
        deployments = []
        for row in rows:
            deployment = dict(row)
            deployment['progress'] = get_deployment_progress(deployment['id'])
            deployments.append(deployment)
        
        return deployments


def cleanup_old_deployment_steps(days: int = 30) -> int:
    """
    Remove steps for deployments older than N days.
    
    Args:
        days: Number of days to keep (default 30)
        
    Returns:
        Number of steps removed
    """
    cutoff = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        # Get deployments older than cutoff
        old_deployments = conn.execute('''
            SELECT id FROM deployments 
            WHERE datetime(deployed_at) < datetime('now', ? || ' days')
            AND status NOT IN ('pending', 'running')
        ''', (f'-{days}',)).fetchall()
        
        count = 0
        for row in old_deployments:
            cursor = conn.execute('DELETE FROM deployment_steps WHERE deployment_id = ?', (row['id'],))
            count += cursor.rowcount
        
        conn.commit()
    
    return count


# ============================================================================
# Deployment History Functions
# ============================================================================

def get_deployment_history(app_id: str = None, environment: str = None, 
                           limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get deployment history with optional filtering.
    
    Args:
        app_id: Filter by application ID (optional)
        environment: Filter by environment (optional)
        limit: Maximum number of results
        offset: Offset for pagination
        
    Returns:
        List of deployment dictionaries with app info
    """
    with get_db() as conn:
        if app_id and environment:
            rows = conn.execute('''
                SELECT d.*, a.name as app_name, a.display_name as app_display_name
                FROM deployments d
                JOIN applications a ON d.app_id = a.id
                WHERE d.app_id = ? AND d.environment = ?
                ORDER BY d.deployed_at DESC
                LIMIT ? OFFSET ?
            ''', (app_id, environment, limit, offset)).fetchall()
        elif app_id:
            rows = conn.execute('''
                SELECT d.*, a.name as app_name, a.display_name as app_display_name
                FROM deployments d
                JOIN applications a ON d.app_id = a.id
                WHERE d.app_id = ?
                ORDER BY d.deployed_at DESC
                LIMIT ? OFFSET ?
            ''', (app_id, limit, offset)).fetchall()
        else:
            rows = conn.execute('''
                SELECT d.*, a.name as app_name, a.display_name as app_display_name
                FROM deployments d
                JOIN applications a ON d.app_id = a.id
                ORDER BY d.deployed_at DESC
                LIMIT ? OFFSET ?
            ''', (limit, offset)).fetchall()
        
        deployments = []
        for row in rows:
            deployment = dict(row)
            if deployment.get('results_json'):
                deployment['results'] = json.loads(deployment['results_json'])
            del deployment['results_json']
            deployments.append(deployment)
        
        return deployments


def get_deployment_stats(app_id: str = None, environment: str = None, 
                         days: int = 30) -> Dict[str, Any]:
    """
    Get deployment statistics.
    
    Args:
        app_id: Filter by application ID (optional)
        environment: Filter by environment (optional)
        days: Number of days to analyze
        
    Returns:
        Dictionary with statistics:
        - total: Total deployments
        - successful: Successful deployments
        - failed: Failed deployments
        - success_rate: Success percentage
        - avg_duration_seconds: Average deployment duration
        - avg_duration_formatted: Human-readable duration
    """
    with get_db() as conn:
        if app_id and environment:
            rows = conn.execute('''
                SELECT status, deployed_at, finished_at
                FROM deployments
                WHERE app_id = ? AND environment = ?
                AND datetime(deployed_at) >= datetime('now', ? || ' days')
            ''', (app_id, environment, f'-{days}')).fetchall()
        elif app_id:
            rows = conn.execute('''
                SELECT status, deployed_at, finished_at
                FROM deployments
                WHERE app_id = ?
                AND datetime(deployed_at) >= datetime('now', ? || ' days')
            ''', (app_id, f'-{days}')).fetchall()
        else:
            rows = conn.execute('''
                SELECT status, deployed_at, finished_at
                FROM deployments
                WHERE datetime(deployed_at) >= datetime('now', ? || ' days')
            ''', (f'-{days}',)).fetchall()
        
        total = len(rows)
        if total == 0:
            return {
                'total': 0,
                'successful': 0,
                'failed': 0,
                'pending': 0,
                'running': 0,
                'success_rate': 0,
                'avg_duration_seconds': 0,
                'avg_duration_formatted': '0s'
            }
        
        successful = sum(1 for r in rows if r['status'] == 'success')
        failed = sum(1 for r in rows if r['status'] == 'failed')
        pending = sum(1 for r in rows if r['status'] == 'pending')
        running = sum(1 for r in rows if r['status'] == 'running')
        
        success_rate = round((successful / total) * 100, 1) if total > 0 else 0
        
        # Calculate average duration for completed deployments
        durations = []
        for row in rows:
            if row['status'] in ('success', 'failed') and row['deployed_at'] and row['finished_at']:
                try:
                    start = datetime.fromisoformat(row['deployed_at'])
                    end = datetime.fromisoformat(row['finished_at'])
                    durations.append((end - start).total_seconds())
                except (ValueError, TypeError):
                    pass
        
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # Format duration
        if avg_duration >= 3600:
            hours = int(avg_duration // 3600)
            minutes = int((avg_duration % 3600) // 60)
            avg_formatted = f"{hours}h {minutes}m"
        elif avg_duration >= 60:
            minutes = int(avg_duration // 60)
            seconds = int(avg_duration % 60)
            avg_formatted = f"{minutes}m {seconds}s"
        else:
            avg_formatted = f"{int(avg_duration)}s"
        
        return {
            'total': total,
            'successful': successful,
            'failed': failed,
            'pending': pending,
            'running': running,
            'success_rate': success_rate,
            'avg_duration_seconds': round(avg_duration, 1),
            'avg_duration_formatted': avg_formatted,
            'period_days': days
        }


def get_last_successful_deployment(app_id: str, environment: str) -> Optional[Dict[str, Any]]:
    """
    Get the last successful deployment for an app/environment.
    
    Args:
        app_id: Application ID
        environment: Environment name
        
    Returns:
        Deployment dictionary or None
    """
    with get_db() as conn:
        row = conn.execute('''
            SELECT d.*, a.name as app_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.app_id = ? AND d.environment = ? AND d.status = 'success'
            ORDER BY d.deployed_at DESC
            LIMIT 1
        ''', (app_id, environment)).fetchone()
        
        if row:
            deployment = dict(row)
            if deployment.get('results_json'):
                deployment['results'] = json.loads(deployment['results_json'])
            return deployment
    
    return None


# ============================================================================
# Real-time Status Tracking
# ============================================================================

def get_deployment_state(deployment_id: str) -> Optional[Dict[str, Any]]:
    """
    Get complete deployment state for WebSocket clients.
    
    Args:
        deployment_id: The deployment ID
        
    Returns:
        Dictionary with complete state:
        {
            'deployment': {...},
            'steps': [...],
            'progress': {...},
            'servers': {
                're-db': {'status': 'running', 'step': 'migrations', 'progress': 60},
                ...
            }
        }
    """
    with get_db() as conn:
        row = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.id = ?
        ''', (deployment_id,)).fetchone()
        
        if not row:
            return None
        
        deployment = dict(row)
        if deployment.get('results_json'):
            deployment['results'] = json.loads(deployment['results_json'])
        
    steps = get_deployment_steps(deployment_id)
    progress = get_deployment_progress(deployment_id)
    
    # Build server-centric view for real-time updates
    servers = {}
    for step in steps:
        server = step['server']
        if server not in servers:
            servers[server] = {
                'status': 'pending',
                'current_step': None,
                'progress': 0,
                'steps': {}
            }
        
        servers[server]['steps'][step['step']] = {
            'status': step['status'],
            'output': step['output'],
            'started_at': step['started_at'],
            'finished_at': step['finished_at']
        }
        
        # Update server-level status based on steps
        if step['status'] == 'running':
            servers[server]['status'] = 'running'
            servers[server]['current_step'] = step['step']
        elif step['status'] == 'failed':
            servers[server]['status'] = 'failed'
        elif step['status'] == 'success':
            servers[server]['status'] = 'running'  # Still running other steps
    
    # Calculate per-server progress
    for server, data in servers.items():
        total = len(data['steps'])
        completed = sum(1 for s in data['steps'].values() if s['status'] == 'success')
        data['progress'] = round((completed / total) * 100, 1) if total > 0 else 0
        
        # If all steps complete, mark server as success
        if all(s['status'] in ('success', 'skipped') for s in data['steps'].values()):
            data['status'] = 'success'
    
    return {
        'deployment': deployment,
        'steps': steps,
        'progress': progress,
        'servers': servers
    }


# ============================================================================
# Deployment Rollback Support
# ============================================================================

def get_rollback_target(app_id: str, environment: str) -> Optional[Dict[str, Any]]:
    """
    Get the deployment to rollback to (second-to-last successful).
    
    Args:
        app_id: Application ID
        environment: Environment name
        
    Returns:
        Deployment dictionary or None if no rollback target available
    """
    with get_db() as conn:
        # Get the last two successful deployments
        rows = conn.execute('''
            SELECT d.*, a.name as app_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.app_id = ? AND d.environment = ? AND d.status = 'success'
            ORDER BY d.deployed_at DESC
            LIMIT 2
        ''', (app_id, environment)).fetchall()
        
        # Return the second one (the one to rollback to)
        if len(rows) >= 2:
            deployment = dict(rows[1])
            if deployment.get('results_json'):
                deployment['results'] = json.loads(deployment['results_json'])
            return deployment
    
    return None


def create_rollback_deployment(original_deployment_id: str) -> str:
    """
    Create a new deployment record for a rollback operation.
    
    Args:
        original_deployment_id: The deployment ID to rollback to
        
    Returns:
        New deployment ID for the rollback
    """
    with get_db() as conn:
        # Get original deployment
        row = conn.execute(
            'SELECT * FROM deployments WHERE id = ?', 
            (original_deployment_id,)
        ).fetchone()
        
        if not row:
            raise ValueError(f"Deployment {original_deployment_id} not found")
        
        original = dict(row)
        
        # Create new deployment for rollback
        new_id = generate_id()
        now = datetime.utcnow().isoformat()
        
        conn.execute('''
            INSERT INTO deployments (id, app_id, environment, commit, branch, status, deployed_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
        ''', (
            new_id,
            original['app_id'],
            original['environment'],
            original['commit'],
            original['branch'],
            now
        ))
        
        # Store rollback reference in logs
        conn.execute('''
            UPDATE deployments SET logs = ? WHERE id = ?
        ''', (f'Rollback to deployment {original_deployment_id}', new_id))
        
        conn.commit()
    
    return new_id


def get_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a deployment by ID.
    
    Args:
        deployment_id: The deployment ID
        
    Returns:
        Deployment dictionary or None
    """
    with get_db() as conn:
        row = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.id = ?
        ''', (deployment_id,)).fetchone()
        
        if row:
            deployment = dict(row)
            if deployment.get('results_json'):
                deployment['results'] = json.loads(deployment['results_json'])
            return deployment
    
    return None


def count_deployments(app_id: str = None, status: str = None) -> int:
    """
    Count deployments with optional filters.
    
    Args:
        app_id: Filter by application ID (optional)
        status: Filter by status (optional)
        
    Returns:
        Count of matching deployments
    """
    with get_db() as conn:
        if app_id and status:
            row = conn.execute(
                'SELECT COUNT(*) as count FROM deployments WHERE app_id = ? AND status = ?',
                (app_id, status)
            ).fetchone()
        elif app_id:
            row = conn.execute(
                'SELECT COUNT(*) as count FROM deployments WHERE app_id = ?',
                (app_id,)
            ).fetchone()
        elif status:
            row = conn.execute(
                'SELECT COUNT(*) as count FROM deployments WHERE status = ?',
                (status,)
            ).fetchone()
        else:
            row = conn.execute('SELECT COUNT(*) as count FROM deployments').fetchone()
        
        return row['count'] if row else 0


# ============================================================================
# Phase 2: Deployment Hooks, Scheduling, Blue-Green Support
# ============================================================================

def init_phase2_schema():
    """
    Initialize Phase 2 schema additions.
    
    Adds:
    - deployment_hooks table
    - hook_executions table
    - scheduled_at and is_scheduled columns to deployments
    - slot and slot_path columns to deployments
    - notification settings
    """
    with get_db() as conn:
        # Deployment hooks table
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
        
        # Add scheduled_at column to deployments if not exists
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN scheduled_at TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Add is_scheduled column to deployments if not exists
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN is_scheduled INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        
        # Add slot column for blue-green deployments
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN slot TEXT')
        except sqlite3.OperationalError:
            pass
        
        # Add slot_path column
        try:
            conn.execute('ALTER TABLE deployments ADD COLUMN slot_path TEXT')
        except sqlite3.OperationalError:
            pass
        
        # Add deployment_mode column (standard, blue-green)
        try:
            conn.execute("ALTER TABLE deployments ADD COLUMN deployment_mode TEXT DEFAULT 'standard'")
        except sqlite3.OperationalError:
            pass
        
        # Create indexes for new tables
        conn.execute('CREATE INDEX IF NOT EXISTS idx_deployment_hooks_app ON deployment_hooks(app_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_hook_executions_hook ON hook_executions(hook_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_hook_executions_deployment ON hook_executions(deployment_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_deployments_scheduled ON deployments(scheduled_at) WHERE status = "scheduled"')
        
        # Initialize notification settings if not exists
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


def get_deployment_hooks(app_id: str, hook_type: str = None, 
                         environment: str = None, enabled_only: bool = True) -> List[Dict[str, Any]]:
    """
    Get deployment hooks for an application.
    
    Args:
        app_id: Application ID
        hook_type: Filter by hook type (optional)
        environment: Filter by environment (optional, None = all environments)
        enabled_only: Only return enabled hooks
        
    Returns:
        List of hook dictionaries
    """
    with get_db() as conn:
        query = 'SELECT * FROM deployment_hooks WHERE app_id = ?'
        params = [app_id]
        
        if hook_type:
            query += ' AND hook_type = ?'
            params.append(hook_type)
        
        if environment:
            query += ' AND (environment = ? OR environment IS NULL)'
            params.append(environment)
        
        if enabled_only:
            query += ' AND enabled = 1'
        
        query += ' ORDER BY created_at'
        
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


def create_deployment_hook(app_id: str, hook_type: str, command: str,
                           environment: str = None, timeout: int = 300,
                           enabled: bool = True) -> str:
    """
    Create a new deployment hook.
    
    Args:
        app_id: Application ID
        hook_type: One of 'pre_deploy', 'post_deploy', 'pre_rollback', 'post_rollback'
        command: Shell command to execute
        environment: 'production', 'staging', or None for all
        timeout: Timeout in seconds
        enabled: Whether hook is active
        
    Returns:
        Hook ID
    """
    hook_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO deployment_hooks 
            (id, app_id, hook_type, environment, command, timeout, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            hook_id, app_id, hook_type, environment, command,
            timeout, 1 if enabled else 0, now
        ))
        conn.commit()
    
    return hook_id


def update_deployment_hook(hook_id: str, updates: Dict[str, Any]) -> bool:
    """Update a deployment hook."""
    allowed_fields = ['hook_type', 'environment', 'command', 'timeout', 'enabled']
    updates = {k: v for k, v in updates.items() if k in allowed_fields}
    
    if not updates:
        return False
    
    if 'enabled' in updates:
        updates['enabled'] = 1 if updates['enabled'] else 0
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [hook_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE deployment_hooks SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def delete_deployment_hook(hook_id: str) -> bool:
    """Delete a deployment hook."""
    with get_db() as conn:
        conn.execute('DELETE FROM deployment_hooks WHERE id = ?', (hook_id,))
        conn.commit()
    return True


def get_hook_executions(deployment_id: str = None, hook_id: str = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get hook execution history.
    
    Args:
        deployment_id: Filter by deployment ID
        hook_id: Filter by hook ID
        limit: Maximum results
        
    Returns:
        List of execution records
    """
    with get_db() as conn:
        if deployment_id:
            rows = conn.execute('''
                SELECT he.*, h.command, h.hook_type
                FROM hook_executions he
                JOIN deployment_hooks h ON he.hook_id = h.id
                WHERE he.deployment_id = ?
                ORDER BY he.started_at DESC
                LIMIT ?
            ''', (deployment_id, limit)).fetchall()
        elif hook_id:
            rows = conn.execute('''
                SELECT he.*, h.command, h.hook_type
                FROM hook_executions he
                JOIN deployment_hooks h ON he.hook_id = h.id
                WHERE he.hook_id = ?
                ORDER BY he.started_at DESC
                LIMIT ?
            ''', (hook_id, limit)).fetchall()
        else:
            rows = conn.execute('''
                SELECT he.*, h.command, h.hook_type
                FROM hook_executions he
                JOIN deployment_hooks h ON he.hook_id = h.id
                ORDER BY he.started_at DESC
                LIMIT ?
            ''', (limit,)).fetchall()
        
        results = []
        for row in rows:
            result = dict(row)
            if result.get('servers_json'):
                result['servers'] = json.loads(result['servers_json'])
            del result['servers_json']
            results.append(result)
        
        return results


def create_hook_execution(hook_id: str, deployment_id: str, success: bool,
                          servers: Dict) -> str:
    """
    Record a hook execution.
    
    Args:
        hook_id: Hook ID
        deployment_id: Deployment ID
        success: Whether execution succeeded
        servers: Server execution results
        
    Returns:
        Execution ID
    """
    execution_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO hook_executions 
            (id, hook_id, deployment_id, success, servers_json, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            execution_id, hook_id, deployment_id, 1 if success else 0,
            json.dumps(servers), now, now
        ))
        conn.commit()
    
    return execution_id


def get_scheduled_deployments(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get all scheduled deployments.
    
    Args:
        limit: Maximum results
        
    Returns:
        List of scheduled deployments
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.status = 'scheduled'
            AND d.scheduled_at IS NOT NULL
            ORDER BY d.scheduled_at ASC
            LIMIT ?
        ''', (limit,)).fetchall()
        
        return [dict(row) for row in rows]


def get_upcoming_deployments(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Get deployments scheduled in the next N hours.
    
    Args:
        hours: Number of hours to look ahead
        
    Returns:
        List of upcoming deployments
    """
    now = datetime.utcnow()
    cutoff = now + __import__('datetime').timedelta(hours=hours)
    
    with get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name, a.display_name as app_display_name
            FROM deployments d
            JOIN applications a ON d.app_id = a.id
            WHERE d.status = 'scheduled'
            AND d.scheduled_at IS NOT NULL
            AND datetime(d.scheduled_at) BETWEEN datetime(?) AND datetime(?)
            ORDER BY d.scheduled_at ASC
        ''', (now.isoformat(), cutoff.isoformat())).fetchall()
        
        return [dict(row) for row in rows]


# ============================================================================
# Phase 3: Add-on Services CRUD Operations
# ============================================================================

def create_service(service_data: Dict[str, Any]) -> str:
    """
    Create a new service.
    
    Args:
        service_data: Service configuration dict
        
    Returns:
        Service ID
    """
    service_id = service_data.get('id', generate_id())
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO services 
            (id, app_id, type, environment, port, server_ip, server_name,
             container_id, container_name, credentials_encrypted, volumes_json,
             memory_limit, cpu_limit, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            service_id,
            service_data.get('app_id'),
            service_data.get('type'),
            service_data.get('environment'),
            service_data.get('port'),
            service_data.get('server_ip'),
            service_data.get('server_name'),
            service_data.get('container_id'),
            service_data.get('container_name'),
            service_data.get('credentials_encrypted'),
            service_data.get('volumes_json', '[]'),
            service_data.get('memory_limit', '256M'),
            service_data.get('cpu_limit', 0.5),
            service_data.get('status', 'pending'),
            now,
            now
        ))
        conn.commit()
    
    return service_id


def get_service(service_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a service by ID.
    
    Args:
        service_id: Service ID
        
    Returns:
        Service dict or None
    """
    with get_db() as conn:
        row = conn.execute('''
            SELECT s.*, a.name as app_name
            FROM services s
            JOIN applications a ON s.app_id = a.id
            WHERE s.id = ?
        ''', (service_id,)).fetchone()
        
        if row:
            service = dict(row)
            return service
    
    return None


def get_services_for_app(app_id: str, environment: str = None) -> List[Dict[str, Any]]:
    """
    Get all services for an application.
    
    Args:
        app_id: Application ID
        environment: Optional environment filter
        
    Returns:
        List of service dicts
    """
    with get_db() as conn:
        if environment:
            rows = conn.execute('''
                SELECT s.*, a.name as app_name
                FROM services s
                JOIN applications a ON s.app_id = a.id
                WHERE s.app_id = ? AND s.environment = ?
                ORDER BY s.type, s.environment
            ''', (app_id, environment)).fetchall()
        else:
            rows = conn.execute('''
                SELECT s.*, a.name as app_name
                FROM services s
                JOIN applications a ON s.app_id = a.id
                WHERE s.app_id = ?
                ORDER BY s.type, s.environment
            ''', (app_id,)).fetchall()
        
        return [dict(row) for row in rows]


def get_all_services() -> List[Dict[str, Any]]:
    """
    Get all services.
    
    Returns:
        List of all service dicts
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT s.*, a.name as app_name
            FROM services s
            JOIN applications a ON s.app_id = a.id
            ORDER BY s.created_at DESC
        ''').fetchall()
        
        return [dict(row) for row in rows]


def get_services_by_type(service_type: str) -> List[Dict[str, Any]]:
    """
    Get all services of a specific type.
    
    Args:
        service_type: Service type (redis, meilisearch, etc.)
        
    Returns:
        List of service dicts
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT s.*, a.name as app_name
            FROM services s
            JOIN applications a ON s.app_id = a.id
            WHERE s.type = ?
            ORDER BY s.created_at DESC
        ''', (service_type,)).fetchall()
        
        return [dict(row) for row in rows]


def update_service(service_id: str, updates: Dict[str, Any]) -> bool:
    """
    Update a service.
    
    Args:
        service_id: Service ID
        updates: Dict of fields to update
        
    Returns:
        True if successful
    """
    updates['updated_at'] = datetime.utcnow().isoformat()
    
    allowed_fields = [
        'status', 'container_id', 'container_name', 'server_ip', 
        'server_name', 'memory_limit', 'cpu_limit', 'credentials_encrypted',
        'updated_at'
    ]
    
    updates = {k: v for k, v in updates.items() if k in allowed_fields}
    
    if not updates:
        return False
    
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [service_id]
    
    with get_db() as conn:
        conn.execute(f'UPDATE services SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def delete_service(service_id: str) -> bool:
    """
    Delete a service.
    
    Args:
        service_id: Service ID
        
    Returns:
        True if successful
    """
    with get_db() as conn:
        conn.execute('DELETE FROM services WHERE id = ?', (service_id,))
        conn.commit()
    
    return True


def record_service_backup(backup_data: Dict[str, Any]) -> str:
    """
    Record a service backup.
    
    Args:
        backup_data: Backup metadata
        
    Returns:
        Backup ID
    """
    backup_id = generate_id()
    now = datetime.utcnow().isoformat()
    
    with get_db() as conn:
        conn.execute('''
            INSERT INTO service_backups 
            (id, service_id, timestamp, backup_path, success, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            backup_id,
            backup_data.get('service_id'),
            backup_data.get('timestamp', now),
            backup_data.get('backup_path'),
            1 if backup_data.get('success') else 0,
            now
        ))
        conn.commit()
    
    return backup_id


def get_service_backups(service_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get backup history for a service.
    
    Args:
        service_id: Service ID
        limit: Maximum number of backups to return
        
    Returns:
        List of backup dicts
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM service_backups
            WHERE service_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (service_id, limit)).fetchall()
        
        return [dict(row) for row in rows]


def get_services_for_export() -> List[Dict[str, Any]]:
    """
    Get all services for configuration export.
    
    Returns:
        List of service dicts (with credentials encrypted)
    """
    with get_db() as conn:
        rows = conn.execute('''
            SELECT s.*, a.name as app_name
            FROM services s
            JOIN applications a ON s.app_id = a.id
            ORDER BY s.app_id, s.type, s.environment
        ''').fetchall()
        
        return [dict(row) for row in rows]


# Initialize database on import
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
init_database()
init_phase2_schema()