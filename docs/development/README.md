# Development Guide

Developer documentation for contributing to Absconda.

## Overview

This section contains resources for developers working on Absconda itself, as opposed to using Absconda to build container images.

## Documentation

### [Contributing Guide](contributing.md)

Complete guide to contributing to Absconda:
- Getting started with development
- Setting up your development environment
- Code style and standards
- Submitting changes
- Pull request process

**Start here** if you want to contribute code, documentation, or bug fixes.

### [Testing Guide](testing.md)

Comprehensive testing documentation:
- Testing philosophy and strategies
- Running tests locally
- Writing new tests (unit, integration, E2E)
- Test coverage and reporting
- Continuous integration

**Essential reading** for understanding our testing approach and writing quality tests.

### [Release Process](release-process.md)

Documentation for maintainers managing releases:
- Semantic versioning guidelines
- Release workflow and checklist
- Publishing to PyPI
- Hotfix procedures
- Post-release tasks

**For maintainers** preparing and publishing releases.

## Quick Start for Contributors

### 1. Setup Development Environment

```bash
# Clone repository
git clone https://github.com/swarbricklab/absconda.git
cd absconda

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Verify installation
absconda --version
pytest
```

### 2. Make Changes

```bash
# Create feature branch
git checkout -b feature/my-feature

# Make changes
vim src/absconda/module.py

# Add tests
vim tests/test_module.py

# Format and lint
black src/ tests/
flake8 src/ tests/
mypy src/

# Run tests
pytest
```

### 3. Submit Pull Request

```bash
# Commit changes
git add .
git commit -m "feat: add new feature"

# Push to fork
git push origin feature/my-feature

# Open PR on GitHub
```

See [Contributing Guide](contributing.md) for details.

## Development Workflow

### Branching Strategy

```
main
 ├── feature/remote-builders    # New features
 ├── fix/docker-build           # Bug fixes
 ├── docs/update-guides         # Documentation
 └── release/v1.3.0             # Release preparation
```

**Branch types**:
- `feature/*` - New features
- `fix/*` - Bug fixes
- `docs/*` - Documentation
- `refactor/*` - Code refactoring
- `test/*` - Test improvements
- `release/*` - Release preparation

### Development Cycle

1. **Plan**: Create/assign GitHub issue
2. **Branch**: Create feature branch from main
3. **Develop**: Implement changes with tests
4. **Test**: Run full test suite
5. **Review**: Submit PR for review
6. **Merge**: Maintainer merges to main
7. **Release**: Include in next release

### Code Review

All changes require:
- ✅ Tests passing
- ✅ Code formatted (Black)
- ✅ Linting passed (flake8)
- ✅ Type hints correct (mypy)
- ✅ Documentation updated
- ✅ Reviewed by maintainer

## Project Structure

### Source Code

```
src/absconda/
├── __init__.py        # Package initialization
├── __main__.py        # Entry point (python -m absconda)
├── cli.py             # CLI commands and options
├── environment.py     # Environment file parsing
├── templates.py       # Jinja2 template engine
├── policy.py          # Policy validation system
├── remote.py          # Remote builder management
├── modules.py         # HPC module generation
├── wrappers.py        # Wrapper script generation
└── _templates/        # Built-in Jinja2 templates
    ├── default/
    │   ├── main.j2
    │   └── Dockerfile.j2
    └── fragments/
        ├── builder_stage.j2
        ├── runtime_stage.j2
        └── ...
```

### Tests

```
tests/
├── conftest.py                # Shared pytest fixtures
├── test_cli.py                # CLI tests
├── test_environment.py        # Environment parsing tests
├── test_templates.py          # Template engine tests
├── test_policy.py             # Policy validation tests
├── test_remote.py             # Remote builder tests
├── test_modules.py            # Module generation tests
├── test_wrappers.py           # Wrapper generation tests
├── test_integration_smoke.py  # Integration tests
└── fixtures/                  # Test data
```

### Documentation

```
docs/
├── getting-started/   # New user guides
├── guides/            # In-depth guides
├── how-to/            # Task-focused guides
├── examples/          # Complete examples
├── reference/         # API/CLI reference
├── architecture/      # Technical design
└── development/       # This section
```

