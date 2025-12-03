# How to: Multi-Stage Builds

Optimize container images using multi-stage builds to separate build-time and runtime dependencies.

## Overview

Multi-stage builds create smaller, more secure images by:
- Separating build tools from runtime environment
- Reducing image size (often 50-70% smaller)
- Minimizing attack surface
- Improving deployment speed

## When to Use

**Use multi-stage builds when**:
- Large build dependencies (compilers, headers, dev tools)
- Significant size difference between builder and runtime
- Security-sensitive deployments
- Bandwidth-constrained environments

**Skip multi-stage builds when**:
- Pure Python with pip packages (minimal overhead)
- Interactive development (Jupyter, RStudio)
- Build and runtime dependencies are similar

## Default Behavior

Absconda automatically uses multi-stage builds based on deployment mode:

```yaml
# Single-stage (default for development)
deploy:
  mode: tarball  # or: full-env

# Multi-stage (default for production)
deploy:
  mode: requirements  # or: export-explicit
```

See [Requirements Mode Guide](../guides/requirements-mode.md) for details.

## Basic Multi-Stage Build

### Environment File

**`ml-app-env.yaml`**:

```yaml
name: ml-app
channels:
  - conda-forge
dependencies:
  # Build dependencies
  - gcc_linux-64=12.3
  - make=4.3
  
  # Runtime
  - python=3.11
  - numpy=1.26
  - scikit-learn=1.4
  - flask=3.0

deploy:
  mode: requirements  # Enables multi-stage
```

### Generate Dockerfile

```bash
absconda generate --file ml-app-env.yaml --output Dockerfile
```

**Generated structure**:

```dockerfile
# Stage 1: Builder
FROM mambaorg/micromamba:1.5.3 AS builder
COPY ml-app-env.yaml /tmp/env.yaml
RUN micromamba create -y -n ml-app -f /tmp/env.yaml

# Stage 2: Runtime
FROM ubuntu:22.04
COPY --from=builder /opt/conda/envs/ml-app /opt/conda/envs/ml-app
ENV PATH=/opt/conda/envs/ml-app/bin:$PATH
```

**Size comparison**:
- Single-stage: 2.8 GB
- Multi-stage: 1.1 GB (61% reduction)

## Custom Multi-Stage Template

For complete control, create a custom template.

### Template Structure

**`custom-multistage.j2`**:

```dockerfile
{% raw %}
#
# Multi-stage build for {{ name }}
#

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM mambaorg/micromamba:1.5.3 AS builder

# Install build tools
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

USER $MAMBA_USER

# Create conda environment
COPY {{ env_filename }} /tmp/env.yaml
RUN micromamba create -y -n {{ name }} -f /tmp/env.yaml && \
    micromamba clean -afy

# Install additional packages
RUN micromamba run -n {{ name }} pip install \
    --no-cache-dir \
    custom-package==1.0.0

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM ubuntu:22.04 AS runtime

# Install minimal runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy environment from builder
COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}

# Set up environment
ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH
ENV CONDA_PREFIX=/opt/conda/envs/{{ name }}

# Labels
{% for key, value in labels.items() %}
LABEL {{ key }}="{{ value }}"
{% endfor %}

# Working directory
WORKDIR /app

# Default command
CMD ["python"]
{% endraw %}
```

### Use Custom Template

```bash
absconda generate \
  --file ml-app-env.yaml \
  --template custom-multistage.j2 \
  --output Dockerfile

docker build -t myapp:latest .
```

## Advanced Patterns

### Pattern 1: Separate Build and Install

Build wheels in one stage, install in another:

```dockerfile
# Stage 1: Build wheels
FROM python:3.11-slim AS builder
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Stage 2: Install wheels
FROM python:3.11-slim
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels
```

### Pattern 2: Compile Native Extensions

