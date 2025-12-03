# Architecture: Design Overview

High-level architecture and design decisions for Absconda.

## Project Vision

Absconda bridges the gap between conda environments and container images, providing a streamlined workflow for scientific computing, HPC, and production deployments.

**Core philosophy**:
- **Simplicity**: Single YAML file describes entire environment
- **Flexibility**: Support diverse deployment targets (Docker, Singularity, HPC)
- **Reproducibility**: Pin versions, track dependencies, ensure consistency
- **Portability**: Build locally or remotely, deploy anywhere

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
│                                                                 │
│  CLI (absconda build, publish, remote, etc.)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Core Components                            │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │ Environment │  │  Template   │  │   Policy    │           │
│  │   Parser    │  │   Engine    │  │  Validator  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │   Build     │  │   Remote    │  │   Module    │           │
│  │  Manager    │  │  Execution  │  │  Generator  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Backend Systems                             │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │   Docker     │  │  Singularity │  │     GCP      │        │
│  │   Engine     │  │    Build     │  │   Builder    │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐                           │
│  │  Container   │  │   HPC/PBS    │                           │
│  │  Registry    │  │   System     │                           │
│  └──────────────┘  └──────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

## Component Architecture

### 1. Environment Parser

**Purpose**: Parse and validate environment YAML files

**Responsibilities**:
- Parse YAML specification
- Validate schema
- Resolve variable substitution
- Extract metadata (labels, env vars)

**Key files**:
- `src/absconda/environment.py`

**Design decisions**:
- Use Pydantic for validation (type safety, clear errors)
- Support conda-lock format for compatibility
- Allow environment variable interpolation

**Data flow**:
```
YAML file → Parser → Validated Environment object → Template engine
```

### 2. Template Engine

**Purpose**: Generate Dockerfiles from templates

**Responsibilities**:
- Load Jinja2 templates
- Render with environment data
- Support custom templates
- Include template fragments

**Key files**:
- `src/absconda/templates.py`
- `src/absconda/_templates/`

**Design decisions**:
- Jinja2 for flexibility and familiarity
- Fragment-based composition for modularity
- Multiple deployment modes (tarball, requirements, export-explicit)
- Template inheritance for customization

**Template hierarchy**:
```
default/
├── main.j2              # Entry point
├── Dockerfile.j2        # Main template
└── fragments/
    ├── builder_stage.j2      # Multi-stage builder
    ├── runtime_stage.j2      # Runtime stage
    ├── single_stage.j2       # Single-stage
    ├── export_block.j2       # Conda export
    ├── requirements_runtime.j2
    └── tarball_runtime.j2
```

### 3. Build Manager

**Purpose**: Orchestrate container builds

**Responsibilities**:
- Generate Dockerfile
- Execute Docker build
- Tag images
- Push to registry
- Handle build context

**Key files**:
- `src/absconda/cli.py` (build command)

**Design decisions**:
- Shell out to Docker CLI (most reliable)
- Stream build output to user
- Support BuildKit features
- Allow custom base images

**Build flow**:
```
Environment → Template → Dockerfile → Docker build → Tagged image
                                              ↓
                                         Push to registry
```

### 4. Remote Execution

**Purpose**: Execute builds on remote infrastructure

**Responsibilities**:
- Manage remote builder lifecycle (provision, start, stop, destroy)
- Transfer build context to remote
- Execute build remotely
- Pull results back

**Key files**:
- `src/absconda/remote.py`
- `absconda-remote.yaml` (configuration)

**Design decisions**:
- SSH-based execution (simple, secure)
- Support multiple cloud providers (GCP, AWS, Azure)
- Terraform for infrastructure (declarative, reproducible)
- Stateful tracking of remote builders

**Remote build flow**:
```
Local: Generate Dockerfile + context
   ↓
SSH: Transfer to remote builder
   ↓
Remote: Docker build
   ↓
Remote: Push to registry
   ↓
Local: Confirmation
```

**State management**:
```
~/.config/absconda/
└── remote-state.json    # Track remote builders
```

### 5. Policy Validator

**Purpose**: Enforce organizational policies

**Responsibilities**:
- Load policy files
- Validate environment against policies
- Check package versions
- Verify base images
- Enforce security standards

**Key files**:
- `src/absconda/policy.py`

**Design decisions**:
- Profile-based policies (dev, staging, prod)
- Allowlist/blocklist for packages
- Base image restrictions
- Fail fast on violations

**Policy structure**:
```yaml
profiles:
  production:
    package_policy:
      mode: allowlist
      allowed: [python, numpy, pandas]
    base_image_policy:
      mode: allowlist
      allowed: [ubuntu:22.04, debian:12-slim]
```

### 6. Module Generator

**Purpose**: Generate HPC module files

**Responsibilities**:
- Create Tcl module files
- Generate wrapper scripts
- Configure environment variables
- Set up PATH/LD_LIBRARY_PATH