## Architecture

### Core Components

**Environment Parser** (`environment.py`)
- Parses YAML environment files
- Validates structure and dependencies
- Extracts conda/pip packages

**Template Engine** (`templates.py`)
- Jinja2-based Dockerfile generation
- Multiple deployment modes
- Custom template support

**Build Manager** (`cli.py` build commands)
- Orchestrates Docker builds
- Manages local/remote builds
- Handles image pushing

**Remote Execution** (`remote.py`)
- SSH-based remote builds
- Terraform-based provisioning
- Lifecycle management

**Policy Validator** (`policy.py`)
- Enforces security policies
- Validates dependencies
- Checks base images

**Module Generator** (`modules.py`)
- Generates Tcl modulefiles
- HPC integration
- Environment setup

See [Architecture Documentation](../architecture/) for technical details.

## Development Tools

### Required Tools

```bash
# Python 3.10+
python --version

# Docker
docker --version

# Git
git --version
```

### Development Dependencies

```bash
# Testing
pytest              # Test framework
pytest-cov          # Coverage reporting
pytest-timeout      # Test timeouts

# Code quality
black               # Code formatter
flake8              # Linter
mypy                # Type checker

# Build tools
build               # Package builder
twine               # PyPI uploader
```

Install all at once:

```bash
pip install -e ".[dev]"
```

### VS Code Setup

Recommended `.vscode/settings.json`:

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "editor.formatOnSave": true,
  "editor.rulers": [100]
}
```

Recommended extensions:
- Python (Microsoft)
- Pylance (Microsoft)
- Black Formatter
- Better Jinja

## Common Tasks

### Adding a New CLI Command

1. **Add command to `cli.py`**:

```python
@cli.command()
@click.option('--option', help='Option description')
def new_command(option):
    """Command description."""
    # Implementation
    pass
```

2. **Add tests to `tests/test_cli.py`**:

```python
def test_new_command():
    """Test new CLI command."""
    result = runner.invoke(cli, ['new-command', '--option', 'value'])
    assert result.exit_code == 0