```dockerfile
# Stage 1: Compile
FROM mambaorg/micromamba:1.5.3 AS builder
RUN micromamba install -y -n base \
    gcc_linux-64 gxx_linux-64 make cmake \
    python=3.11 numpy cython
COPY setup.py /build/
RUN cd /build && python setup.py build_ext --inplace

# Stage 2: Runtime
FROM ubuntu:22.04
COPY --from=builder /opt/conda/envs/base /opt/conda/envs/base
COPY --from=builder /build/*.so /app/
ENV PATH=/opt/conda/envs/base/bin:$PATH
```

### Pattern 3: Multiple Builders

Combine artifacts from multiple build stages:

```dockerfile
# Stage 1: Python environment
FROM mambaorg/micromamba:1.5.3 AS python-builder
COPY python-env.yaml /tmp/env.yaml
RUN micromamba create -y -n app -f /tmp/env.yaml

# Stage 2: R environment
FROM mambaorg/micromamba:1.5.3 AS r-builder
COPY r-env.yaml /tmp/env.yaml
RUN micromamba create -y -n renv -f /tmp/env.yaml

# Stage 3: Runtime with both
FROM ubuntu:22.04
COPY --from=python-builder /opt/conda/envs/app /opt/conda/envs/app
COPY --from=r-builder /opt/conda/envs/renv /opt/conda/envs/renv
ENV PATH=/opt/conda/envs/app/bin:/opt/conda/envs/renv/bin:$PATH
```

## Optimizing Image Size

### Strategy 1: Minimal Runtime Base

Use distroless or minimal base images:

```bash
absconda build \
  --file app-env.yaml \
  --runtime-base gcr.io/distroless/base-debian11 \
  --tag myapp:distroless
```

**Size impact**: 200-300 MB smaller

### Strategy 2: Remove Unnecessary Files

```dockerfile
# In runtime stage
RUN find /opt/conda -name "*.pyc" -delete && \
    find /opt/conda -name "__pycache__" -type d -exec rm -rf {} + && \
    rm -rf /opt/conda/envs/*/share/man && \
    rm -rf /opt/conda/envs/*/share/doc
```

**Size impact**: 50-100 MB saved

### Strategy 3: Export Explicit Requirements

Use explicit pins to minimize package count:

```yaml
deploy:
  mode: export-explicit  # Only explicitly listed packages
```

```bash
absconda build \
  --file app-env.yaml \
  --tag myapp:minimal \
  --push
```

**Size impact**: Up to 40% smaller

## Layer Caching

Optimize for Docker layer caching:

### Good Practice

```dockerfile
# Cache-friendly order
FROM base

# 1. System dependencies (rarely change)
RUN apt-get update && apt-get install -y libgomp1

# 2. Conda environment (changes occasionally)
COPY environment.yaml /tmp/
RUN micromamba create -y -n app -f /tmp/environment.yaml

# 3. Application code (changes frequently)
COPY --from=builder /app /app
```

### Build with Cache

```bash
# First build (no cache)
docker build -t myapp:v1 .  # 10 minutes

# Rebuild after code change (uses cache)
docker build -t myapp:v2 .  # 30 seconds (layers 1-2 cached)
```

## Security Hardening

### Non-Root User

```dockerfile
# Stage 2: Runtime
FROM ubuntu:22.04

# Create non-root user
RUN useradd -m -u 1000 appuser

COPY --from=builder --chown=appuser:appuser \
  /opt/conda/envs/app /opt/conda/envs/app

USER appuser
ENV PATH=/opt/conda/envs/app/bin:$PATH

CMD ["python", "app.py"]
```

### Read-Only Filesystem

```dockerfile
# Runtime stage
FROM ubuntu:22.04

# ... environment setup ...

# Ensure writable directories
RUN mkdir -p /app/tmp && chmod 1777 /app/tmp
ENV TMPDIR=/app/tmp

# Run with read-only root
# docker run --read-only -v /app/tmp myapp:latest
```

Test:

```bash
docker run --rm --read-only \
  -v /tmp:/app/tmp \
  myapp:latest python -c "import tempfile; print(tempfile.gettempdir())"
```

