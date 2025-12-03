# Requirements Mode

Build Python-only containers without Conda/Mamba, using pip and `requirements.txt`.

## Overview

Requirements mode creates lightweight containers with just Python and pip packages—no Conda overhead. Ideal for pure Python projects or when working with PyPI-only packages.

## When to Use

**Use requirements mode when**:
- Pure Python project with only PyPI packages
- Need smallest possible image size
- All dependencies available on PyPI
- No complex system dependencies

**Use Conda/Mamba instead when**:
- Need non-Python dependencies (R, Julia, system libraries)
- Mixing Conda and pip packages
- Need compiled packages with optimized binaries
- Using scientific computing stack (NumPy, SciPy, etc.)

## Quick Example

### 1. Create requirements.txt

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
sqlalchemy==2.0.23
```

### 2. Generate Dockerfile

```bash
absconda generate \
  --requirements requirements.txt \
  --output Dockerfile \
  --python-version 3.11
```

### 3. Build

```bash
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/org/myapp \
  --tag latest \
  --python-version 3.11 \
  --push
```

## Generated Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install pip packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Validation
RUN python -c "import fastapi; import uvicorn"

CMD ["python"]
```

## Command Reference

### Generate from Requirements

```bash
absconda generate \
  --requirements requirements.txt \
  --output Dockerfile \
  --python-version 3.11 \
  --base-image python:3.11-slim
```

**Options**:
- `--requirements PATH` - Path to requirements.txt
- `--python-version VER` - Python version (3.8, 3.9, 3.10, 3.11, 3.12)
- `--base-image IMAGE` - Base Docker image (default: python:{version}-slim)
- `--output PATH` - Output Dockerfile path
- `--template NAME` - Custom template

### Build from Requirements

```bash
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/org/myapp \
  --tag v1.0 \
  --python-version 3.11 \
  --push
```

**Options**:
- `--requirements PATH` - Path to requirements.txt
- `--python-version VER` - Python version
- `--repository REPO` - Docker repository
- `--tag TAG` - Image tag
- `--push` - Push after building
- `--remote-builder NAME` - Build remotely

## Base Images

### Slim Images (Default)

```bash
absconda build \
  --requirements requirements.txt \
  --python-version 3.11 \
  --base-image python:3.11-slim
```

**Size**: ~120 MB  
**Use for**: Most applications

### Alpine Images

```bash
absconda build \
  --requirements requirements.txt \
  --python-version 3.11 \
  --base-image python:3.11-alpine
```

**Size**: ~50 MB  
**Trade-off**: Smaller but compilation issues with some packages

### Full Images

```bash
absconda build \
  --requirements requirements.txt \
  --python-version 3.11 \
  --base-image python:3.11
```

**Size**: ~900 MB  
**Use for**: Development, need build tools

## Advanced Examples

### Multi-stage Build

For smaller final images:

Create custom template `templates/requirements-multistage.j2`:

```dockerfile
# Build stage
FROM python:{{ python_version }}-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:{{ python_version }}-slim

WORKDIR /app

# Copy only installed packages
COPY --from=builder /install /usr/local

# Validation
RUN python -c "{{ validation_imports }}"

CMD ["python"]
```

Use it:

```bash
absconda generate \
  --requirements requirements.txt \
  --template templates/requirements-multistage.j2 \
  --python-version 3.11
```

### System Dependencies

For packages needing system libraries:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

### Development vs Production

**requirements-dev.txt**:

```
# Production
fastapi==0.104.1
uvicorn==0.24.0

# Development only
pytest==7.4.3
black==23.11.0
mypy==1.7.1
```

**requirements.txt** (production):

```
fastapi==0.104.1
uvicorn==0.24.0
```

Build production:

```bash
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/org/myapp \
  --tag v1.0 \
  --python-version 3.11 \
  --push
```

Build development:

