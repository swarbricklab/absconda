# How to: Secrets and Authentication

Securely handle credentials, API keys, and authentication for building and deploying containers.

## Overview

This guide covers:
- Private conda channels authentication
- Container registry authentication
- Build-time secrets (API keys, tokens)
- Runtime secrets (application credentials)
- Secure secret management

## Private Conda Channels

### Conda Token Authentication

For private Anaconda.org channels:

**Method 1: Environment variable**

```bash
export CONDA_TOKEN=your_token_here

absconda build \
  --file env.yaml \
  --repository ghcr.io/yourorg/app \
  --tag v1.0.0
```

**Method 2: .condarc file**

```yaml
# ~/.condarc
channels:
  - https://conda.anaconda.org/t/YOUR_TOKEN/private-channel
  - conda-forge
  - defaults
```

Build:

```bash
absconda build --file env.yaml --tag app:latest
```

**Method 3: In environment file**

```yaml
name: private-app
channels:
  - https://conda.anaconda.org/t/${CONDA_TOKEN}/yourorg
  - conda-forge
dependencies:
  - python=3.11
  - private-package=1.0.0
```

### GitHub Packages (Conda)

```yaml
# environment.yaml
name: github-app
channels:
  - https://conda.pkg.github.com/yourorg
  - conda-forge
dependencies:
  - python=3.11
  - your-private-package=2.0.0
```

Authenticate:

```bash
# Create ~/.condarc with GitHub token
cat > ~/.condarc <<EOF
channels:
  - https://conda.pkg.github.com/t/ghp_yourtoken/yourorg
  - conda-forge
EOF

absconda build --file environment.yaml --tag app:latest
```

### Artifactory/Nexus

```yaml
name: artifactory-app
channels:
  - https://artifactory.company.com/artifactory/conda-local
  - conda-forge
dependencies:
  - python=3.11
  - company-package=1.5.0
```

Setup authentication:

```bash
# Add credentials to .condarc
cat >> ~/.condarc <<EOF
channel_alias: https://artifactory.company.com/artifactory/conda-local
default_channels:
  - https://username:password@artifactory.company.com/artifactory/conda-local
EOF

# Or use bearer token
cat >> ~/.condarc <<EOF
channel_settings:
  - channel: https://artifactory.company.com/artifactory/conda-local
    auth: bearer
    token: your_artifactory_token
EOF
```

## Container Registry Authentication

### Docker Hub

```bash
# Login
docker login

# Or with credentials
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

# Build and push
absconda build \
  --file env.yaml \
  --repository yourusername/app \
  --tag v1.0.0 \
  --push
```

### GitHub Container Registry (ghcr.io)

```bash
# Create Personal Access Token (PAT) with write:packages scope
# https://github.com/settings/tokens

# Login
echo "$GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin

# Build and push
absconda build \
  --file env.yaml \
  --repository ghcr.io/yourorg/app \
  --tag v1.0.0 \
  --push
```

### Google Artifact Registry

```bash
# Configure Docker credential helper
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push
absconda build \
  --file env.yaml \
  --repository us-central1-docker.pkg.dev/project/repo/app \
  --tag v1.0.0 \
  --push
```

### AWS ECR

```bash
# Login (token valid for 12 hours)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build and push
absconda build \
  --file env.yaml \
  --repository 123456789012.dkr.ecr.us-east-1.amazonaws.com/app \
  --tag v1.0.0 \
  --push
```

### Azure Container Registry

```bash
# Login
az acr login --name myregistry

# Build and push
absconda build \
  --file env.yaml \
  --repository myregistry.azurecr.io/app \
  --tag v1.0.0 \
  --push
```

## Build-Time Secrets

Secrets needed during `docker build` (API keys, credentials).

### Docker BuildKit Secrets

**Best practice** for build-time secrets:

**Dockerfile with secret**:

```dockerfile
# syntax=docker/dockerfile:1.4

FROM mambaorg/micromamba:1.5.3 AS builder

# Mount secret during build
RUN --mount=type=secret,id=pypi_token \
    export PIP_INDEX_URL=https://token:$(cat /run/secrets/pypi_token)@pypi.company.com/simple && \
    micromamba create -y -n app python=3.11 && \
    micromamba run -n app pip install private-package

FROM ubuntu:22.04
COPY --from=builder /opt/conda/envs/app /opt/conda/envs/app
ENV PATH=/opt/conda/envs/app/bin:$PATH
```

