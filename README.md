# Absconda

[![PyPI version](https://badge.fury.io/py/absconda.svg)](https://pypi.org/project/absconda/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

**Turn conda environments into optimized container images for development and HPC deployment.**

Absconda bridges the gap between conda's reproducible environments and container-based workflows. Define your scientific computing environment once with conda, then deploy it anywhere—Docker, Singularity/Apptainer, HPC clusters—with production-ready optimizations.

## Key Features

🚀 **Multi-Stage Builds** - Automatic optimization that reduces image sizes by 40-60%  
🔐 **Policy Validation** - Enforce security and compliance rules organization-wide  
🏗️ **Remote Builders** - Offload builds to cloud instances with automatic provisioning  
🧪 **HPC Integration** - First-class Singularity support with module files and wrappers  
📦 **R + renv Support** - Combine conda environments with R package management  
🎯 **Flexible Deployment** - Multiple modes: full-env, tarball, requirements, export-explicit  
🔧 **Custom Templates** - Jinja2-based system for advanced customization

## Quick Start

### Installation

```bash
# Install from PyPI
pip install absconda

# Or with pipx (recommended)
pipx install absconda

# Verify installation
absconda --version
```

### Basic Usage

**1. Create a conda environment file:**

```yaml
# environment.yaml
name: my-analysis
channels:
  - conda-forge
  - bioconda
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.1
  - scikit-learn=1.3
```

**2. Build a Docker image:**

```bash
absconda build \
  --file environment.yaml \
  --repository ghcr.io/myorg/my-analysis \
  --tag latest \
  --push
```

**3. Use the image:**

```bash
docker run --rm ghcr.io/myorg/my-analysis:latest python -c "import numpy; print(numpy.__version__)"
```

**For HPC with Singularity:**

```bash
# Build and push Docker image, then convert to Singularity
absconda publish \
  --file environment.yaml \
  --repository ghcr.io/myorg/my-analysis \
  --tag latest \
  --singularity-out my-analysis.sif

# Or manually convert after building
absconda build \
  --file environment.yaml \
  --repository ghcr.io/myorg/my-analysis \
  --tag latest \
  --push

singularity pull my-analysis.sif docker://ghcr.io/myorg/my-analysis:latest

# Generate HPC module and wrappers
absconda module \
  --image my-analysis.sif \
  --module-path /apps/modules/my-analysis/1.0
```

See the [Quick Start Guide](docs/getting-started/quickstart.md) for a complete walkthrough.

## Documentation

### For New Users

- **[Installation](docs/getting-started/installation.md)** - Get up and running
- **[Quick Start](docs/getting-started/quickstart.md)** - 5-minute tutorial
- **[Core Concepts](docs/getting-started/concepts.md)** - Understanding absconda

### Guides

- **[Basic Usage](docs/guides/basic-usage.md)** - Essential workflows
- **[Building Images](docs/guides/building-images.md)** - Docker build process
- **[HPC Deployment](docs/guides/hpc-deployment.md)** - Singularity on HPC clusters
- **[Remote Builders](docs/guides/remote-builders.md)** - Cloud-based builds
- **[R + renv Integration](docs/guides/renv-integration.md)** - Combining conda and renv
- **[Requirements Mode](docs/guides/requirements-mode.md)** - Deployment mode comparison
- **[Advanced Templating](docs/guides/advanced-templating.md)** - Custom Dockerfiles

### How-To Guides

- **[Multi-Stage Builds](docs/how-to/multi-stage-builds.md)** - Optimize image size
- **[Custom Base Images](docs/how-to/custom-base-images.md)** - GPU and specialized bases
- **[Secrets Management](docs/how-to/secrets-and-auth.md)** - Handle credentials safely
- **[CI/CD Integration](docs/how-to/ci-cd-integration.md)** - Automate with GitHub Actions

### Examples

Complete working examples with explanations:

- **[Minimal Python](docs/examples/minimal-python.md)** - Simple Python environment
- **[Data Science Stack](docs/examples/data-science.md)** - NumPy/pandas/scikit-learn
- **[R + Bioconductor](docs/examples/r-bioconductor.md)** - RNA-seq analysis
- **[GPU + PyTorch](docs/examples/gpu-pytorch.md)** - Deep learning with CUDA
- **[HPC Workflow](docs/examples/hpc-singularity.md)** - Complete HPC deployment

### Reference

- **[CLI Reference](docs/reference/cli.md)** - Complete command documentation
- **[Environment Files](docs/reference/environment-files.md)** - YAML specification
- **[Configuration](docs/reference/configuration.md)** - System configuration
- **[Policies](docs/reference/policies.md)** - Policy validation system

### For Contributors

- **[Contributing](docs/development/contributing.md)** - How to contribute
- **[Testing](docs/development/testing.md)** - Running and writing tests
- **[Architecture](docs/architecture/)** - Technical design documentation

## Why Absconda?

### The Problem

Scientific computing has conflicting requirements:
- **Reproducibility**: Need exact package versions
- **Portability**: Must run on laptops, HPC clusters, cloud
- **Performance**: Large conda environments create huge containers
- **HPC Reality**: Singularity/Apptainer, not Docker; module systems, not Docker Compose

### The Solution

Absconda solves this by:

1. **Starting with conda** - Use the ecosystem you already know
2. **Optimizing automatically** - Multi-stage builds reduce image sizes by 40-60%
3. **Targeting HPC** - Native Singularity support with modules and wrappers
4. **Enforcing policies** - Organization-wide security and compliance
5. **Enabling remote builds** - Build on powerful cloud instances, not your laptop

### Compared to Alternatives

| Feature | Absconda | repo2docker | docker-conda | Manual Dockerfile |
|---------|----------|-------------|--------------|-------------------|
| Multi-stage optimization | ✅ Automatic | ❌ No | ❌ No | ⚠️ Manual |
| Singularity integration | ✅ First-class | ❌ No | ❌ No | ⚠️ Manual |
| HPC modules | ✅ Built-in | ❌ No | ❌ No | ⚠️ Manual |
| Policy enforcement | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Remote builders | ✅ Yes | ❌ No | ❌ No | ❌ No |
| R + renv support | ✅ Yes | ⚠️ Limited | ❌ No | ⚠️ Manual |
| Custom templates | ✅ Jinja2 | ❌ No | ❌ No | ✅ Full control |

## Real-World Example

Complete workflow for deploying to NCI Gadi HPC:

```bash
# 1. Build optimized Docker image (locally or on GCP)
absconda build \
  --file rnaseq-env.yaml \
  --repository ghcr.io/lab/rnaseq \
  --tag v1.0 \
  --remote-builder gcp-builder \
  --push

# 2. Convert to Singularity on HPC
ssh gadi.nci.org.au
singularity pull rnaseq.sif docker://ghcr.io/lab/rnaseq:v1.0

# 3. Generate module file
absconda module \
  --image /apps/rnaseq/v1.0/rnaseq.sif \
  --module-path /apps/Modules/modulefiles/rnaseq/1.0 \
  --wrapper-dir /apps/rnaseq/v1.0/wrappers

# 4. Use in PBS job
module load rnaseq/1.0
python analysis.py  # Uses containerized environment transparently
```

The result: reproducible, optimized, compliant environments deployed consistently from development through production.

## Use Cases

### 🔬 Research Computing

- Reproducible analysis pipelines
- Sharing environments with collaborators
- Publishing with computational papers
- Archive environments for long-term reproducibility

### 🏢 Multi-User HPC

- Centralized environment management
- Policy enforcement across teams
- Module system integration
- Singularity deployment at scale

### ☁️ Cloud + HPC Hybrid

- Build in cloud (fast, powerful VMs)
- Deploy to HPC (Singularity)
- Consistent environments across platforms
- Cost-optimized with remote builders

### 🧬 Bioinformatics

- Bioconda + R/Bioconductor workflows
- GPU-accelerated analysis
- Large-scale genomics pipelines
- Compliance with data policies

## Project Status

Absconda is production-ready and actively maintained. It powers scientific computing workflows for research teams at the Garvan Institute and beyond.

**Current version**: 0.1.0  
**Python support**: 3.10, 3.11, 3.12  
**License**: MIT

## Getting Help

- **Documentation**: [docs/](docs/)
- **Issues**: [GitHub Issues](https://github.com/swarbricklab/absconda/issues)
- **Discussions**: [GitHub Discussions](https://github.com/swarbricklab/absconda/discussions)

## Contributing

Contributions welcome! See [Contributing Guide](docs/development/contributing.md).

**Areas needing help**:
- Documentation improvements
- Example workflows
- Testing on different platforms
- Feature requests and feedback

## Acknowledgments

Developed at the [Garvan Institute of Medical Research](https://www.garvan.org.au/) by the Swarbrick Lab.

Built with:
- [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html) - Fast conda package manager
- [Jinja2](https://jinja.palletsprojects.com/) - Template engine
- [Singularity/Apptainer](https://apptainer.org/) - HPC containers
- [Terraform](https://www.terraform.io/) - Infrastructure as code

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Ready to get started?** → [Installation Guide](docs/getting-started/installation.md)

**Have questions?** → [GitHub Discussions](https://github.com/swarbricklab/absconda/discussions)

