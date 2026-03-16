# Adding a New SaaS Product

## Overview

Adding a new product involves:
1. Creating the application (with optional database)
2. Setting up CI/CD for deployments
3. Configuring the application environment

## Method 1: Dashboard Wizard (Recommended)

The easiest way to create a new application with database:

1. **Access Dashboard**: http://100.102.220.16:8080/apps/create
2. **Select Framework**: Laravel, Next.js, Svelte, or Go
3. **Enter Application Name**: lowercase, underscores allowed (e.g., `my_product`)
4. **Add Description**: Brief description of the product
5. **Enter Git Repository URL**: Your GitHub/GitLab repository
6. **Configure Database**:
   - ✅ Create PostgreSQL database (checked by default)
   - Database name (defaults to app name)
   - Connection pool size (default: 20)
   - ✅ Create staging environment (optional)
   - ✅ Allocate Redis database (optional)
7. **Click "Create Application"**

### What Gets Created

**Database:**
- PostgreSQL database: `my_product`
- Admin user: `my_product_admin` with random password
- Optional staging database: `my_product_staging`
- PgBouncer pool configuration on both routers

**GitHub Actions:**
- `.github/workflows/deploy.yml` workflow
- Parallel deployment to both app servers
- Optional staging deployment on `develop` branch

**Connection Strings:**
- Production database URL
- Staging database URL (if enabled)
- Redis URL (if enabled)

## Method 2: Manual Database Creation

### Step 1: Generate Password Hashes

```bash
# On any DB server or local with PostgreSQL tools
./scripts/generate-pg-password.sh "your-secure-password"
```

Example output:
```
SCRAM-SHA-256$4096:abc123...$stored_key:server_key
```

### Step 2: Add Database Configuration

Edit `ansible/inventory/group_vars/databases.yml`:

```yaml
databases:
  # Existing databases...
  
  product_two:
    name: product_two
    description: "Second SaaS Product"
    owner: product_two_admin
    users:
      - name: product_two_admin
        password_hash: "SCRAM-SHA-256$4096:...$...:..."
        roles:
          - SUPERUSER
          - CREATEDB
      - name: product_two_app
        password_hash: "SCRAM-SHA-256$4096:...$...:..."
        roles:
          - NOSUPERUSER
    pgbouncer_pool_size: 20
    pgbouncer_max_clients: 150
```

### Step 3: Create the Database

```bash
ansible-playbook ansible/playbooks/create-databases.yml
```

### Step 4: Deploy PgBouncer Config

```bash
ansible-playbook ansible/playbooks/deploy-pgbouncer.yml
```

## Connection Strings

After creation, use these connection strings:

**Through PgBouncer (recommended):**
```
# Write (primary)
postgres://product_admin:password@100.102.220.16:6432/product

# Router 02 (failover)
postgres://product_admin:password@100.116.175.9:6432/product
```

**Direct through HAProxy:**
```
# Write (port 5000)
postgres://product_admin:password@100.102.220.16:5000/product

# Read (port 5001) - load balanced across replicas
postgres://product_admin:password@100.102.220.16:5001/product
```

**Redis:**
```
redis://:password@100.102.220.16:6379/0
```

## Application Deployment

### Option 1: GitHub Actions (Recommended)

1. Copy the workflow from the dashboard wizard
2. Add to `.github/workflows/deploy.yml`
3. Add required secrets to GitHub:
   - `DEPLOY_HOST`: `100.102.220.16`
   - `DEPLOY_USER`: `admin`
   - `DEPLOY_PASSWORD`: `DbAdmin2026!`
   - `DATABASE_URL`: Connection string from dashboard

### Option 2: Manual Deployment

```bash
# On both app servers
ssh root@100.92.26.38 "cd /opt/apps/product && git pull && systemctl restart product"
ssh root@100.101.39.22 "cd /opt/apps/product && git pull && systemctl restart product"
```

## User Roles Reference

| Role | Permissions |
|------|-------------|
| SUPERUSER | Full admin access |
| CREATEDB | Can create databases |
| CREATEROLE | Can create roles |
| NOSUPERUSER | Regular user (no admin) |

## Redis Databases

For manual Redis database allocation, add to `redis_databases`:

```yaml
redis_databases:
  product_two:
    db_number: 1
    description: "Product Two cache"
```

## Directory Structure

```
infrastructure/
├── ansible/
│   ├── inventory/
│   │   └── group_vars/
│   │       └── databases.yml    # Database definitions
│   ├── playbooks/
│   │   ├── create-databases.yml
│   │   └── deploy-pgbouncer.yml
│   └── templates/
│       ├── pgbouncer.ini.j2
│       └── pgbouncer_userlist.txt.j2
├── dashboard/
│   ├── app.py                  # Dashboard application
│   └── templates/
│       └── create_app.html     # Wizard template
└── docs/
    ├── adding_new_product.md
    └── ci_cd.md
```

## Quick Checklist

**Via Dashboard:**
- [ ] Open http://100.102.220.16:8080/apps/create
- [ ] Fill in application details
- [ ] Configure database options
- [ ] Click "Create Application"
- [ ] Copy GitHub Actions workflow
- [ ] Add secrets to GitHub
- [ ] Push to main branch

**Manual:**
- [ ] Generate password hashes
- [ ] Add config to `databases.yml`
- [ ] Run `create-databases.yml` playbook
- [ ] Run `deploy-pgbouncer.yml` playbook
- [ ] Test connection with psql
- [ ] Update application environment variables

## After Creation

1. **Verify Database**:
   ```bash
   psql -h 100.102.220.16 -p 6432 -U product_admin -d product
   ```

2. **Verify PgBouncer**:
   ```bash
   ssh router-01 "cat /etc/pgbouncer/pgbouncer.ini | grep product"
   ```

3. **Set Up Application**:
   - Clone repo to `/opt/apps/product/` on both app servers
   - Create systemd service
   - Configure environment variables

4. **Configure CI/CD**:
   - Add GitHub secrets
   - Add workflow file
   - Test deployment