## Testing Multi-Stage Builds

### Verify Size Reduction

```bash
# Build both versions
docker build -t myapp:single --target builder .
docker build -t myapp:multi .

# Compare sizes
docker images | grep myapp
# myapp:multi   latest  1.1GB
# myapp:single  latest  2.8GB
```

### Verify Functionality

```bash
# Test runtime image
docker run --rm myapp:multi python -c "import numpy; print(numpy.__version__)"

# Ensure build tools are NOT present
docker run --rm myapp:multi gcc --version
# Should fail: gcc: command not found
```

### Benchmark Startup Time

```bash
# Single-stage
time docker run --rm myapp:single python -c "import sys"
# real: 1.2s

# Multi-stage
time docker run --rm myapp:multi python -c "import sys"
# real: 0.4s (3x faster)
```

## Troubleshooting

### Missing Runtime Dependencies

**Problem**: Application fails in runtime stage

```
ImportError: libgomp.so.1: cannot open shared object file
```

**Solution**: Add system dependencies to runtime stage:

```dockerfile
# Stage 2: Runtime
FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/conda/envs/app /opt/conda/envs/app
```

**Identify missing libs**:

```bash
docker run --rm myapp:multi ldd /opt/conda/envs/app/lib/libsomething.so
```

### Large Conda Cache

**Problem**: Builder stage still too large

**Solution**: Clean micromamba cache:

```dockerfile
# Stage 1: Builder
RUN micromamba create -y -n app -f /tmp/env.yaml && \
    micromamba clean -afy
```

Saves 200-500 MB.

### Copy Fails Between Stages

**Problem**: `COPY --from=builder` fails

```
COPY failed: stat /var/lib/docker/overlay2/.../opt/conda: no such file
```

**Solution**: Verify path exists in builder:

```bash
# Check builder stage
docker build --target builder -t myapp:builder .
docker run --rm myapp:builder ls -la /opt/conda/envs/
```

Fix path in COPY instruction.

## Complete Example

**`production-env.yaml`**:

```yaml
name: production-app
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.2
  - scikit-learn=1.4
  - flask=3.0
  - gunicorn=21.2

deploy:
  mode: requirements

labels:
  org.opencontainers.image.title: "Production ML API"
  org.opencontainers.image.version: "1.0.0"
```

**Build and test**:

```bash
# Generate optimized Dockerfile
absconda generate \
  --file production-env.yaml \
  --output Dockerfile.multi

# Build
docker build -f Dockerfile.multi -t mlapi:1.0.0 .

# Test
docker run --rm mlapi:1.0.0 python -c \
  "import sklearn; print(f'sklearn {sklearn.__version__}')"

# Check size
docker images mlapi:1.0.0
# mlapi  1.0.0  850MB

# Deploy
docker push ghcr.io/yourorg/mlapi:1.0.0
```

## Best Practices Summary

✅ **Do**:
- Use multi-stage for production deployments
- Clean package manager caches in builder stage
- Use minimal runtime base images
- Remove unnecessary files (.pyc, docs, man pages)
- Order Dockerfile layers by change frequency
- Test runtime image thoroughly

❌ **Don't**:
- Use multi-stage for development/interactive work
- Copy entire `/opt/conda` if using tarball mode
- Install build tools in runtime stage
- Run as root in runtime stage
- Forget to clean caches in builder

## Related Documentation

- [Requirements Mode Guide](../guides/requirements-mode.md) - Deployment modes
- [Building Images Guide](../guides/building-images.md) - Build options
- [Custom Base Images](custom-base-images.md) - Runtime base configuration
- [Environment Files Reference](../reference/environment-files.md) - Deploy section

## Further Reading

- [Docker Multi-Stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [Container Image Optimization](https://docs.docker.com/develop/dev-best-practices/)
- [Distroless Images](https://github.com/GoogleContainerTools/distroless)