**Build with secret**:

```bash
# Secret from file
echo "your_token" > .pypi_token
docker build --secret id=pypi_token,src=.pypi_token -t app:latest .
rm .pypi_token  # Clean up

# Secret from environment variable
docker build --secret id=pypi_token,env=PYPI_TOKEN -t app:latest .
```

**With Absconda custom template**:

```dockerfile
{% raw %}
# syntax=docker/dockerfile:1.4

FROM mambaorg/micromamba:1.5.3 AS builder

# Install with authenticated private channel
RUN --mount=type=secret,id=conda_token \
    export CONDA_TOKEN=$(cat /run/secrets/conda_token) && \
    micromamba create -y -n {{ name }} python=3.11

COPY {{ env_filename }} /tmp/env.yaml

# Use token in channel URL
RUN --mount=type=secret,id=conda_token \
    sed "s/\${CONDA_TOKEN}/$(cat /run/secrets/conda_token)/g" /tmp/env.yaml > /tmp/env_auth.yaml && \
    micromamba install -y -n {{ name }} -f /tmp/env_auth.yaml && \
    micromamba clean -afy

FROM ubuntu:22.04
COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}
ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH
{% endraw %}
```

### SSH Keys for Private Git Repos

```dockerfile
# syntax=docker/dockerfile:1.4

FROM mambaorg/micromamba:1.5.3 AS builder

# Install from private git repos
RUN --mount=type=ssh \
    micromamba create -y -n app python=3.11 pip git && \
    micromamba run -n app pip install \
      git+ssh://git@github.com/yourorg/private-repo.git@v1.0.0
```

Build:

```bash
# Start ssh-agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa

# Build with SSH mount
docker build --ssh default -t app:latest .
```

### Build Arguments (Less Secure)

**⚠️ Warning**: Build args are visible in image history!

```dockerfile
FROM mambaorg/micromamba:1.5.3 AS builder

ARG CONDA_TOKEN
ENV CONDA_TOKEN=${CONDA_TOKEN}

COPY env.yaml /tmp/env.yaml
RUN micromamba create -y -n app -f /tmp/env.yaml

# IMPORTANT: Remove from final image
FROM ubuntu:22.04
COPY --from=builder /opt/conda/envs/app /opt/conda/envs/app
ENV PATH=/opt/conda/envs/app/bin:$PATH
# CONDA_TOKEN not copied to final stage
```

Build:

```bash
docker build --build-arg CONDA_TOKEN=$CONDA_TOKEN -t app:latest .

# ⚠️ Token visible in history of builder image!
docker history app:latest
```

## Runtime Secrets

Secrets needed when running containers (database passwords, API keys).

### Environment Variables

**Simple but less secure**:

```bash
docker run -e DATABASE_PASSWORD=secret123 app:latest
```

### Docker Secrets (Swarm)

```bash
# Create secret
echo "mysecret" | docker secret create db_password -

# Deploy service
docker service create \
  --name myapp \
  --secret db_password \
  app:latest

# Access in container
# /run/secrets/db_password
```

**In application**:

```python
# app.py
import os
from pathlib import Path

def get_secret(name):
    """Get secret from /run/secrets or environment."""
    secret_path = Path('/run/secrets') / name
    if secret_path.exists():
        return secret_path.read_text().strip()
    return os.environ.get(name.upper())

db_password = get_secret('db_password')
```

### Kubernetes Secrets

```yaml
# secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: app-secrets
type: Opaque
stringData:
  database-password: mysecretpassword
  api-key: myapikey
```

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  template:
    spec:
      containers:
      - name: app
        image: ghcr.io/yourorg/app:latest
        env:
        - name: DATABASE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: app-secrets
              key: database-password
        # Or mount as files
        volumeMounts:
        - name: secrets
          mountPath: /run/secrets
          readOnly: true
      volumes:
      - name: secrets
        secret:
          secretName: app-secrets
```

### Docker Compose Secrets

```yaml
# docker-compose.yml
version: '3.8'

