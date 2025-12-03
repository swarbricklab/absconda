# Environment Files Reference

Complete specification for Conda environment YAML files used by Absconda.

## Format Overview

Absconda accepts standard Conda/Mamba environment files with extensions for labels, OCI metadata, and R integration.

```yaml
name: myenv               # Required: environment name
channels:                 # Required: list of conda channels
  - conda-forge
  - bioconda
dependencies:             # Required: packages to install
  - python=3.11
  - numpy=1.26
  - pip:                  # Optional: pip packages
      - requests==2.31.0
labels:                   # Optional: OCI image labels
  maintainer: "user@example.com"
env:                      # Optional: environment variables
  LOG_LEVEL: INFO
```

## Required Fields

### name

Environment name. Used as:
- Conda environment name
- Default image name component
- Container metadata

```yaml
name: my-analysis-env
```

**Rules**:
- Must be a valid identifier
- Used in image tagging if no repository specified
- Slugified for Docker: `my-analysis-env` → `my-analysis-env`

### channels

List of Conda channels for package resolution.

```yaml
channels:
  - conda-forge
  - bioconda
  - defaults
```

**Order matters**: Channels listed first have priority.

**Common channels**:
- `conda-forge` - Community packages (recommended)
- `bioconda` - Bioinformatics packages
- `defaults` - Anaconda default channel
- `nvidia` - NVIDIA packages (CUDA, cuDNN)
- `pytorch` - PyTorch packages

**Policy enforcement**: Channels may be restricted by policy profiles.

### dependencies

List of packages to install.

```yaml
dependencies:
  - python=3.11
  - numpy=1.26.2
  - pandas>=2.0,<3.0
  - scikit-learn
```

**Syntax**:
- `package` - Latest version
- `package=X.Y` - Specific version (major.minor)
- `package=X.Y.Z` - Exact version
- `package>=X.Y` - Minimum version
- `package>=X,<Y` - Range

**Best practice**: Pin major versions for reproducibility.

## Optional Fields

### pip Packages

Nested pip packages under `dependencies`:

```yaml
dependencies:
  - python=3.11
  - pip                   # Ensure pip is installed
  - pip:
      - requests==2.31.0
      - flask==3.0.0
```

**Important**: Include `pip` in conda dependencies first.

**Version syntax**: Use `==` for exact versions (pip convention).

### pip_requirements

Reference an external requirements.txt:

```yaml
name: myenv
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
pip_requirements: requirements.txt
```

Absconda will `pip install -r requirements.txt` after conda packages.

### labels

OCI image labels (metadata):

```yaml
labels:
  org.opencontainers.image.title: "Data Science Environment"
  org.opencontainers.image.description: "Python ML/AI stack"
  org.opencontainers.image.authors: "team@example.com"
  org.opencontainers.image.version: "2024.01"
  org.opencontainers.image.url: "https://github.com/org/repo"
  custom.project: "project-alpha"
```

**Standard labels** (OCI spec):
- `org.opencontainers.image.title`
- `org.opencontainers.image.description`
- `org.opencontainers.image.authors`
- `org.opencontainers.image.version`
- `org.opencontainers.image.url`
- `org.opencontainers.image.documentation`
- `org.opencontainers.image.source`
- `org.opencontainers.image.licenses`

**Custom labels**: Use reverse-DNS notation (e.g., `com.company.project`).

### env

Environment variables set in the container:

```yaml
env:
  LOG_LEVEL: INFO
  DATABASE_URL: postgres://localhost/mydb
  PYTHONUNBUFFERED: "1"
```

**Note**: Values must be strings in YAML.

### renv

R package management with renv:

```yaml
name: r-analysis
channels:
  - conda-forge
dependencies:
  - r-base=4.3.1
  - libgit2
renv:
  lockfile: renv.lock
  restore_options:
    - "--no-cache"
```

**Fields**:
- `lockfile` - Path to renv.lock file (required)
- `restore_options` - List of options for `renv::restore()`
- `repositories` - Custom CRAN/Bioconductor repos (optional)
- `cache_dir` - renv cache directory (optional)

See [R and renv Integration](../guides/renv-integration.md) for details.

## Complete Examples

### Minimal Python

```yaml
name: minimal-python
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      - requests==2.31.0
```

### Data Science Stack

```yaml
name: data-science
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.2
  - scikit-learn=1.4
  - matplotlib=3.8
  - jupyter=1.0
  - pip
  - pip:
      - jupyterlab==4.0.11
labels:
  org.opencontainers.image.title: "Data Science Environment"
  org.opencontainers.image.description: "Python ML/AI stack"
env:
  PYTHONUNBUFFERED: "1"
```

### Bioinformatics

```yaml
name: bioinformatics
channels:
  - bioconda
  - conda-forge
dependencies:
  - python=3.11
  - bwa=0.7.17
  - samtools=1.19
  - bcftools=1.19
  - fastqc=0.12.1
  - multiqc=1.19
  - pip
  - pip:
      - pysam==0.22.0
labels:
  org.opencontainers.image.title: "Bioinformatics Tools"
  org.opencontainers.image.description: "NGS analysis pipeline"
```

### GPU / PyTorch

