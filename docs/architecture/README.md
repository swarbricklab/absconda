# Architecture Documentation

Technical design and implementation documentation for Absconda.

## Overview

This section documents the internal architecture, design decisions, and technical implementation details. These documents are intended for:
- **Contributors**: Understanding the codebase
- **Maintainers**: Making informed architectural decisions
- **Advanced users**: Deep customization and extension

For user-facing documentation, see [Guides](../guides/) and [How-to](../how-to/).

## Documents

### [Design Overview](design-overview.md)
**High-level architecture and design philosophy**

**Contents**:
- System architecture diagram
- Component responsibilities
- Data flow and workflows
- Design decisions and rationale
- Configuration system
- Security architecture
- Testing strategy
- Future considerations

**Audience**: Contributors, maintainers, system architects

---

### [Template System](template-system.md)
**Jinja2 template engine for Dockerfile generation**

**Contents**:
- Template structure and hierarchy
- Fragment composition
- Deployment modes (full-env, tarball, requirements, export-explicit)
- Custom template creation
- Template inheritance
- Performance optimization
- Testing templates

**Audience**: Contributors, advanced users creating custom templates

---

### [Remote Execution](remote-execution.md)
**Cloud-based build infrastructure**

**Contents**:
- Remote builder architecture
- Terraform integration
- SSH communication
- Lifecycle management (provision, start, stop, destroy)
- State management
- Cost optimization
- Security considerations
- Monitoring and health checks

**Audience**: Contributors, DevOps engineers, cloud architects

---

### [Specification](spec.md)
**Technical specification and requirements**

**Contents**:
- Project goals and requirements
- YAML environment specification
- API contracts
- File formats
- Validation rules

**Audience**: Contributors, integrators

---

### [Development Plan](plan.md)
**Project roadmap and development priorities**

**Contents**:
- Feature roadmap
- Implementation phases
- Known limitations
- Future enhancements

**Audience**: Maintainers, contributors

---

## Architecture Principles

### 1. Simplicity First

**Philosophy**: Complex problems deserve simple solutions

**Application**:
- Single YAML file for environment definition
- Familiar tools (Docker, conda, SSH)
- Clear abstractions
- Minimal configuration

**Example**:
```yaml
# Simple environment definition
name: myapp
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
```

### 2. Flexibility Through Composition

**Philosophy**: Provide building blocks, not monoliths

**Application**:
- Template fragments (mix and match)
- Multiple deployment modes
- Custom templates supported
- Plugin architecture (planned)

**Example**:
```
Template = Base + Fragments + Custom overrides
```

### 3. Fail Fast, Fail Clear

**Philosophy**: Errors should be caught early and explained clearly

**Application**:
- Validate YAML before building
- Check policies before execution
- Clear error messages with suggestions
- Preserve context for debugging

**Example**:
```
Error: Package 'numpyy' not found

Suggestion: Did you mean 'numpy'?
  - numpy=1.26
```

### 4. Secure by Default

**Philosophy**: Security should be the default, not an option

**Application**:
- Non-root containers
- BuildKit secrets (no leakage)
- Minimal base images
- Read-only filesystems (where possible)

### 5. Convention Over Configuration

**Philosophy**: Smart defaults, explicit overrides

**Application**:
- Sensible defaults (Ubuntu 22.04, micromamba)
- Configuration hierarchy (CLI → env → config → defaults)
- Auto-detection (deployment mode, runtime base)

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          Absconda CLI                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Environment │  │   Template   │  │   Policy     │         │
│  │  Parser      │  │   Engine     │  │   Validator  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                 │
│         └──────────────────┼──────────────────┘                 │
│                            │                                    │
│  ┌─────────────────────────▼─────────────────────────┐         │
│  │            Build Manager                           │         │
│  │  ┌──────────────────┐  ┌──────────────────┐      │         │
│  │  │  Local Builder   │  │  Remote Builder  │      │         │
│  │  └──────────────────┘  └──────────────────┘      │         │
│  └────────────────────────────────────────────────────┘         │
│                            │                                    │
│  ┌─────────────────────────▼─────────────────────────┐         │
│  │            Module Generator                        │         │
│  │  ┌──────────────────┐  ┌──────────────────┐      │         │
│  │  │  Tcl Modules     │  │  Wrappers        │      │         │
│  │  └──────────────────┘  └──────────────────┘      │         │
│  └────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Build Pipeline

```
1. Parse environment.yaml
        │
        ├─► Validate schema
        ├─► Resolve variables
        └─► Extract metadata
        │
        ▼
2. Apply policies (if configured)
        │
        ├─► Check package allowlist
        ├─► Validate base images
        └─► Enforce security rules
        │
        ▼
3. Generate Dockerfile
        │
        ├─► Select template
        ├─► Render with context
        └─► Write to file/stdout
        │
        ▼
4. Build container
        │
        ├─► Local: docker build
        └─► Remote: SSH + docker build
        │
        ▼
5. Tag and push
        │
        ├─► Apply tags
        └─► Push to registry
```

## Key Technologies

