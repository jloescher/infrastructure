"""
SSL certificate management tasks.

Phase 4 automation for:
- SSL certificate expiration monitoring
- Auto-renewal of certificates expiring within 30 days
- Alert notifications for SSL issues
"""

import os
import sys
import subprocess
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tasks import celery_app
import database as db

# Router IPs for SSL certificate checking
ROUTER_IPS = [
    os.environ.get('ROUTER_01_IP', '100.102.220.16'),
    os.environ.get('ROUTER_02_IP', '100.116.175.9'),
]

# Renewal threshold in days
SSL_RENEWAL_THRESHOLD = 30

# Warning thresholds
SSL_WARNING_THRESHOLD = 14  # Days before expiration to send warning
SSL_CRITICAL_THRESHOLD = 7  # Days before expiration to send critical alert


@celery_app.task
def check_ssl_expiration() -> Dict:
    """
    Check all domains for SSL certificate expiration.
    Renew certificates expiring within 30 days.
    
    This task runs twice daily (configured in Celery Beat).
    It:
    1. Gets all provisioned domains with SSL enabled
    2. Checks expiration date of each certificate
    3. Stores expiration info in database
    4. Renews certificates expiring within threshold
    5. Sends alerts for issues
    
    Returns:
        Dictionary with check results
    """
    results = {
        'checked': 0,
        'renewed': 0,
        'warnings': 0,
        'errors': [],
        'started_at': datetime.utcnow().isoformat()
    }
    
    try:
        # Get all domains with SSL enabled
        domains = get_ssl_enabled_domains()
        
        for domain in domains:
            domain_name = domain['domain']
            results['checked'] += 1
            
            try:
                # Check expiration via remote router
                cert_info = check_certificate_expiration(domain_name)
                
                if cert_info and cert_info.get('expires_at'):
                    expires_at = datetime.fromisoformat(cert_info['expires_at'])
                    days_remaining = (expires_at - datetime.utcnow()).days
                    
                    # Update domain with SSL info
                    update_domain_ssl_info(domain['id'], {
                        'ssl_expires_at': cert_info['expires_at'],
                        'ssl_days_remaining': days_remaining,
                        'ssl_issuer': cert_info.get('issuer'),
                        'ssl_last_checked': datetime.utcnow().isoformat()
                    })
                    
                    # Check for warnings
                    if days_remaining <= SSL_CRITICAL_THRESHOLD:
                        results['warnings'] += 1
                        send_ssl_alert(domain_name, days_remaining, 'critical')
                    
                    elif days_remaining <= SSL_WARNING_THRESHOLD:
                        results['warnings'] += 1
                        send_ssl_alert(domain_name, days_remaining, 'warning')
                    
                    # Auto-renew if within threshold
                    if days_remaining <= SSL_RENEWAL_THRESHOLD:
                        renew_result = renew_certificate(domain_name)
                        
                        if renew_result['success']:
                            results['renewed'] += 1
                            
                            # Log renewal
                            log_ssl_event(domain_name, 'renewed', {
                                'previous_expiration': cert_info['expires_at'],
                                'renewed_at': datetime.utcnow().isoformat()
                            })
                        else:
                            results['errors'].append({
                                'domain': domain_name,
                                'error': renew_result.get('error', 'Unknown renewal error'),
                                'type': 'renewal_failed'
                            })
                            
                            # Send alert for renewal failure
                            send_ssl_alert(domain_name, days_remaining, 'renewal_failed', 
                                         renew_result.get('error'))
                
            except Exception as e:
                results['errors'].append({
                    'domain': domain_name,
                    'error': str(e),
                    'type': 'check_failed'
                })
        
        # Send summary alert if there are errors
        if results['errors']:
            send_ssl_summary_alert(results)
        
        results['success'] = True
        results['finished_at'] = datetime.utcnow().isoformat()
        
        print(f"[{datetime.utcnow().isoformat()}] SSL check complete: "
              f"checked={results['checked']}, renewed={results['renewed']}, "
              f"warnings={results['warnings']}, errors={len(results['errors'])}")
        
        return results
        
    except Exception as e:
        results['success'] = False
        results['error'] = str(e)
        results['finished_at'] = datetime.utcnow().isoformat()
        return results


