# PaaS UX Design Guide

> User experience patterns and product design based on Coolify analysis, adapted for Quantyra infrastructure.

## Overview

This document outlines UX patterns, navigation structure, and feature design for the enhanced PaaS dashboard. The goal is to create an intuitive interface for managing multi-application deployments while maintaining the simplicity of the current infrastructure.

## Navigation Structure

### Information Architecture

```
Dashboard
├── Overview (Home)
│   ├── Cluster Health
│   ├── Active Deployments
│   ├── Recent Activity
│   └── Quick Actions
│
├── Applications
│   ├── Application List
│   ├── Create Application (+)
│   └── [Application Detail]
│       ├── Overview
│       ├── Deployments
│       ├── Domains
│       ├── Secrets
│       ├── Databases
│       ├── Logs
│       └── Settings
│
├── Servers
│   ├── Server List
│   └── [Server Detail]
│       ├── Metrics
│       ├── Services
│       ├── Logs
│       └── Packages
│
├── Databases
│   ├── Database List
│   ├── Create Database (+)
│   └── [Database Detail]
│       ├── Tables
│       ├── Query
│       └── Backups
│
├── Monitoring
│   ├── Alerts
│   ├── Metrics Explorer
│   └── Dashboards (Grafana)
│
└── Settings
    ├── Cloudflare
    ├── GitHub
    ├── SSL Certificates
    └── Backups
```

### Navigation Patterns from Coolify

| Pattern | Coolify Approach | Quantyra Adaptation |
|---------|------------------|---------------------|
| Project → Environment → Resource | Hierarchical drill-down | App → Environment → Deployments |
| Sidebar Navigation | Collapsible with icons | Same pattern |
| Breadcrumb Trail | Show current location | Same pattern |
| Quick Actions | Floating action button | Same pattern |
| Search | Global search (Cmd+K) | Same pattern |

## Resource-Centric Mental Model

### Core Concept

Users think in terms of **resources** (applications, databases, domains) rather than infrastructure components. The UI should reflect this mental model.

```mermaid
graph TB
    subgraph "User Mental Model"
        A[Application] --> B[Production]
        A --> C[Staging]
        B --> D[Domains]
        B --> E[Database]
        B --> F[Secrets]
        C --> G[Domains]
        C --> H[Database]
        C --> I[Secrets]
    end
    
    subgraph "Infrastructure Mapping"
        D --> J[HAProxy + Cloudflare]
        E --> K[PostgreSQL]
        F --> L[SOPS Encryption]
    end
```

### Application Detail View

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Applications > rentalfixer                                    [Edit]  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─ Production ──────────────────────────────────────────────────────┐  │
│  │ Status: ● Running     Commit: a1b2c3d     Deployed: 2 hours ago   │  │
│  │                                                                     │  │
│  │ [Deploy] [Rollback] [Restart] [Logs]                               │  │
│  │                                                                     │  │
│  │ Domains:                                                            │  │
│  │   ● rentalfixer.app (SSL valid, expires in 60 days)               │  │
│  │   ● www.rentalfixer.app → redirects to rentalfixer.app            │  │
│  │                                                                     │  │
│  │ Database: rentalfixer_prod (120 MB)                                │  │
│  │ Secrets: 12 configured                                              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─ Staging ─────────────────────────────────────────────────────────┐  │
│  │ Status: ● Running     Commit: e4f5g6h     Deployed: 30 mins ago   │  │
│  │                                                                     │  │
│  │ [Deploy] [Rollback] [Restart] [Logs]                               │  │
│  │                                                                     │  │
│  │ Domains:                                                            │  │
│  │   ● staging.rentalfixer.app (password protected)                  │  │
│  │     Password: admin / ••••••••  [Copy] [Regenerate]               │  │
│  │                                                                     │  │
│  │ Database: rentalfixer_staging (45 MB)                              │  │
│  │ Secrets: 8 configured (2 staging-only)                             │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌─ Deployment History ──────────────────────────────────────────────┐  │
│  │ ● a1b2c3d  production  2 hours ago   ✓ Success   [View Logs]      │  │
│  │ ● e4f5g6h  staging      30 mins ago  ✓ Success   [View Logs]      │  │
│  │ ● b2c3d4e  production   1 day ago    ✗ Failed   [View Logs]       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Onboarding Flow

