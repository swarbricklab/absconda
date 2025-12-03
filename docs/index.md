# Absconda Documentation

Welcome to Absconda, a tool for building containerized Conda and pip environments with ease.

## What is Absconda?

Absconda transforms Conda environment files, pip requirements, or pre-packed tarballs into optimized container images. It's designed for researchers, data scientists, and teams who need reproducible computational environments that can run anywhere—from laptops to HPC clusters.

**Key Features:**

- **Multi-stage builds** - Slim runtime images without build dependencies
- **Remote builders** - Build on powerful cloud instances (GCP support)
- **HPC integration** - Generate Singularity wrappers and environment modules
- **R + renv support** - Seamlessly integrate R package environments
- **Policy enforcement** - Control allowed channels, packages, and build settings
- **Requirements mode** - Use pip requirements.txt instead of Conda

## Quick Links

- **[Getting Started](getting-started/quickstart.md)** - Build your first container in 5 minutes
- **[Installation](getting-started/installation.md)** - Install Absconda
- **[CLI Reference](reference/cli.md)** - Complete command documentation
- **[Examples](examples/)** - Working examples for common scenarios
- **[GitHub Repository](https://github.com/swarbricklab/absconda)** - Source code and issues

## Documentation Structure

### [Getting Started](getting-started/)
New to Absconda? Start here to install and learn core concepts.

- [Installation](getting-started/installation.md) - Install via pip or container
- [Quickstart](getting-started/quickstart.md) - 5-minute tutorial
- [Concepts](getting-started/concepts.md) - Understanding environments, policies, and templates

### [Guides](guides/)
Step-by-step tutorials for common workflows.

- [Basic Usage](guides/basic-usage.md) - Environment files to Dockerfiles
- [Building Images](guides/building-images.md) - Using `build` and `publish` commands
- [Remote Builders](guides/remote-builders.md) - Setting up GCP remote builders
- [HPC Deployment](guides/hpc-deployment.md) - Wrappers and modules for Singularity
- [R + renv Integration](guides/renv-integration.md) - Combining R with Conda
- [Requirements Mode](guides/requirements-mode.md) - Using pip requirements.txt
- [Advanced Templating](guides/advanced-templating.md) - Custom Dockerfile templates

### [Reference](reference/)
Detailed documentation for looking up specifics.

- [CLI Reference](reference/cli.md) - All commands and options
- [Environment Files](reference/environment-files.md) - YAML format specification
- [Configuration](reference/configuration.md) - Config files and XDG paths
- [Policies](reference/policies.md) - Policy profiles and constraints

### [How-To](how-to/)
Solutions to specific problems and tasks.

- [Multi-stage Builds](how-to/multi-stage-builds.md) - Optimize image size
- [Custom Base Images](how-to/custom-base-images.md) - Use different base images
- [Secrets and Auth](how-to/secrets-and-auth.md) - Registry authentication
- [CI/CD Integration](how-to/ci-cd-integration.md) - GitHub Actions, GitLab CI

### [Examples](examples/)
Complete, working examples with explanations.

- [Minimal Python](examples/minimal-python.md) - Simple Python environment
- [Data Science](examples/data-science.md) - NumPy, pandas, JupyterLab
- [R + Bioconductor](examples/r-bioconductor.md) - R environment with Bioconductor
- [GPU PyTorch](examples/gpu-pytorch.md) - GPU-enabled ML environment
- [HPC Singularity](examples/hpc-singularity.md) - Complete HPC deployment

### [Architecture](architecture/)
Design and implementation details for advanced users and contributors.

- [Design Overview](architecture/design-overview.md) - High-level architecture
- [Template System](architecture/template-system.md) - How templates work
- [Remote Execution](architecture/remote-execution.md) - Remote builder internals
- [Specification](architecture/spec.md) - Detailed feature specifications
- [Planning Documents](architecture/plan.md) - Development roadmap

### [Development](development/)
Information for contributors.

- [Contributing](development/contributing.md) - How to contribute
- [Testing](development/testing.md) - Running tests
- [Release Process](development/release-process.md) - Cutting releases

## Getting Help

- **Issues**: Report bugs or request features on [GitHub Issues](https://github.com/swarbricklab/absconda/issues)
- **Discussions**: Ask questions on [GitHub Discussions](https://github.com/swarbricklab/absconda/discussions)

## License

Absconda is open source software. See the repository for license details.
