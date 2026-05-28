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
# Output: Absconda 0.2.5
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

**Dockerfile Override Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--dockerfile PATH` | Use a pre-existing Dockerfile (skips generation) | - |
| `--build-arg KEY=VALUE` | Docker build argument (repeatable) | - |
| `--env-name NAME` | Override the environment name used for tagging and PATH setup | From env file |

**Notes on `--env-name`**: When `--dockerfile` is used without `--file`/`--tarball`/`--requirements`, absconda attempts to auto-detect the environment name from `ENV CONDA_DEFAULT_ENV=<name>` in the Dockerfile. If that line is absent, either `--repository` or `--env-name` must be specified.

**Progress messages are written to stderr**, so `absconda generate --file env.yaml > Dockerfile` produces a clean Dockerfile on stdout.

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

# Build from a pre-existing Dockerfile (env name auto-detected)
absconda build \
  --dockerfile Dockerfile \
  --repository ghcr.io/org/myenv \
  --tag v1.0 \
  --push

# Build from a pre-existing Dockerfile with explicit env name
absconda build \
  --dockerfile Dockerfile \
  --env-name myenv \
  --push
```

**Output** (progress goes to stderr, clean output on stdout):

```
Using policy profile default from /Users/user/.config/absconda/policy.yaml.
Image built: ghcr.io/org/myenv:v1.0
Image pushed: ghcr.io/org/myenv:v1.0
```

---

### publish

Build and push a container image to a registry. Push is always performed.

```bash
absconda publish [OPTIONS]
```

Accepts the same options as `build` (see above), except `--push` is implicit and not needed.
Key options:

| Option | Description | Default |
|--------|-------------|---------|
| `--repository REPO` | Image repository | `<registry>/<org>/<env-name>` from config |
| `--tag TAG` | Image tag | `YYYYMMDD` |
| `--file PATH`, `-f` | Conda environment YAML | `env.yaml` |
| `--tarball PATH`, `-t` | Pre-packed conda tarball | - |
| `--requirements PATH`, `-r` | pip requirements.txt | - |
| `--dockerfile PATH` | Use a pre-existing Dockerfile | - |
| `--build-arg KEY=VALUE` | Docker build argument (repeatable) | - |
| `--env-name NAME` | Override the environment name | From env file |
| `--remote-builder NAME` | Remote builder name | - |
| `--remote-off` | Stop builder after build | `false` |

**To create a Singularity image after pushing**, use `singularity pull` or the `deploy` command:

```bash
singularity pull myenv.sif docker://ghcr.io/org/myenv:v1.0
# or
absconda deploy ghcr.io/org/myenv:v1.0 --commands python,pip
```

**Examples**:

```bash
# Build and push
absconda publish \
  --file env.yaml \
  --repository ghcr.io/org/myenv \
  --tag v1.0

# Remote build, then push
absconda publish \
  --file env.yaml \
  --remote-builder gcp-builder

# Publish from a pre-existing Dockerfile
absconda publish \
  --dockerfile Dockerfile \
  --env-name myenv
```

**Output**:

```
Using policy profile default from /Users/user/.config/absconda/policy.yaml.
Image pushed: ghcr.io/org/myenv:v1.0
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
| `--env-dir PATH` | Conda env path inside container (for PATH setup) | Auto-derived from policy `env_prefix` |
| `--shims LIST` | Shim groups to inject alongside wrappers (e.g., `pbs,singularity`) | - |

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

Generate a Tcl environment module file that adds wrapper scripts to PATH.

```bash
absconda module [OPTIONS]
```

**Required Options**:

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Container image reference (used to derive defaults) |

**Optional Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--name NAME` | Module name (e.g., `myenv/1.0`) | Derived from image `<name>/<tag>` |
| `--wrapper-dir PATH` | Directory containing wrapper scripts | Config or `~/.local/absconda/wrappers/<name>/<tag>` |
| `--output-dir PATH` | Module file output directory | Config or `~/.local/absconda/modulefiles` |
| `--description TEXT` | Module description | `<name> environment` |
| `--runtime RUNTIME` | Container runtime | `singularity` |
| `--commands LIST` | Comma-separated command list (for help text) | - |