services:
  app:
    image: ghcr.io/yourorg/app:latest
    secrets:
      - db_password
      - api_key
    environment:
      - DATABASE_PASSWORD_FILE=/run/secrets/db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    external: true  # Managed externally
```

**Application reads secret**:

```python
import os

def read_secret_file(env_var):
    """Read secret from file path specified in env var."""
    file_path = os.environ.get(env_var)
    if file_path:
        with open(file_path) as f:
            return f.read().strip()
    return None

db_password = read_secret_file('DATABASE_PASSWORD_FILE')
```

## Secret Management Tools

### HashiCorp Vault

**Retrieve secrets at runtime**:

```python
# app.py
import hvac
import os

def get_vault_secret(path, key):
    client = hvac.Client(url=os.environ['VAULT_ADDR'])
    client.token = os.environ['VAULT_TOKEN']
    secret = client.secrets.kv.v2.read_secret_version(path=path)
    return secret['data']['data'][key]

db_password = get_vault_secret('secret/myapp', 'database_password')
```

**Inject secrets at container start**:

```bash
# vault-entrypoint.sh
#!/bin/bash
export DATABASE_PASSWORD=$(vault kv get -field=password secret/myapp/db)
export API_KEY=$(vault kv get -field=key secret/myapp/api)

# Run application
exec python app.py
```

### AWS Secrets Manager

```python
# app.py
import boto3
import json

def get_aws_secret(secret_name):
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

secrets = get_aws_secret('myapp/production')
db_password = secrets['database_password']
```

**In Dockerfile** (retrieval at runtime):

```dockerfile
FROM ubuntu:22.04

# Install AWS CLI
RUN apt-get update && \
    apt-get install -y awscli && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/conda/envs/app /opt/conda/envs/app
ENV PATH=/opt/conda/envs/app/bin:$PATH

# Entrypoint retrieves secrets
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "app.py"]
```

**entrypoint.sh**:

```bash
#!/bin/bash
set -e

# Retrieve secrets from AWS Secrets Manager
SECRET=$(aws secretsmanager get-secret-value \
    --secret-id myapp/prod \
    --query SecretString \
    --output text)

export DATABASE_PASSWORD=$(echo $SECRET | jq -r .database_password)
export API_KEY=$(echo $SECRET | jq -r .api_key)

exec "$@"
```

### Google Secret Manager

```python
# app.py
from google.cloud import secretmanager

def get_gcp_secret(project_id, secret_id, version='latest'):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode('UTF-8')

db_password = get_gcp_secret('my-project', 'database-password')
```

## CI/CD Secrets

### GitHub Actions

```yaml
# .github/workflows/build.yml
name: Build and Push

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
      
      - name: Build and push
        env:
          CONDA_TOKEN: ${{ secrets.CONDA_TOKEN }}
        run: |
          absconda build \
            --file env.yaml \
            --repository ghcr.io/${{ github.repository }} \
            --tag latest \
            --push
```

**Set secrets**: Repository Settings → Secrets and variables → Actions → New repository secret

### GitLab CI

```yaml
# .gitlab-ci.yml
variables:
  DOCKER_HOST: tcp://docker:2376
  DOCKER_TLS_CERTDIR: "/certs"

build:
  image: docker:latest
  services:
    - docker:dind
  before_script:
    - echo "$REGISTRY_PASSWORD" | docker login -u "$REGISTRY_USER" --password-stdin
  script:
    - apk add --no-cache python3 py3-pip
    - pip install absconda
    - |
      absconda build \
        --file env.yaml \
        --repository registry.gitlab.com/$CI_PROJECT_PATH \
        --tag $CI_COMMIT_SHA \
        --push
  only:
    - main
```

**Set secrets**: Settings → CI/CD → Variables → Add variable

### Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any
    environment {
        DOCKER_CREDS = credentials('docker-hub-credentials')
        CONDA_TOKEN = credentials('conda-token')
    }
    stages {
        stage('Build') {
            steps {
                sh '''
                    echo "$DOCKER_CREDS_PSW" | docker login -u "$DOCKER_CREDS_USR" --password-stdin
                    
                    absconda build \
                        --file env.yaml \
                        --repository myorg/app \
                        --tag ${BUILD_NUMBER} \
                        --push
                '''
            }
        }
    }
}
```