@celery_app.task
def check_ssl_expiration_remote(router_ip: str) -> Dict:
    """
    Check SSL certificates on a specific remote router.
    
    Args:
        router_ip: IP address of the router to check
        
    Returns:
        Dictionary with check results
    """
    results = {
        'router': router_ip,
        'certificates': [],
        'errors': []
    }
    
    try:
        # Get list of certificates from router
        cmd = f"ssh root@{router_ip} 'certbot certificates 2>/dev/null'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            # Parse certbot output
            certificates = parse_certbot_output(result.stdout)
            results['certificates'] = certificates
        else:
            results['errors'].append(f"Failed to list certificates: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        results['errors'].append(f"Timeout connecting to {router_ip}")
    except Exception as e:
        results['errors'].append(str(e))
    
    return results


@celery_app.task
def renew_certificate(domain: str) -> Dict:
    """
    Renew SSL certificate for a domain.
    
    Args:
        domain: Domain name to renew certificate for
        
    Returns:
        Dictionary with renewal result
    """
    # Try renewal on both routers
    results = []
    
    for router_ip in ROUTER_IPS:
        try:
            # Use DNS-01 challenge for Cloudflare proxied domains
            cmd = f"ssh root@{router_ip} 'certbot renew --cert-name {domain} --non-interactive --quiet'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Reload HAProxy to pick up new certificate
                reload_cmd = f"ssh root@{router_ip} 'systemctl reload haproxy'"
                subprocess.run(reload_cmd, shell=True, capture_output=True, text=True, timeout=30)
                
                results.append({
                    'router': router_ip,
                    'success': True
                })
            else:
                results.append({
                    'router': router_ip,
                    'success': False,
                    'error': result.stderr or result.stdout
                })
                
        except subprocess.TimeoutExpired:
            results.append({
                'router': router_ip,
                'success': False,
                'error': 'Timeout during renewal'
            })
        except Exception as e:
            results.append({
                'router': router_ip,
                'success': False,
                'error': str(e)
            })
    
    # Success if at least one router succeeded
    success = any(r['success'] for r in results)
    
    return {
        'success': success,
        'domain': domain,
        'results': results,
        'renewed_at': datetime.utcnow().isoformat() if success else None
    }


@celery_app.task
def force_renew_all_certificates() -> Dict:
    """
    Force renewal of all certificates (emergency use).
    
    Returns:
        Dictionary with renewal results
    """
    results = {
        'renewed': 0,
        'failed': 0,
        'domains': []
    }
    
    domains = get_ssl_enabled_domains()
    
    for domain in domains:
        domain_name = domain['domain']
        renew_result = renew_certificate(domain_name)
        
        if renew_result['success']:
            results['renewed'] += 1
            results['domains'].append({
                'domain': domain_name,
                'status': 'renewed'
            })
        else:
            results['failed'] += 1
            results['domains'].append({
                'domain': domain_name,
                'status': 'failed',
                'error': renew_result.get('error')
            })
    
    return results


def check_certificate_expiration(domain: str) -> Optional[Dict]:
    """
    Check SSL certificate expiration for a domain.
    
    Uses multiple methods to check:
    1. Direct SSL connection check
    2. certbot certificates command on routers
    
    Args:
        domain: Domain name to check
        
    Returns:
        Dictionary with certificate info or None
    """
    # Try direct SSL check first
    try:
        result = subprocess.run([
            'openssl', 's_client', '-servername', domain,
            '-connect', f'{domain}:443'
        ], input=b'', capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Get certificate details
            cert_result = subprocess.run([
                'openssl', 'x509', '-noout', '-dates', '-issuer'
            ], input=result.stdout.encode(), capture_output=True, text=True, timeout=10)
            
            if cert_result.returncode == 0:
                info = parse_openssl_output(cert_result.stdout)
                return info
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass
    
    # Fallback: check via router
    for router_ip in ROUTER_IPS:
        try:
            # Use certbot to check certificate dates
            cmd = f"ssh root@{router_ip} 'certbot certificates --cert-name {domain} 2>/dev/null'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                certs = parse_certbot_output(result.stdout)
                if certs:
                    # Return first matching cert
                    for cert in certs:
                        if domain in cert.get('domains', []):
                            return cert
        except Exception:
            continue
    
    return None


def parse_openssl_output(output: str) -> Dict:
    """
    Parse openssl x509 output.
    
    Args:
        output: Output from openssl x509 -noout -dates -issuer
        
    Returns:
        Dictionary with certificate info
    """
    info = {}
    
    # Parse notAfter date
    match = re.search(r'notAfter=(.+)', output)
    if match:
        date_str = match.group(1).strip()
        try:
            # Parse date format: "Mar 26 12:00:00 2026 GMT"
            expires_at = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z')
            info['expires_at'] = expires_at.isoformat()
            info['days_remaining'] = (expires_at - datetime.utcnow()).days
        except ValueError:
            pass
    
    # Parse notBefore date
    match = re.search(r'notBefore=(.+)', output)
    if match:
        date_str = match.group(1).strip()
        try:
            info['valid_from'] = datetime.strptime(date_str, '%b %d %H:%M:%S %Y %Z').isoformat()
        except ValueError:
            pass
    
    # Parse issuer
    match = re.search(r'issuer=(.+)', output)
    if match:
        info['issuer'] = match.group(1).strip()
    
    return info


def parse_certbot_output(output: str) -> List[Dict]:
    """
    Parse certbot certificates output.
    
    Args:
        output: Output from certbot certificates command
        
    Returns:
        List of certificate dictionaries
    """
    certificates = []
    current_cert = {}
    
    for line in output.split('\n'):
        line = line.strip()
        
        if line.startswith('Certificate Name:'):
            if current_cert:
                certificates.append(current_cert)
            current_cert = {'name': line.split(':', 1)[1].strip()}
        
        elif line.startswith('Domains:'):
            current_cert['domains'] = [d.strip() for d in line.split(':', 1)[1].split()]
        
        elif line.startswith('Expiry Date:'):
            # Parse: "Expiry Date: 2026-03-26 12:00:00+00:00 (VALID: 89 days)"
            match = re.match(r'Expiry Date: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2})', line)
            if match:
                try:
                    expires_at = datetime.fromisoformat(match.group(1))
                    current_cert['expires_at'] = expires_at.isoformat()
                    
                    # Parse days remaining
                    days_match = re.search(r'\(VALID:\s*(\d+)\s*days?\)', line)
                    if days_match:
                        current_cert['days_remaining'] = int(days_match.group(1))
                except ValueError:
                    pass
    
    if current_cert:
        certificates.append(current_cert)
    
    return certificates


def get_ssl_enabled_domains() -> List[Dict]:
    """
    Get all domains with SSL enabled.
    
    Returns:
        List of domain dictionaries
    """
    with db.get_db() as conn:
        rows = conn.execute('''
            SELECT d.*, a.name as app_name
            FROM domains d
            JOIN applications a ON d.app_id = a.id
            WHERE d.ssl_enabled = 1
            AND d.provisioned = 1
            ORDER BY d.domain
        ''').fetchall()
        
        return [dict(row) for row in rows]


def update_domain_ssl_info(domain_id: str, ssl_info: Dict) -> bool:
    """
    Update domain with SSL information.
    
    Args:
        domain_id: Domain ID
        ssl_info: SSL information dictionary
        
    Returns:
        True if successful
    """
    # Add ssl_days_remaining column if not exists
    try:
        with db.get_db() as conn:
            conn.execute('ALTER TABLE domains ADD COLUMN ssl_days_remaining INTEGER')
            conn.commit()
    except:
        pass  # Column already exists
    
    try:
        with db.get_db() as conn:
            conn.execute('ALTER TABLE domains ADD COLUMN ssl_issuer TEXT')
            conn.commit()
    except:
        pass
    
    try:
        with db.get_db() as conn:
            conn.execute('ALTER TABLE domains ADD COLUMN ssl_last_checked TEXT')
            conn.commit()
    except:
        pass
    
    # Update domain
    set_clause = ', '.join(f'{k} = ?' for k in ssl_info.keys())
    values = list(ssl_info.values()) + [domain_id]
    
    with db.get_db() as conn:
        conn.execute(f'UPDATE domains SET {set_clause} WHERE id = ?', values)
        conn.commit()
    
    return True


def log_ssl_event(domain: str, event_type: str, details: Dict) -> str:
    """
    Log an SSL-related event.
    
    Args:
        domain: Domain name
        event_type: Type of event (checked, renewed, warning, error)
        details: Event details
        
    Returns:
        Event ID
    """
    # Ensure ssl_events table exists
    with db.get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ssl_events (
                id TEXT PRIMARY KEY,
                domain TEXT NOT NULL,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    
    event_id = db.generate_id()
    
    with db.get_db() as conn:
        conn.execute('''
            INSERT INTO ssl_events (id, domain, event_type, details, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (event_id, domain, event_type, str(details), datetime.utcnow().isoformat()))
        conn.commit()
    
    return event_id


def send_ssl_alert(domain: str, days_remaining: int, severity: str, 
                   error: str = None) -> None:
    """
    Send SSL alert notification.
    
    Args:
        domain: Domain name
        days_remaining: Days until expiration
        severity: Alert severity (warning, critical, renewal_failed)
        error: Optional error message
    """
    from services.notifications import NotificationService
    
    severity_emoji = {
        'warning': '⚠️',
        'critical': '🚨',
        'renewal_failed': '❌'
    }
    
    emoji = severity_emoji.get(severity, '⚠️')
    
    if error:
        message = f"""
{emoji} SSL Certificate Alert - {severity.upper()}

Domain: {domain}
Days Remaining: {days_remaining}
Error: {error}

Action required: Please check the SSL certificate status.
"""
    else:
        message = f"""
{emoji} SSL Certificate Alert - {severity.upper()}

Domain: {domain}
Days Remaining: {days_remaining}

Action required: Certificate will expire soon.
"""
    
    # Send via notification service
    NotificationService._send_notifications({
        'title': f'{emoji} SSL Alert: {domain}',
        'domain': domain,
        'days_remaining': days_remaining,
        'severity': severity,
        'error': error,
        'timestamp': datetime.utcnow().isoformat()
    }, f'ssl_{severity}')


def send_ssl_summary_alert(results: Dict) -> None:
    """
    Send summary alert for SSL check run.
    
    Args:
        results: Check results dictionary
    """
    from services.notifications import NotificationService
    
    message = f"""
⚠️ SSL Certificate Check Summary

Checked: {results['checked']} domains
Renewed: {results['renewed']} certificates
Warnings: {results['warnings']}
Errors: {len(results['errors'])}

Failed checks:
{chr(10).join(f"  - {e['domain']}: {e['error']}" for e in results['errors'][:10])}
"""
    
    NotificationService._send_notifications({
        'title': '⚠️ SSL Check Summary',
        'summary': message,
        'results': results,
        'timestamp': datetime.utcnow().isoformat()
    }, 'ssl_summary')


# Register with Celery Beat
CELERYBEAT_SCHEDULE = {
    'check-ssl-expiration': {
        'task': 'tasks.ssl.check_ssl_expiration',
        'schedule': 43200.0,  # Every 12 hours
    }
}