**Key files**:
- `src/absconda/modules.py`

**Design decisions**:
- Support multiple module systems (Tcl, Lua)
- Automatic wrapper generation
- Singularity bind path configuration
- Version-based module hierarchy

**Module structure**:
```
/apps/modulefiles/
└── myapp/
    └── 1.0.0       # Tcl module file

/apps/myapp/
└── 1.0.0/
    ├── myapp.sif
    └── bin/
        └── python-wrapper
```

## Data Flow

### Build Workflow

```
1. User: absconda build --file env.yaml --tag myapp:v1
                │
                ▼
2. Parse: environment.yaml → Environment object
                │
                ▼
3. Validate: Check against policies (if configured)
                │
                ▼
4. Generate: Environment + Template → Dockerfile
                │
                ▼
5. Build: Dockerfile + context → Docker image
                │
                ▼
6. Tag: myapp:v1, myapp:latest
                │
                ▼
7. Push: Registry (if --push)
```

### Remote Build Workflow

```
1. User: absconda build --remote-builder gcp-builder
                │
                ▼
2. Check: Remote builder status (start if stopped)
                │
                ▼
3. Prepare: Generate Dockerfile locally
                │
                ▼
4. Transfer: rsync Dockerfile + context → remote
                │
                ▼
5. Execute: SSH → docker build on remote
                │
                ▼
6. Push: Remote → registry
                │
                ▼
7. Cleanup: Remove build context (optional)
```

### Publish Workflow

```
1. User: absconda publish --singularity-out app.sif
                │
                ▼
2. Build: Docker image (as above)
                │
                ▼
3. Convert: Docker → Singularity (singularity build)
                │
                ▼
4. Output: app.sif file
```

## Design Decisions

### Why Conda + Containers?

**Problem**: Scientific computing requires complex dependencies
- System libraries (gcc, CUDA, etc.)
- Python/R packages with native extensions
- Versioned, reproducible environments

**Solution**: Conda manages dependencies, containers provide isolation
- Conda: Best package manager for scientific software
- Containers: Portable, reproducible, isolated runtime
- Together: Reproducible science, production deployments

### Why Not Just Use Conda Environments?

Containers provide:
- **Isolation**: No conflicts with host system
- **Portability**: Run anywhere (cloud, HPC, local)
- **Versioning**: Immutable, tagged images
- **Distribution**: Push to registry, pull anywhere
- **Security**: Controlled runtime environment

### Why Jinja2 Templates?

**Alternatives considered**:
- Hardcoded Dockerfiles: Inflexible
- Python string formatting: Limited logic
- Custom DSL: Learning curve

**Jinja2 wins because**:
- Familiar to many developers
- Powerful (conditionals, loops, inheritance)
- Mature, well-tested
- Good error messages

### Why Multi-Stage Builds?

**Benefits**:
- Smaller images (50-70% reduction)
- Faster deployments
- Reduced attack surface
- Separates build-time from runtime dependencies

**Trade-offs**:
- More complex Dockerfiles
- Longer initial build time
- Need to identify runtime dependencies

**Decision**: Offer both single-stage (default) and multi-stage (requirements mode)

### Why SSH for Remote Execution?

**Alternatives considered**:
- Docker context: Limited to Docker, complex setup
- Kubernetes jobs: Requires K8s cluster, overkill
- Cloud-specific APIs: Not portable

**SSH wins because**:
- Universal (works everywhere)
- Simple (no special setup)
- Secure (standard authentication)
- Flexible (works with any cloud provider)

### Why Terraform for Infrastructure?

**Alternatives considered**:
- Cloud-specific tools (gcloud, aws cli): Not portable
- Ansible: More imperative, less reproducible
- Pulumi: Requires programming knowledge

**Terraform wins because**:
- Declarative (describe desired state)
- Portable (works across clouds)
- Mature ecosystem
- State management built-in

## Configuration System

### XDG Base Directory Specification

Configuration follows XDG standard:

```
~/.config/absconda/
├── config.yaml          # Global configuration
├── policies/            # Policy files
│   ├── default.yaml
│   └── production.yaml
└── templates/           # Custom templates
    └── mytemplate.j2

~/.cache/absconda/
└── builds/              # Build cache

~/.local/share/absconda/
└── remote-state.json    # Remote builder state
```

**Benefits**:
- Standard location (users know where to look)
- Multiple config files (hierarchy)
- Easy to backup/share
- Follows Unix conventions

### Configuration Hierarchy

1. Command-line arguments (highest priority)
2. Environment variables
3. Project config (`.absconda.yaml`)
4. User config (`~/.config/absconda/config.yaml`)
5. Defaults (lowest priority)

**Example**:
```bash
# Default
--runtime-base ubuntu:22.04

# Override in config
runtime_base: debian:12-slim

# Override on CLI
--runtime-base alpine:3.19
```

## Extension Points

### Custom Templates

Users can override any template:

```bash
absconda generate \
  --file env.yaml \
  --template ~/.config/absconda/templates/custom.j2 \
  --output Dockerfile
```

**Use cases**:
- Organization-specific requirements
- Special base images
- Custom build steps
- Compliance requirements

### Policy Framework

Organizations can enforce policies:

```yaml
# ~/.config/absconda/policies/production.yaml
profiles:
  production:
    package_policy:
      mode: allowlist
      allowed_prefixes: [python, numpy, pandas, scikit-learn]
    base_image_policy:
      mode: allowlist
      allowed: [ubuntu:22.04@sha256:...]
```

Apply:
```bash
absconda build --policy production --file env.yaml
```

### Remote Builder Plugins

Add new cloud providers:

```python
# ~/.config/absconda/plugins/aws_builder.py
class AWSBuilder(RemoteBuilder):
    def provision(self):
        # AWS-specific provisioning
        pass
    
    def start(self):
        # Start EC2 instance
        pass
```

## Performance Considerations

### Build Time Optimization

**Layer caching**:
- Order Dockerfile from least to most frequently changed
- Cache conda environment creation
- Separate code from dependencies

**Parallel builds**:
- Matrix builds in CI/CD
- Multiple environments simultaneously
- Remote builders for parallelization

**Remote builders**:
- Faster network (cloud → registry)
- More powerful machines (n1-standard-8 vs laptop)
- Dedicated resources (no laptop competition)

### Image Size Optimization

**Multi-stage builds**:
- Remove build tools from final image
- Only copy necessary files
- 50-70% size reduction typical

**Export modes**:
- `full-env`: All packages (largest)
- `tarball`: Conda environment tarball
- `requirements`: Only specified packages (smaller)
- `export-explicit`: Minimal (smallest)

**Compression**:
- Docker layers are compressed
- Singularity SIF files are compressed
- Use `.dockerignore` to exclude files

## Security Architecture

### Build-Time Security

**Secrets handling**:
- BuildKit secrets (never in layers)
- SSH agent forwarding for private repos
- Environment variables for tokens

**Image scanning**:
- Trivy for vulnerabilities
- Grype for additional checks
- Integration with CI/CD

### Runtime Security

**Minimal base images**:
- Distroless (no shell, no package manager)
- Alpine (minimal footprint)
- Regularly updated

**Non-root execution**:
- Create dedicated user
- Drop privileges
- Read-only filesystem where possible

**Network isolation**:
- Internal networks
- Firewall rules
- Service mesh (Kubernetes)

## Testing Strategy

### Unit Tests

Test individual components:
- Environment parsing
- Template rendering
- Policy validation
- Configuration loading

**Location**: `tests/test_*.py`

### Integration Tests

Test workflows:
- Build → tag → push
- Remote build execution
- Singularity conversion

**Location**: `tests/test_integration_*.py`

### Example Tests

Validate all examples:
- Build each example
- Run tests in container
- Verify expected behavior

**Location**: `tests/test_examples.py`

## Error Handling

### Graceful Degradation

**Network failures**:
- Retry with exponential backoff
- Clear error messages
- Offline mode (where possible)

**Build failures**:
- Preserve build context for debugging
- Stream build output (see errors immediately)
- Suggest common fixes

**Remote execution failures**:
- Check connectivity first
- Validate credentials
- Provide fallback to local build

### Error Messages

**Good error message**:
```
Error: Failed to build container image

Reason: Package 'nonexistent-pkg' not found in channels
  - conda-forge
  - defaults

Suggestion: Check package name spelling or add channel:
  channels:
    - conda-forge
    - your-channel
```

**Not this**:
```
Error: Build failed
```

## Future Architecture Considerations

### Potential Enhancements

**Caching layer**:
- Cache conda environments between builds
- Share cache across projects
- Reduce build times 50%+

**DAG-based builds**:
- Parallel stage execution
- Dependency resolution
- Optimized build order

**Plugin system**:
- Third-party templates
- Custom builders
- Alternative container runtimes

**Web UI**:
- Visual environment builder
- Build history/logs
- Remote builder dashboard

### Scalability

**Current limits**:
- Local builds: Laptop resources
- Remote builders: 1 at a time
- Registry: Network bandwidth

**Scaling options**:
- Build farm (multiple remote builders)
- Distributed cache (Redis, S3)
- Build queue (RabbitMQ, Kafka)

## Related Documentation

- [Template System](template-system.md) - Template architecture details
- [Remote Execution](remote-execution.md) - Remote builder implementation
- [Specification](spec.md) - Technical specification
- [Plan](plan.md) - Development roadmap

## References

- **XDG Base Directory**: https://specifications.freedesktop.org/basedir-spec/basedir-spec-latest.html
- **Docker BuildKit**: https://github.com/moby/buildkit
- **Conda**: https://docs.conda.io/
- **Singularity**: https://sylabs.io/docs/
- **Terraform**: https://www.terraform.io/docs
