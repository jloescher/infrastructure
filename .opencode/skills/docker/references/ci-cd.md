# CI/CD Reference

## Contents
- GitHub Actions Workflow
- Container Build Strategy
- Deployment Patterns
- Rollback Procedures
- Anti-Patterns

## GitHub Actions Workflow

### Multi-Job Pipeline

The deploy workflow separates build and deploy concerns:

```yaml
jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
    steps:
      # Build and push image
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      # SSH and deploy
```

**Why:** Build failures don't trigger partial deployments. The `environment` protection enables manual approvals.

### Buildx with Caching

```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3

- name: Build and push Docker image
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: ${{ steps.meta.outputs.tags }}
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Why:** `gha` cache type uses GitHub Actions cache, dramatically reducing build times for unchanged layers.

### Metadata Action

```yaml
- name: Extract metadata
  id: meta
  uses: docker/metadata-action@v5
  with:
    images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
    tags: |
      type=ref,event=branch
      type=sha,prefix=
      type=raw,value=latest,enable={{is_default_branch}}
```

**Why:** Generates multiple tags (branch name, commit SHA, latest) for flexible rollback.

## Deployment Patterns

### SSH-Based Deployment

```yaml
- name: Deploy to server
  run: |
    ssh $DEPLOY_USER@$DEPLOY_HOST << 'ENDSSH'
      set -e
      cd /opt/apps/$APP_NAME
      docker-compose pull
      docker-compose up -d --remove-orphans
      sleep 10
      curl -f http://localhost:3000/health || exit 1
    ENDSSH
```

**Why:** `--remove-orphans` cleans up containers for removed services. The health check validates before marking success.

### Slack Notifications

```yaml
- name: Notify on success
  if: success()
  run: |
    curl -X POST -H 'Content-type: application/json' \
      --data "{\"text\":\"✅ Deployment successful: $APP_NAME\"}" \
      ${{ secrets.SLACK_WEBHOOK }}
```

## Rollback Procedures

### Image Tag Rollback

```yaml
rollback:
  if: github.event.inputs.rollback == 'true'
  steps:
    - run: |
        ssh $DEPLOY_USER@$DEPLOY_HOST << 'ENDSSH'
          PREVIOUS_IMAGE=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep $APP_NAME | head -2 | tail -1)
          docker-compose down
          docker tag $PREVIOUS_IMAGE $APP_NAME:latest
          docker-compose up -d
        ENDSSH
```

**Why:** Tags the previous image as `latest`, then restarts. Assumes compose file references `image: app-name:latest`.

## Anti-Patterns

### WARNING: Building on Production Servers

**The Problem:**

```yaml
# BAD - Builds on target server
- run: |
    ssh server << 'EOF'
      docker build -t app .
      docker-compose up -d
    EOF
```

**Why This Breaks:**
1. Resource contention on production servers
2. Inconsistent build environments
3. Longer downtime during deployment

**The Fix:** Build in CI (GitHub Actions), push to registry, pull on server.

### WARNING: Missing Health Checks

**The Problem:**

```yaml
# BAD - No validation after deploy
- run: docker-compose up -d
```

**Why This Breaks:**
1. Deployment reports success while app crashes
2. Errors surface during user traffic
3. Rollback requires manual detection

**The Fix:**

```bash
docker-compose up -d
sleep 10
curl -f http://localhost:3000/health || exit 1
```

### WARNING: Using `docker-compose` (v1) Command

**The Problem:**
GitHub Actions runners may have v1 installed. This project uses v2 (`docker compose`).

**The Fix:**
Always use `docker compose` (space, not hyphen) in scripts and CI.