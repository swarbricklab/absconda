# Example: Minimal Python Environment

Complete walkthrough for building a minimal Python container with pip packages.

## Overview

This example demonstrates:
- Creating a minimal Python environment with pip packages
- Building and testing locally
- Pushing to a container registry
- Running the container

**Use case**: Lightweight Python applications with PyPI-only dependencies.

## Prerequisites

- Docker installed and running
- Absconda installed (`pip install absconda`)
- Container registry access (GitHub Container Registry in this example)

## Step 1: Create Environment File

Create `minimal-env.yaml`:

```yaml
name: minimal-python
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - requests==2.31.0
      - click==8.1.7
labels:
  org.opencontainers.image.title: "Minimal Python Environment"
  org.opencontainers.image.description: "Lightweight Python with requests and click"
  org.opencontainers.image.authors: "your-email@example.com"
```

**Package breakdown**:
- **python=3.11**: Python interpreter from Conda
- **pip**: Pip package manager
- **requests**: HTTP library for API calls
- **click**: CLI framework

## Step 2: Validate Environment

Check the environment file for issues:

```bash
absconda validate --file minimal-env.yaml
```

**Expected output**:

```
Using policy profile default from built-in defaults.
Environment minimal-python is valid with 2 dependency entries.
```

## Step 3: Generate Dockerfile

Preview the generated Dockerfile:

```bash
absconda generate --file minimal-env.yaml --output Dockerfile.preview
```

**Generated Dockerfile** (excerpt):

```dockerfile
# Builder stage
FROM mambaorg/micromamba:latest AS builder

COPY minimal-env.yaml /tmp/env.yaml
RUN micromamba create -y -n minimal-python -f /tmp/env.yaml && \
    micromamba clean -afy

# Runtime stage
FROM mambaorg/micromamba:latest

COPY --from=builder /opt/conda/envs/minimal-python /opt/conda/envs/minimal-python

ENV PATH=/opt/conda/envs/minimal-python/bin:$PATH

LABEL org.opencontainers.image.title="Minimal Python Environment"
LABEL org.opencontainers.image.description="Lightweight Python with requests and click"
```

## Step 4: Build Image Locally

Build the container image:

```bash
absconda build \
  --file minimal-env.yaml \
  --repository ghcr.io/yourusername/minimal-python \
  --tag v1.0
```

**Build output**:

```
Using policy profile default from built-in defaults.
[+] Building 45.2s (12/12) FINISHED
 => [builder 1/3] FROM docker.io/mambaorg/micromamba:latest
 => [builder 2/3] COPY minimal-env.yaml /tmp/env.yaml
 => [builder 3/3] RUN micromamba create -y -n minimal-python -f /tmp/env.yaml
 => [stage-1 1/1] COPY --from=builder /opt/conda/envs/minimal-python ...
 => exporting to image
Image built: ghcr.io/yourusername/minimal-python:v1.0
```

**Image size**: ~200 MB (Python + requests + click)

## Step 5: Test the Image

### Basic Python Test

```bash
docker run --rm ghcr.io/yourusername/minimal-python:v1.0 python --version
```

**Output**: `Python 3.11.7`

### Test Installed Packages

```bash
docker run --rm ghcr.io/yourusername/minimal-python:v1.0 python -c "import requests; print(requests.__version__)"
```

**Output**: `2.31.0`

```bash
docker run --rm ghcr.io/yourusername/minimal-python:v1.0 python -c "import click; print(click.__version__)"
```

**Output**: `8.1.7`

### Test Requests Library

```bash
docker run --rm ghcr.io/yourusername/minimal-python:v1.0 \
  python -c "import requests; r = requests.get('https://api.github.com'); print(r.status_code)"
```

**Output**: `200`

## Step 6: Create Sample Application

Create a simple CLI application to test in the container.

**app.py**:

```python
#!/usr/bin/env python3
"""Simple CLI app using click and requests."""

import click
import requests


@click.command()
@click.option('--url', default='https://api.github.com', help='URL to fetch')
def main(url):
    """Fetch URL and display status."""
    click.echo(f"Fetching {url}...")
    response = requests.get(url)
    click.echo(f"Status: {response.status_code}")
    click.echo(f"Content-Type: {response.headers.get('content-type')}")


if __name__ == '__main__':
    main()
```

