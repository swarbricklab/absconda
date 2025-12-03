# Quickstart

Get up and running with Absconda in 5 minutes.

## Prerequisites

- Absconda installed (see [Installation](installation.md))
- Docker or Podman running on your system

## Step 1: Create an Environment File

Create a file called `environment.yaml`:

```yaml
name: myenv
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - requests
      - rich
```

This defines a simple Python environment with a few packages.

## Step 2: Generate a Dockerfile

```bash
absconda generate --file environment.yaml --output Dockerfile
```

This creates a `Dockerfile` using a multi-stage build:
- **Builder stage**: Uses micromamba to solve and pack the environment
- **Runtime stage**: Unpacks the environment into a slim Debian image

Inspect the generated `Dockerfile` to see how Absconda structures the build.

## Step 3: Build the Image

```bash
docker build -t myenv:latest .
```

Or let Absconda do it for you:

```bash
absconda build \
  --file environment.yaml \
  --repository myenv \
  --tag latest
```

## Step 4: Run Your Container

```bash
docker run --rm -it myenv:latest python -c "import requests; print(requests.__version__)"
```

You should see the requests version printed, confirming your environment is working!

## What Just Happened?

1. **Environment Definition**: You described your dependencies in a Conda environment YAML
2. **Dockerfile Generation**: Absconda created an optimized multi-stage Dockerfile
3. **Image Build**: Docker built a container image with your environment
4. **Execution**: Your Python code ran inside the container with all dependencies available

## Next Steps

### Build with pip requirements instead

If you prefer pip over Conda:

```bash
echo "requests" > requirements.txt
echo "rich" >> requirements.txt

absconda build \
  --requirements requirements.txt \
  --repository myenv-pip \
  --tag latest
```

### Push to a Registry

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/yourusername/myenv \
  --tag latest \
  --push
```

Make sure you're logged in to the registry first:

```bash
docker login ghcr.io
```

### Create a Singularity Image for HPC

```bash
absconda publish \
  --file environment.yaml \
  --repository ghcr.io/yourusername/myenv \
  --singularity-out myenv.sif
```

This pushes to a registry and converts to a `.sif` file for HPC systems.

### Use Remote Builders

Build on a powerful GCP instance instead of locally:

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/yourusername/myenv \
  --remote-builder gcp-builder \
  --push
```

See [Remote Builders Guide](../guides/remote-builders.md) for setup.

## Learn More

- [Core Concepts](concepts.md) - Understand multi-stage builds, policies, and templates
- [Basic Usage](../guides/basic-usage.md) - Detailed workflow guide
- [Building Images](../guides/building-images.md) - All the build options
- [Examples](../examples/) - More complex scenarios
