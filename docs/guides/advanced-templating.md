# Advanced Templating

Customize Dockerfile generation with Jinja2 templates for complete control over build process.

## Overview

Absconda uses Jinja2 templates to generate Dockerfiles. You can override the default templates to:
- Add custom build steps
- Modify base images
- Include additional files
- Customize the build process

## Template System

### Default Templates

Located in `src/absconda/_templates/`:

```
_templates/
├── default/
│   ├── Dockerfile.j2         # Main template
│   └── main.j2               # Entry point
└── fragments/
    ├── builder_stage.j2      # Multi-stage builder
    ├── runtime_stage.j2      # Multi-stage runtime
    ├── single_stage.j2       # Single-stage build
    ├── export_block.j2       # Export/tarball creation
    ├── requirements_runtime.j2  # pip requirements
    └── tarball_runtime.j2    # Tarball installation
```

### Template Variables

Available in all templates:

```python
{
    'name': 'myenv',              # Environment name
    'channels': [...],            # Conda channels
    'packages': [...],            # Conda packages
    'pip_packages': [...],        # pip packages
    'renv_lockfile': 'renv.lock', # R lockfile
    'builder_image': 'mambaorg/micromamba:latest',
    'runtime_image': 'mambaorg/micromamba:latest',
    'labels': {...},              # OCI labels
    'env_vars': {...},            # Environment variables
    'mode': 'conda',              # conda|pip|tarball|snapshot
    'multi_stage': True,          # Multi-stage build?
    'python_version': '3.11',     # Python version
}
```

## Using Custom Templates

### Option 1: Specify Template File

```bash
absconda generate \
  --file environment.yaml \
  --output Dockerfile \
  --template my-template.j2
```

### Option 2: Specify Template Directory

```bash
absconda generate \
  --file environment.yaml \
  --output Dockerfile \
  --template-dir ./templates
```

Looks for `./templates/Dockerfile.j2`.

### Option 3: XDG Config Directory

Place template at `~/.config/absconda/templates/Dockerfile.j2`:

```bash
absconda generate --file environment.yaml --output Dockerfile
```

Auto-discovers custom template.

## Example Templates

### Minimal Template

`minimal-template.j2`:

```dockerfile
FROM {{ builder_image }}

# Install packages
RUN micromamba install -y -n base -c {{ channels|join(' -c ') }} \
    {{ packages|join(' ') }} && \
    micromamba clean -afy

{% if pip_packages %}
RUN pip install --no-cache-dir {{ pip_packages|join(' ') }}
{% endif %}

CMD ["bash"]
```

Use it:

```bash
absconda generate \
  --file environment.yaml \
  --template minimal-template.j2
```

### GPU-Enabled Template

`gpu-template.j2`:

```dockerfile
# Use CUDA base image
FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04 AS builder

# Install micromamba
RUN apt-get update && \
    apt-get install -y wget bzip2 && \
    wget -qO- https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C / bin/micromamba

ENV MAMBA_ROOT_PREFIX=/opt/conda

# Install Conda packages
RUN micromamba install -y -n base -c {{ channels|join(' -c ') }} \
    {{ packages|join(' ') }} && \
    micromamba clean -afy

{% if pip_packages %}
RUN pip install --no-cache-dir {{ pip_packages|join(' ') }}
{% endif %}

# Validate CUDA
RUN python -c "import torch; assert torch.cuda.is_available()"

CMD ["python"]
```

Use it:

```bash
absconda generate \
  --file gpu-env.yaml \
  --template gpu-template.j2
```

### Multi-Stage with Custom Runtime

`custom-runtime.j2`:

```dockerfile
# Builder stage
FROM {{ builder_image }} AS builder

COPY environment.yaml /tmp/env.yaml

RUN micromamba create -y -n myenv -f /tmp/env.yaml && \
    micromamba clean -afy

# Runtime stage - use minimal base
FROM ubuntu:22.04

# Copy only the environment
COPY --from=builder /opt/conda/envs/myenv /opt/conda/envs/myenv

# Add to PATH
ENV PATH=/opt/conda/envs/myenv/bin:$PATH

# Install only runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

CMD ["python"]
```

### Adding Custom Files

`with-files-template.j2`:

```dockerfile
FROM {{ builder_image }}

# Install packages
RUN micromamba install -y -n base -f environment.yaml && \
    micromamba clean -afy

# Copy application files
COPY ./app /app
COPY ./config /config
COPY ./scripts /scripts

# Set up permissions
RUN chmod +x /scripts/*.sh

# Configure environment
ENV APP_CONFIG=/config/app.yaml
WORKDIR /app

CMD ["python", "main.py"]
```

### Security-Hardened Template

`secure-template.j2`:

```dockerfile
FROM {{ builder_image }}

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install packages
RUN micromamba install -y -n base -c {{ channels|join(' -c ') }} \
    {{ packages|join(' ') }} && \
    micromamba clean -afy

# Remove unnecessary packages
RUN apt-get purge -y --auto-remove wget curl && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Switch to non-root user
USER appuser
WORKDIR /home/appuser

CMD ["python"]
```

## Template Fragments

Reuse common patterns with fragments.

### Create Fragment

`fragments/validation.j2`:

```dockerfile
# Validate installed packages
{% for package in packages %}
RUN python -c "import {{ package.split('=')[0].replace('-', '_') }}"
{% endfor %}
```

### Use Fragment

`main-template.j2`:

```dockerfile
FROM {{ builder_image }}

# Install packages
RUN micromamba install -y -n base {{ packages|join(' ') }}

# Include validation fragment
{% include 'fragments/validation.j2' %}

CMD ["python"]
```

## Advanced Jinja2 Features

### Conditionals

