# Examples

Complete end-to-end workflows demonstrating different use cases for Absconda.

## Available Examples

Each example provides a complete, working workflow from environment definition to production deployment:

### [Minimal Python Environment](minimal-python.md)
**Audience**: Python developers, web services, lightweight applications  
**What you'll learn**:
- Creating minimal Python environments with pip packages
- Building and testing containers
- Deploying with Docker Compose and Kubernetes
- Requirements mode for faster iteration

**Tools**: Python, requests, click

**Time**: 30 minutes

---

### [Data Science Stack](data-science.md)
**Audience**: Data scientists, ML engineers, researchers  
**What you'll learn**:
- Setting up full data science environments
- Jupyter Lab integration
- Machine learning workflows
- HPC deployment with PBS
- CI/CD pipelines

**Tools**: NumPy, pandas, scikit-learn, Jupyter, matplotlib

**Time**: 1 hour

---

### [R and Bioconductor](r-bioconductor.md)
**Audience**: Bioinformaticians, R users, RNA-seq analysts  
**What you'll learn**:
- R environments with renv integration
- Bioconductor package management
- RNA-seq differential expression analysis
- RStudio Server deployment

**Tools**: R, renv, DESeq2, edgeR, limma

**Time**: 1.5 hours

---

### [GPU PyTorch Deep Learning](gpu-pytorch.md)
**Audience**: Deep learning practitioners, GPU users  
**What you'll learn**:
- CUDA-enabled container builds
- PyTorch GPU configuration
- Neural network training workflows
- Multi-GPU setups
- HPC GPU jobs

**Tools**: PyTorch, CUDA, transformers, wandb

**Time**: 1 hour

---

### [Complete HPC Singularity Workflow](hpc-singularity.md)
**Audience**: HPC users, system administrators  
**What you'll learn**:
- End-to-end HPC deployment
- Singularity/Apptainer conversion
- Creating wrappers and modules
- PBS job submission
- Array jobs and Snakemake workflows

**Tools**: Singularity, PBS, samtools, bedtools, snakemake

**Time**: 2 hours

---

## Quick Start

All examples follow this pattern:

1. **Define** environment in YAML
2. **Build** container image
3. **Test** locally
4. **Deploy** to target platform

## Prerequisites

Before starting any example:

- Absconda installed ([Installation](../getting-started/installation.md))
- Docker installed (for local builds)
- Basic command-line knowledge

Additional requirements per example:
- **GPU examples**: NVIDIA GPU + NVIDIA Container Toolkit
- **HPC examples**: SSH access to HPC system
- **R examples**: Familiarity with R and renv

## Example Files

Complete example files are in the [`examples/`](../../examples/) directory:

```
examples/
├── minimal-env.yaml           # Minimal Python
├── data-science-env.yaml      # Data science stack
├── renv-env.yaml              # R with renv
├── pytorch-gpu-env.yaml       # PyTorch with CUDA
├── bioinfo-workflow-env.yaml  # HPC bioinformatics
└── README.md
```

## Learning Path

### Beginner
Start here if you're new to Absconda:
1. [Minimal Python](minimal-python.md)
2. [Data Science](data-science.md)

### Intermediate
For users comfortable with containers:
1. [R and Bioconductor](r-bioconductor.md)
2. [GPU PyTorch](gpu-pytorch.md)

### Advanced
For HPC deployment and complex workflows:
1. [HPC Singularity Workflow](hpc-singularity.md)

## Related Documentation

- **Guides**: In-depth guides on specific features
  - [Basic Usage](../guides/basic-usage.md)
  - [Building Images](../guides/building-images.md)
  - [HPC Deployment](../guides/hpc-deployment.md)
  - [Remote Builders](../guides/remote-builders.md)

- **Reference**: Detailed specifications
  - [CLI Reference](../reference/cli.md)
  - [Environment Files](../reference/environment-files.md)
  - [Configuration](../reference/configuration.md)

- **How-to**: Task-focused instructions
  - Multi-stage builds
  - Custom base images
  - Secrets and authentication
  - CI/CD integration

## Getting Help

- Check [Troubleshooting](../guides/basic-usage.md#troubleshooting) sections in each example
- Review [Concepts](../getting-started/concepts.md) for terminology
- See [Quickstart](../getting-started/quickstart.md) for command overview

## Contributing Examples

Have a workflow to share? We welcome contributions!

1. Create your example following the existing format
2. Include complete, working code
3. Add troubleshooting section
4. Test on target platform
5. Submit a pull request

Example template:

```markdown
# Example: [Title]

## Overview
- What this demonstrates
- Use case
- Target audience

## Prerequisites
- Required tools
- System requirements

## Steps
1. Define environment
2. Build container
3. Test
4. Deploy

## Complete Code
[All scripts and config files]

## Troubleshooting
[Common issues and solutions]

## Next Steps
[Related examples and docs]
```

---

**Next**: Start with [Minimal Python](minimal-python.md) or explore [Getting Started](../getting-started/quickstart.md)
