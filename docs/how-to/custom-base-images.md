# How to: Custom Base Images

Configure custom base images for specific runtime requirements, GPU support, or organizational standards.

## Overview

Base images provide the foundation for your containers. Absconda supports:
- **Default**: Ubuntu 22.04 (general purpose)
- **GPU**: NVIDIA CUDA images
- **Minimal**: Alpine, distroless
- **Custom**: Your organization's approved images

## When to Customize

**Use custom base images when**:
- GPU/CUDA support required
- Organizational security policies mandate specific images
- Minimal image size is critical
- Specific system libraries needed
- Compliance requirements (FIPS, hardened images)

## Base Image Types

### Builder Base

Used during `conda create` phase:

```bash
absconda build \
  --file env.yaml \
  --builder-base mambaorg/micromamba:1.5.8 \
  --tag myimage:latest
```

**Common choices**:
- `mambaorg/micromamba:1.5.3` (default, recommended)
- `condaforge/miniforge3:latest` (conda alternative)
- `continuumio/miniconda3:latest` (official Miniconda)

### Runtime Base

Used for final container image:

```bash
absconda build \
  --file env.yaml \
  --runtime-base ubuntu:22.04 \
  --tag myimage:latest
```

**Common choices**:
- `ubuntu:22.04` (default, 77MB)
- `ubuntu:24.04` (newer packages)
- `debian:12-slim` (49MB, stable)
- `alpine:3.19` (7MB, minimal)
- `gcr.io/distroless/base-debian12` (security-focused)

## GPU Base Images

### NVIDIA CUDA

For PyTorch, TensorFlow, JAX with GPU support:

```bash
absconda build \
  --file pytorch-gpu-env.yaml \
  --runtime-base nvidia/cuda:12.2.0-runtime-ubuntu22.04 \
  --tag pytorch-gpu:latest
```

**CUDA base images**:

| Image | Size | Use Case |
|-------|------|----------|
| `nvidia/cuda:12.2.0-base-ubuntu22.04` | 200MB | Minimal CUDA |
| `nvidia/cuda:12.2.0-runtime-ubuntu22.04` | 1.5GB | Production runtime |
| `nvidia/cuda:12.2.0-devel-ubuntu22.04` | 3.5GB | Development/building |

### Builder with CUDA

For compiling GPU code:

```bash
absconda build \
  --file gpu-env.yaml \
  --builder-base nvidia/cuda:12.2.0-devel-ubuntu22.04 \
  --runtime-base nvidia/cuda:12.2.0-runtime-ubuntu22.04 \
  --tag gpu-app:latest
```

**Environment file**:

```yaml
name: gpu-app
channels:
  - pytorch
  - nvidia
  - conda-forge
dependencies:
  - python=3.11
  - pytorch=2.1.0
  - pytorch-cuda=12.1
  - cudatoolkit=12.1
```

### Verify GPU Support

```bash
docker run --rm --gpus all gpu-app:latest \
  python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
```

## Minimal Base Images

### Alpine Linux

**Pros**: Tiny size (7MB base)  
**Cons**: musl libc (compatibility issues)

```bash
absconda build \
  --file env.yaml \
  --runtime-base alpine:3.19 \
  --tag myapp:alpine
```

**Requires** compatible packages:

```yaml
name: alpine-app
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26  # Built with musl support
  - pip
  - pip:
      - flask==3.0.0
```

**Note**: Many scientific packages (e.g., TensorFlow) don't support Alpine.

### Distroless

**Pros**: Minimal attack surface, no shell/package manager  
**Cons**: Debugging difficult, no apt/yum

```bash
absconda build \
  --file env.yaml \
  --runtime-base gcr.io/distroless/base-debian12 \
  --tag myapp:distroless
```

**Test** (no shell available):

```bash
# This will fail - no /bin/bash
docker run --rm myapp:distroless bash

# Use entrypoint directly
docker run --rm myapp:distroless python --version
```

### Debian Slim

**Good balance**: Small (49MB), compatible, easy debugging

```bash
absconda build \
  --file env.yaml \
  --runtime-base debian:12-slim \
  --tag myapp:debian
```

## Custom Templates with Base Images

For complete control, use custom templates.

### GPU Template

**`gpu-template.j2`**:

```dockerfile
{% raw %}
# Builder stage with CUDA development tools
FROM nvidia/cuda:12.2.0-devel-ubuntu22.04 AS builder

# Install micromamba
RUN apt-get update && \
    apt-get install -y wget bzip2 && \
    wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | \
    tar -xj -C / bin/micromamba && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

ENV MAMBA_ROOT_PREFIX=/opt/conda

# Create environment
COPY {{ env_filename }} /tmp/env.yaml
RUN micromamba create -y -n {{ name }} -f /tmp/env.yaml && \
    micromamba clean -afy

# Runtime stage with CUDA runtime only
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

# Copy environment
COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}

# Set up environment
ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH
ENV LD_LIBRARY_PATH=/opt/conda/envs/{{ name }}/lib:$LD_LIBRARY_PATH
ENV CUDA_HOME=/usr/local/cuda

# Labels
{% for key, value in labels.items() %}
LABEL {{ key }}="{{ value }}"
{% endfor %}

CMD ["python"]
{% endraw %}
```