```dockerfile
{% if mode == 'conda' %}
RUN micromamba install -y -n base {{ packages|join(' ') }}
{% elif mode == 'pip' %}
RUN pip install --no-cache-dir -r requirements.txt
{% endif %}

{% if multi_stage %}
FROM {{ runtime_image }} AS runtime
COPY --from=builder /opt/conda /opt/conda
{% endif %}
```

### Loops

```dockerfile
# Install each package individually for better caching
{% for package in packages %}
RUN micromamba install -y -n base {{ package }}
{% endfor %}

# Set multiple environment variables
{% for key, value in env_vars.items() %}
ENV {{ key }}={{ value }}
{% endfor %}
```

### Filters

```dockerfile
# Join with commas
RUN pip install {{ pip_packages|join(', ') }}

# Convert to uppercase
ENV APP_NAME={{ name|upper }}

# Default value
ENV LOG_LEVEL={{ log_level|default('INFO') }}

# Custom filter (define in template)
{% set sorted_packages = packages|sort %}
```

### Macros

```dockerfile
{% macro install_conda_package(package) %}
RUN micromamba install -y -n base {{ package }} && \
    micromamba clean -afy
{% endmacro %}

# Use macro
{{ install_conda_package('numpy=1.24') }}
{{ install_conda_package('pandas=2.0') }}
```

## Template Testing

### Validate Template Syntax

```bash
# Generate but don't build
absconda generate \
  --file environment.yaml \
  --template my-template.j2 \
  --output Dockerfile

# Check syntax
docker build --check Dockerfile
```

### Test with Dry Run

```bash
# Build without pushing
absconda build \
  --file environment.yaml \
  --template my-template.j2 \
  --repository test/myimage \
  --tag test
```

### Debug Template Variables

Add to template:

```dockerfile
# DEBUG: Print variables
RUN echo "Name: {{ name }}"
RUN echo "Packages: {{ packages|join(', ') }}"
RUN echo "Mode: {{ mode }}"
```

## Real-World Examples

### Bioinformatics Pipeline

`bioinformatics-template.j2`:

```dockerfile
FROM {{ builder_image }} AS builder

# Install Conda packages
RUN micromamba install -y -n base -c bioconda -c conda-forge \
    {{ packages|join(' ') }} && \
    micromamba clean -afy

# Install reference genomes
RUN mkdir -p /data/genomes && \
    wget -P /data/genomes https://example.com/genome.fa.gz

# Runtime
FROM {{ runtime_image }}

COPY --from=builder /opt/conda /opt/conda
COPY --from=builder /data/genomes /data/genomes

# Add pipeline scripts
COPY ./pipeline /pipeline
RUN chmod +x /pipeline/*.sh

ENV PATH=/opt/conda/bin:/pipeline:$PATH
WORKDIR /data

CMD ["bash"]
```

### Web Service

`webservice-template.j2`:

```dockerfile
FROM {{ builder_image }} AS builder

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime
FROM python:{{ python_version }}-slim

COPY --from=builder /install /usr/local

# Copy application
COPY ./app /app
WORKDIR /app

# Non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### ML Training

`ml-training-template.j2`:

```dockerfile
FROM nvidia/cuda:12.2.0-cudnn8-devel-ubuntu22.04 AS builder

# Install Python + Conda
RUN apt-get update && apt-get install -y wget && \
    wget -qO /tmp/Mambaforge.sh https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh && \
    bash /tmp/Mambaforge.sh -b -p /opt/conda

ENV PATH=/opt/conda/bin:$PATH

# Install ML packages
COPY environment.yaml /tmp/
RUN mamba env create -f /tmp/environment.yaml && \
    mamba clean -afy

# Runtime
FROM nvidia/cuda:12.2.0-cudnn8-runtime-ubuntu22.04

COPY --from=builder /opt/conda /opt/conda
ENV PATH=/opt/conda/envs/{{ name }}/bin:$PATH

# Copy training scripts
COPY ./training /training
WORKDIR /training

# Validation
RUN python -c "import torch; assert torch.cuda.is_available()"

CMD ["python", "train.py"]
```

## Best Practices

### 1. Keep Templates Modular

Break complex templates into fragments:

```
templates/
├── Dockerfile.j2           # Main template
└── fragments/
    ├── base.j2            # Base image setup
    ├── conda.j2           # Conda installation
    ├── validation.j2      # Package validation
    └── entrypoint.j2      # Entry point setup
```

### 2. Use Comments

```dockerfile
{# This is a Jinja2 comment - won't appear in output #}

# This is a Docker comment - will appear in Dockerfile

{# 
Multi-line Jinja2 comment
explaining template logic
#}
```

### 3. Validate Inputs

```dockerfile
{% if not packages %}
  {{ raise_error("No packages specified!") }}
{% endif %}

{% if python_version not in ['3.8', '3.9', '3.10', '3.11', '3.12'] %}
  {{ raise_error("Unsupported Python version") }}
{% endif %}
```

### 4. Provide Defaults

```dockerfile
{% set work_dir = work_dir|default('/app') %}
{% set user = user|default('root') %}

WORKDIR {{ work_dir }}
USER {{ user }}
```

### 5. Document Variables

At top of template:

```dockerfile
{#
Template Variables:
  - name: Environment name (required)
  - packages: List of Conda packages (required)
  - pip_packages: List of pip packages (optional)
  - python_version: Python version (default: 3.11)
  - work_dir: Working directory (default: /app)
  - user: User to run as (default: root)
#}
```

## Next Steps

- [Building Images](building-images.md) - Using custom templates
- [Architecture: Template System](../architecture/template-system.md) - How templates work
- [Examples](../examples/) - Real-world template examples