| Technology | Purpose | Rationale |
|------------|---------|-----------|
| **Python** | Implementation language | Ecosystem, readability, conda integration |
| **Click** | CLI framework | Intuitive, composable, well-documented |
| **Pydantic** | Data validation | Type safety, clear errors, dataclasses |
| **Jinja2** | Template engine | Familiar, powerful, mature |
| **Docker** | Container runtime | Industry standard, widespread adoption |
| **Terraform** | Infrastructure as code | Declarative, portable, mature |
| **SSH** | Remote communication | Universal, secure, simple |
| **YAML** | Configuration format | Human-readable, widely used |

## Directory Structure

```
src/absconda/
├── __init__.py           # Package initialization
├── __main__.py           # CLI entry point
├── cli.py                # CLI commands (Click)
├── config.py             # Configuration management
├── environment.py        # Environment parsing (Pydantic)
├── templates.py          # Template engine (Jinja2)
├── policy.py             # Policy validation
├── remote.py             # Remote execution
├── modules.py            # HPC module generation
├── wrappers.py           # Wrapper script generation
└── _templates/           # Built-in templates
    └── default/
        ├── main.j2
        ├── Dockerfile.j2
        └── fragments/

tests/
├── test_cli.py
├── test_environment.py
├── test_templates.py
├── test_policy.py
├── test_remote.py
└── fixtures/

terraform/
├── gcp/
│   ├── main.tf
│   ├── compute.tf
│   ├── network.tf
│   └── variables.tf
└── aws/
    └── ...

docs/
├── architecture/         # This directory
├── guides/
├── how-to/
├── examples/
└── reference/
```

## Extension Points

Absconda is designed for extensibility:

### 1. Custom Templates

**Override**: Place templates in `~/.config/absconda/templates/`

**Usage**:
```bash
absconda generate --template custom.j2 --file env.yaml
```

### 2. Policy Profiles

**Define**: Create `~/.config/absconda/policies/myprofile.yaml`

**Usage**:
```bash
absconda build --policy myprofile --file env.yaml
```

### 3. Remote Builder Plugins

**Implement**: Create custom `RemoteBuilder` subclass

**Register**: Add to `absconda-remote.yaml`

### 4. Module Systems

**Add**: Implement `ModuleGenerator` for Lua, etc.

**Use**: `absconda module generate --system lua`

## Testing Architecture

### Unit Tests
- Test individual functions and classes
- Fast execution (<1s)
- No external dependencies
- Mocking for I/O

### Integration Tests
- Test component interactions
- Moderate execution (1-30s)
- May use Docker
- Test real workflows

### End-to-End Tests
- Test complete workflows
- Slow execution (>30s)
- Real builds and deployments
- Validate examples

### CI/CD
- GitHub Actions for automated testing
- Matrix builds for multiple Python versions
- Example validation on each commit

## Performance Considerations

### Build Time
- **Local**: Depends on machine resources
- **Remote**: Faster (cloud resources, network)
- **Cache**: Docker layer caching crucial

### Image Size
- **Single-stage**: 2-3 GB (full environment)
- **Multi-stage**: 1-1.5 GB (runtime only)
- **Optimized**: 800 MB - 1 GB (minimal)

### Network
- **Pull images**: Bandwidth-limited
- **Push images**: Faster from cloud
- **Transfer context**: rsync efficient

## Security Model

### Build Time
- BuildKit secrets (no layer pollution)
- SSH agent forwarding (private repos)
- Separate builder from runtime

### Runtime
- Non-root user
- Minimal base images
- Read-only filesystem (where possible)
- Network isolation

### Remote
- SSH key authentication
- Firewall rules (source IP restriction)
- IAM roles (least privilege)
- Secrets encryption

## Contributing

### Adding Features

1. **Design**: Document architecture decision
2. **Implement**: Write code with tests
3. **Document**: Update architecture docs
4. **Review**: Architecture review
5. **Merge**: Update documentation

### Architecture Reviews

Major changes require architecture review:
- New components
- Significant refactoring
- Breaking changes
- Security-sensitive changes

### Documentation Standards

Architecture docs should:
- Explain **why**, not just **what**
- Include diagrams
- Show code examples
- Consider future extensions
- Be kept up-to-date

## Related Documentation

### For Users
- [Getting Started](../getting-started/) - Quick start
- [Guides](../guides/) - In-depth learning
- [How-to](../how-to/) - Task-focused guides
- [Examples](../examples/) - Complete workflows

### For Contributors
- [Development Guide](../development/) - Contributing
- [Testing Guide](../development/testing.md) - Testing practices
- [Release Process](../development/release-process.md) - Releases

### For Reference
- [CLI Reference](../reference/cli.md) - Command syntax
- [Environment Files](../reference/environment-files.md) - YAML spec
- [Configuration](../reference/configuration.md) - Config system

## Further Reading

- **Clean Architecture**: https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html
- **The Twelve-Factor App**: https://12factor.net/
- **Container Best Practices**: https://docs.docker.com/develop/dev-best-practices/
- **Infrastructure as Code**: https://www.terraform.io/intro

---

**For Contributors**: Start with [Design Overview](design-overview.md), then explore specific components.

**For Advanced Users**: Review [Template System](template-system.md) for customization, [Remote Execution](remote-execution.md) for cloud builds.