**Set secrets**: Credentials → Add Credentials → Secret text

## Best Practices

### Build Time

✅ **Do**:
- Use BuildKit secrets (`--secret`)
- Use multi-stage builds (secrets not in final image)
- Use SSH mounts for git repos
- Clean up secrets after use
- Scan images for leaked secrets

❌ **Don't**:
- Use `ARG` for sensitive values
- Commit secrets to git
- Leave secrets in image layers
- Use `ENV` for build secrets
- Store secrets in Dockerfile

### Runtime

✅ **Do**:
- Use secret management tools (Vault, AWS Secrets Manager)
- Mount secrets as files (read-only)
- Use minimal permission IAM roles
- Rotate secrets regularly
- Encrypt secrets at rest

❌ **Don't**:
- Pass secrets via command line args
- Log secrets
- Store secrets in environment variables (when possible)
- Hardcode secrets in application code
- Share secrets across environments

### General

✅ **Do**:
- Use separate secrets for dev/staging/prod
- Limit secret access (principle of least privilege)
- Audit secret access
- Automate secret rotation
- Use short-lived credentials when possible

❌ **Don't**:
- Reuse secrets across services
- Store secrets in version control
- Share secrets via insecure channels (email, Slack)
- Use weak passwords
- Ignore secret sprawl

## Troubleshooting

### Build Fails with Authentication Error

**Error**:
```
HTTP 401: Unauthorized when accessing https://conda.anaconda.org/private-channel
```

**Solution**: Verify token is set correctly:

```bash
# Check token in environment
echo $CONDA_TOKEN

# Test channel access
curl -I "https://conda.anaconda.org/t/$CONDA_TOKEN/private-channel/linux-64/repodata.json"

# Rebuild with token
export CONDA_TOKEN=your_actual_token
absconda build --file env.yaml --tag app:latest
```

### Secret Not Available in Container

**Error**: Application can't read secret

**Solution**: Verify mount point:

```bash
# Check secret location
docker run --rm app:latest ls -la /run/secrets/

# Check permissions
docker run --rm app:latest cat /run/secrets/db_password
```

### BuildKit Secret Not Working

**Error**: `/run/secrets/my_secret: no such file`

**Solution**: Enable BuildKit:

```bash
# Set environment variable
export DOCKER_BUILDKIT=1

# Or in daemon.json
# /etc/docker/daemon.json
{
  "features": {
    "buildkit": true
  }
}

# Restart Docker
sudo systemctl restart docker
```

### Token Visible in Image History

**Problem**: Secret appears in `docker history`

**Solution**: Use multi-stage build:

```dockerfile
# BAD: Secret in final image
FROM base
ARG SECRET
RUN --mount=... install_with_secret

# GOOD: Secret only in builder
FROM base AS builder
ARG SECRET
RUN --mount=... install_with_secret

FROM base
COPY --from=builder /app /app
# SECRET not in this stage
```

## Security Scanning

### Detect Leaked Secrets

```bash
# Scan with Trivy
trivy image --scanners secret myapp:latest

# Scan with TruffleHog
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  trufflesecurity/trufflehog docker --image myapp:latest

# Scan Dockerfile
docker run --rm -v $PWD:/src \
  goodwithtech/dockle:latest /src/Dockerfile
```

### Pre-commit Hooks

Prevent committing secrets:

```bash
# Install pre-commit
pip install pre-commit

# .pre-commit-config.yaml
repos:
  - repo: https://github.com/trufflesecurity/trufflehog
    rev: v3.63.0
    hooks:
      - id: trufflehog
        args: ['filesystem', '.']

# Install hooks
pre-commit install
```

## Related Documentation

- [CI/CD Integration](ci-cd-integration.md) - Automated builds
- [Building Images Guide](../guides/building-images.md) - Build process
- [Configuration Reference](../reference/configuration.md) - Config files
- [Remote Builders Guide](../guides/remote-builders.md) - Remote authentication

## Further Reading

- [Docker BuildKit Secrets](https://docs.docker.com/build/building/secrets/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [HashiCorp Vault](https://www.vaultproject.io/)
- [AWS Secrets Manager](https://aws.amazon.com/secrets-manager/)
- [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
