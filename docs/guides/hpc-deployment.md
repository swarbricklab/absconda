# HPC Deployment

Deploy containerized environments to HPC systems using Singularity wrappers and environment modules.

## Overview

HPC systems like NCI Gadi use **Singularity/Apptainer** for containers and **Environment Modules** for software management. Absconda bridges the gap by generating:

1. **Wrapper scripts** - Make containerized commands feel like native executables
2. **Module files** - Integrate with the HPC module system

## Workflow

```
Build Image → Create Singularity Image → Generate Wrappers → Create Module → Deploy
```

## Step 1: Build Your Image

First, build and push your container image:

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/myorg/myenv \
  --tag 1.0.0 \
  --push
```

Or build with Singularity output directly:

```bash
absconda publish \
  --file environment.yaml \
  --repository ghcr.io/myorg/myenv \
  --tag 1.0.0 \
  --singularity-out myenv-1.0.0.sif
```

## Step 2: Generate Wrapper Scripts

Wrapper scripts handle running commands inside the container transparently.

### Basic Wrapper Generation

```bash
absconda wrap \
  --image ghcr.io/myorg/myenv:1.0.0 \
  --commands python,pip,jupyter \
  --runtime singularity \
  --output-dir ./wrappers
```

This creates three executable scripts:
- `wrappers/python` - Runs python in container
- `wrappers/pip` - Runs pip in container  
- `wrappers/jupyter` - Runs jupyter in container

### With HPC Mounts

NCI Gadi example:

```bash
absconda wrap \
  --image ghcr.io/myorg/myenv:1.0.0 \
  --commands python,pip,jupyter,R,Rscript \
  --runtime singularity \
  --output-dir ./wrappers \
  --extra-mounts '/g/data/$PROJECT,/scratch/$PROJECT'
```

Environment variables like `$PROJECT` are expanded at runtime.

### With GPU Support

```bash
absconda wrap \
  --image ghcr.io/myorg/gpu-pytorch:1.0.0 \
  --commands python,pytorch \
  --runtime singularity \
  --output-dir ./wrappers \
  --gpu
```

Adds `--nv` flag for NVIDIA GPU support.

### Custom SIF Cache

```bash
absconda wrap \
  --image ghcr.io/myorg/myenv:1.0.0 \
  --commands python,pip \
  --runtime singularity \
  --output-dir ./wrappers \
  --image-cache /g/data/$PROJECT/singularity-cache
```

## What Wrapper Scripts Do

Generated wrapper scripts:

1. **Pull SIF on first use**:
   ```bash
   if [[ ! -f "$SIF_FILE" ]]; then
       singularity pull "$SIF_FILE" docker://ghcr.io/myorg/myenv:1.0.0
   fi
   ```

2. **Mount required paths**:
   ```bash
   MOUNTS+=("-B" "$HOME")
   MOUNTS+=("-B" "$PWD")
   MOUNTS+=("-B" "/g/data/$PROJECT")
   ```

3. **Execute command**:
   ```bash
   exec singularity exec ${MOUNTS[@]} "$SIF_FILE" python "$@"
   ```

Users run commands normally:
```bash
./wrappers/python script.py
```

## Step 3: Generate Module File

Module files integrate with HPC environment modules.

### Basic Module Generation

```bash
absconda module \
  --name myenv/1.0.0 \
  --wrapper-dir ./wrappers \
  --output-dir ./modulefiles \
  --description "My research environment" \
  --image ghcr.io/myorg/myenv:1.0.0 \
  --runtime singularity \
  --commands python,pip,jupyter
```

Creates `modulefiles/myenv/1.0.0`.

### Module Structure

```tcl
#%Module1.0
proc ModulesHelp { } {
    puts stderr "My research environment"
    puts stderr ""
    puts stderr "Containerized environment: ghcr.io/myorg/myenv:1.0.0"
    puts stderr "Runtime: singularity"
    puts stderr "Wrapped commands: python, pip, jupyter"
}

module-whatis "My research environment"

conflict myenv

prepend-path PATH /path/to/wrappers

setenv MYENV_VERSION 1.0.0
setenv MYENV_IMAGE ghcr.io/myorg/myenv:1.0.0
setenv MYENV_RUNTIME singularity
```

## Step 4: Deploy to HPC

### Copy Files to HPC

```bash
# From local machine
scp -r wrappers modulefiles username@gadi.nci.org.au:/g/data/$PROJECT/
```

Or build directly on HPC login node:

```bash
# On Gadi
absconda wrap --image ... --output-dir $PROJECT_HOME/wrappers
absconda module --wrapper-dir $PROJECT_HOME/wrappers --output-dir $PROJECT_HOME/modulefiles
```

### Set Up Module Path

Add to `~/.bashrc` or project setup script:

```bash
module use /g/data/$PROJECT/modulefiles
```

### Use the Module

```bash
module avail myenv
# myenv/1.0.0

module load myenv/1.0.0
# Loading myenv/1.0.0

python --version
# Python 3.11.5  (running in container)

