# Core Concepts

Understanding these concepts will help you get the most out of Absconda.

## Environment Definitions

Absconda accepts three types of environment definitions:

### 1. Conda Environment Files

Standard Conda YAML format:

```yaml
name: myenv
channels:
  - conda-forge
  - bioconda
dependencies:
  - python=3.11
  - numpy
  - pandas
  - pip:
      - seaborn
```

**When to use**: You need Conda packages (scientific computing, bioinformatics) or a mix of Conda and pip.

### 2. pip Requirements Files

Standard `requirements.txt` format:

```
flask==3.0.0
requests>=2.31.0
pandas
```

**When to use**: Pure Python projects without Conda dependencies.

### 3. Pre-packed Tarballs

A `.tar.gz` file created with `conda-pack`:

```bash
conda pack -o myenv.tar.gz
```

**When to use**: You've already solved the environment locally and want to skip the solve step in the container build.

## Multi-stage Builds

Absconda uses **multi-stage Docker builds** by default to create smaller images.

### How It Works

**Builder Stage:**
```
┌─────────────────────────────┐
│ micromamba base image       │
│ • Install dependencies      │
│ • Solve environment         │
│ • Pack with conda-pack      │
│ → myenv.tar.gz             │
└─────────────────────────────┘
```

**Runtime Stage:**
```
┌─────────────────────────────┐
│ debian:bookworm-slim        │
│ • Copy packed environment   │
│ • Unpack to /opt/absconda   │
│ • Set PATH and activation   │
└─────────────────────────────┘
```

### Benefits

- **Smaller images**: Build tools and caches don't ship in the final image
- **Faster pushes**: Less data to transfer to registries
- **Security**: Fewer attack surface with minimal runtime

### Single-stage Alternative

Use `--single-stage` when you need build tools at runtime (e.g., for compiling C extensions):

```bash
absconda generate --file env.yaml --single-stage
```

## Base Images

Absconda uses two base images:

### Builder Base

Default: `mambaorg/micromamba:1.5.5`

Override with `--builder-base`:

```bash
absconda generate \
  --file env.yaml \
  --builder-base mambaorg/micromamba:2.0.0
```

### Runtime Base

Default: `debian:bookworm-slim` (multi-stage) or `mambaorg/micromamba:1.5.5` (single-stage)

Override with `--runtime-base`:

```bash
absconda generate \
  --file env.yaml \
  --runtime-base ubuntu:22.04
```

**Requirements**: Must have glibc and basic shell utilities.

## Policies

Policies enforce organizational standards and constraints.

### Policy Profiles

Define allowed channels, packages, and build settings in `absconda-policy.yaml`:

```yaml
profiles:
  production:
    allowed_channels:
      - conda-forge
      - bioconda
    denied_packages:
      - pytorch  # Use production-pytorch instead
    multi_stage: true
    runtime_base: debian:bookworm-slim
    
  development:
    allowed_channels: null  # Allow any channel
    multi_stage: false      # Single-stage for easier debugging
```

Activate a profile:

```bash
absconda --profile production generate --file env.yaml
```

### XDG Config Discovery

Policies are auto-discovered from:

1. `/etc/xdg/absconda/absconda-policy.yaml` (system-wide)
2. `~/.config/absconda/absconda-policy.yaml` (user-level)
3. `./absconda-policy.yaml` (project-level)

Later configs override earlier ones.

See [Policies Reference](../reference/policies.md) for full specification.

## Templates

Absconda uses Jinja2 templates to generate Dockerfiles.

### Built-in Templates

Absconda ships with default templates for:
- Multi-stage builds
- Single-stage builds  
- Requirements mode (pip-only)
- R + renv integration

### Custom Templates

Override with your own template:

```bash
absconda generate \
  --file env.yaml \
  --template my-template.j2
```

Templates receive a `RenderConfig` object with environment details, policy settings, and base image information.

See [Advanced Templating Guide](../guides/advanced-templating.md) for details.

## Remote Builders

Build on remote cloud instances instead of locally.

### Why Use Remote Builders?

- **Faster builds**: Leverage powerful cloud VMs
- **Consistent environment**: Same build environment for all team members
- **Cost-effective**: Pay only when building (VMs auto-stop)

### How It Works

```
Local Machine                      GCP Remote Builder
├─ absconda CLI                    ├─ Receives build context
├─ Uploads Dockerfile + context    ├─ Runs docker build
└─ Monitors build progress         └─ Pushes to registry
```

Define in `absconda-remote.yaml`:

```yaml
builders:
  gcp-builder:
    provider: gcp
    project: my-gcp-project
    zone: us-central1-a
    machine_type: n1-standard-8
```

Use with `--remote-builder`:

```bash
absconda build \
  --file env.yaml \
  --repository ghcr.io/org/myenv \
  --remote-builder gcp-builder \
  --push
```

See [Remote Builders Guide](../guides/remote-builders.md) for setup.

## HPC Integration

Deploy to HPC systems using Singularity wrappers and environment modules.

### Wrapper Scripts

Generate scripts that make containerized commands feel native:

```bash
absconda wrap \
  --image ghcr.io/org/myenv:latest \
  --commands python,pip,jupyter \
  --runtime singularity \
  --output-dir ./wrappers
```

Creates executable shell scripts that handle:
- SIF pulling and caching
- Volume mounts
- GPU support
- Environment variable passthrough

### Environment Modules

Generate Tcl module files for HPC module systems:

```bash
absconda module \
  --name myenv/1.0 \
  --wrapper-dir ./wrappers \
  --output-dir ./modulefiles \
  --description "My research environment" \
  --image ghcr.io/org/myenv:latest \
  --runtime singularity
```

Users can then:

```bash
module use ./modulefiles
module load myenv/1.0
python script.py  # Runs inside container transparently
```

See [HPC Deployment Guide](../guides/hpc-deployment.md) for complete workflow.

## Next Steps

- [Basic Usage](../guides/basic-usage.md) - Start using Absconda
- [CLI Reference](../reference/cli.md) - All commands and options
- [Examples](../examples/) - Real-world scenarios
