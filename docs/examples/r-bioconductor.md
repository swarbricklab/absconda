# Example: R and Bioconductor Environment

Complete walkthrough for building an R/Bioconductor environment for RNA-seq analysis with renv integration.

## Overview

This example demonstrates:
- R base installation with Conda
- Bioconductor package management via renv
- RNA-seq analysis workflow (DESeq2, edgeR)
- HPC deployment for computational biology

**Use case**: Reproducible bioinformatics analysis with R and Bioconductor.

## Prerequisites

- Docker installed
- Absconda installed
- R knowledge (basic)
- Optional: Singularity for HPC

## Step 1: Setup R Project with renv

### Create R Project

```bash
mkdir rnaseq-analysis
cd rnaseq-analysis
```

### Initialize renv in R

```r
# Start R
R

# Install renv if needed
install.packages("renv")

# Initialize renv project
renv::init()

# Install Bioconductor packages
if (!require("BiocManager", quietly = TRUE))
    install.packages("BiocManager")

BiocManager::install(c(
    "DESeq2",
    "edgeR",
    "limma"
))

# Install CRAN packages
install.packages(c(
    "ggplot2",
    "dplyr",
    "tidyr",
    "pheatmap"
))

# Create lockfile
renv::snapshot()
```

This generates `renv.lock` with exact package versions.

## Step 2: Create Environment File

Create `r-bioconductor-env.yaml`:

```yaml
name: r-bioconductor
channels:
  - conda-forge
  - bioconda
dependencies:
  # R base and system dependencies
  - r-base=4.3.1
  - bioconductor-biocinstaller=3.18
  
  # System libraries (required for many R packages)
  - libxml2
  - libgit2
  - openssl
  - libcurl
  - ca-certificates
  
  # Build tools
  - make
  - gcc
  - gxx

renv:
  lockfile: renv.lock
  restore_options:
    - "--no-cache"

labels:
  org.opencontainers.image.title: "R Bioconductor Analysis"
  org.opencontainers.image.description: "RNA-seq analysis with DESeq2 and edgeR"
  org.opencontainers.image.authors: "bioinformatics@example.com"
  org.opencontainers.image.version: "4.3.1-bioc3.18"

env:
  R_LIBS_USER: "/opt/conda/envs/r-bioconductor/lib/R/library"
```

**Key components**:
- **r-base=4.3.1**: Specific R version
- **bioconductor-biocinstaller=3.18**: Locks Bioconductor version
- **System libraries**: libxml2, libgit2, openssl (required by many R packages)
- **renv lockfile**: Manages R package versions

## Step 3: Check renv.lock

Your `renv.lock` should look like:

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
  "Bioconductor": {
    "Version": "3.18"
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
      "Version": "3.4.4",
      "Source": "Repository",
      "Repository": "CRAN"
    },
    "dplyr": {
      "Package": "dplyr",
      "Version": "1.1.4",
      "Source": "Repository",
      "Repository": "CRAN"
    }
  }
}
```

## Step 4: Build Container

```bash
absconda build \
  --file r-bioconductor-env.yaml \
  --repository ghcr.io/yourusername/r-bioconductor \
  --tag 4.3.1-bioc3.18 \
  --push
```

**Build time**: 10-20 minutes (Bioconductor packages are large)  
**Image size**: ~3-4 GB

## Step 5: Test R Environment

### Basic R Test

```bash
docker run --rm ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  R --version
```

**Output**:

```
R version 4.3.1 (2023-06-16) -- "Beagle Scouts"
```

### Test Bioconductor Packages

```bash
docker run --rm ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  Rscript -e 'library(DESeq2); packageVersion("DESeq2")'
```

**Output**: `[1] '1.42.0'`

```bash
docker run --rm ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  Rscript -e 'library(edgeR); packageVersion("edgeR")'
```

**Output**: `[1] '4.0.2'`

## Step 6: Example RNA-seq Analysis

### Create Analysis Script

**deseq2_analysis.R**:

```r
#!/usr/bin/env Rscript
"""
DESeq2 RNA-seq differential expression analysis.
"""

suppressPackageStartupMessages({
  library(DESeq2)
  library(ggplot2)
  library(dplyr)
  library(pheatmap)
})

# Parse command-line arguments
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Usage: Rscript deseq2_analysis.R <counts.csv> <metadata.csv>")
}

counts_file <- args[1]
metadata_file <- args[2]
output_prefix <- ifelse(length(args) >= 3, args[3], "results")

# Load data
cat("Loading count data from", counts_file, "\n")
counts <- read.csv(counts_file, row.names = 1)

cat("Loading metadata from", metadata_file, "\n")
metadata <- read.csv(metadata_file, row.names = 1)

# Ensure sample order matches
counts <- counts[, rownames(metadata)]

# Create DESeq2 object
cat("Creating DESeq2 object...\n")
dds <- DESeqDataSetFromMatrix(
  countData = counts,
  colData = metadata,
  design = ~ condition
)