Use:

```bash
absconda generate \
  --file pytorch-env.yaml \
  --template gpu-template.j2 \
  --output Dockerfile.gpu

docker build -f Dockerfile.gpu -t pytorch:gpu .
```

### Hardened Template

**`hardened-template.j2`**:

```dockerfile
{% raw %}
# Builder stage
FROM mambaorg/micromamba:1.5.3 AS builder
COPY {{ env_filename }} /tmp/env.yaml
RUN micromamba create -y -n {{ name }} -f /tmp/env.yaml && \
    micromamba clean -afy

# Hardened runtime
FROM gcr.io/distroless/base-debian12

# Copy environment
COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}

# Non-root user (distroless default)
USER nonroot:nonroot

ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH

{% for key, value in labels.items() %}
LABEL {{ key }}="{{ value }}"
{% endfor %}

ENTRYPOINT ["/opt/conda/envs/{{ name }}/bin/python"]
{% endraw %}
```

## Organizational Base Images

### Using Private Registry

```bash
absconda build \
  --file env.yaml \
  --runtime-base myregistry.company.com/base/ubuntu:22.04-approved \
  --tag myapp:latest
```

### Authenticated Pull

```bash
# Login to private registry
docker login myregistry.company.com

# Build with private base
absconda build \
  --file env.yaml \
  --runtime-base myregistry.company.com/base/secure:latest \
  --tag myapp:1.0.0
```

### Buildkit Secrets

For credentials in Dockerfile:

```dockerfile
# syntax=docker/dockerfile:1.4

FROM myregistry.company.com/base:latest

# Use secret for apt authentication
RUN --mount=type=secret,id=apt_auth \
    cp /run/secrets/apt_auth /etc/apt/auth.conf && \
    apt-get update && \
    apt-get install -y custom-package && \
    rm /etc/apt/auth.conf
```

Build:

```bash
docker build --secret id=apt_auth,src=$HOME/.apt_auth -t myapp .
```

## System Dependencies

### Adding System Packages

Some conda packages require system libraries:

```dockerfile
{% raw %}
# In custom template
FROM ubuntu:22.04

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/conda/envs/{{ name }} /opt/conda/envs/{{ name }}
{% endraw %}
```

### Identifying Dependencies

Find required system libraries:

```bash
# Run container
docker run --rm -it myapp:test bash

# Check shared library dependencies
ldd /opt/conda/envs/myenv/lib/libsomething.so

# Identify missing packages
apt-file search libgomp.so.1
# libgomp1: /usr/lib/x86_64-linux-gnu/libgomp.so.1
```

## Version Pinning

### Pin Base Image Digest

Ensure reproducibility with digest pinning:

```bash
# Get digest
docker pull ubuntu:22.04
docker inspect ubuntu:22.04 --format='{{.RepoDigests}}'
# [ubuntu@sha256:abc123...]

# Use digest in build
absconda build \
  --file env.yaml \
  --runtime-base ubuntu@sha256:abc123... \
  --tag myapp:v1.0.0
```

### In Custom Template

```dockerfile
# Pinned by digest
FROM ubuntu@sha256:77906da86b60585ce12215807090eb327e7386c8fafb5402369e421f44eff17e

# Still readable
LABEL base.image.tag="ubuntu:22.04"
LABEL base.image.digest="sha256:77906da86b6058..."
```

## Multi-Architecture

### Build for Multiple Platforms

```bash
# Build for amd64 and arm64
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --file <(absconda generate --file env.yaml) \
  --tag myapp:multi-arch \
  --push \
  .
```

### Platform-Specific Base Images

```dockerfile
# Automatic platform selection
FROM --platform=$TARGETPLATFORM ubuntu:22.04

# Or explicit
FROM --platform=linux/amd64 ubuntu:22.04
```

## Testing Base Images

### Compatibility Check

```bash
# Test base image
docker run --rm ubuntu:22.04 \
  bash -c "apt-get update && apt-get install -y python3 && python3 --version"

# Test with conda
docker run --rm mambaorg/micromamba:1.5.3 \
  micromamba --version
```

### Verify System Libraries

```bash
# Check glibc version (important for compatibility)
docker run --rm ubuntu:22.04 ldd --version
# ldd (Ubuntu GLIBC 2.35-0ubuntu3.1) 2.35

# Conda packages require glibc >= 2.17
```

