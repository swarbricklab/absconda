# Example: Complete HPC Singularity Workflow

End-to-end workflow for deploying containers to HPC systems with Singularity.

## Overview

This example demonstrates the complete HPC workflow:
- Building containers locally or remotely
- Converting to Singularity
- Deploying to HPC systems
- Creating wrappers and modules
- Running batch jobs

**Target system**: NCI Gadi (Australia), but applicable to any HPC with Singularity/Apptainer.

## Prerequisites

- Absconda installed
- SSH access to HPC system (NCI Gadi)
- NCI project allocation (e.g., `a56`)
- Understanding of PBS job submission

## Step 1: Environment Definition

We'll create a bioinformatics workflow environment with multiple tools.

**bioinfo-workflow-env.yaml**:

```yaml
name: bioinfo-workflow
channels:
  - bioconda
  - conda-forge
  - defaults
dependencies:
  # Core Python
  - python=3.11
  - numpy=1.26
  - pandas=2.2
  - scipy=1.12
  - matplotlib=3.8
  
  # Bioinformatics
  - biopython=1.83
  - pysam=0.22
  - bedtools=2.31
  - samtools=1.19
  - bcftools=1.19
  - vcftools=0.1.16
  
  # Analysis
  - snakemake=7.32
  - multiqc=1.19
  
  # R
  - r-base=4.3
  - r-tidyverse=2.0
  - r-ggplot2=3.4
  
  - pip
  - pip:
      - cutadapt==4.6
      - deeptools==3.5.4

labels:
  org.opencontainers.image.title: "Bioinformatics Workflow Environment"
  org.opencontainers.image.description: "NGS analysis pipeline tools"
  org.opencontainers.image.version: "1.0.0"

env:
  LC_ALL: "C.UTF-8"
  LANG: "C.UTF-8"
```

## Step 2: Build Container (Local)

### Option A: Local Build

```bash
cd ~/projects/bioinfo-pipeline

absconda build \
  --file bioinfo-workflow-env.yaml \
  --repository ghcr.io/yourusername/bioinfo-workflow \
  --tag 1.0.0 \
  --push
```

**Build time**: 15-20 minutes  
**Image size**: ~2 GB

### Option B: Remote Build (GCP)

For larger images or limited local resources:

```bash
# Check remote builder status
absconda remote list
absconda remote status gcp-builder

# Start if needed
absconda remote start gcp-builder

# Build remotely
absconda build \
  --file bioinfo-workflow-env.yaml \
  --repository ghcr.io/yourusername/bioinfo-workflow \
  --tag 1.0.0 \
  --remote-builder gcp-builder \
  --push

# Stop builder (saves costs)
absconda remote stop gcp-builder
```

**Build time**: 10-15 minutes (faster instance)  
**Cost**: ~$0.50 per build

## Step 3: Convert to Singularity

### Using Docker

```bash
# Pull Docker image
docker pull ghcr.io/yourusername/bioinfo-workflow:1.0.0

# Build Singularity image
singularity build bioinfo-workflow.sif docker://ghcr.io/yourusername/bioinfo-workflow:1.0.0
```

**Output**: `bioinfo-workflow.sif` (~1.5 GB)

### Using Absconda Publish

```bash
absconda publish \
  --file bioinfo-workflow-env.yaml \
  --repository ghcr.io/yourusername/bioinfo-workflow \
  --tag 1.0.0 \
  --singularity-out bioinfo-workflow.sif
```

This combines build + convert in one step.

## Step 4: Transfer to HPC

### Copy Singularity Image

```bash
# Create directory structure
ssh gadi "mkdir -p /g/data/a56/apps/bioinfo-workflow/1.0.0"

# Copy SIF file
rsync -avP bioinfo-workflow.sif \
  gadi:/g/data/a56/apps/bioinfo-workflow/1.0.0/

# Copy environment file (for reference)
rsync -avP bioinfo-workflow-env.yaml \
  gadi:/g/data/a56/apps/bioinfo-workflow/1.0.0/
```

### Transfer to Multiple Locations

