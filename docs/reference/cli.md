# CLI Reference

Complete reference for all `absconda` commands and options.

## Global Options

Available for all commands:

```bash
absconda [GLOBAL_OPTIONS] COMMAND [OPTIONS]
```

### --version

Show version and exit.

```bash
absconda --version
# Output: Absconda 0.1.0
```

### --policy PATH

Path to custom policy file.

```bash
absconda --policy ./custom-policy.yaml generate --file env.yaml
```

**Default**: Auto-discovers from:
1. `./absconda-policy.yaml`
2. `~/.config/absconda/policy.yaml`
3. `/etc/xdg/absconda/policy.yaml`
4. Built-in defaults

### --profile NAME

Policy profile to activate.

```bash
absconda --profile strict build --file env.yaml
```

**Default**: Profile marked `default: true` in policy file.

## Commands

### generate

Generate a Dockerfile from an environment definition.

```bash
absconda generate [OPTIONS]
```

**Input Options** (choose one):

| Option | Description | Default |
|--------|-------------|---------|
| `--file PATH`, `-f` | Conda environment YAML file | `env.yaml` |
| `--tarball PATH`, `-t` | Pre-packed conda tarball | - |
| `--requirements PATH`, `-r` | pip requirements.txt | - |

**Output Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--output PATH`, `-o` | Write Dockerfile to path | stdout |

**Build Configuration**:

| Option | Description | Default |
|--------|-------------|---------|
| `--template PATH` | Custom Jinja2 template | Built-in |
| `--builder-base IMAGE` | Builder stage base image | Policy default |
| `--runtime-base IMAGE` | Runtime stage base image | Policy default |
| `--multi-stage` / `--single-stage` | Force multi-stage mode | Policy default |
| `--renv-lock PATH` | R renv.lock file | - |
| `--snapshot PATH` | Conda snapshot for validation | - |

**Examples**:

```bash
# Generate to stdout
absconda generate --file environment.yaml

# Write to file
absconda generate --file environment.yaml --output Dockerfile

# Use custom template
absconda generate --file environment.yaml --template custom.j2

# Requirements mode
absconda generate --requirements requirements.txt --output Dockerfile

# With R support
absconda generate --file env.yaml --renv-lock renv.lock --output Dockerfile

# Single-stage build
absconda generate --file env.yaml --single-stage --output Dockerfile
```

---

### validate

Validate environment files without generating output.

```bash
absconda validate [OPTIONS]
```

**Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--file PATH`, `-f` | Conda environment YAML file | `env.yaml` |
| `--tarball PATH`, `-t` | Pre-packed conda tarball | - |
| `--requirements PATH`, `-r` | pip requirements.txt | - |
| `--snapshot PATH` | Conda snapshot for validation | - |

**Examples**:

```bash
# Validate environment file
absconda validate --file environment.yaml

# Validate tarball
absconda validate --tarball conda-env.tar.gz

# Validate requirements
absconda validate --requirements requirements.txt

# Validate with snapshot
absconda validate --file env.yaml --snapshot snapshot.yaml
```

**Output**:

```
Using policy profile default from /Users/user/.config/absconda/policy.yaml.
Environment myenv is valid with 15 dependency entries.
warning: Package 'numpy' version not pinned
```

---

### build

Build a container image locally or remotely.

```bash
absconda build [OPTIONS]
```

**Repository Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--repository REPO` | Image repository | `<registry>/<org>/<env-name>` from config |
| `--tag TAG` | Image tag | `YYYYMMDD` |

**Input Options** (choose one):

| Option | Description | Default |
|--------|-------------|---------|
| `--file PATH`, `-f` | Conda environment YAML | `env.yaml` |
| `--tarball PATH`, `-t` | Pre-packed conda tarball | - |
| `--requirements PATH`, `-r` | pip requirements.txt | - |

**Build Configuration**:

| Option | Description | Default |
|--------|-------------|---------|
| `--template PATH` | Custom Jinja2 template | Built-in |
| `--builder-base IMAGE` | Builder stage base image | Policy default |
| `--runtime-base IMAGE` | Runtime stage base image | Policy default |
| `--multi-stage` / `--single-stage` | Force multi-stage mode | Policy default |
| `--context PATH` | Docker build context | `.` |
| `--push` | Push after building | `false` |
| `--renv-lock PATH` | R renv.lock file | - |
| `--snapshot PATH` | Conda snapshot | - |

**Remote Build Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--remote-builder NAME` | Remote builder name | - |
| `--remote-config PATH` | Remote config file | Auto-discover |
| `--remote-wait SECONDS` | Wait timeout for busy builder | `900` |
| `--remote-off` | Stop builder after build | `false` |

**Examples**:

```bash
# Basic local build
absconda build --file env.yaml --repository ghcr.io/org/myenv --tag v1.0

# Build and push
absconda build --file env.yaml --repository ghcr.io/org/myenv --push

# Remote build
absconda build \
  --file env.yaml \
  --repository ghcr.io/org/myenv \
  --tag v1.0 \
  --remote-builder gcp-builder \
  --push

# Remote build with auto-shutdown
absconda build \
  --file env.yaml \
  --remote-builder gcp-builder \
  --remote-off \
  --push

# Requirements mode
absconda build \
  --requirements requirements.txt \
  --repository ghcr.io/org/myapp \
  --tag latest \
  --push

# With custom context
absconda build \
  --file env.yaml \
  --context /path/to/project \
  --repository ghcr.io/org/myenv

# Use config defaults for repository
absconda build --file env.yaml --tag v1.0 --push
```

**Output**:

```
Using policy profile default from /Users/user/.config/absconda/policy.yaml.
[remote] Starting builder gcp-builder...
[remote] Builder is running
[remote] Uploading build context (2.3 MB)...
[remote] Running docker build...
[remote] Build completed successfully
Image built: ghcr.io/org/myenv:v1.0
Image pushed: ghcr.io/org/myenv:v1.0
```

---

### publish

Build, push, and optionally create Singularity artifact.

```bash
absconda publish [OPTIONS]
```

Same options as `build`, plus:

| Option | Description | Default |
|--------|-------------|---------|
| `--singularity-out PATH` | Output .sif file path | - |

**Note**: `--push` is automatic with publish command.

**Examples**:

```bash
# Build, push, and pull Singularity image
absconda publish \
  --file env.yaml \
  --repository ghcr.io/org/myenv \
  --tag v1.0 \
  --singularity-out myenv.sif

# Remote build with Singularity
absconda publish \
  --file env.yaml \
  --remote-builder gcp-builder \
  --singularity-out myenv.sif
```

**Output**:

```
Image pushed: ghcr.io/org/myenv:v1.0
INFO:    Converting OCI blobs to SIF format
INFO:    Starting build...
Singularity image written to myenv.sif
```

---

### wrap

Generate wrapper scripts for container commands.

```bash
absconda wrap [OPTIONS]
```

**Required Options**:

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Container image reference (e.g., `ghcr.io/org/env:tag`) |
| `--commands LIST` | Comma-separated commands to wrap |

**Configuration Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--runtime RUNTIME` | Container runtime (`singularity` or `docker`) | `singularity` |
| `--output-dir PATH` | Wrapper script directory | Config or `~/.local/absconda/wrappers/<image>` |
| `--image-cache PATH` | SIF cache directory (Singularity) | Config or `~/.local/absconda/sif-cache` |

**Mount and Environment Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--extra-mounts LIST` | Comma-separated mount paths | Config defaults |
| `--env LIST` | Comma-separated env vars to pass through | Config defaults |
| `--gpu` | Enable GPU support | `false` |

**Examples**:

```bash
# Basic wrapper generation
absconda wrap \
  --image ghcr.io/org/myenv:v1.0 \
  --commands python,pip,jupyter

# Docker runtime
absconda wrap \
  --image ghcr.io/org/myenv:v1.0 \
  --commands python \
  --runtime docker

# With GPU support
absconda wrap \
  --image ghcr.io/org/gpu-env:latest \
  --commands python \
  --gpu

# Custom mounts and env vars
absconda wrap \
  --image ghcr.io/org/myenv:v1.0 \
  --commands python \
  --extra-mounts /scratch/$PROJECT,/g/data/$PROJECT \
  --env PBS_JOBID,TMPDIR

# Custom output directory
absconda wrap \
  --image ghcr.io/org/myenv:v1.0 \
  --commands python,pip \
  --output-dir /path/to/wrappers
```

**Output**:

```
✓ Generated 3 wrapper script(s) in /Users/user/.local/absconda/wrappers/myenv

Runtime: singularity
Image: ghcr.io/org/myenv:v1.0

Wrapped commands:
  • python → /Users/user/.local/absconda/wrappers/myenv/python
  • pip → /Users/user/.local/absconda/wrappers/myenv/pip
  • jupyter → /Users/user/.local/absconda/wrappers/myenv/jupyter

Next steps:
  1. Add /Users/user/.local/absconda/wrappers/myenv to your PATH, or
  2. Generate a module file with: absconda module --wrapper-dir /Users/user/.local/absconda/wrappers/myenv
```

---

### module

Generate an environment module file for wrappers.

```bash
absconda module [OPTIONS]
```

**Required Options**:

| Option | Description |
|--------|-------------|
| `--name NAME` | Module name with version (e.g., `myenv/1.0`) |
| `--wrapper-dir PATH` | Directory containing wrapper scripts |
| `--description TEXT` | Module description |
| `--image IMAGE` | Container image reference |

**Configuration Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--runtime RUNTIME` | Container runtime | `singularity` |
| `--output-dir PATH` | Module file directory | Config or `~/.local/absconda/modulefiles` |
| `--commands LIST` | Comma-separated command list | Auto-detect from wrapper-dir |

**Examples**:

```bash
# Basic module generation
absconda module \
  --name myenv/1.0 \
  --wrapper-dir ~/.local/absconda/wrappers/myenv \
  --description "Python data science environment" \
  --image ghcr.io/org/myenv:v1.0

# With explicit commands
absconda module \
  --name myenv/1.0 \
  --wrapper-dir /path/to/wrappers \
  --description "Analysis environment" \
  --image ghcr.io/org/myenv:v1.0 \
  --commands python,pip,jupyter

# Docker runtime
absconda module \
  --name myenv/1.0 \
  --wrapper-dir ~/.local/absconda/wrappers/myenv \
  --description "Container environment" \
  --image ghcr.io/org/myenv:v1.0 \
  --runtime docker

# Custom output directory
absconda module \
  --name myenv/1.0 \
  --wrapper-dir ~/.local/absconda/wrappers/myenv \
  --description "Environment" \
  --image ghcr.io/org/myenv:v1.0 \
  --output-dir /path/to/modulefiles
```

**Output**:

```
✓ Generated module file: /Users/user/.local/absconda/modulefiles/myenv/1.0

Module name: myenv/1.0
Wrapper directory: /Users/user/.local/absconda/wrappers/myenv
Runtime: singularity
Image: ghcr.io/org/myenv:v1.0

Usage:
  module use /Users/user/.local/absconda/modulefiles
  module load myenv/1.0
  module help myenv/1.0
```

---

## Remote Commands

### remote list

List configured remote builders.

```bash
absconda remote list [--config PATH]
```

**Output**:

```
Remote builders defined in /Users/user/project/absconda-remote.yaml:
 • gcp-builder
 • aws-builder
```

---

### remote provision

Provision remote builder infrastructure (Terraform).

```bash
absconda remote provision BUILDER [--config PATH]
```

**Example**:

```bash
absconda remote provision gcp-builder
```

---

### remote start

Start a stopped remote builder instance.

```bash
absconda remote start BUILDER [--config PATH]
```

**Example**:

```bash
absconda remote start gcp-builder
```

---

### remote stop

Stop a running remote builder instance.

```bash
absconda remote stop BUILDER [--config PATH]
```

**Example**:

```bash
absconda remote stop gcp-builder
```

---

### remote status

Check remote builder status and availability.

```bash
absconda remote status BUILDER [--config PATH]
```

**Output**:

```
Builder gcp-builder is reachable via SSH.
Lock: free
Health check: passing
```

Or if there are issues:

```
Builder gcp-builder is unreachable via SSH.
  ssh: Permission denied (publickey)

💡 Tip: For GCP VMs with OS Login, you may need to authenticate first:
   gcloud compute ssh gcp-builder --zone=$GCP_ZONE --tunnel-through-iap --project=$GCP_PROJECT
```

---

### remote init

Initialize SSH access to remote builder (GCP OS Login).

```bash
absconda remote init BUILDER [--config PATH]
```

**Example**:

```bash
absconda remote init gcp-builder
```

**Output**:

```
Initializing SSH access to gcp-builder...
This will run: gcloud compute ssh gcp-builder --zone=us-central1-a --tunnel-through-iap --project=my-project

✓ SSH access initialized successfully!

💡 Note: Your OS Login username is: j_reeves_garvan_org_au
Update the 'user' field in your config if it differs from the current setting.

You can now use: absconda remote status gcp-builder
```

---

## Environment Variables

Absconda recognizes these environment variables:

| Variable | Description |
|----------|-------------|
| `ABSCONDA_POLICY` | Default policy file path |
| `ABSCONDA_PROFILE` | Default policy profile name |
| `ABSCONDA_CONFIG` | Config file path (overrides XDG defaults) |
| `GCP_PROJECT` | GCP project ID (for remote builders) |
| `GCP_REGION` | GCP region (for remote builders) |
| `GCP_ZONE` | GCP zone (for remote builders) |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error (invalid input, command failed) |
| `2` | Policy violation |

---

## Next Steps

- [Environment Files](environment-files.md) - YAML format reference
- [Configuration](configuration.md) - Config file reference
- [Policies](policies.md) - Policy system reference
- [Guides](../guides/basic-usage.md) - Workflow examples