module help myenv/1.0.0
# My research environment
# Containerized environment: ghcr.io/myorg/myenv:1.0.0
# Runtime: singularity
# Wrapped commands: python, pip, jupyter
```

## Complete NCI Gadi Example

### 1. Build on Local Machine with Remote Builder

```bash
# Build using GCP remote builder
absconda build \
  --file environment.yaml \
  --repository ghcr.io/mylab/analysis \
  --tag 2025.12.03 \
  --remote-builder gcp-builder \
  --push
```

### 2. Generate Wrappers Locally

```bash
absconda wrap \
  --image ghcr.io/mylab/analysis:2025.12.03 \
  --commands python,pip,jupyter,R,Rscript \
  --runtime singularity \
  --output-dir ./wrappers \
  --extra-mounts '/g/data/xy99,/scratch/xy99'
```

### 3. Generate Module Locally

```bash
absconda module \
  --name analysis/2025.12.03 \
  --wrapper-dir ./wrappers \
  --output-dir ./modulefiles \
  --description "Analysis environment for XY99 project" \
  --image ghcr.io/mylab/analysis:2025.12.03 \
  --runtime singularity \
  --commands python,pip,jupyter,R,Rscript
```

### 4. Deploy to Gadi

```bash
# Copy to shared project space
scp -r wrappers modulefiles username@gadi.nci.org.au:/g/data/xy99/modules/

# SSH to Gadi
ssh username@gadi.nci.org.au

# Add module path
module use /g/data/xy99/modules/modulefiles

# Load and use
module load analysis/2025.12.03
python analysis.py
```

### 5. Team Members Use It

```bash
# In job script or interactive session
module use /g/data/xy99/modules/modulefiles
module load analysis/2025.12.03

python -c "import pandas; print(pandas.__version__)"
jupyter lab --no-browser --port=8888
```

## Configuration Defaults

Set defaults in `~/.config/absconda/config.yaml`:

```yaml
wrappers:
  default_runtime: singularity
  default_output_dir: ~/modules/wrappers
  image_cache: /g/data/$PROJECT/.singularity-cache
  default_mounts:
    - $HOME
    - $PWD
    - /g/data/$PROJECT
    - /scratch/$PROJECT
  env_passthrough:
    - USER
    - HOME
    - PROJECT
    - PBS_JOBID

modules:
  default_output_dir: ~/modules/modulefiles
  format: tcl
```

Then simplify commands:

```bash
absconda wrap \
  --image ghcr.io/mylab/analysis:2025.12.03 \
  --commands python,pip,jupyter
  # Uses config defaults for output-dir, mounts, etc.
```

## Docker Runtime Alternative

For systems with Docker instead of Singularity:

```bash
absconda wrap \
  --image ghcr.io/myorg/myenv:1.0.0 \
  --commands python,pip \
  --runtime docker \
  --output-dir ./wrappers
```

Creates Docker-based wrappers using `docker run`.

## Deploying Absconda Itself

Use Absconda to deploy itself to HPC:

```bash
# Generate wrappers for absconda command
absconda wrap \
  --image ghcr.io/swarbricklab/absconda:0.1.0 \
  --commands absconda \
  --runtime singularity \
  --output-dir ./wrappers \
  --extra-mounts '/g/data/$PROJECT,/scratch/$PROJECT'

# Generate module
absconda module \
  --name absconda/0.1.0 \
  --wrapper-dir ./wrappers \
  --output-dir ./modulefiles \
  --description "Absconda: Conda environment containerization" \
  --image ghcr.io/swarbricklab/absconda:0.1.0 \
  --runtime singularity \
  --commands absconda
```

Then team members can:

```bash
module load absconda/0.1.0
absconda build --file myenv.yaml --repository ghcr.io/mylab/myenv
```

## Tips for HPC Deployment

### 1. Pre-pull SIF Files

Pull SIF files once to shared cache:

```bash
# On login node
SINGULARITY_CACHEDIR=/g/data/$PROJECT/.singularity-cache \
  singularity pull docker://ghcr.io/myorg/myenv:1.0.0
```

Then all users share the cached SIF.

### 2. Version Your Modules

Use date-based or semantic versions:

```bash
myenv/2025.12.03
myenv/1.0.0
myenv/1.1.0-beta
```

Users can pin specific versions in job scripts.

### 3. Test Interactively First

```bash
# Interactive session
qsub -I -P xy99 -q normal -l ncpus=4,mem=16GB,walltime=1:00:00

module load myenv/1.0.0
python test_import.py
```

### 4. Document in README

Create a README in your module directory:

```markdown
# XY99 Project Modules

## Available Environments

- `analysis/2025.12.03` - Python 3.11, pandas, scikit-learn
- `deeplearning/2025.11.15` - PyTorch 2.1, CUDA 12

## Usage

\`\`\`bash
module use /g/data/xy99/modules/modulefiles
module load analysis/2025.12.03
\`\`\`
```

## Next Steps

- [Requirements Mode](requirements-mode.md) - Using pip requirements
- [R + renv Integration](renv-integration.md) - R environments
- [Remote Builders](remote-builders.md) - Build on GCP
- [Examples: HPC Singularity](../examples/hpc-singularity.md) - Complete example