```bash
absconda build \
  --requirements requirements-dev.txt \
  --repository ghcr.io/org/myapp \
  --tag dev \
  --python-version 3.11
```

## Hybrid: Conda + Requirements

Combine Conda for system deps with pip for Python packages:

**environment.yaml**:

```yaml
name: hybrid
type: conda

channels:
  - conda-forge

conda:
  - python=3.11
  - postgresql
  - libxml2

pip:
  - fastapi==0.104.1
  - uvicorn==0.24.0
```

Or reference requirements.txt:

```yaml
name: hybrid
type: conda

channels:
  - conda-forge

conda:
  - python=3.11
  - postgresql

pip_requirements: requirements.txt
```

## Comparison: Conda vs Requirements

| Aspect | Conda/Mamba | Requirements |
|--------|-------------|--------------|
| **Image size** | Larger (~500MB+) | Smaller (~120MB) |
| **Build time** | Slower | Faster |
| **Package ecosystem** | Conda + PyPI | PyPI only |
| **System dependencies** | Built-in | Manual |
| **Scientific packages** | Optimized binaries | Standard PyPI |
| **Reproducibility** | Excellent | Good |

## Best Practices

### 1. Pin All Versions

```
# ✅ Do this
fastapi==0.104.1
uvicorn==0.24.0

# ❌ Not this
fastapi
uvicorn>=0.20
```

### 2. Use pip-compile

Generate locked requirements:

```bash
# requirements.in
fastapi
uvicorn[standard]

# Generate locked requirements.txt
pip-compile requirements.in
```

### 3. Separate Build and Runtime Deps

**requirements.txt**:

```
fastapi==0.104.1
uvicorn==0.24.0
```

**Dockerfile**:

```dockerfile
FROM python:3.11-slim AS builder

# Build-time dependencies
RUN apt-get update && apt-get install -y gcc

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.11-slim

# Copy only runtime artifacts
COPY --from=builder /install /usr/local
```

### 4. Use --no-cache-dir

Always include in Dockerfile:

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

Saves ~100MB by not caching pip downloads.

### 5. Validate Imports

Add validation to Dockerfile:

```dockerfile
RUN python -c "import fastapi; import uvicorn"
```

Catches missing dependencies at build time.

## Troubleshooting

### Package Build Fails

**Error**: `error: command 'gcc' failed`

**Solution**: Use multi-stage build with build tools in builder stage, or switch to Conda for binary packages.

### Image Too Large

```bash
# Check layer sizes
docker history ghcr.io/org/myapp:latest

# Common issues:
# - pip cache not cleared (add --no-cache-dir)
# - apt cache not cleaned (add rm -rf /var/lib/apt/lists/*)
# - Build deps in final image (use multi-stage build)
```

### Import Fails at Runtime

**Error**: `ModuleNotFoundError`

**Solution**: Add to validation:

```dockerfile
RUN python -c "import problematic_module"
```

This fails the build early instead of at runtime.

## Converting Between Formats

### From environment.yaml to requirements.txt

```bash
# Install environment
conda env create -f environment.yaml

# Activate
conda activate myenv

# Export pip packages
pip freeze > requirements.txt
```

### From requirements.txt to environment.yaml

```yaml
name: myenv
type: conda

channels:
  - conda-forge

conda:
  - python=3.11

pip_requirements: requirements.txt
```

## HPC Deployment

Requirements-mode containers work great on HPC:

```bash
# Build
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/org/myapp \
  --tag v1.0 \
  --python-version 3.11 \
  --push

# Generate wrapper
absconda wrap \
  --image docker://ghcr.io/org/myapp:v1.0 \
  --command python \
  --output wrappers/myapp-python

# Deploy
rsync -av wrappers/ hpc:/path/to/wrappers/
```

## Next Steps

- [Building Images](building-images.md) - Build options and workflows
- [Basic Usage](basic-usage.md) - Complete workflow guide
- [Examples](../examples/minimal-python.md) - Minimal Python example