```yaml
name: pytorch-gpu
channels:
  - pytorch
  - nvidia
  - conda-forge
dependencies:
  - python=3.11
  - pytorch=2.1.0
  - pytorch-cuda=12.1
  - torchvision=0.16.0
  - cudatoolkit=12.1
  - pip
  - pip:
      - transformers==4.36.0
labels:
  org.opencontainers.image.title: "PyTorch GPU Environment"
env:
  CUDA_VISIBLE_DEVICES: "0"
```

### R with Bioconductor

```yaml
name: r-bioconductor
channels:
  - conda-forge
  - bioconda
dependencies:
  - r-base=4.3.1
  - bioconductor-biocinstaller=3.18
  - libxml2
  - libgit2
  - openssl
renv:
  lockfile: renv.lock
  restore_options:
    - "--no-cache"
labels:
  org.opencontainers.image.title: "R Bioconductor Analysis"
  org.opencontainers.image.description: "RNA-seq with DESeq2"
```

### Mixed Python + R

```yaml
name: multi-lang
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
labels:
  org.opencontainers.image.title: "Python + R Environment"
```

## Advanced Patterns

### Version Pinning

**Exact versions** (most reproducible):

```yaml
dependencies:
  - python=3.11.7
  - numpy=1.26.2
  - pandas=2.2.0
```

**Major.minor** (balance updates and stability):

```yaml
dependencies:
  - python=3.11
  - numpy=1.26
  - pandas=2.2
```

**Ranges** (less reproducible):

```yaml
dependencies:
  - python>=3.11,<3.12
  - numpy>=1.26,<2.0
```

### Multi-Architecture Support

Use compatible package versions:

```yaml
name: multi-arch
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26          # Has builds for multiple arches
  - pip
  - pip:
      - requests==2.31.0  # Pure Python, works everywhere
```

Avoid architecture-specific packages or test on all targets.

### Conda + System Packages

Some packages need system libraries. Use conda packages:

```yaml
dependencies:
  # Application packages
  - python=3.11
  - psycopg2=2.9      # PostgreSQL adapter
  
  # System libraries (from conda-forge)
  - postgresql        # Provides libpq
  - libxml2
  - libxslt
  - openssl
  - ca-certificates
```

### Conda vs Pip Priority

**Prefer Conda when available**:

```yaml
dependencies:
  - numpy=1.26        # ✅ From conda-forge (optimized binaries)
  - scipy=1.11        # ✅ From conda-forge
  - pip
  - pip:
      - custom-pkg==1.0  # ✅ Only if not in conda
```

**Avoid mixing** for same package:

```yaml
# ❌ Don't do this
dependencies:
  - numpy=1.26
  - pip:
      - numpy==1.26.2   # Conflicts with conda numpy
```

### Development vs Production

**Production** (pinned):

```yaml
name: myapp-prod
channels:
  - conda-forge
dependencies:
  - python=3.11.7
  - numpy=1.26.2
  - pandas=2.2.0
```

**Development** (flexible):

```yaml
name: myapp-dev
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy>=1.26
  - pandas>=2.2
  - pytest=8.0
  - black=23.12
```

## Validation

### Check Syntax

```bash
absconda validate --file environment.yaml
```

### Warnings

Absconda warns about:
- Unpinned versions
- Missing pip in conda when using pip packages
- Suspicious package names
- Unrecognized fields (typos)

### Policy Enforcement

Policies can restrict:
- Allowed channels
- Required version pinning
- Forbidden packages
- Label requirements

See [Policies](policies.md) for details.

## Converting Formats

### From conda env export

```bash
conda env export -n myenv > environment.yaml
```

May need cleanup:
- Remove `prefix:` line
- Remove build strings (`numpy=1.26.2=py311h...`)
- Simplify to major.minor versions

### From requirements.txt

Create minimal environment:

```yaml
name: from-requirements
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
pip_requirements: requirements.txt
```

Or generate inline:

```yaml
name: from-requirements
channels:
  - conda-forge
dependencies:
  - python=3.11
  - pip
  - pip:
      # Paste from requirements.txt
      - package1==1.0.0
      - package2==2.0.0
```

### To requirements.txt

Extract pip packages:

```bash
conda activate myenv
pip freeze > requirements.txt
```

## Best Practices

1. **Always pin major versions**: `python=3.11`, `numpy=1.26`
2. **Use conda-forge first**: Most active, best coverage
3. **Conda for system deps**: `libxml2`, `postgresql`, `openssl`
4. **Include pip explicitly**: If using pip packages
5. **Order channels by priority**: First listed = highest priority
6. **Add labels**: Help with image discovery and management
7. **Test locally first**: `conda env create -f environment.yaml`
8. **Version control**: Commit environment files to git
9. **Document custom packages**: Use comments for non-obvious dependencies
10. **Validate before building**: `absconda validate --file environment.yaml`

## Common Issues

### "ResolvePackageNotFound"

**Cause**: Package name typo or not available in specified channels.

**Solution**: Check package name on anaconda.org, add missing channel.

### "Conflicting dependencies"

**Cause**: Incompatible version constraints.

**Solution**: Relax version constraints or use different packages.

### Pip packages not installing

**Cause**: Missing `pip` in conda dependencies.

**Solution**: Add `pip` to dependencies before `pip:` section.

## Next Steps

- [CLI Reference](cli.md) - Command-line usage
- [Configuration](configuration.md) - Config file reference
- [Policies](policies.md) - Policy system
- [Basic Usage Guide](../guides/basic-usage.md) - Workflow examples