```

3. **Update documentation**:
- Add to `docs/reference/cli.md`
- Add example to relevant guide

### Adding a New Deployment Mode

1. **Add template fragment** in `src/absconda/_templates/fragments/`:

```jinja2
{# new_mode.j2 #}
# New deployment mode
RUN micromamba create -n {{ env_name }} --file env.yaml
```

2. **Update template engine** in `templates.py`:

```python
def render(self, env, deploy_mode='full-env'):
    if deploy_mode == 'new-mode':
        return self._render_new_mode(env)
```

3. **Add tests**:

```python
def test_new_deploy_mode():
    """Test new deployment mode."""
    env = Environment.from_dict(...)
    dockerfile = engine.render(env, deploy_mode='new-mode')
    assert 'expected content' in dockerfile
```

4. **Document**:
- Add to `docs/guides/requirements-mode.md`
- Add example to `docs/examples/`

### Adding a Configuration Option

1. **Add to XDG config** in `config.py`:

```python
def load_config():
    config_file = Path.home() / '.config' / 'absconda' / 'config.yaml'
    # Parse and return config
```

2. **Add CLI option**:

```python
@click.option('--new-option', help='New option')
def command(new_option):
    config = load_config()
    value = new_option or config.get('new_option')
```

3. **Document in `docs/reference/configuration.md`**

## Debugging

### Local Debugging

```bash
# Run with verbose output
absconda build --file env.yaml --verbose

# Use Python debugger
python -m pdb -m absconda build --file env.yaml

# Print debugging
# Add to code:
import sys
print(f"DEBUG: value={value}", file=sys.stderr)
```

### Test Debugging

```bash
# Run single test with output
pytest tests/test_module.py::test_function -s

# Drop into debugger on failure
pytest --pdb

# Verbose output
pytest -vv
```

### Docker Debugging

```bash
# Keep container running
docker run -it test:latest /bin/bash

# Check container logs
docker logs container_id

# Inspect image
docker history test:latest
```

## Performance

### Profiling

```bash
# Profile code
python -m cProfile -o profile.stats -m absconda build --file env.yaml

# View results
python -m pstats profile.stats
>>> sort cumtime
>>> stats 20
```

### Benchmarking

```bash
# Time command
time absconda build --file env.yaml

# Multiple runs
for i in {1..10}; do
  time absconda build --file env.yaml --tag test:$i
done
```

## Security

### Security Best Practices

- ✅ Never commit secrets
- ✅ Use BuildKit secrets for credentials
- ✅ Validate all user inputs
- ✅ Run containers as non-root
- ✅ Keep dependencies updated
- ✅ Follow least privilege principle

### Security Scanning

```bash
# Scan dependencies
pip install safety
safety check

# Scan Docker images
docker scan test:latest

# Check for secrets
git secrets --scan
```

## Getting Help

### Resources

- [GitHub Issues](https://github.com/swarbricklab/absconda/issues) - Bug reports, features
- [GitHub Discussions](https://github.com/swarbricklab/absconda/discussions) - Questions, ideas
- [Architecture Docs](../architecture/) - Technical design
- [User Guides](../guides/) - Usage documentation

### Maintainers

Core maintainers can help with:
- Architecture decisions
- Code review
- Release management
- Infrastructure

Tag maintainers in issues/PRs for help.

## Related Documentation

### For Contributors

- **[Contributing Guide](contributing.md)** - Start here for contributing
- **[Testing Guide](testing.md)** - Writing and running tests
- **[Release Process](release-process.md)** - For maintainers

### For Understanding the Codebase

- **[Architecture Overview](../architecture/design-overview.md)** - System design
- **[Template System](../architecture/template-system.md)** - Template internals
- **[Remote Execution](../architecture/remote-execution.md)** - Remote builder design

### For Using Absconda

- **[Getting Started](../getting-started/)** - New user guides
- **[User Guides](../guides/)** - Comprehensive guides
- **[How-to Guides](../how-to/)** - Task-focused guides
- **[Examples](../examples/)** - Complete examples

## Development Principles

### Code Quality

1. **Simplicity**: Prefer simple solutions over complex ones
2. **Readability**: Code is read more than written
3. **Testability**: Write testable code with clear interfaces
4. **Documentation**: Document intent, not just what code does
5. **Consistency**: Follow established patterns

### Testing

1. **Test first**: Write tests before or with code
2. **Fast tests**: Keep unit tests fast (< 1s)
3. **Independent tests**: Tests shouldn't depend on each other
4. **Clear names**: Test names describe what's tested
5. **Good coverage**: Aim for 85%+ coverage

### Documentation

1. **User-focused**: Write for the user, not yourself
2. **Examples**: Show, don't just tell
3. **Up-to-date**: Update docs with code changes
4. **Cross-reference**: Link related documentation
5. **Complete**: Cover happy path and edge cases

## Contributing Areas

### Code Contributions

- **Features**: New functionality
- **Fixes**: Bug fixes
- **Performance**: Optimizations
- **Refactoring**: Code improvements

### Documentation Contributions

- **Guides**: New guides or improvements
- **Examples**: Real-world examples
- **API docs**: Docstring improvements
- **Translations**: Multi-language support (future)

### Other Contributions

- **Testing**: More tests, better coverage
- **CI/CD**: Workflow improvements
- **Tooling**: Development tool enhancements
- **Design**: UI/UX improvements

All contributions welcome! 🎉

## Quick Reference

### Development Commands

```bash
# Setup
pip install -e ".[dev]"

# Test
pytest                          # All tests
pytest tests/test_cli.py        # Specific file
pytest -m unit                  # Unit tests only

# Code quality
black src/ tests/               # Format
flake8 src/ tests/              # Lint
mypy src/                       # Type check

# Build
python -m build                 # Build package
twine upload dist/*             # Upload to PyPI
```

### Project Links

- **Repository**: https://github.com/swarbricklab/absconda
- **Issues**: https://github.com/swarbricklab/absconda/issues
- **Discussions**: https://github.com/swarbricklab/absconda/discussions
- **PyPI**: https://pypi.org/project/absconda/

---

**Ready to contribute?** Start with the [Contributing Guide](contributing.md)!

**Questions?** Ask in [GitHub Discussions](https://github.com/swarbricklab/absconda/discussions)