### Test Application in Container

```bash
# Mount current directory and run app
docker run --rm -v $PWD:/app -w /app \
  ghcr.io/yourusername/minimal-python:v1.0 \
  python app.py --url https://api.github.com/users/octocat
```

**Output**:

```
Fetching https://api.github.com/users/octocat...
Status: 200
Content-Type: application/json; charset=utf-8
```

## Step 7: Push to Registry

### Authenticate to GitHub Container Registry

```bash
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
```

### Build and Push

```bash
absconda build \
  --file minimal-env.yaml \
  --repository ghcr.io/yourusername/minimal-python \
  --tag v1.0 \
  --push
```

**Output**:

```
Image built: ghcr.io/yourusername/minimal-python:v1.0
The push refers to repository [ghcr.io/yourusername/minimal-python]
v1.0: digest: sha256:abc123... size: 1234
Image pushed: ghcr.io/yourusername/minimal-python:v1.0
```

### Tag Additional Versions

```bash
docker tag ghcr.io/yourusername/minimal-python:v1.0 \
  ghcr.io/yourusername/minimal-python:latest

docker push ghcr.io/yourusername/minimal-python:latest
```

## Step 8: Use in Production

### Docker Compose

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  app:
    image: ghcr.io/yourusername/minimal-python:v1.0
    volumes:
      - ./app:/app
    working_dir: /app
    command: python app.py --url https://api.example.com
```

Run:

```bash
docker-compose up
```

### Kubernetes Deployment

**deployment.yaml**:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: minimal-python-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: minimal-python
  template:
    metadata:
      labels:
        app: minimal-python
    spec:
      containers:
      - name: app
        image: ghcr.io/yourusername/minimal-python:v1.0
        command: ["python", "app.py"]
        volumeMounts:
        - name: app-code
          mountPath: /app
      volumes:
      - name: app-code
        configMap:
          name: app-code
```

## Variations

### Requirements Mode (No Conda)

For even smaller images, use pure pip:

**requirements.txt**:

```
requests==2.31.0
click==8.1.7
```

Build:

```bash
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/yourusername/minimal-python-pure \
  --tag v1.0 \
  --push
```

**Result**: ~120 MB image (vs ~200 MB with Conda)

### Add Development Tools

**minimal-dev.yaml**:

```yaml
name: minimal-python-dev
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - requests==2.31.0
      - click==8.1.7
      - pytest==7.4.3
      - black==23.12.0
      - mypy==1.7.1
labels:
  org.opencontainers.image.title: "Minimal Python Dev Environment"
```

### Multi-Architecture Build

Build for multiple platforms:

```bash
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/yourusername/minimal-python:v1.0 \
  -f Dockerfile \
  --push \
  .
```

## Troubleshooting

### Import Error

**Error**: `ModuleNotFoundError: No module named 'requests'`

**Solution**: Verify pip is in conda dependencies and packages are in `pip:` section:

```yaml
dependencies:
  - pip          # ← Must be here
  - pip:
      - requests
```

### Permission Denied

**Error**: `docker: permission denied`

**Solution**: Add user to docker group or use sudo:

```bash
sudo usermod -aG docker $USER
# Log out and back in
```

### Image Too Large

**Solution 1**: Use multi-stage build (default)

**Solution 2**: Use requirements mode instead of Conda

**Solution 3**: Use alpine base:

```bash
absconda generate \
  --requirements requirements.txt \
  --base-image python:3.11-alpine \
  --output Dockerfile
```

## Next Steps

- [Data Science Example](data-science.md) - NumPy, pandas, scikit-learn
- [Requirements Mode Guide](../guides/requirements-mode.md) - Pure pip workflow
- [Building Images Guide](../guides/building-images.md) - Advanced build options
- [CI/CD Integration](../how-to/ci-cd-integration.md) - Automate builds

## Complete Files

**Project structure**:

```
minimal-python/
├── minimal-env.yaml
├── app.py
├── requirements.txt (optional)
└── Dockerfile.preview
```

**Download**: All files available in [`examples/`](../../examples/) directory.