```bash
# App directory
rsync bioinfo-workflow.sif gadi:/g/data/a56/apps/bioinfo-workflow/1.0.0/

# User workflow directory
rsync bioinfo-workflow.sif gadi:/scratch/a56/$USER/containers/

# Shared team location
rsync bioinfo-workflow.sif gadi:/g/data/a56/containers/
```

## Step 5: Test on HPC

### Interactive Session

```bash
ssh gadi

# Request interactive node
qsub -I -q normal -l ncpus=4,mem=16GB,walltime=1:00:00 -l storage=gdata/a56

# Load Singularity module
module load singularity

# Test basic execution
singularity exec /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  python --version

# Test bioinformatics tools
singularity exec /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  samtools --version

singularity exec /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  bedtools --version
```

**Expected output**:

```
Python 3.11.8
samtools 1.19
bedtools v2.31.0
```

### Test with Data Binding

```bash
# Create test data
mkdir -p /scratch/a56/$USER/test-data
cd /scratch/a56/$USER/test-data

# Run with mounted directories
singularity exec \
  --bind /scratch/a56/$USER:/scratch \
  --bind /g/data/a56:/g/data \
  /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  python process_reads.py --input /scratch/reads.fastq
```

## Step 6: Create Wrapper Scripts

### Samtools Wrapper

**`/g/data/a56/apps/bioinfo-workflow/1.0.0/bin/samtools-wrapper`**:

```bash
#!/bin/bash
# Wrapper for samtools in Singularity container

module load singularity

exec singularity exec \
  --bind /scratch:/scratch \
  --bind /g/data:/g/data \
  /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  samtools "$@"
```

### Python Wrapper

**`/g/data/a56/apps/bioinfo-workflow/1.0.0/bin/python-wrapper`**:

```bash
#!/bin/bash
# Wrapper for Python in Singularity container

module load singularity

exec singularity exec \
  --bind /scratch:/scratch \
  --bind /g/data:/g/data \
  /g/data/a56/apps/bioinfo-workflow/1.0.0/bioinfo-workflow.sif \
  python "$@"
```

### Make Executable

```bash
chmod +x /g/data/a56/apps/bioinfo-workflow/1.0.0/bin/*-wrapper
```

## Step 7: Create Module File

**`/g/data/a56/apps/modulefiles/bioinfo-workflow/1.0.0`**:

```tcl
#%Module1.0
## Bioinformatics Workflow Environment Module

proc ModulesHelp { } {
    puts stderr "Bioinformatics Workflow Environment v1.0.0"
    puts stderr ""
    puts stderr "This module provides access to a comprehensive bioinformatics"
    puts stderr "toolkit including samtools, bedtools, bcftools, and Python"
    puts stderr "with biopython, pysam, and analysis libraries."
    puts stderr ""
    puts stderr "Tools available:"
    puts stderr "  - samtools, bcftools, vcftools"
    puts stderr "  - bedtools"
    puts stderr "  - cutadapt, deeptools"
    puts stderr "  - Python with biopython, pysam, pandas"
    puts stderr "  - R with tidyverse, ggplot2"
    puts stderr "  - snakemake, multiqc"
}

module-whatis "Bioinformatics Workflow Environment v1.0.0"

# Conflicts
conflict bioinfo-workflow
conflict python/3.11

# Prerequisites
prereq singularity

# Paths
set APP_ROOT /g/data/a56/apps/bioinfo-workflow/1.0.0
set SIF_FILE $APP_ROOT/bioinfo-workflow.sif
set BIN_DIR $APP_ROOT/bin

# Add wrappers to PATH
prepend-path PATH $BIN_DIR

# Environment variables
setenv BIOINFO_WORKFLOW_ROOT $APP_ROOT
setenv BIOINFO_WORKFLOW_SIF $SIF_FILE
setenv BIOINFO_WORKFLOW_VERSION "1.0.0"

# Singularity bind paths (if not set globally)
if { ![info exists env(SINGULARITY_BIND)] } {
    setenv SINGULARITY_BIND "/scratch,/g/data"
} else {
    setenv SINGULARITY_BIND "$env(SINGULARITY_BIND),/scratch,/g/data"
}

# Helper function for running commands
set-alias bioinfo-exec "singularity exec $SIF_FILE"
set-alias bioinfo-shell "singularity shell $SIF_FILE"
set-alias bioinfo-python "singularity exec $SIF_FILE python"
```