# Pre-filtering (optional but recommended)
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep, ]

cat("Running DESeq2 analysis...\n")
dds <- DESeq(dds)

# Get results
res <- results(dds)
res_ordered <- res[order(res$padj), ]

# Save results
output_file <- paste0(output_prefix, "_deseq2_results.csv")
cat("Saving results to", output_file, "\n")
write.csv(as.data.frame(res_ordered), file = output_file)

# Summary
cat("\nAnalysis Summary:\n")
summary(res)

# Volcano plot
pdf(paste0(output_prefix, "_volcano.pdf"), width = 8, height = 6)
plotMA(res, main = "MA Plot", ylim = c(-5, 5))
dev.off()

# PCA plot
vsd <- vst(dds, blind = FALSE)
pdf(paste0(output_prefix, "_pca.pdf"), width = 8, height = 6)
plotPCA(vsd, intgroup = "condition")
dev.off()

# Heatmap of top genes
topGenes <- head(order(res$padj), 50)
mat <- assay(vsd)[topGenes, ]
mat <- mat - rowMeans(mat)
anno <- as.data.frame(colData(vsd)[, "condition", drop = FALSE])

pdf(paste0(output_prefix, "_heatmap.pdf"), width = 10, height = 12)
pheatmap(mat, annotation_col = anno)
dev.off()

cat("\nAnalysis complete! Generated files:\n")
cat(" -", output_file, "\n")
cat(" -", paste0(output_prefix, "_volcano.pdf"), "\n")
cat(" -", paste0(output_prefix, "_pca.pdf"), "\n")
cat(" -", paste0(output_prefix, "_heatmap.pdf"), "\n")
```

### Example Data

**counts.csv**:

```csv
,sample1,sample2,sample3,sample4,sample5,sample6
gene1,100,120,95,450,500,480
gene2,50,60,55,200,220,210
gene3,1000,1100,950,1050,1150,1000
gene4,20,25,18,300,320,290
```

**metadata.csv**:

```csv
,condition
sample1,control
sample2,control
sample3,control
sample4,treated
sample5,treated
sample6,treated
```

### Run Analysis

```bash
docker run --rm \
  -v $PWD:/work \
  -w /work \
  ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  Rscript deseq2_analysis.R counts.csv metadata.csv results
```

**Output**:

```
Loading count data from counts.csv
Loading metadata from metadata.csv
Creating DESeq2 object...
Running DESeq2 analysis...
estimating size factors
estimating dispersions
gene-wise dispersion estimates
mean-dispersion relationship
final dispersion estimates
fitting model and testing
Saving results to results_deseq2_results.csv

Analysis Summary:
out of 4 with nonzero total read count
adjusted p-value < 0.1
LFC > 0 (up)       : 2, 50%
LFC < 0 (down)     : 1, 25%
outliers [1]       : 0, 0%
low counts [2]     : 0, 0%

Analysis complete! Generated files:
 - results_deseq2_results.csv
 - results_volcano.pdf
 - results_pca.pdf
 - results_heatmap.pdf
```

## Step 7: HPC Deployment

### Build for HPC

```bash
absconda publish \
  --file r-bioconductor-env.yaml \
  --repository ghcr.io/yourusername/r-bioconductor \
  --tag 4.3.1-bioc3.18 \
  --singularity-out r-bioconductor.sif
```

### Generate Wrappers

```bash
absconda wrap \
  --image ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  --commands Rscript,R \
  --output-dir wrappers/r-bioconductor \
  --extra-mounts /scratch/$PROJECT,/g/data/$PROJECT
```

### Generate Module

```bash
absconda module \
  --name r-bioconductor/4.3.1-bioc3.18 \
  --wrapper-dir wrappers/r-bioconductor \
  --description "R 4.3.1 with Bioconductor 3.18 (DESeq2, edgeR)" \
  --image ghcr.io/yourusername/r-bioconductor:4.3.1-bioc3.18 \
  --commands Rscript,R \
  --output-dir modulefiles
```

### Deploy to NCI Gadi

```bash
# Copy to Gadi
rsync -av wrappers/ gadi:/g/data/a56/apps/r-bioconductor/4.3.1-bioc3.18/wrappers/
rsync -av modulefiles/ gadi:/g/data/a56/apps/modulefiles/
rsync r-bioconductor.sif gadi:/g/data/a56/apps/r-bioconductor/4.3.1-bioc3.18/

# Use on Gadi
ssh gadi
module use /g/data/a56/apps/modulefiles
module load r-bioconductor/4.3.1-bioc3.18

# Run analysis
Rscript deseq2_analysis.R \
  /g/data/a56/data/counts.csv \
  /g/data/a56/data/metadata.csv \
  /g/data/a56/results/sample1
