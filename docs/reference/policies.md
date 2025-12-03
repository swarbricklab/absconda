# Policies Reference

Complete reference for Absconda policy system for enforcing standards and best practices.

## Overview

Policies allow you to:
- Enforce allowed Conda channels
- Set default base images
- Control multi-stage builds
- Require specific OCI labels
- Inject custom logic via hooks

Policy files use YAML format and are discovered automatically or specified explicitly.

## Policy File Discovery

Absconda searches for `absconda-policy.yaml` in this order:

1. **Explicit path**: `--policy /path/to/policy.yaml`
2. **Project directory**: `./absconda-policy.yaml`
3. **Parent directories**: Recursively up to root
4. **User config**: `~/.config/absconda/absconda-policy.yaml`
5. **System config**: `/etc/xdg/absconda/absconda-policy.yaml`
6. **Built-in defaults**: If no file found

**Environment variable**: `ABSCONDA_POLICY=/path/to/policy.yaml`

## Basic Structure

```yaml
# absconda-policy.yaml

# Default profile to use
default_profile: standard

# Profile definitions
profiles:
  standard:
    # Base images
    builder_base: mambaorg/micromamba:latest
    runtime_base: mambaorg/micromamba:latest
    
    # Build mode
    multi_stage: true
    
    # Channel restrictions
    allowed_channels:
      - conda-forge
      - bioconda
    
    # Required labels
    required_labels:
      org.opencontainers.image.authors: "team@example.com"
    
  strict:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: mambaorg/micromamba:1.5.6
    multi_stage: true
    allowed_channels:
      - conda-forge
    required_labels:
      org.opencontainers.image.authors: "team@example.com"
      org.opencontainers.image.version: ""  # Required but any value

# Optional: Hook functions
hooks:
  module: my_policy_hooks
  before_render: validate_env
  after_validate: log_packages
```

## Profile Fields

### builder_base

Base image for builder stage (multi-stage builds).

```yaml
profiles:
  standard:
    builder_base: mambaorg/micromamba:latest
```

**Type**: string  
**Default**: `mambaorg/micromamba:latest`  
**Override**: `--builder-base` CLI flag

**Common values**:
- `mambaorg/micromamba:latest` - Latest Micromamba
- `mambaorg/micromamba:1.5.6` - Specific version
- `condaforge/miniforge3:latest` - Miniforge
- `continuumio/miniconda3:latest` - Miniconda

### runtime_base

Base image for runtime stage (multi-stage builds) or single-stage builds.

```yaml
profiles:
  standard:
    runtime_base: mambaorg/micromamba:latest
```

**Type**: string  
**Default**: `mambaorg/micromamba:latest`  
**Override**: `--runtime-base` CLI flag

**Common values**:
- `mambaorg/micromamba:latest` - Conda environment
- `ubuntu:22.04` - Minimal Ubuntu
- `python:3.11-slim` - Python base
- `nvidia/cuda:12.2.0-runtime-ubuntu22.04` - GPU runtime

### multi_stage

Enable or disable multi-stage builds.

```yaml
profiles:
  standard:
    multi_stage: true
```

**Type**: boolean  
**Default**: `true`  
**Override**: `--multi-stage` / `--single-stage` CLI flags

**Multi-stage** (recommended):
- Smaller final images
- Separate build and runtime dependencies
- Better layer caching

**Single-stage**:
- Simpler Dockerfile
- Includes build tools in final image
- Faster for development

### env_prefix

Conda environment installation prefix.

```yaml
profiles:
  standard:
    env_prefix: /opt/conda/envs
```

**Type**: string  
**Default**: `/opt/conda/envs`

Used for PATH and environment setup in container.

### allowed_channels

Restrict which Conda channels can be used.

```yaml
profiles:
  standard:
    allowed_channels:
      - conda-forge
      - bioconda
```

**Type**: list of strings  
**Default**: `[]` (no restrictions)

**Enforcement**: Build fails if environment file uses disallowed channels.

**Example restriction**:

```yaml
# Policy
allowed_channels:
  - conda-forge

# Environment file (REJECTED)
channels:
  - defaults    # ❌ Not allowed
  - conda-forge # ✅ OK
```

**Error message**:

```
Policy violation: channels [defaults] are not permitted by profile 'standard'.
Allowed channels: conda-forge
```

### required_labels

Require specific OCI labels in environment files.

```yaml
profiles:
  standard:
    required_labels:
      org.opencontainers.image.authors: "team@example.com"
      org.opencontainers.image.version: ""  # Any value OK
      custom.project: "project-name"
```

**Type**: dictionary (string → string)  
**Default**: `{}`

**Validation**:
- If value is empty string (`""`), any value satisfies requirement
- If value is non-empty, label must match exactly

**Example**:

```yaml
# Policy
required_labels:
  org.opencontainers.image.authors: "team@example.com"

# Environment file (OK)
labels:
  org.opencontainers.image.authors: "team@example.com"

# Environment file (REJECTED - wrong value)
labels:
  org.opencontainers.image.authors: "other@example.com"

# Environment file (REJECTED - missing)
labels:
  org.opencontainers.image.title: "My Environment"
```

### default_fragments

List of template fragments to include by default.

```yaml
profiles:
  standard:
    default_fragments:
      - validation
      - healthcheck
```

**Type**: list of strings  
**Default**: `[]`

**Usage**: Advanced template customization (see [Advanced Templating](../guides/advanced-templating.md)).

## Complete Profile Examples

### Permissive Profile

Allows flexibility for development:

```yaml
profiles:
  dev:
    builder_base: mambaorg/micromamba:latest
    runtime_base: mambaorg/micromamba:latest
    multi_stage: false
    allowed_channels: []  # Any channel OK
    required_labels: {}   # No labels required
```

### Standard Profile

Balanced for production use:

```yaml
profiles:
  standard:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: mambaorg/micromamba:1.5.6
    multi_stage: true
    allowed_channels:
      - conda-forge
      - bioconda
      - nvidia
    required_labels:
      org.opencontainers.image.authors: "team@example.com"
```

### Strict Profile

Maximum reproducibility and security:

```yaml
profiles:
  strict:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: ubuntu:22.04  # Minimal runtime
    multi_stage: true
    allowed_channels:
      - conda-forge
    required_labels:
      org.opencontainers.image.title: ""
      org.opencontainers.image.description: ""
      org.opencontainers.image.authors: "team@example.com"
      org.opencontainers.image.version: ""
      org.opencontainers.image.url: ""
      custom.project: ""
```

### GPU Profile

For CUDA/GPU workloads:

```yaml
profiles:
  gpu:
    builder_base: nvidia/cuda:12.2.0-devel-ubuntu22.04
    runtime_base: nvidia/cuda:12.2.0-runtime-ubuntu22.04
    multi_stage: true
    allowed_channels:
      - conda-forge
      - nvidia
      - pytorch
    required_labels:
      org.opencontainers.image.authors: "ml-team@example.com"
      custom.gpu: "required"
```

## Multiple Profiles

Define multiple profiles for different use cases:

```yaml
default_profile: standard

profiles:
  dev:
    builder_base: mambaorg/micromamba:latest
    runtime_base: mambaorg/micromamba:latest
    multi_stage: false
    allowed_channels: []
    required_labels: {}

  standard:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: mambaorg/micromamba:1.5.6
    multi_stage: true
    allowed_channels:
      - conda-forge
      - bioconda
    required_labels:
      org.opencontainers.image.authors: "team@example.com"

  strict:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: ubuntu:22.04
    multi_stage: true
    allowed_channels:
      - conda-forge
    required_labels:
      org.opencontainers.image.title: ""
      org.opencontainers.image.description: ""
      org.opencontainers.image.authors: "team@example.com"
      org.opencontainers.image.version: ""

  gpu:
    builder_base: nvidia/cuda:12.2.0-devel-ubuntu22.04
    runtime_base: nvidia/cuda:12.2.0-runtime-ubuntu22.04
    multi_stage: true
    allowed_channels:
      - conda-forge
      - nvidia
      - pytorch
    required_labels:
      org.opencontainers.image.authors: "ml-team@example.com"
```

**Usage**:

```bash
# Use default profile
absconda build --file env.yaml

# Use specific profile
absconda --profile strict build --file env.yaml

# Override for development
absconda --profile dev build --file env.yaml
```

## Hooks (Advanced)

Inject custom Python logic at key points in the build process.

### Hook Types

| Hook | When Called | Use Case |
|------|-------------|----------|
| `before_render` | Before Dockerfile generation | Modify environment, validate packages |
| `after_validate` | After environment validation | Log audit trail, check versions |
| `on_build_finished` | After successful build | Tag images, notify teams |

### Hook Configuration

```yaml
hooks:
  module: my_company.absconda_hooks
  before_render: validate_package_versions
  after_validate: audit_log
  on_build_finished: tag_and_notify
```

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `module` | string | Python module path to import |
| `before_render` | string | Function name for before_render hook |
| `after_validate` | string | Function name for after_validate hook |
| `on_build_finished` | string | Function name for on_build_finished hook |

### Hook Implementation

Create a Python module with hook functions:

```python
# my_company/absconda_hooks.py

def validate_package_versions(env, profile):
    """Called before Dockerfile rendering."""
    for package in env.dependencies:
        if '=' not in package:
            raise ValueError(f"Package {package} must have pinned version")

def audit_log(env, warnings):
    """Called after environment validation."""
    import logging
    logging.info(f"Building environment: {env.name}")
    logging.info(f"Packages: {len(env.dependencies)}")
    if warnings:
        logging.warning(f"Warnings: {warnings}")

def tag_and_notify(image_ref, manifest):
    """Called after successful build."""
    import requests
    # Tag image with additional tags
    # Notify team via Slack/email
    requests.post("https://hooks.slack.com/...", json={
        "text": f"New image built: {image_ref}"
    })
```

**Note**: Hooks must be importable from Python path.

## Using Policies

### Default Profile

```bash
# Uses default_profile from policy file
absconda build --file env.yaml
```

### Specific Profile

```bash
# Override profile
absconda --profile strict build --file env.yaml
```

### Custom Policy File

```bash
# Use specific policy file
absconda --policy ./custom-policy.yaml build --file env.yaml

# With specific profile
absconda --policy ./custom-policy.yaml --profile gpu build --file env.yaml
```

### Environment Variable

```bash
# Set default policy file
export ABSCONDA_POLICY=~/.config/absconda/custom-policy.yaml
absconda build --file env.yaml

# Set default profile
export ABSCONDA_PROFILE=strict
absconda build --file env.yaml
```

## Policy Enforcement

### Channel Violations

**Policy**:

```yaml
profiles:
  standard:
    allowed_channels:
      - conda-forge
```

**Environment file**:

```yaml
channels:
  - defaults
  - conda-forge
```

**Result**:

```
Policy violation: channels [defaults] are not permitted by profile 'standard'.
Allowed channels: conda-forge
```

### Label Requirements

**Policy**:

```yaml
profiles:
  standard:
    required_labels:
      org.opencontainers.image.authors: "team@example.com"
```

**Environment file** (missing label):

```yaml
name: myenv
channels:
  - conda-forge
dependencies:
  - python=3.11
```

**Result**: Build fails with label requirement error.

## Best Practices

1. **Use profiles for environments**: Dev, staging, production
2. **Pin base images**: Use specific versions in strict profiles
3. **Restrict channels**: Limit to trusted sources
4. **Require labels**: Enforce metadata standards
5. **Multi-stage by default**: Smaller, more secure images
6. **Document profiles**: Add comments explaining each profile's purpose
7. **Version control**: Commit policy files to repository
8. **Team-wide policies**: Place in system config for consistency
9. **Test policies**: Validate with sample environments
10. **Gradual enforcement**: Start permissive, tighten over time

## Team Setup Example

**System-wide policy** (`/etc/xdg/absconda/absconda-policy.yaml`):

```yaml
# Company-wide defaults
default_profile: standard

profiles:
  standard:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: mambaorg/micromamba:1.5.6
    multi_stage: true
    allowed_channels:
      - conda-forge
      - bioconda
    required_labels:
      org.opencontainers.image.authors: "bioinfo@company.com"

  production:
    builder_base: mambaorg/micromamba:1.5.6
    runtime_base: ubuntu:22.04
    multi_stage: true
    allowed_channels:
      - conda-forge
    required_labels:
      org.opencontainers.image.title: ""
      org.opencontainers.image.version: ""
      org.opencontainers.image.authors: "bioinfo@company.com"
```

**User override** (`~/.config/absconda/absconda-policy.yaml`):

```yaml
# Personal development profile
profiles:
  dev:
    builder_base: mambaorg/micromamba:latest
    multi_stage: false
    allowed_channels: []
    required_labels: {}
```

**Usage**:

```bash
# Development (personal profile)
absconda --profile dev build --file env.yaml

# Standard (company profile)
absconda build --file env.yaml

# Production (company profile, stricter)
absconda --profile production build --file env.yaml
```

## Troubleshooting

### Policy not loading

```bash
# Check which policy file is loaded
absconda build --file env.yaml
# Output shows: "Using policy profile X from /path/to/policy.yaml"

# Explicitly specify policy
absconda --policy ./my-policy.yaml build --file env.yaml
```

### Profile not found

```
Error: Profile 'strict' was not found in policy file '/path/to/policy.yaml'.
```

**Solution**: Check profile name spelling, ensure it's defined in `profiles:` section.

### Hook module not found

```
Error: Failed to import hook module 'my_hooks': No module named 'my_hooks'
```

**Solution**: Ensure module is installed or in `PYTHONPATH`:

```bash
export PYTHONPATH=/path/to/hooks:$PYTHONPATH
absconda build --file env.yaml
```

## Next Steps

- [CLI Reference](cli.md) - Command-line usage
- [Configuration](configuration.md) - Config file reference
- [Environment Files](environment-files.md) - Environment YAML format
- [Basic Usage Guide](../guides/basic-usage.md) - Workflow examples
