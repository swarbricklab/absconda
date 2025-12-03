# Configuration Reference

Complete reference for Absconda configuration system using XDG Base Directory specification.

## Overview

Absconda uses a hierarchical configuration system:

1. **System-wide**: `/etc/xdg/absconda/config.yaml` (or `$XDG_CONFIG_DIRS`)
2. **User-level**: `~/.config/absconda/config.yaml` (or `$XDG_CONFIG_HOME`)
3. **Environment variables**: Override config file settings
4. **Command-line arguments**: Override everything

Later sources override earlier ones.

## Configuration Files

### Locations

Config files are discovered in this order:

```bash
# System-wide (lowest priority)
/etc/xdg/absconda/config.yaml

# User-level (higher priority)
~/.config/absconda/config.yaml

# Custom location via environment variable
export XDG_CONFIG_HOME=/custom/path
$XDG_CONFIG_HOME/absconda/config.yaml
```

### Format

Configuration files use YAML format:

```yaml
# ~/.config/absconda/config.yaml

# Container registry settings
registry: ghcr.io
organization: myorg

# GCP settings for remote builders
gcp_project: my-gcp-project
gcp_region: us-central1
gcp_zone: us-central1-a

# Remote builder definitions
remote_builders:
  gcp-builder:
    provider: gcp
    project: my-gcp-project
    zone: us-central1-a
    machine_type: n1-standard-8

# Policy settings
default_policy: ~/.config/absconda/policy.yaml
default_profile: standard

# Template paths
template_dir: ~/.config/absconda/templates

# Wrapper generation settings
wrappers:
  default_runtime: singularity
  default_output_dir: ~/.local/absconda/wrappers
  image_cache: ~/.local/absconda/sif-cache
  default_mounts:
    - $HOME
    - $PWD
    - /scratch/$PROJECT
  env_passthrough:
    - USER
    - HOME
    - LANG
    - TZ
  env_filter:
    - PATH
    - LD_LIBRARY_PATH
    - PYTHONPATH

# Module generation settings
modules:
  default_output_dir: ~/.local/absconda/modulefiles
  format: tcl
```

## Configuration Sections

### Registry Settings

Configure default container registry and organization.

```yaml
registry: ghcr.io
organization: swarbricklab
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `registry` | string | `ghcr.io` | Container registry hostname |
| `organization` | string | - | Organization/user name for images |

**Usage**: When `--repository` is not specified, images use:

```
<registry>/<organization>/<env-name>:<tag>
```

**Example**:

```yaml
registry: ghcr.io
organization: myteam
```

With `absconda build --file env.yaml --tag v1.0`:

```
Built: ghcr.io/myteam/env:v1.0
```

### GCP Settings

Google Cloud Platform configuration for remote builders.

```yaml
gcp_project: my-gcp-project
gcp_region: us-central1
gcp_zone: us-central1-a
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gcp_project` | string | - | GCP project ID |
| `gcp_region` | string | - | GCP region (e.g., `us-central1`) |
| `gcp_zone` | string | - | GCP zone (e.g., `us-central1-a`) |

**Environment variable override**:

```bash
export GCP_PROJECT=my-project
export GCP_REGION=us-central1
export GCP_ZONE=us-central1-a
```

Environment variables take precedence over config file.

### Remote Builders

Define remote build infrastructure.

```yaml
remote_builders:
  gcp-builder:
    provider: gcp
    project: my-gcp-project
    zone: us-central1-a
    machine_type: n1-standard-8
    disk_size_gb: 100
    
    # Commands (optional, auto-detected for GCP)
    start_command: "gcloud compute instances start absconda-builder --zone=us-central1-a"
    stop_command: "gcloud compute instances stop absconda-builder --zone=us-central1-a"
    status_command: "gcloud compute instances describe absconda-builder --zone=us-central1-a --format='value(status)'"
    
    # SSH settings
    user: myusername
    host: absconda-builder
    ssh_port: 22
    
    # Metadata
    metadata:
      project: my-gcp-project
      zone: us-central1-a