### New Application Wizard

The wizard guides users through creating a complete application stack.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Create Application                                               1/5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 1: Framework Selection                                           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │   Laravel   │  │   Next.js   │  │   Svelte    │  │   Python    │   │
│  │     🔧      │  │     ⚡      │  │     🔥      │  │     🐍      │   │
│  │   [SELECT]  │  │             │  │             │  │             │   │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
│                                                                         │
│  ┌─────────────┐                                                       │
│  │     Go      │                                                       │
│  │     🐹      │                                                       │
│  │             │                                                       │
│  └─────────────┘                                                       │
│                                                                         │
│                                              [Cancel]  [Next Step →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Create Application                                               2/5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 2: Application Details                                           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                         │
│  Framework: Laravel ✓                                                  │
│                                                                         │
│  Application Name *                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ my-awesome-app                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  Used for: deploy path, database name, service names                  │
│                                                                         │
│  Display Name                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ My Awesome App                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Description                                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ A Laravel application for...                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Git Repository *                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ https://github.com/owner/repo                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  [Validate Repository]                                                  │
│                                                                         │
│  ☑ Create staging environment                                          │
│                                                                         │
│                                              [← Back]  [Next Step →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Create Application                                               3/5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 3: Build Configuration                                           │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                         │
│  Build commands (auto-detected from Laravel framework):                │
│                                                                         │
│  Install Dependencies                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ composer install --no-interaction --optimize-autoloader         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Build Assets                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ npm run build                                                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Database Migrations                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ php artisan migrate --force                                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Health Check Path                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ /                                                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  [ ] Customize (use custom commands)                                   │
│                                                                         │
│                                              [← Back]  [Next Step →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Create Application                                               4/5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 4: Database Configuration                                        │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                         │
│  ☑ Create PostgreSQL database for this application                     │
│                                                                         │
│  Production Database                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Database: my-awesome-app_prod                                    │   │
│  │ User: my-awesome-app_user                                        │   │
│  │ Admin User: my-awesome-app_admin                                 │   │
│  │ Password: [Auto-generate] 🔒                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ☑ Create staging database                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Database: my-awesome-app_staging                                 │   │
│  │ User: my-awesome-app_staging_user                                │   │
│  │ Password: [Auto-generate] 🔒                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Connection String Preview                                             │
│  postgres://my-awesome-app_user:***@100.102.220.16:5000/my-awesome-app_prod
│                                                                         │
│                                              [← Back]  [Next Step →]    │
└─────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Create Application                                               5/5  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Step 5: Domain Configuration                                         │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                                         │
│  Select domains from Cloudflare zones:                                 │
│                                                                         │
│  Search zones...                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 🔍 rentalfixer                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ☑ rentalfixer.app                                                    │
│    Production: ☑ root domain (rentalfixer.app)                        │
│    ☑ WWW redirect (www.rentalfixer.app → rentalfixer.app)             │
│    Staging: ☑ staging.rentalfixer.app                                 │
│    Password: [Auto-generate] 🔒                                        │
│                                                                         │
│  ☑ example.com                                                        │
│    Production: ☐ root domain  ☑ subdomain: [api] .example.com         │
│    Staging: ☐ staging.example.com                                     │
│                                                                         │
│  DNS Records to Create:                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ A    rentalfixer.app          → 172.93.54.112, 23.29.118.6     │   │
│  │ A    www.rentalfixer.app      → 172.93.54.112, 23.29.118.6     │   │
│  │ A    staging.rentalfixer.app  → 172.93.54.112, 23.29.118.6     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│                                              [← Back]  [Create App]     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Empty States

Empty states guide users when there's no content to display.

### No Applications

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Applications                                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                   │   │
│  │                         📦                                        │   │
│  │                                                                   │   │
│  │              No applications yet                                  │   │
│  │                                                                   │   │
│  │     Deploy your first application to get started.               │   │
│  │                                                                   │   │
│  │              [+ Create Application]                              │   │
│  │                                                                   │   │
│  │     Or check out the docs:                                       │   │
│  │     • Getting Started Guide                                      │   │
│  │     • Deployment Documentation                                   │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### No Deployments

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Deployment History                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                   │   │
│  │                         🚀                                        │   │
│  │                                                                   │   │
│  │              Ready to deploy!                                     │   │
│  │                                                                   │   │
│  │     Push to the 'main' branch to trigger a deployment,          │   │
│  │     or click Deploy Now to deploy manually.                      │   │
│  │                                                                   │   │
│  │              [Deploy Now]                                        │   │
│  │                                                                   │   │
│  │     Webhook URL:                                                 │   │
│  │     https://hooks.quantyralabs.cc/my-awesome-app                │   │
│  │     [Copy]                                                       │   │
│  │                                                                   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Deployment Progress

### Real-Time Progress Display

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Deploying rentalfixer                                                  │
│  production • main branch • commit a1b2c3d                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  re-db (Primary)                                          ● Running    │
│  ├─ ✅ Pull code (2s)                                                   │
│  ├─ ✅ Install dependencies (45s)                                       │
│  ├─ ✅ Run migrations (3s)                                              │
│  ├─ ✅ Restart services (2s)                                            │
│  └─ 🔄 Health check...                                                  │
│                                                                         │
│  re-node-02 (Secondary)                                    ⏳ Waiting  │
│  └─ Waiting for primary to complete...                                  │
│                                                                         │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  80%                │
│                                                                         │
│  Started 52 seconds ago • ETA ~15 seconds                              │
│                                                                         │
│                                          [Cancel Deployment]            │
└─────────────────────────────────────────────────────────────────────────┘
```

### Deployment Complete

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Deployment Complete                                                    │
│  production • main branch • commit a1b2c3d                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ✅ Deployed successfully in 1m 23s                                    │
│                                                                         │
│  re-db (Primary)                                            ✅ Success │
│  ├─ ✅ Pull code (2s)                                                   │
│  ├─ ✅ Install dependencies (45s)                                       │
│  ├─ ✅ Run migrations (3s)                                              │
│  ├─ ✅ Restart services (2s)                                            │
│  └─ ✅ Health check (1s)                                                │
│                                                                         │
│  re-node-02 (Secondary)                                    ✅ Success  │
│  ├─ ✅ Pull code (2s)                                                   │
│  ├─ ✅ Install dependencies (38s)                                       │
│  ├─ ✅ Run migrations (3s)                                              │
│  ├─ ✅ Restart services (2s)                                            │
│  └─ ✅ Health check (1s)                                                │
│                                                                         │
│  Domains:                                                               │
│  ● rentalfixer.app → http://rentalfixer.app [Open]                     │
│                                                                         │
│                                    [View Logs]  [View Application]      │
└─────────────────────────────────────────────────────────────────────────┘
```

### Deployment Failed

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Deployment Failed                                                      │
│  production • main branch • commit a1b2c3d                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ❌ Health check failed                                                │
│                                                                         │
│  re-db (Primary)                                              ❌ Failed │
│  ├─ ✅ Pull code (2s)                                                   │
│  ├─ ✅ Install dependencies (45s)                                       │
│  ├─ ✅ Run migrations (3s)                                              │
│  ├─ ✅ Restart services (2s)                                            │
│  └─ ❌ Health check - returned 503                                     │
│                                                                         │
│  re-node-02 (Secondary)                                         ⏭ Skipped
│  └─ Skipped due to primary failure                                     │
│                                                                         │
│  Error:                                                                 │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ HTTP 503 Service Unavailable                                    │   │
│  │ Application failed to start within 30 seconds                   │   │
│  │ Check logs for details                                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Previous commit b2c3d4e is still running.                             │
│                                                                         │
│        [View Logs]  [Rollback]  [Redeploy]  [View Application]         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Feature Prioritization

### Phase 1: Core UX (Essential)

| Feature | Priority | Effort | Value |
|---------|----------|--------|-------|
| Application list with status | P0 | Low | High |
| Application detail view | P0 | Medium | High |
| Deploy button + progress | P0 | Medium | High |
| Environment tabs (prod/staging) | P0 | Low | High |
| Domain list with SSL status | P0 | Low | Medium |
| Secrets management | P0 | Medium | High |

### Phase 2: Enhanced UX (Important)

| Feature | Priority | Effort | Value |
|---------|----------|--------|-------|
| Deployment history | P1 | Medium | High |
| Real-time progress via WebSocket | P1 | High | High |
| Rollback UI | P1 | Low | High |
| Domain health status | P1 | Low | Medium |
| Server metrics dashboard | P1 | Medium | Medium |
| Database management UI | P1 | Medium | Medium |

### Phase 3: Advanced Features (Nice to Have)

| Feature | Priority | Effort | Value |
|---------|----------|--------|-------|
| Deployment previews (PR deploys) | P2 | High | Medium |
| Log streaming | P2 | Medium | Medium |
| Metrics explorer | P2 | Medium | Low |
| Team collaboration | P2 | High | Low |
| Custom deployment pipelines | P2 | High | Medium |
| Blue-green deployments | P2 | High | Medium |

## Framework Auto-Detection

### Detection Logic

```python
# services/framework_detection.py
from typing import Optional, Dict
import re

FRAMEWORK_SIGNATURES = {
    'laravel': {
        'files': ['artisan', 'composer.json'],
        'patterns': {
            'composer.json': r'"laravel/framework"'
        }
    },
    'nextjs': {
        'files': ['package.json', 'next.config.js'],
        'patterns': {
            'package.json': r'"next"'
        }
    },
    'svelte': {
        'files': ['package.json', 'svelte.config.js'],
        'patterns': {
            'package.json': r'"@sveltejs/kit"'
        }
    },
    'python': {
        'files': ['requirements.txt', 'app.py', 'main.py'],
        'patterns': {
            'requirements.txt': r'(flask|django|fastapi)'
        }
    },
    'go': {
        'files': ['go.mod', 'main.go'],
        'patterns': {
            'go.mod': r'module'
        }
    }
}

def detect_framework(repo_url: str, branch: str = 'main') -> Optional[str]:
    """
    Detect framework from repository.
    
    Returns framework name or None if not detected.
    """
    # Clone shallow copy
    # Check for signature files
    # Return detected framework
    
    for framework, signatures in FRAMEWORK_SIGNATURES.items():
        # Check files exist
        # Check patterns match
        pass
    
    return None

def get_framework_defaults(framework: str) -> Dict[str, str]:
    """Get default commands for a framework."""
    
    DEFAULTS = {
        'laravel': {
            'install': 'composer install --no-interaction --optimize-autoloader',
            'build': 'npm run build',
            'migrate': 'php artisan migrate --force',
            'start': 'nginx + php-fpm',
            'health_path': '/'
        },
        'nextjs': {
            'install': 'npm ci',
            'build': 'npm run build',
            'migrate': None,
            'start': 'npm start',
            'health_path': '/'
        },
        'svelte': {
            'install': 'npm ci',
            'build': 'npm run build',
            'migrate': None,
            'start': 'npm start',
            'health_path': '/'
        },
        'python': {
            'install': 'pip install -r requirements.txt',
            'build': None,
            'migrate': 'python manage.py migrate' if 'django' else None,
            'start': 'gunicorn app:app',
            'health_path': '/health'
        },
        'go': {
            'install': 'go mod download',
            'build': 'go build -o app .',
            'migrate': None,
            'start': './app',
            'health_path': '/health'
        }
    }
    
    return DEFAULTS.get(framework, {})
```

### Framework Detection UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 1: Framework Selection                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Detected Framework:                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  🎉 Laravel detected!                                           │   │
│  │                                                                   │   │
│  │  Found: artisan, composer.json                                  │   │
│  │  Version: Laravel 11.x                                          │   │
│  │                                                                   │   │
│  │  [Use Laravel]  [Choose Different Framework]                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  Or select manually:                                                    │
│  [Laravel]  [Next.js]  [Svelte]  [Python]  [Go]                        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Service Templates

Pre-configured templates for common services.

### Template Library

```yaml
# config/service_templates.yml
services:
  redis:
    name: Redis
    description: In-memory data structure store
    icon: 🔴
    default_port: 6379
    config_template: |
      # Redis configuration
      bind 0.0.0.0
      port {{ port }}
      requirepass {{ password }}
      maxmemory {{ max_memory }}mb
      maxmemory-policy allkeys-lru
    
  postgresql:
    name: PostgreSQL
    description: Object-relational database
    icon: 🐘
    default_port: 5432
    config_template: |
      # PostgreSQL configuration
      listen_addresses = '*'
      port = {{ port }}
      max_connections = {{ max_connections }}
    
  meilisearch:
    name: Meilisearch
    description: Search engine
    icon: 🔍
    default_port: 7700
    docker_image: getmeili/meilisearch:latest
    
  minio:
    name: MinIO
    description: Object storage
    icon: 📦
    default_port: 9000
    docker_image: minio/minio:latest
```

### Add Service UI

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Add Service to rentalfixer                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Available Services:                                                    │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│
│  │    🔴 Redis  │  │ 🐘 PostgreSQL│  │ 🔍 Meilisearch│  │  📦 MinIO   ││
│  │   [Add]      │  │   [Add]      │  │   [Add]      │  │   [Add]     ││
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘│
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐                                    │
│  │ 🐇 RabbitMQ  │  │   🗄️ MySQL   │                                    │
│  │   [Add]      │  │   [Add]      │                                    │
│  └──────────────┘  └──────────────┘                                    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Status Indicators

### Health Status

| Status | Color | Icon | Description |
|--------|-------|------|-------------|
| Running | Green | ● | Service is healthy |
| Starting | Blue | ◐ | Service is starting |
| Stopping | Orange | ◔ | Service is stopping |
| Stopped | Gray | ○ | Service is stopped |
| Error | Red | ● | Service has errors |
| Unknown | Gray | ? | Status unavailable |

### Deployment Status

| Status | Color | Icon | Description |
|--------|-------|------|-------------|
| Success | Green | ✅ | Deployment succeeded |
| Running | Blue | 🔄 | Deployment in progress |
| Failed | Red | ❌ | Deployment failed |
| Rolled Back | Orange | ↩️ | Deployment rolled back |
| Pending | Gray | ⏳ | Deployment queued |

### SSL Status

| Status | Color | Icon | Description |
|--------|-------|------|-------------|
| Valid | Green | 🔒 | Certificate valid |
| Expiring Soon | Orange | ⚠️ | Expires in <30 days |
| Expired | Red | 🔓 | Certificate expired |
| Pending | Blue | ⏳ | Provisioning |
| Error | Red | ❌ | Provisioning failed |

## Responsive Design

### Breakpoints

```css
/* Mobile first */
.container { max-width: 100%; }

/* Tablet */
@media (min-width: 768px) {
  .container { max-width: 720px; }
}

/* Desktop */
@media (min-width: 1024px) {
  .container { max-width: 960px; }
}

/* Large desktop */
@media (min-width: 1280px) {
  .container { max-width: 1140px; }
}
```

### Mobile Navigation

On mobile, use bottom navigation bar:

```
┌─────────────────────────────────────┐
│                                     │
│        Application Content          │
│                                     │
├─────────────────────────────────────┤
│  🏠    📦    🗄️    📊    ⚙️       │
│ Home  Apps  DBs  Monitor Settings  │
└─────────────────────────────────────┘
```

## Accessibility

### Keyboard Navigation

- Tab through all interactive elements
- Enter/Space to activate buttons
- Escape to close modals
- Arrow keys for lists

### ARIA Labels

```html
<!-- Application card -->
<article role="article" aria-labelledby="app-name">
  <h2 id="app-name">rentalfixer</h2>
  <span role="status" aria-label="Status: Running">● Running</span>
  <button aria-label="Deploy rentalfixer">Deploy</button>
</article>

<!-- Deployment progress -->
<div role="progressbar" aria-valuenow="80" aria-valuemin="0" aria-valuemax="100">
  <span class="sr-only">Deployment 80% complete</span>
</div>
```

## Next Steps

1. **Phase 1**: Implement core UI components (cards, lists, forms)
2. **Phase 2**: Build application detail view with tabs
3. **Phase 3**: Add real-time deployment progress
4. **Phase 4**: Implement framework auto-detection
5. **Phase 5**: Add service templates

See [paas_roadmap.md](paas_roadmap.md) for implementation timeline.