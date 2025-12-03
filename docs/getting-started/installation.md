# Installation

Absconda can be installed via pip or run from a container.

## Requirements

- **Python 3.10 or later**
- **Docker or Podman** (for building images)
- **Singularity/Apptainer** (optional, for HPC deployments)

## Install via pip

### From PyPI (when released)

```bash
pip install absconda
```

### From source

```bash
git clone https://github.com/swarbricklab/absconda.git
cd absconda
pip install -e .
```

The `-e` flag installs in editable/development mode, useful if you want to modify the code.

## Verify Installation

```bash
absconda --version
```

You should see output like:

```
absconda, version 0.1.0
```

## Run from Container

If you don't want to install Python dependencies locally, you can run Absconda from its own container:

### Using Docker

```bash
docker run --rm -v "$PWD:/work" -w /work \
  ghcr.io/swarbricklab/absconda:0.1.0 \
  absconda --help
```

### Using Singularity (HPC systems)

```bash
# Pull the image (one-time)
singularity pull docker://ghcr.io/swarbricklab/absconda:0.1.0

# Run commands
singularity exec absconda_0.1.0.sif absconda --help
```

See [HPC Deployment](../guides/hpc-deployment.md) for information about generating wrapper scripts and module files.

## Optional: Remote Builders

To use GCP remote builders for building images on powerful cloud instances, you'll need:

- **Google Cloud SDK** (`gcloud` command)
- **GCP project** with Compute Engine API enabled
- **Terraform** (for provisioning infrastructure)

See [Remote Builders Guide](../guides/remote-builders.md) for setup instructions.

## Optional: R + renv Support

To use Absconda with R environments:

- Include `r-base` or `r` in your Conda environment
- Have an `renv.lock` file from your R project

No additional installation needed—Absconda handles R package restoration automatically.

## Next Steps

- [Quickstart Tutorial](quickstart.md) - Build your first container
- [Core Concepts](concepts.md) - Understand how Absconda works
- [Basic Usage Guide](../guides/basic-usage.md) - Detailed workflow