```

**Provider-specific fields**:

**GCP**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `provider` | string | Yes | Must be `gcp` |
| `project` | string | Yes | GCP project ID |
| `zone` | string | Yes | GCP zone |
| `machine_type` | string | No | Instance type (default: `n1-standard-4`) |
| `disk_size_gb` | int | No | Boot disk size (default: 100) |
| `image_family` | string | No | Image family (default: `cos-stable`) |
| `image_project` | string | No | Image project (default: `cos-cloud`) |

**SSH fields**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user` | string | Yes | SSH username |
| `host` | string | Yes | Hostname or IP |
| `ssh_port` | int | No | SSH port (default: 22) |

**Command fields** (optional, auto-detected for GCP):

| Field | Type | Description |
|-------|------|-------------|
| `start_command` | string | Command to start instance |
| `stop_command` | string | Command to stop instance |
| `status_command` | string | Command to check status |

### Policy Settings

Configure default policy behavior.

```yaml
default_policy: ~/.config/absconda/policy.yaml
default_profile: strict
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_policy` | string | - | Path to policy file |
| `default_profile` | string | - | Default profile name |

**Note**: Command-line flags (`--policy`, `--profile`) override these.

### Template Settings

Configure custom template directory.

```yaml
template_dir: ~/.config/absconda/templates
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `template_dir` | string | - | Directory containing custom templates |

Absconda searches for `Dockerfile.j2` in this directory when no `--template` flag is provided.

### Wrapper Settings

Configure wrapper script generation defaults.

```yaml
wrappers:
  default_runtime: singularity
  default_output_dir: ~/.local/absconda/wrappers
  image_cache: ~/.local/absconda/sif-cache
  default_mounts:
    - $HOME
    - $PWD
    - /scratch/$PROJECT
    - /g/data/$PROJECT
  env_passthrough:
    - USER
    - HOME
    - LANG
    - TZ
    - PBS_JOBID
    - SLURM_JOB_ID
  env_filter:
    - PATH
    - LD_LIBRARY_PATH
    - PYTHONPATH
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_runtime` | string | `singularity` | Container runtime (`singularity` or `docker`) |
| `default_output_dir` | string | `~/.local/absconda/wrappers/<image>` | Wrapper script directory |
| `image_cache` | string | `~/.local/absconda/sif-cache` | SIF cache (Singularity only) |
| `default_mounts` | list | `[$HOME, $PWD]` | Default volume mounts |
| `env_passthrough` | list | `[USER, HOME, LANG, TZ]` | Environment variables to pass through |
| `env_filter` | list | `[PATH, LD_LIBRARY_PATH, PYTHONPATH]` | Environment variables to NOT pass through |

**Mount paths**: Can use environment variables (e.g., `$PROJECT`, `$USER`).

**Environment passthrough**:
- `env_passthrough`: Variables explicitly passed to container
- `env_filter`: Variables explicitly blocked from container

### Module Settings

Configure environment module generation defaults.

```yaml
modules:
  default_output_dir: ~/.local/absconda/modulefiles
  format: tcl
```

**Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_output_dir` | string | `~/.local/absconda/modulefiles` | Module file directory |
| `format` | string | `tcl` | Module file format (currently only `tcl`) |

## Environment Variables

Environment variables override config file settings:

| Variable | Overrides | Description |
|----------|-----------|-------------|
| `XDG_CONFIG_HOME` | - | Config directory location |
| `XDG_CONFIG_DIRS` | - | System config directories |
| `GCP_PROJECT` | `gcp_project` | GCP project ID |
| `GCP_REGION` | `gcp_region` | GCP region |
| `GCP_ZONE` | `gcp_zone` | GCP zone |
| `ABSCONDA_POLICY` | `default_policy` | Policy file path |
| `ABSCONDA_PROFILE` | `default_profile` | Policy profile name |

## Complete Example

Comprehensive configuration for NCI Gadi HPC system:

```yaml
# ~/.config/absconda/config.yaml

# Container registry
registry: ghcr.io
organization: swarbricklab

# GCP for remote builds
gcp_project: swarbrick-gcp
gcp_region: us-central1
gcp_zone: us-central1-a

# Remote builders
remote_builders:
  gcp-builder:
    provider: gcp
    project: swarbrick-gcp
    zone: us-central1-a
    machine_type: n1-standard-8
    disk_size_gb: 100
    user: j_reeves_garvan_org_au
    host: absconda-builder
    metadata:
      project: swarbrick-gcp
      zone: us-central1-a

# Policy
default_policy: ~/.config/absconda/policy.yaml
default_profile: standard

# Templates
template_dir: ~/.config/absconda/templates

# Wrappers - NCI Gadi specific
wrappers:
  default_runtime: singularity
  default_output_dir: /g/data/a56/apps/absconda/wrappers
  image_cache: /g/data/a56/apps/absconda/sif-cache
  default_mounts:
    - $HOME
    - $PWD
    - /scratch/$PROJECT
    - /g/data/$PROJECT
  env_passthrough:
    - USER
    - HOME
    - LANG
    - TZ
    - TMPDIR
    - PBS_JOBID
    - PBS_JOBNAME
    - PBS_QUEUE
    - PBS_O_WORKDIR
  env_filter:
    - PATH
    - LD_LIBRARY_PATH
    - PYTHONPATH
    - PERL5LIB
    - R_LIBS
    - JULIA_DEPOT_PATH

# Modules - NCI Gadi specific
modules:
  default_output_dir: /g/data/a56/apps/absconda/modulefiles
  format: tcl
```

## Config Merging

Multiple config files are deep-merged:

**System config** (`/etc/xdg/absconda/config.yaml`):

```yaml
registry: ghcr.io
wrappers:
  default_runtime: singularity
  default_mounts:
    - $HOME
    - $PWD
```

**User config** (`~/.config/absconda/config.yaml`):

```yaml
organization: myteam
wrappers:
  default_mounts:
    - $HOME
    - $PWD
    - /scratch/$PROJECT
  image_cache: ~/.local/absconda/sif-cache
```

**Merged result**:

```yaml
registry: ghcr.io                    # From system
organization: myteam                 # From user
wrappers:
  default_runtime: singularity       # From system
  default_mounts:                    # From user (overrides)
    - $HOME
    - $PWD
    - /scratch/$PROJECT
  image_cache: ~/.local/absconda/sif-cache  # From user (adds)
```

## Configuration Discovery

To see which config files are loaded:

```bash
# Check config directories
python3 -c "from absconda.config import get_config_dirs; print('\n'.join(str(d) for d in get_config_dirs()))"

# Load and inspect config
python3 -c "from absconda.config import load_config; import pprint; pprint.pprint(load_config().__dict__)"
```

## Best Practices

1. **User-level config**: Put personal settings in `~/.config/absconda/config.yaml`
2. **System-level config**: Put shared team settings in `/etc/xdg/absconda/config.yaml`
3. **Environment variables**: Use for CI/CD or temporary overrides
4. **Registry and org**: Set these globally to avoid repeating `--repository`
5. **Remote builders**: Define once, use across all projects
6. **HPC mounts**: Configure project-specific mounts in user config
7. **Version control**: Don't commit config files with secrets (use env vars for sensitive data)

## Migration

### From absconda-remote.yaml

Old format:

```yaml
# absconda-remote.yaml
builders:
  gcp-builder:
    provider: gcp
    ...
```

New format:

```yaml
# ~/.config/absconda/config.yaml
remote_builders:
  gcp-builder:
    provider: gcp
    ...
```

Absconda still discovers `absconda-remote.yaml` for backwards compatibility, but config file is preferred.

## Troubleshooting

### Config not loading

```bash
# Check config file syntax
python3 -c "import yaml; yaml.safe_load(open('~/.config/absconda/config.yaml'))"

# Check permissions
ls -la ~/.config/absconda/config.yaml
```

### Wrong defaults applied

Check config merge order:

```bash
# See which files exist
for dir in /etc/xdg/absconda ~/.config/absconda; do
  if [ -f "$dir/config.yaml" ]; then
    echo "Found: $dir/config.yaml"
  fi
done
```

Later files override earlier ones.

### Environment variables not working

Environment variables only override specific fields (GCP settings, policy). Use config file for other settings.

## Next Steps

- [CLI Reference](cli.md) - Command-line usage
- [Policies Reference](policies.md) - Policy system
- [Remote Builders Guide](../guides/remote-builders.md) - Remote build setup
- [HPC Deployment Guide](../guides/hpc-deployment.md) - HPC-specific configuration
