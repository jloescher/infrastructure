"""
GitHub Gist sync service for configuration backup.

This module handles:
- Syncing PaaS configuration to a private GitHub Gist
- Restoring configuration from Gist
- Version history management
- Auto-sync with debouncing
"""

import os
import json
import time
import threading
import requests
from datetime import datetime
from typing import Optional, Dict, Any, List

# Import database functions
from database import (
    export_configuration, import_configuration,
    get_sync_status, update_sync_status, record_sync_event, get_sync_history,
    get_setting, set_setting
)


GITHUB_API_BASE = 'https://api.github.com'
GIST_FILENAME = 'quantyra-paas-config.json'


class GistSyncService:
    """Service for syncing PaaS configuration to GitHub Gist."""
    
    def __init__(self, github_token: str = None, gist_id: str = None):
        self.github_token = github_token or os.environ.get('GITHUB_TOKEN') or get_setting('github_token')
        self.gist_id = gist_id or os.environ.get('GIST_ID') or get_setting('gist_id')
        self._sync_timer = None
        self._sync_lock = threading.Lock()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get GitHub API headers."""
        return {
            'Authorization': f'token {self.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'Content-Type': 'application/json'
        }
    
    def create_gist(self) -> Dict[str, Any]:
        """Create a new private Gist with current configuration."""
        if not self.github_token:
            return {'success': False, 'error': 'GitHub token not configured'}
        
        config = export_configuration()
        config_json = json.dumps(config, indent=2)
        
        payload = {
            'description': 'Quantyra PaaS Configuration Backup',
            'public': False,
            'files': {
                GIST_FILENAME: {
                    'content': config_json
                }
            }
        }
        
        try:
            response = requests.post(
                f'{GITHUB_API_BASE}/gists',
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 201:
                gist = response.json()
                gist_id = gist['id']
                
                # Save gist ID
                set_setting('gist_id', gist_id)
                update_sync_status({
                    'gist_id': gist_id,
                    'gist_url': gist['html_url'],
                    'gist_version': gist['history'][0]['version'] if gist.get('history') else None,
                    'last_sync_at': datetime.utcnow().isoformat(),
                    'last_sync_status': 'success'
                })
                
                record_sync_event('export', 'success', gist_id=gist_id, 
                                  gist_version=gist.get('history', [{}])[0].get('version'))
                
                return {
                    'success': True,
                    'gist_id': gist_id,
                    'gist_url': gist['html_url']
                }
            else:
                error_msg = response.json().get('message', 'Unknown error')
                record_sync_event('export', 'failed', details=error_msg)
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            record_sync_event('export', 'failed', details=str(e))
            return {'success': False, 'error': str(e)}
    
    def update_gist(self) -> Dict[str, Any]:
        """Update existing Gist with current configuration."""
        if not self.github_token:
            return {'success': False, 'error': 'GitHub token not configured'}
        
        if not self.gist_id:
            # Create new gist if none exists
            return self.create_gist()
        
        config = export_configuration()
        config_json = json.dumps(config, indent=2)
        
        payload = {
            'description': 'Quantyra PaaS Configuration Backup',
            'files': {
                GIST_FILENAME: {
                    'content': config_json
                }
            }
        }
        
        try:
            response = requests.patch(
                f'{GITHUB_API_BASE}/gists/{self.gist_id}',
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                gist = response.json()
                
                update_sync_status({
                    'gist_url': gist['html_url'],
                    'gist_version': gist['history'][0]['version'] if gist.get('history') else None,
                    'last_sync_at': datetime.utcnow().isoformat(),
                    'last_sync_status': 'success'
                })
                
                record_sync_event('gist_sync', 'success', gist_id=self.gist_id,
                                  gist_version=gist.get('history', [{}])[0].get('version'))
                
                return {
                    'success': True,
                    'gist_id': self.gist_id,
                    'gist_url': gist['html_url'],
                    'version': gist['history'][0]['version'] if gist.get('history') else None
                }
            else:
                error_msg = response.json().get('message', 'Unknown error')
                update_sync_status({'last_sync_status': 'failed'})
                record_sync_event('gist_sync', 'failed', gist_id=self.gist_id, details=error_msg)
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            update_sync_status({'last_sync_status': 'failed'})
            record_sync_event('gist_sync', 'failed', gist_id=self.gist_id, details=str(e))
            return {'success': False, 'error': str(e)}
    
    def get_gist_versions(self) -> List[Dict[str, Any]]:
        """Get version history of the Gist."""
        if not self.github_token or not self.gist_id:
            return []
        
        try:
            response = requests.get(
                f'{GITHUB_API_BASE}/gists/{self.gist_id}/commits',
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                versions = []
                for commit in response.json():
                    versions.append({
                        'version': commit['version'],
                        'committed_at': commit['committed_at'],
                        'url': commit['url']
                    })
                return versions
            return []
            
        except Exception:
            return []
    
    def get_gist_content(self, version: str = None) -> Optional[Dict[str, Any]]:
        """Get Gist content, optionally at a specific version."""
        if not self.github_token or not self.gist_id:
            return None
        
        try:
            url = f'{GITHUB_API_BASE}/gists/{self.gist_id}'
            if version:
                url = f'{GITHUB_API_BASE}/gists/{self.gist_id}/{version}'
            
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=30
            )
            
            if response.status_code == 200:
                gist = response.json()
                content = gist['files'].get(GIST_FILENAME, {}).get('content')
                if content:
                    return json.loads(content)
            return None
            
        except Exception:
            return None
    
    def restore_from_gist(self, version: str = None, mode: str = 'merge') -> Dict[str, Any]:
        """Restore configuration from Gist."""
        if not self.gist_id:
            return {'success': False, 'error': 'No Gist ID configured'}
        
        config = self.get_gist_content(version)
        if not config:
            return {'success': False, 'error': 'Could not fetch Gist content'}
        
        result = import_configuration(config, mode)
        
        record_sync_event('import', 'success' if result['success'] else 'failed',
                          gist_id=self.gist_id, gist_version=version,
                          details=json.dumps(result) if not result['success'] else None)
        
        return result
    
    def sync(self) -> Dict[str, Any]:
        """Sync current configuration to Gist."""
        with self._sync_lock:
            if self.gist_id:
                return self.update_gist()
            else:
                return self.create_gist()
    
    def schedule_sync(self, delay_seconds: int = 5):
        """Schedule a sync after a delay (debounce)."""
        with self._sync_lock:
            # Cancel existing timer
            if self._sync_timer:
                self._sync_timer.cancel()
            
            # Schedule new sync
            self._sync_timer = threading.Timer(delay_seconds, self._sync)
            self._sync_timer.daemon = True
            self._sync_timer.start()
    
    def cancel_scheduled_sync(self):
        """Cancel any scheduled sync."""
        with self._sync_lock:
            if self._sync_timer:
                self._sync_timer.cancel()
                self._sync_timer = None


# Global sync service instance
_sync_service: Optional[GistSyncService] = None


def get_sync_service() -> GistSyncService:
    """Get or create the global sync service."""
    global _sync_service
    if _sync_service is None:
        _sync_service = GistSyncService()
    return _sync_service


def trigger_sync(delay: int = 5):
    """Trigger a sync after a delay (called on config changes)."""
    sync_status = get_sync_status()
    if sync_status.get('auto_sync_enabled'):
        service = get_sync_service()
        service.schedule_sync(delay)


# Decorator to trigger sync after function execution
def sync_after(func):
    """Decorator that triggers sync after function execution."""
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        trigger_sync()
        return result
    return wrapper