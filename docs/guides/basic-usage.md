# Basic Usage

Learn the fundamental workflow of using Absconda to containerize your environments.

## The Absconda Workflow

```
Environment Definition → Generate Dockerfile → Build Image → Run Container
```

Let's walk through each step.

## Step 1: Define Your Environment

Create a Conda environment file that describes your dependencies.

### Example: Data Science Environment

Create `environment.yaml`:

```yaml
name: data-science
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - numpy=1.24
  - pandas=2.0
  - matplotlib
  - scikit-learn
  - pip
  - pip:
      - seaborn>=0.12
      - plotly
```

### Environment File Structure

```yaml
name: <environment-name>          # Required: Name of the environment
channels:                         # Required: Conda channels to search
  - conda-forge
  - bioconda
dependencies:                     # Required: Package list
  - python=3.11                   # Pin to specific version
  - numpy>=1.24                   # Minimum version
  - pandas                        # Latest version
  - pip                           # Required if using pip packages
  - pip:
      - package-name==1.0.0       # pip dependencies
```

### Validating Your Environment

Before generating a Dockerfile, validate your environment:

```bash
absconda validate --file environment.yaml
```

This checks:
- ✅ Required fields present
- ✅ Channel names valid
- ✅ Policy constraints satisfied (if using policies)
- ⚠️  Warns about potential issues

## Step 2: Generate a Dockerfile

### Basic Generation

```bash
absconda generate --file environment.yaml --output Dockerfile
```

This creates a multi-stage Dockerfile using default settings.

### Controlling the Build Type

**Multi-stage (default, smaller images):**
```bash
absconda generate --file environment.yaml --output Dockerfile --multi-stage
```

**Single-stage (includes build tools):**
```bash
absconda generate --file environment.yaml --output Dockerfile --single-stage
```

### Customizing Base Images

**Change builder base:**
```bash
absconda generate \
  --file environment.yaml \
  --builder-base mambaorg/micromamba:2.0.0 \
  --output Dockerfile
```

**Change runtime base:**
```bash
absconda generate \
  --file environment.yaml \
  --runtime-base ubuntu:22.04 \
  --output Dockerfile
```

### Using Policies

Apply organizational policies:

```bash
absconda --profile production generate \
  --file environment.yaml \
  --output Dockerfile
```

See [Policies Reference](../reference/policies.md) for details.

## Step 3: Build the Image

Once you have a Dockerfile, you have two options:

### Option A: Use Docker Directly

```bash
docker build -t myimage:latest .
```

Good for:
- Quick local testing
- Integration with existing Docker workflows
- Custom build arguments

### Option B: Let Absconda Build

```bash
absconda build \
  --file environment.yaml \
  --repository myimage \
  --tag latest
```

Benefits:
- No need to generate Dockerfile separately
- Consistent tagging (defaults to date-based tags)
- Easy registry push with `--push`

### Tagging Strategy

**Default: Date-based tags**
```bash
absconda build --file environment.yaml --repository myimage
# Creates: myimage:20251203
```

**Custom tags:**
```bash
absconda build \
  --file environment.yaml \
  --repository myimage \
  --tag v1.0.0
```

**Multiple tags:**
```bash
# Build once, tag multiple times
absconda build --file environment.yaml --repository myimage --tag latest
docker tag myimage:latest myimage:v1.0.0
docker tag myimage:latest myimage:stable
```

## Step 4: Push to a Registry

### Using --push Flag

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/myorg/myimage \
  --tag latest \
  --push
```

### Prerequisites

Log in to your registry first:

```bash
# GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Docker Hub
docker login -u USERNAME

# Google Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

### Organization Defaults

Set default registry and organization in `~/.config/absconda/config.yaml`:

```yaml
registry: ghcr.io
organization: myorg
```

Then omit `--repository`:

```bash
absconda build \
  --file environment.yaml \
  --tag latest \
  --push
# Pushes to: ghcr.io/myorg/data-science:latest
```

## Step 5: Run Your Container

### Interactive Session

```bash
docker run --rm -it myimage:latest /bin/bash
```

### Run a Command

```bash
docker run --rm myimage:latest python -c "import pandas; print(pandas.__version__)"
```

### Mount Data

```bash
docker run --rm \
  -v "$PWD/data:/data" \
  -w /data \
  myimage:latest \
  python script.py
```

### As Current User

```bash
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$PWD:/work" \
  -w /work \
  myimage:latest \
  python script.py
```

## Alternative Input Modes

### Using pip Requirements

Skip Conda entirely with `--requirements`:

```bash
echo "pandas" > requirements.txt
echo "numpy" >> requirements.txt

absconda build \
  --requirements requirements.txt \
  --repository myimage \
  --tag latest
```

Uses Python base images instead of Conda.

### Using Pre-packed Tarballs

Already have a solved environment? Pack it:

```bash
conda activate myenv
conda pack -o myenv.tar.gz
```

Then build:

```bash
absconda build \
  --tarball myenv.tar.gz \
  --repository myimage \
  --tag latest
```

This skips environment solving in the container build.

## Environment Snapshots

Pin exact versions for reproducibility:

```bash
# Generate snapshot
conda env export > snapshot.yaml

# Use in build
absconda build \
  --file environment.yaml \
  --snapshot snapshot.yaml \
  --repository myimage
```

The snapshot ensures you get exactly the versions that worked for you.

## Build Context

By default, Absconda uses the current directory as the Docker build context. Change with `--context`:

```bash
absconda build \
  --file environment.yaml \
  --repository myimage \
  --context /path/to/project
```

Useful when your Dockerfile needs to COPY local files.

## Complete Example

Here's a complete workflow:

```bash
# 1. Create environment file
cat > environment.yaml <<EOF
name: analysis
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pandas
  - matplotlib
  - pip:
      - seaborn
EOF

# 2. Validate
absconda validate --file environment.yaml

# 3. Build and push
absconda build \
  --file environment.yaml \
  --repository ghcr.io/myorg/analysis \
  --tag v1.0.0 \
  --push

# 4. Run analysis
docker run --rm \
  -v "$PWD:/work" \
  -w /work \
  ghcr.io/myorg/analysis:v1.0.0 \
  python analyze.py
```

## Next Steps

- [Building Images Guide](building-images.md) - Detailed build options
- [Remote Builders](remote-builders.md) - Build on cloud instances
- [HPC Deployment](hpc-deployment.md) - Deploy to HPC systems
- [CLI Reference](../reference/cli.md) - All commands and options
