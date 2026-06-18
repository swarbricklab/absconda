# Building Images

Comprehensive guide to the `build` and `publish` commands.

## The build Command

Build a container image from an environment definition.

### Basic Build

```bash
absconda build \
  --file environment.yaml \
  --repository myimage \
  --tag latest
```

This:
1. Generates a Dockerfile
2. Runs `docker build`
3. Tags the result

### With Push

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --tag v1.0.0 \
  --push
```

Pushes to the registry after successful build.

## The publish Command

Build and push a container image to a registry. Push is always performed (unlike `build`, which requires `--push`).

```bash
absconda publish \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --tag latest
```

This is equivalent to `build --push`. To also create a Singularity image and generate wrappers, use `deploy` instead (see [HPC Deployment](hpc-deployment.md)).

### Using a Pre-existing Dockerfile

```bash
absconda publish \
  --dockerfile Dockerfile \
  --env-name myimage \
  --repository ghcr.io/org/myimage \
  --tag latest
```

When `--dockerfile` is used without `--file`, the environment name is auto-detected from `ENV CONDA_DEFAULT_ENV=<name>` in the Dockerfile (set automatically by `absconda generate`). Use `--env-name` to override.

## Input Options

### From Conda Environment

```bash
absconda build --file environment.yaml --repository myimage
```

#### Conda + pip dependencies

When an `environment.yaml` mixes conda dependencies with a `pip:` section,
absconda installs them in two phases:

1. conda solves and installs the conda dependencies (honouring their pins);
2. the `pip:` packages are installed **constrained to the versions conda just
   resolved**, so pip cannot silently upgrade a conda-managed package (e.g.
   `numpy`) past its conda pin.

If a pip package genuinely requires a version that conflicts with a conda pin,
**the build fails** with a pip resolution error rather than producing an
environment that violates the pins. Resolve it by relaxing the conda pin or
pinning the pip package to a compatible version. A `pip check` runs afterwards
to confirm the final environment has a consistent dependency tree.

> Note: this coordination applies to conda + pip. Mixing conda-installed R
> packages with `renv` is not yet guarded — keep R packages managed by a single
> tool for now.

#### Environment variables in the image

A conda-style `variables:` section in the environment file is baked into the
image as `ENV` lines:

```yaml
name: myenv
dependencies:
  - python=3.12
variables:
  CLOUDSDK_PYTHON_SITEPACKAGES: "1"
```

The image runs binaries directly (it never `conda activate`s), so this is how
runtime environment variables are made to stick. The `variables:` section is not
passed to the conda solver.

### From pip Requirements

```bash
absconda build --requirements requirements.txt --repository myimage
```

### From Tarball

```bash
absconda build --tarball myenv.tar.gz --repository myimage
```

### With Snapshot

Pin exact versions:

```bash
absconda build \
  --file environment.yaml \
  --snapshot snapshot.yaml \
  --repository myimage
```

## Template Options

### Custom Template

```bash
absconda build \
  --file environment.yaml \
  --template custom-template.j2 \
  --repository myimage
```

### Build Stage Override

```bash
absconda build \
  --file environment.yaml \
  --builder-base mambaorg/micromamba:2.0.0 \
  --repository myimage
```

### Runtime Stage Override

```bash
absconda build \
  --file environment.yaml \
  --runtime-base ubuntu:22.04 \
  --repository myimage
```

### Force Build Type

```bash
# Force multi-stage
absconda build --file environment.yaml --multi-stage --repository myimage

# Force single-stage
absconda build --file environment.yaml --single-stage --repository myimage
```

## Build Context

### Default Context

Uses current directory:

```bash
absconda build --file environment.yaml --repository myimage
```

### Custom Context

```bash
absconda build \
  --file environment.yaml \
  --context /path/to/project \
  --repository myimage
```

### Why Context Matters

The context contains files that can be COPY'd into the image. If your custom template or environment needs local files, ensure they're in the context directory.

## R + renv Integration

### Basic R Environment

```bash
absconda build \
  --file r-environment.yaml \
  --renv-lock renv.lock \
  --repository my-r-image
```

Requires `r-base` in your environment.yaml.

### Complete Example

```yaml
# r-environment.yaml
name: r-analysis
channels:
  - conda-forge
dependencies:
  - r-base=4.3
  - r-essentials
```

```bash
absconda build \
  --file r-environment.yaml \
  --renv-lock renv.lock \
  --repository ghcr.io/org/r-analysis \
  --push
```

See [R + renv Guide](renv-integration.md) for details.

## Remote Builds

### Basic Remote Build

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --push
```

### Custom Config

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-config custom-remote.yaml \
  --push
```

### Wait Timeout

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-wait 1800 \
  --push
```

### Auto-shutdown

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/org/myimage \
  --remote-builder gcp-builder \
  --remote-off \
  --push
```

Stops the VM after build completes.

See [Remote Builders Guide](remote-builders.md) for setup.

## Repository and Tagging

### Default Repository Behavior

If you configure organization defaults in `~/.config/absconda/config.yaml`:

```yaml
registry: ghcr.io
organization: myorg
```

Then:

```bash
absconda build --file environment.yaml
# Builds: ghcr.io/myorg/data-science:20251203
```

Environment name is slugified and current date is used as tag.

### Explicit Repository

```bash
absconda build \
  --file environment.yaml \
  --repository custom-name
```

### Full Registry Path

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/someorg/specific-name
```

### Custom Tags

```bash
absconda build \
  --file environment.yaml \
  --repository myimage \
  --tag v1.0.0
```

## Policy Profiles

### Using Profiles

```bash
absconda --profile production build \
  --file environment.yaml \
  --repository myimage
```

### Profile Overrides

Profiles can set defaults for:
- `multi_stage` (bool)
- `builder_base` (image)
- `runtime_base` (image)
- `allowed_channels` (list)
- `denied_packages` (list)

Command-line flags override profile settings.

## Output and Logging

### Verbose Output

```bash
absconda build --file environment.yaml --repository myimage
# Shows Docker build progress
```

### Quiet Mode

```bash
docker build output goes to stdout/stderr as normal
```

### Build Manifest

Remote builds create a manifest with metadata:

```json
{
  "absconda_version": "0.2.5",
  "env_name": "myenv",
  "image": "ghcr.io/org/myimage:latest",
  "generated_at": "2025-12-03T10:30:00Z",
  "policy_profile": "default",
  "channels": ["conda-forge"],
  "remote_builder": "gcp-builder"
}
```

## Troubleshooting Builds

### Check Generated Dockerfile

Generate without building:

```bash
absconda generate --file environment.yaml --output Dockerfile
cat Dockerfile
```

### Build with Docker Directly

```bash
absconda generate --file environment.yaml --output Dockerfile
docker build -t myimage:debug .
```

### Check Environment Validation

```bash
absconda validate --file environment.yaml
```

### Inspect Policy

```bash
absconda --profile production validate --file environment.yaml
# Shows which policy is active and any constraint violations
```

## Next Steps

- [Remote Builders](remote-builders.md) - Build on GCP
- [HPC Deployment](hpc-deployment.md) - Create Singularity artifacts
- [Advanced Templating](advanced-templating.md) - Custom Dockerfiles
- [CLI Reference](../reference/cli.md) - All build options