```

### PBS Job Script

**run_deseq2.pbs**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q normal
#PBS -l ncpus=4
#PBS -l mem=32GB
#PBS -l walltime=02:00:00
#PBS -l storage=gdata/a56
#PBS -N deseq2_analysis

module use /g/data/a56/apps/modulefiles
module load r-bioconductor/4.3.1-bioc3.18

cd $PBS_O_WORKDIR

Rscript deseq2_analysis.R \
  /g/data/a56/data/counts.csv \
  /g/data/a56/data/metadata.csv \
  $PBS_JOBFS/results

# Copy results back
cp $PBS_JOBFS/results* /g/data/a56/results/
```

Submit:

```bash
qsub run_deseq2.pbs
```

## Step 8: Interactive RStudio Server

### Dockerfile with RStudio

Create custom template `rstudio-template.j2`:

```dockerfile
FROM {{ builder_image }} AS builder

COPY r-bioconductor-env.yaml /tmp/env.yaml
RUN micromamba create -y -n {{ env_name }} -f /tmp/env.yaml && \
    micromamba clean -afy

COPY renv.lock /tmp/renv.lock
RUN . /opt/conda/etc/profile.d/conda.sh && \
    conda activate {{ env_name }} && \
    Rscript -e 'renv::restore(lockfile="/tmp/renv.lock", prompt=FALSE)'

FROM {{ runtime_image }}

COPY --from=builder /opt/conda/envs/{{ env_name }} /opt/conda/envs/{{ env_name }}

ENV PATH=/opt/conda/envs/{{ env_name }}/bin:$PATH

# Install RStudio Server
RUN apt-get update && \
    apt-get install -y wget gdebi-core && \
    wget https://download2.rstudio.org/server/jammy/amd64/rstudio-server-2023.12.0-369-amd64.deb && \
    gdebi -n rstudio-server-2023.12.0-369-amd64.deb && \
    rm rstudio-server-2023.12.0-369-amd64.deb && \
    apt-get clean

EXPOSE 8787

CMD ["/usr/lib/rstudio-server/bin/rserver", "--server-daemonize=0"]
```

Build and run:

```bash
absconda generate \
  --file r-bioconductor-env.yaml \
  --template rstudio-template.j2 \
  --output Dockerfile.rstudio

docker build -t ghcr.io/yourusername/r-bioconductor-rstudio:4.3.1 -f Dockerfile.rstudio .

docker run -p 8787:8787 \
  -v $PWD:/home/rstudio \
  -e PASSWORD=rstudio \
  ghcr.io/yourusername/r-bioconductor-rstudio:4.3.1
```

Access RStudio at `http://localhost:8787` (user: rstudio, password: rstudio)

## Variations

### Add Additional Bioconductor Packages

In R:

```r
BiocManager::install(c(
    "GenomicRanges",
    "rtracklayer",
    "Rsamtools",
    "GenomicFeatures"
))

renv::snapshot()
```

Rebuild container with updated `renv.lock`.

### Python + R Integration

**r-python-env.yaml**:

```yaml
name: r-python
channels:
  - conda-forge
dependencies:
  - python=3.11
  - r-base=4.3.1
  - numpy=1.26
  - pandas=2.2
  - r-essentials
  - pip
  - pip:
      - rpy2==3.5.15

renv:
  lockfile: renv.lock
```

Use rpy2 to call R from Python or vice versa.

## Troubleshooting

### Package Compilation Fails

**Error**: `installation of package 'X' had non-zero exit status`

**Solution**: Add system dependencies:

```yaml
dependencies:
  - r-base=4.3.1
  - libxml2        # For XML packages
  - libgit2        # For devtools/remotes
  - openssl        # For HTTPS
  - libcurl        # For downloads
  - make
  - gcc
  - gxx
```

### renv::restore() Fails

**Error**: `Failed to retrieve package 'X'`

**Solution 1**: Check Bioconductor version matches:

```yaml
dependencies:
  - bioconductor-biocinstaller=3.18  # Must match renv.lock
```

**Solution 2**: Specify repositories in renv config:

```yaml
renv:
  lockfile: renv.lock
  repositories:
    BioCsoft: "https://bioconductor.org/packages/3.18/bioc"
    CRAN: "https://cloud.r-project.org"
```

### GitHub Package Errors

For packages from GitHub in `renv.lock`, ensure remotes is installed:

In R before snapshot:

```r
install.packages("remotes")
renv::snapshot()
```

## Next Steps

- [GPU PyTorch Example](gpu-pytorch.md) - Deep learning
- [Data Science Example](data-science.md) - Python ML stack
- [renv Integration Guide](../guides/renv-integration.md) - R package management
- [HPC Deployment Guide](../guides/hpc-deployment.md) - Complete HPC workflow

## Complete Files

All files in [`examples/`](../../examples/):
- `r-bioconductor-env.yaml`
- `renv.lock`
- `deseq2_analysis.R`
- `counts.csv`
- `metadata.csv`
- `run_deseq2.pbs`