**Examples**:

```bash
# Minimal — all defaults derived from image reference
absconda module --image ghcr.io/org/myenv:v1.0

# Explicit name and wrapper directory
absconda module \
  --image ghcr.io/org/myenv:v1.0 \
  --name myenv/1.0 \
  --wrapper-dir ~/.local/absconda/wrappers/myenv/v1.0 \
  --description "Python data science environment"

# Custom output directory
absconda module \
  --image ghcr.io/org/myenv:v1.0 \
  --output-dir /path/to/modulefiles
```

**Output**:

```
✓ Generated module file: /Users/user/.local/absconda/modulefiles/myenv/v1.0

Module name: myenv/v1.0
Wrapper directory: /Users/user/.local/absconda/wrappers/myenv/v1.0
Runtime: singularity
Image: ghcr.io/org/myenv:v1.0

Usage:
  module use /Users/user/.local/absconda/modulefiles
  module load myenv/v1.0
  module help myenv/v1.0
```

---

### deploy

Pull a container image, generate wrapper scripts, and create an environment module in one step. Can also build and push the image first when `--file` is provided.

```bash
absconda deploy [IMAGE] [OPTIONS]
```

**Arguments**:

| Argument | Description |
|----------|-------------|
| `IMAGE` | Container image reference (e.g., `ghcr.io/org/env:tag`). Omit when using `--file` to build first. |

**Deploy Options**:

| Option | Description | Default |
|--------|-------------|---------|
| `--commands LIST` | Comma-separated commands to wrap (required unless `--no-wrap`) | - |
| `--runtime RUNTIME` | Container runtime: `singularity` or `docker` | Config or `singularity` |
| `--image-cache PATH` | Directory to cache pulled SIF files | Config or `~/.local/absconda/sif-cache` |
| `--output-dir PATH` | Directory for wrapper scripts | Config or `~/.local/absconda/wrappers/<name>/<tag>` |
| `--module-dir PATH` | Directory for module files | Config or `~/.local/absconda/modulefiles` |
| `--extra-mounts LIST` | Additional volume mounts (comma-separated) | Config defaults |
| `--env LIST` | Additional env vars to pass through (comma-separated) | Config defaults |
| `--gpu` | Enable GPU support | `false` |
| `--env-dir PATH` | Conda env path inside container | Auto-derived |
| `--shims LIST` | Shim groups to inject (e.g., `pbs,singularity`) | - |
| `--no-wrap` | Skip wrapper generation | `false` |
| `--no-module` | Skip module file generation | `false` |

**Build Options** (when providing `--file` to build first):

Same as `build`/`publish`: `--file`, `--tarball`, `--requirements`, `--repository`, `--tag`, `--snapshot`, `--template`, `--builder-base`, `--runtime-base`, `--multi-stage/--single-stage`, `--context`, `--renv-lock`, `--remote-builder`, `--remote-config`, `--remote-wait`, `--remote-off`, `--dockerfile`, `--build-arg`, `--env-name`.

**Examples**:

```bash
# Deploy an existing image (pull SIF, generate wrappers and module)
absconda deploy ghcr.io/org/myenv:v1.0 \
  --commands python,pip,jupyter

# Full pipeline: build + push + deploy
absconda deploy \
  --file env.yaml \
  --repository ghcr.io/org/myenv \
  --commands python,pip

# Full pipeline with remote builder
absconda deploy \
  --file env.yaml \
  --remote-builder gcp-builder \
  --commands python,pip,R,Rscript

# Deploy without generating a module file
absconda deploy ghcr.io/org/myenv:v1.0 \
  --commands python,pip \
  --no-module

# With GPU and custom mounts
absconda deploy ghcr.io/org/gpu-env:v1.0 \
  --commands python \
  --gpu \
  --extra-mounts /scratch/$PROJECT,/g/data/$PROJECT
```

**Output**:

```
Using policy profile default from /Users/user/.config/absconda/policy.yaml.
Image pushed: ghcr.io/org/myenv:v1.0
Pulling image to /home/user/.local/absconda/sif-cache/myenv-v1.0.sif...
Singularity image pulled to /home/user/.local/absconda/sif-cache/myenv-v1.0.sif
✓ Generated 3 wrapper(s) in /home/user/.local/absconda/wrappers/myenv/v1.0
✓ Generated module file: /home/user/.local/absconda/modulefiles/myenv/v1.0

Deployed: ghcr.io/org/myenv:v1.0

Usage:
  module use /home/user/.local/absconda/modulefiles
  module load myenv/v1.0
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

## Config Commands

Manage Absconda configuration from the command line.

### config list

List all configuration settings from all config files.

```bash
absconda config list [--show-origin]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--show-origin` | Show which config file each value comes from | `false` |

**Example**:

```bash
absconda config list
# registry=ghcr.io
# organization=myorg

absconda config list --show-origin
# /home/user/.config/absconda/config.yaml
#   registry=ghcr.io
#   organization=myorg
```

---

### config get

Get a single configuration value using dot-notation.

```bash
absconda config get KEY
```

**Examples**:

```bash
absconda config get registry
# ghcr.io

absconda config get wrappers.default_runtime
# singularity
```

---

### config set

Set a configuration value (written to user config by default).

```bash
absconda config set KEY VALUE [--system]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--system` | Write to system config instead of user config | `false` |

**Examples**:

```bash
absconda config set registry ghcr.io
absconda config set organization myteam
absconda config set wrappers.default_runtime singularity
```

---

### config unset

Remove a configuration value.

```bash
absconda config unset KEY [--system]
```

---

### config edit

Open the configuration file in `$EDITOR` or `vi`.

```bash
absconda config edit [--system]
```

---

### config paths

Show all configuration file paths and whether they exist.

```bash
absconda config paths
```

**Output**:

```
Configuration file search order:

  ✓ /home/user/.config/absconda/config.yaml
  ✗ /etc/xdg/absconda/config.yaml

User config: /home/user/.config/absconda/config.yaml
System config: /etc/xdg/absconda/config.yaml
```

---

## Workflow Commands

Scan a Snakemake workflow, containerise each unique conda env, and rewrite
the workflow to use `container:` directives. See the
[Workflow Containerise guide](../guides/workflow-containerise.md) for the full
walkthrough.

### workflow scan

Discover `conda:` directives and write `absconda-workflow.yaml`.

```bash
absconda workflow scan [PATH] [--output PATH] [--dry-run] [--force]
```

| Option | Description | Default |
|--------|-------------|---------|
| `PATH` | Workflow root directory | `.` |
| `--output PATH` | Manifest output path | `<PATH>/absconda-workflow.yaml` |
| `--dry-run` | Print manifest to stdout, don't write | `false` |
| `--force` | Overwrite an existing manifest | `false` |
| `--type` | Workflow type (snakemake only in v1) | `snakemake` |

### workflow containerise

Build and push one image per unique env file in the manifest. Updates the
manifest in place as each image succeeds, so partial failures resume cleanly.

```bash
absconda workflow containerise [PATH] [--tag TAG] [--remote-builder NAME] ...
```

Accepts the same `--builder-base`, `--runtime-base`, `--multi-stage`,
`--remote-builder`, `--remote-wait`, `--remote-off`, `--build-arg`,
`--template` flags as `absconda publish`. Use `--force-rebuild` to rebuild
images that already have an `image_ref` recorded.

### workflow update

Rewrite the workflow files to add `container:` alongside each `conda:`
directive (which is commented out, not removed).

```bash
absconda workflow update [PATH] [--manifest PATH] [--dry-run] [--revert]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--manifest PATH` | Manifest to read image refs from | `<PATH>/absconda-workflow.yaml` |
| `--dry-run` | Print diff but don't modify files | `false` |
| `--revert` | Strip absconda-injected blocks, restore `conda:` | `false` |

### workflow apply

One-shot: scan → containerise → update.

```bash
absconda workflow apply [PATH] [--tag TAG] [--remote-builder NAME] ...
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
