# R and renv Integration

Build reproducible R container images with `renv` for package management.

## Overview

Absconda supports R environments using the `renv` lockfile system for precise package version control. This enables reproducible R/Bioconductor workflows in containers.

## Prerequisites

- R environment file with `renv.lock`
- Understanding of renv basics (see [renv documentation](https://rstudio.github.io/renv/))

## Quick Example

### 1. Create R Environment File

`r-analysis.yaml`:

```yaml
name: r-analysis
type: conda

channels:
  - conda-forge
  - bioconda

conda:
  - r-base=4.3.1
  - r-essentials
  - libgit2

renv:
  lockfile: renv.lock
  restore_options:
    - "--no-cache"
```

### 2. Create renv.lock

In your R project:

```r
# Initialize renv
renv::init()

# Install packages
install.packages("ggplot2")
install.packages("dplyr")
BiocManager::install("DESeq2")

# Create lockfile
renv::snapshot()
```

This generates `renv.lock` with exact versions:

```json
{
  "R": {
    "Version": "4.3.1",
    "Repositories": [
      {
        "Name": "CRAN",
        "URL": "https://cloud.r-project.org"
      }
    ]
  },
  "Packages": {
    "ggplot2": {
      "Package": "ggplot2",
      "Version": "3.4.2",
      "Source": "Repository",
      "Repository": "CRAN"
    },
    "dplyr": {
      "Package": "dplyr",
      "Version": "1.1.2",
      "Source": "Repository",
      "Repository": "CRAN"
    }
  }
}
```

### 3. Build Container

```bash
absconda build \
  --file r-analysis.yaml \
  --repository ghcr.io/org/r-analysis \
  --tag v1.0 \
  --push
```

## How It Works

### Build Process

1. **Conda layer**: Installs R base and system dependencies
2. **renv layer**: Restores R packages from lockfile
3. **Validation**: Runs R to verify packages load

Generated Dockerfile:

```dockerfile
# Stage 1: Builder
FROM mambaorg/micromamba:latest AS builder

# Install Conda packages
COPY environment.yaml /tmp/env.yaml
RUN micromamba install -y -n base -f /tmp/env.yaml && \
    micromamba clean -afy

# Restore renv packages
COPY renv.lock /tmp/renv.lock
RUN Rscript -e 'renv::restore(lockfile="/tmp/renv.lock", prompt=FALSE)'

# Stage 2: Runtime
FROM mambaorg/micromamba:latest

COPY --from=builder /opt/conda /opt/conda

# Validation
RUN Rscript -e 'library(ggplot2); library(dplyr)'
```

## Complete Example: Bioconductor Analysis

### Environment File

`bioc-analysis.yaml`:

```yaml
name: bioconductor
type: conda

channels:
  - conda-forge
  - bioconda

conda:
  - r-base=4.3.1
  - bioconductor-biocinstaller
  - libgit2
  - libxml2
  - libcurl
  - openssl

renv:
  lockfile: renv.lock
  restore_options:
    - "--no-cache"

labels:
  org.opencontainers.image.title: "Bioconductor Analysis"
  org.opencontainers.image.description: "RNA-seq analysis with DESeq2"
```

### renv.lock

```json
{
  "R": {
    "Version": "4.3.1",
    "Repositories": [
      {
        "Name": "BioCsoft",
        "URL": "https://bioconductor.org/packages/3.18/bioc"
      },
      {
        "Name": "CRAN",
        "URL": "https://cloud.r-project.org"
      }
    ]
  },
  "Packages": {
    "DESeq2": {
      "Package": "DESeq2",
      "Version": "1.42.0",
      "Source": "Bioconductor"
    },
    "edgeR": {
      "Package": "edgeR",
      "Version": "4.0.2",
      "Source": "Bioconductor"
    },
    "ggplot2": {
      "Package": "ggplot2",
      "Version": "3.4.2",
      "Source": "Repository",
      "Repository": "CRAN"
    }
  }
}
```

### Build and Test

```bash
# Build
absconda build \
  --file bioc-analysis.yaml \
  --repository ghcr.io/org/bioc-analysis \
  --tag 2024.01 \
  --push

# Test
docker run --rm ghcr.io/org/bioc-analysis:2024.01 \
  Rscript -e 'library(DESeq2); packageVersion("DESeq2")'
```

## Advanced Configuration

### Custom Repositories

Add private CRAN/Bioconductor mirrors:

```yaml
renv:
  lockfile: renv.lock
  repositories:
    CRAN: "https://internal-cran.company.com"
    BioCsoft: "https://internal-bioc.company.com/bioc"
```

### Cache Package Downloads

Speed up builds with a download cache:

```yaml
renv:
  lockfile: renv.lock
  cache_dir: /opt/renv/cache
  restore_options:
    - "--no-cache"
```

### GitHub Packages

Include packages from GitHub:

In R:

```r
# Install from GitHub
remotes::install_github("user/package@v1.2.3")

# Snapshot
renv::snapshot()
```

This adds to `renv.lock`:

```json
{
  "Packages": {
    "mypackage": {
      "Package": "mypackage",
      "Version": "1.2.3",
      "Source": "GitHub",
      "RemoteType": "github",
      "RemoteHost": "api.github.com",
      "RemoteUsername": "user",
      "RemoteRepo": "package",
      "RemoteRef": "v1.2.3"
    }
  }
}
```

Absconda handles GitHub remotes automatically.

## System Dependencies

R packages often need system libraries. Add them via Conda:

```yaml
conda:
  - r-base=4.3.1
  
  # For XML packages
  - libxml2
  - libxslt
  
  # For HTTPS/SSL
  - openssl
  - libcurl
  - ca-certificates
  
  # For Git operations
  - libgit2
  - git
  
  # For spatial packages
  - gdal
  - geos
  - proj
  
  # For graphics
  - cairo
  - libpng
  - libjpeg-turbo
```

## Troubleshooting

### Package Won't Install

**Error**: `installation of package 'X' had non-zero exit status`

**Solution**: Add system dependencies to Conda packages.

```yaml
conda:
  - r-base=4.3.1
  - libxml2      # Often needed
  - libgit2      # For devtools/remotes
  - openssl      # For HTTPS
```

### renv::restore() Fails

**Error**: `renv restore failed`

**Solution**: Check repository accessibility:

```yaml
renv:
  lockfile: renv.lock
  repositories:
    CRAN: "https://cloud.r-project.org"
    BioCsoft: "https://bioconductor.org/packages/3.18/bioc"
```

### Bioconductor Version Mismatch

**Error**: `Bioconductor version mismatch`

**Solution**: Lock Bioconductor version in environment file:

```yaml
conda:
  - r-base=4.3.1
  - bioconductor-biocinstaller=3.18
```

## Best Practices

### 1. Pin R Version

Always specify exact R version:

```yaml
conda:
  - r-base=4.3.1  # Not "r-base" or "r-base>=4.3"
```

### 2. Use renv.lock

Never specify R packages in both `conda:` and `renv:`. Use renv.lock for all R packages.

```yaml
# ❌ Don't do this
conda:
  - r-base=4.3.1
  - r-ggplot2
  - r-dplyr

# ✅ Do this
conda:
  - r-base=4.3.1
  - libxml2

renv:
  lockfile: renv.lock  # Contains ggplot2, dplyr
```

### 3. Separate System and R Deps

- **Conda**: R base + system libraries
- **renv**: R packages

```yaml
conda:
  - r-base=4.3.1
  - libxml2        # System library
  - libcurl        # System library

renv:
  lockfile: renv.lock  # R packages: xml2, httr
```

### 4. Test Locally First

Before building container:

```r
# In local R session
renv::restore()

# Verify
library(ggplot2)
library(DESeq2)
```

### 5. Version Everything

```yaml
name: r-project
type: conda

channels:
  - conda-forge
  - bioconda

conda:
  - r-base=4.3.1           # Exact version
  - bioconductor-biocinstaller=3.18  # Lock Bioc

renv:
  lockfile: renv.lock      # All R packages pinned

labels:
  org.opencontainers.image.version: "2024.01"
```

## HPC Deployment

Build, convert to Singularity, deploy:

```bash
# Build container
absconda build \
  --file r-analysis.yaml \
  --repository ghcr.io/org/r-analysis \
  --tag v1.0 \
  --push

# Generate wrapper
absconda wrap \
  --image docker://ghcr.io/org/r-analysis:v1.0 \
  --command Rscript \
  --output wrappers/Rscript

# Generate module
absconda module \
  --image docker://ghcr.io/org/r-analysis:v1.0 \
  --version 1.0 \
  --output modulefiles/r-analysis/1.0

# Deploy to HPC
rsync -av wrappers/ gadi:/path/to/wrappers/
rsync -av modulefiles/ gadi:/path/to/modulefiles/

# Use on HPC
module load r-analysis/1.0
Rscript my_analysis.R
```

## Real-World Example

See [examples/renv-env.yaml](../../examples/renv-env.yaml) for a complete working example with:
- Base R 4.3.1
- Tidyverse packages
- Bioconductor packages (DESeq2, edgeR)
- Custom GitHub packages
- System dependencies

## Next Steps

- [Building Images](building-images.md) - Build options for R containers
- [HPC Deployment](hpc-deployment.md) - Deploy R containers to HPC
- [Examples](../examples/r-bioconductor.md) - Complete R/Bioconductor workflow