### Test Module

```bash
# Add to module path
module use /g/data/a56/apps/modulefiles

# Load module
module load bioinfo-workflow/1.0.0

# Test commands
samtools-wrapper --version
python-wrapper --version

# Or use aliases
bioinfo-python --version
bioinfo-exec samtools --version
```

## Step 8: Production Workflow

### Analysis Script

**`variant_calling.py`**:

```python
#!/usr/bin/env python3
"""Variant calling pipeline using workflow environment."""

import argparse
import subprocess
from pathlib import Path


def run_command(cmd, desc):
    """Run shell command with logging."""
    print(f"\n{'=' * 60}")
    print(f"{desc}")
    print(f"Command: {cmd}")
    print(f"{'=' * 60}\n")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    
    print(result.stdout)
    return result


def variant_calling_pipeline(bam_file, reference, output_dir, sample_name):
    """Complete variant calling pipeline."""
    
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Step 1: Sort BAM
    sorted_bam = output_dir / f"{sample_name}.sorted.bam"
    run_command(
        f"samtools sort -@ 4 -o {sorted_bam} {bam_file}",
        "Step 1: Sorting BAM file"
    )
    
    # Step 2: Index BAM
    run_command(
        f"samtools index {sorted_bam}",
        "Step 2: Indexing BAM file"
    )
    
    # Step 3: Call variants with bcftools
    vcf_file = output_dir / f"{sample_name}.vcf.gz"
    run_command(
        f"bcftools mpileup -Ou -f {reference} {sorted_bam} | "
        f"bcftools call -mv -Oz -o {vcf_file}",
        "Step 3: Calling variants"
    )
    
    # Step 4: Index VCF
    run_command(
        f"bcftools index {vcf_file}",
        "Step 4: Indexing VCF file"
    )
    
    # Step 5: Filter variants
    filtered_vcf = output_dir / f"{sample_name}.filtered.vcf.gz"
    run_command(
        f"bcftools view -i 'QUAL>=30 && DP>=10' {vcf_file} -Oz -o {filtered_vcf}",
        "Step 5: Filtering variants"
    )
    
    # Step 6: Generate statistics
    stats_file = output_dir / f"{sample_name}.stats.txt"
    run_command(
        f"bcftools stats {filtered_vcf} > {stats_file}",
        "Step 6: Generating variant statistics"
    )
    
    print(f"\n{'=' * 60}")
    print("Pipeline completed successfully!")
    print(f"Output directory: {output_dir}")
    print(f"Filtered VCF: {filtered_vcf}")
    print(f"Statistics: {stats_file}")
    print(f"{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(description='Variant calling pipeline')
    parser.add_argument('--bam', required=True, help='Input BAM file')
    parser.add_argument('--reference', required=True, help='Reference genome FASTA')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--sample', required=True, help='Sample name')
    
    args = parser.parse_args()
    
    variant_calling_pipeline(
        bam_file=args.bam,
        reference=args.reference,
        output_dir=args.output,
        sample_name=args.sample
    )


if __name__ == '__main__':
    main()
```

### PBS Job Script

**`variant_calling.pbs`**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q normal
#PBS -l ncpus=4
#PBS -l mem=16GB
#PBS -l walltime=4:00:00
#PBS -l storage=gdata/a56+scratch/a56
#PBS -N variant_calling
#PBS -j oe

# Change to working directory
cd $PBS_O_WORKDIR

# Load required modules
module use /g/data/a56/apps/modulefiles
module load bioinfo-workflow/1.0.0

# Set up paths
BAM_FILE=/g/data/a56/data/sample1.bam
REFERENCE=/g/data/a56/reference/genome.fa
OUTPUT_DIR=/scratch/a56/$USER/variants/sample1
SAMPLE_NAME=sample1

# Create output directory
mkdir -p $OUTPUT_DIR