### Security Scanning

```bash
# Scan base image
docker scan ubuntu:22.04

# Or with Trivy
trivy image ubuntu:22.04
```

## Troubleshooting

### GLIBC Version Mismatch

**Error**:
```
ImportError: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.29' not found
```

**Solution**: Use newer base image:

```bash
# Check required glibc
docker run --rm myapp:test \
  bash -c "ldd /opt/conda/envs/app/bin/python | grep libc"

# Use Ubuntu 22.04 (glibc 2.35) instead of 18.04 (glibc 2.27)
absconda build \
  --file env.yaml \
  --runtime-base ubuntu:22.04 \
  --tag myapp:fixed
```

### Missing System Libraries

**Error**:
```
OSError: libgomp.so.1: cannot open shared object file
```

**Solution**: Add to custom template:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/*
```

### Alpine Compatibility

**Error**:
```
OSError: Error loading shared libraries: libstdc++.so.6
```

**Solution**: Alpine uses musl, not glibc. Use glibc-compatible base:

```bash
# Instead of alpine:3.19
absconda build \
  --file env.yaml \
  --runtime-base debian:12-slim \
  --tag myapp:debian
```

### GPU Not Available

**Error**:
```
RuntimeError: CUDA not available
```

**Solution**: Ensure CUDA base image:

```bash
# Check CUDA version needed
docker run --rm myapp:test python -c \
  "import torch; print(f'Expected CUDA: {torch.version.cuda}')"
# Expected CUDA: 12.1

# Use matching base
absconda build \
  --file env.yaml \
  --runtime-base nvidia/cuda:12.1.0-runtime-ubuntu22.04 \
  --tag myapp:gpu
```

## Configuration File

Store base image preferences:

**`~/.config/absconda/config.yaml`**:

```yaml
build:
  default_builder_base: mambaorg/micromamba:1.5.3
  default_runtime_base: ubuntu:22.04
  
  # Organization-specific
  approved_bases:
    - ubuntu:22.04
    - debian:12-slim
    - myregistry.company.com/base/approved:latest
  
  # GPU defaults
  gpu:
    builder_base: nvidia/cuda:12.2.0-devel-ubuntu22.04
    runtime_base: nvidia/cuda:12.2.0-runtime-ubuntu22.04
```

Use in policy:

```yaml
# policy.yaml
base_image_policy:
  mode: allowlist
  allowed:
    - ubuntu:22.04
    - ubuntu@sha256:abc123...
    - nvidia/cuda:12.*-runtime-ubuntu22.04
  denied:
    - "*:latest"  # Prevent unversioned images
    - "alpine:*"  # Organization doesn't support Alpine
```

## Best Practices

✅ **Do**:
- Pin base images by digest for production
- Use minimal base images when possible
- Test base image compatibility before deployment
- Document system dependencies required
- Use multi-stage builds with different bases
- Scan base images for vulnerabilities

❌ **Don't**:
- Use `:latest` tag in production
- Assume Alpine compatibility without testing
- Mix musl (Alpine) and glibc packages
- Use development base images in production
- Ignore security scan results
- Use outdated/unsupported base images

## Common Patterns

### Development vs Production

```bash
# Development: full environment
absconda build \
  --file dev-env.yaml \
  --runtime-base ubuntu:22.04 \
  --tag myapp:dev

# Production: minimal runtime
absconda build \
  --file prod-env.yaml \
  --runtime-base gcr.io/distroless/base \
  --tag myapp:prod
```

### GPU Training vs Inference

```bash
# Training: CUDA + cuDNN + development tools
absconda build \
  --file train-env.yaml \
  --runtime-base nvidia/cuda:12.2.0-cudnn8-devel-ubuntu22.04 \
  --tag model-training:latest

# Inference: CUDA runtime only
absconda build \
  --file inference-env.yaml \
  --runtime-base nvidia/cuda:12.2.0-cudnn8-runtime-ubuntu22.04 \
  --tag model-serving:latest
```

### Compliance Requirements

```bash
# FIPS-compliant base
absconda build \
  --file app-env.yaml \
  --runtime-base registry1.dso.mil/ironbank/redhat/ubi/ubi8:latest \
  --tag app:fips-compliant
```

## Related Documentation

- [Multi-Stage Builds](multi-stage-builds.md) - Optimize with multi-stage
- [Building Images Guide](../guides/building-images.md) - Build process
- [GPU PyTorch Example](../examples/gpu-pytorch.md) - GPU setup
- [Configuration Reference](../reference/configuration.md) - Config files

## Further Reading

- [Docker Official Images](https://hub.docker.com/_/ubuntu)
- [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit)
- [Distroless Images](https://github.com/GoogleContainerTools/distroless)
- [Alpine Linux](https://alpinelinux.org/)