# Run variant calling pipeline
bioinfo-python variant_calling.py \
  --bam $BAM_FILE \
  --reference $REFERENCE \
  --output $OUTPUT_DIR \
  --sample $SAMPLE_NAME

echo "Job completed at $(date)"
```

### Submit Job

```bash
# Copy scripts to HPC
rsync variant_calling.py gadi:~/scripts/
rsync variant_calling.pbs gadi:~/jobs/

# Submit
ssh gadi "cd ~/jobs && qsub variant_calling.pbs"

# Monitor
watch qstat -u $USER

# Check output
ssh gadi "tail -f ~/jobs/variant_calling.o*"
```

## Step 9: Array Jobs

For processing multiple samples:

**`variant_calling_array.pbs`**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q normal
#PBS -l ncpus=4
#PBS -l mem=16GB
#PBS -l walltime=4:00:00
#PBS -l storage=gdata/a56+scratch/a56
#PBS -N variant_array
#PBS -j oe
#PBS -J 1-10

# Array job: processes samples 1-10

cd $PBS_O_WORKDIR

module use /g/data/a56/apps/modulefiles
module load bioinfo-workflow/1.0.0

# Get sample name from array index
SAMPLE_NAME="sample${PBS_ARRAY_INDEX}"
BAM_FILE=/g/data/a56/data/${SAMPLE_NAME}.bam
REFERENCE=/g/data/a56/reference/genome.fa
OUTPUT_DIR=/scratch/a56/$USER/variants/${SAMPLE_NAME}

# Run analysis
bioinfo-python variant_calling.py \
  --bam $BAM_FILE \
  --reference $REFERENCE \
  --output $OUTPUT_DIR \
  --sample $SAMPLE_NAME

echo "Sample ${SAMPLE_NAME} completed at $(date)"
```

Submit array job:

```bash
qsub variant_calling_array.pbs
```

This processes 10 samples in parallel!

## Step 10: Snakemake Workflow

For complex pipelines with dependencies:

**`Snakefile`**:

```python
"""Snakemake workflow for variant calling."""

# Configuration
SAMPLES = ['sample1', 'sample2', 'sample3']
REFERENCE = '/g/data/a56/reference/genome.fa'
DATA_DIR = '/g/data/a56/data'
OUTPUT_DIR = '/scratch/a56/variants'

rule all:
    input:
        expand(f"{OUTPUT_DIR}/{{sample}}/{{sample}}.filtered.vcf.gz", sample=SAMPLES),
        f"{OUTPUT_DIR}/multiqc_report.html"

rule sort_bam:
    input:
        f"{DATA_DIR}/{{sample}}.bam"
    output:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.sorted.bam"
    threads: 4
    shell:
        "samtools sort -@ {threads} -o {output} {input}"

rule index_bam:
    input:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.sorted.bam"
    output:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.sorted.bam.bai"
    shell:
        "samtools index {input}"

rule call_variants:
    input:
        bam=f"{OUTPUT_DIR}/{{sample}}/{{sample}}.sorted.bam",
        bai=f"{OUTPUT_DIR}/{{sample}}/{{sample}}.sorted.bam.bai",
        ref=REFERENCE
    output:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.vcf.gz"
    threads: 2
    shell:
        "bcftools mpileup -Ou -f {input.ref} {input.bam} | "
        "bcftools call -mv -Oz -o {output}"

rule filter_variants:
    input:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.vcf.gz"
    output:
        f"{OUTPUT_DIR}/{{sample}}/{{sample}}.filtered.vcf.gz"
    shell:
        "bcftools view -i 'QUAL>=30 && DP>=10' {input} -Oz -o {output}"

rule multiqc:
    input:
        expand(f"{OUTPUT_DIR}/{{sample}}/{{sample}}.filtered.vcf.gz", sample=SAMPLES)
    output:
        f"{OUTPUT_DIR}/multiqc_report.html"
    shell:
        "multiqc {OUTPUT_DIR} -o {OUTPUT_DIR}"
```

**`snakemake_run.pbs`**:

```bash
#!/bin/bash
#PBS -P a56
#PBS -q normal
#PBS -l ncpus=12
#PBS -l mem=48GB
#PBS -l walltime=8:00:00
#PBS -l storage=gdata/a56+scratch/a56
#PBS -N snakemake_workflow
#PBS -j oe

cd $PBS_O_WORKDIR

module use /g/data/a56/apps/modulefiles
module load bioinfo-workflow/1.0.0

# Run Snakemake workflow
bioinfo-exec snakemake \
  --cores 12 \
  --printshellcmds \
  --keep-going \
  --rerun-incomplete
```

## Troubleshooting

### Bind Path Errors

**Error**: `WARNING: Skipping mount /g/data: path does not exist`

**Solution**: Add bind paths:

```bash
singularity exec --bind /scratch,/g/data container.sif command
```

Or set globally in module:

```tcl
setenv SINGULARITY_BIND "/scratch,/g/data"
```

### Permission Denied

**Error**: `Permission denied` when accessing files

**Solution**: Check file ownership and permissions:

```bash
# Fix ownership
chown -R $USER:$PROJECT /scratch/a56/$USER/

# Fix permissions
chmod -R 755 /scratch/a56/$USER/
```

### Module Not Found

**Error**: `Module 'bioinfo-workflow/1.0.0' not found`

**Solution**: Add module path:

```bash
module use /g/data/a56/apps/modulefiles
```

Add to `~/.bashrc` for permanent:

```bash
echo "module use /g/data/a56/apps/modulefiles" >> ~/.bashrc
```

### Container Version Mismatch

**Error**: Different results between local and HPC

**Solution**: Use exact same container image:

```bash
# Pull specific digest
docker pull ghcr.io/yourusername/bioinfo-workflow@sha256:abc123...

# Build SIF from digest
singularity build bioinfo-workflow.sif \
  docker://ghcr.io/yourusername/bioinfo-workflow@sha256:abc123...
```

## Best Practices

### Directory Structure

```
/g/data/a56/
├── apps/
│   ├── bioinfo-workflow/
│   │   └── 1.0.0/
│   │       ├── bioinfo-workflow.sif
│   │       ├── bioinfo-workflow-env.yaml
│   │       └── bin/
│   │           ├── samtools-wrapper
│   │           └── python-wrapper
│   └── modulefiles/
│       └── bioinfo-workflow/
│           └── 1.0.0
├── data/
│   └── reference/
│       └── genome.fa
└── containers/
    └── (shared containers)

/scratch/a56/$USER/
├── workflows/
│   └── variant-calling/
├── temp/
└── results/
```

### Version Pinning

Always pin versions in environment files:

```yaml
dependencies:
  - samtools=1.19    # Good: specific version
  - samtools         # Bad: unpredictable version
```

### Documentation

Include README with each container:

**`/g/data/a56/apps/bioinfo-workflow/1.0.0/README.md`**:

```markdown
# Bioinformatics Workflow Environment v1.0.0

## Tools Included
- samtools 1.19
- bedtools 2.31
- Python 3.11 with biopython, pysam

## Usage
```bash
module load bioinfo-workflow/1.0.0
samtools-wrapper --version
```

## Build Date
2024-01-15

## Maintainer
team@example.com
```

## Next Steps

- [GPU PyTorch Example](gpu-pytorch.md) - GPU containers on HPC
- [HPC Deployment Guide](../guides/hpc-deployment.md) - Detailed HPC setup
- [Remote Builders Guide](../guides/remote-builders.md) - Cloud build infrastructure
- [Singularity Wrappers How-to](../how-to/singularity-wrappers.md) - Creating wrappers

## Complete Workflow Summary

1. **Define** environment (YAML)
2. **Build** container (local or remote)
3. **Convert** to Singularity (SIF)
4. **Transfer** to HPC (rsync)
5. **Create** wrappers (executable scripts)
6. **Module** file (Tcl)
7. **Test** interactively
8. **Deploy** production workflow
9. **Submit** PBS jobs
10. **Monitor** and iterate

This workflow ensures reproducible, portable HPC deployments! 🚀
