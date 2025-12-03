# Contributing to Absconda

Thank you for considering contributing to Absconda! This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Code Style](#code-style)
- [Documentation](#documentation)
- [Release Process](#release-process)

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to build something useful together.

**Key principles**:
- Respect different viewpoints and experiences
- Accept constructive criticism gracefully
- Focus on what's best for the community
- Show empathy towards others

## Getting Started

### Prerequisites

- Python 3.10 or later
- Docker installed and running
- Git
- Basic understanding of conda and containers

### Find Something to Work On

1. **Check Issues**: Look for issues labeled `good first issue` or `help wanted`
2. **Feature Requests**: Browse discussions for feature ideas
3. **Documentation**: Improvements always welcome
4. **Bug Reports**: Help us fix bugs

### Before You Start

1. **Check existing issues**: Avoid duplicate work
2. **Discuss major changes**: Open an issue first for large features
3. **Read documentation**: Familiarize yourself with the codebase

## Development Setup

### 1. Fork and Clone

```bash
# Fork on GitHub, then clone
git clone https://github.com/YOUR_USERNAME/absconda.git
cd absconda

# Add upstream remote
git remote add upstream https://github.com/swarbricklab/absconda.git
```

### 2. Create Virtual Environment

```bash
# Create venv
python -m venv .venv

# Activate (macOS/Linux)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate
```

### 3. Install in Development Mode

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Or manually
pip install -e .
pip install pytest pytest-cov black flake8 mypy
```

### 4. Verify Setup

```bash
# Check installation
absconda --version

# Run tests
pytest

# Check code style
black --check src/
flake8 src/
mypy src/
```

### 5. Configure Environment

```bash
# Copy example environment
cp .env.example .env

# Edit with your settings
vim .env
```

For GCP remote builds:
```bash
# Set up GCP credentials
export GCP_PROJECT=your-project
export GCP_REGION=us-central1
export GCP_ZONE=us-central1-a

# Or use direnv
echo 'export GCP_PROJECT=your-project' >> .env
direnv allow
```

## Making Changes

### Branching Strategy

```bash
# Update main
git checkout main
git pull upstream main

# Create feature branch
git checkout -b feature/my-feature

# Or bug fix
git checkout -b fix/bug-description
```

**Branch naming**:
- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation
- `refactor/description` - Refactoring
- `test/description` - Test improvements

### Development Workflow

1. **Make changes**: Edit code in `src/absconda/`
2. **Add tests**: Write tests in `tests/`
3. **Run tests**: `pytest tests/`
4. **Format code**: `black src/ tests/`
5. **Check style**: `flake8 src/ tests/`
6. **Type check**: `mypy src/`
7. **Update docs**: Edit relevant documentation
8. **Commit**: Clear, descriptive commit messages

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Test changes
- `chore`: Build, CI, dependencies

**Example**:

```
feat: add support for custom base images

Add --builder-base and --runtime-base CLI options to allow users
to specify custom Docker base images for multi-stage builds.

Closes #123
```

### Code Organization

```
src/absconda/
├── __init__.py        # Package exports
├── __main__.py        # Entry point
├── cli.py             # CLI commands
├── environment.py     # Environment parsing
├── templates.py       # Template engine
├── policy.py          # Policy validation
├── remote.py          # Remote execution
├── modules.py         # HPC modules
└── _templates/        # Built-in templates
```

**Adding a new feature**:

1. Add core logic to appropriate module
2. Add CLI command/option in `cli.py`
3. Add tests in `tests/test_*.py`
4. Update documentation
5. Add example if applicable

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_environment.py

# Specific test
pytest tests/test_environment.py::test_parse_valid_env

# With coverage
pytest --cov=absconda --cov-report=html

# Verbose
pytest -v

# Stop on first failure
pytest -x
```

### Test Structure

```python
# tests/test_myfeature.py

import pytest
from absconda.mymodule import MyClass


class TestMyClass:
    """Tests for MyClass."""
    
    def test_basic_functionality(self):
        """Test basic use case."""
        obj = MyClass()
        result = obj.do_something()
        assert result == expected
    
    def test_edge_case(self):
        """Test edge case."""
        obj = MyClass()
        with pytest.raises(ValueError):
            obj.do_something_invalid()
    
    @pytest.fixture
    def sample_data(self):
        """Fixture for test data."""
        return {"key": "value"}
    
    def test_with_fixture(self, sample_data):
        """Test using fixture."""
        obj = MyClass(sample_data)
        assert obj.key == "value"
```

### Test Categories

**Unit tests**: Test individual functions/classes
```python
def test_parse_environment():
    """Unit test for environment parsing."""
    env = Environment.from_dict({"name": "test"})
    assert env.name == "test"
```

**Integration tests**: Test component interactions
```python
def test_build_workflow():
    """Integration test for build workflow."""
    env = Environment.from_file("test-env.yaml")
    dockerfile = generate_dockerfile(env)
    assert "FROM" in dockerfile
```

**End-to-end tests**: Test complete workflows
```python
def test_full_build(tmp_path):
    """E2E test for complete build."""
    result = subprocess.run(
        ["absconda", "build", "--file", "test-env.yaml", "--tag", "test:latest"],
        capture_output=True
    )
    assert result.returncode == 0
```

### Test Fixtures

Use pytest fixtures for common setup:

```python
# conftest.py

import pytest
from pathlib import Path


@pytest.fixture
def sample_env_file(tmp_path):
    """Create sample environment file."""
    env_file = tmp_path / "env.yaml"
    env_file.write_text("""
name: test-env
channels:
  - conda-forge
dependencies:
  - python=3.11
  - numpy=1.26
""")
    return env_file


@pytest.fixture
def docker_available():
    """Check if Docker is available."""
    result = subprocess.run(["docker", "ps"], capture_output=True)
    return result.returncode == 0
```

## Submitting Changes

### Before Submitting

**Checklist**:
- [ ] Tests pass (`pytest`)
- [ ] Code formatted (`black src/ tests/`)
- [ ] No linting errors (`flake8 src/ tests/`)
- [ ] Type hints correct (`mypy src/`)
- [ ] Documentation updated
- [ ] Commit messages clear
- [ ] Branch up to date with main

### Create Pull Request

1. **Push branch**:
```bash
git push origin feature/my-feature
```

2. **Open PR on GitHub**:
   - Go to https://github.com/swarbricklab/absconda
   - Click "New Pull Request"
   - Select your fork and branch
   - Fill in PR template

3. **PR Description**:
```markdown
## Description
Clear description of changes

## Motivation
Why is this change needed?

## Changes
- Added X
- Fixed Y
- Updated Z

## Testing
How was this tested?

## Checklist
- [x] Tests added/updated
- [x] Documentation updated
- [x] Code formatted and linted
```

### PR Review Process

1. **Automated checks**: CI runs tests
2. **Code review**: Maintainers review code
3. **Feedback**: Address review comments
4. **Approval**: PR approved by maintainer
5. **Merge**: Maintainer merges PR

### Responding to Feedback

```bash
# Make requested changes
git add .
git commit -m "Address review feedback"
git push origin feature/my-feature
```

**Be responsive**:
- Acknowledge feedback
- Ask questions if unclear
- Update PR description if scope changes
- Mark resolved conversations

## Code Style

### Python Style

**Follow PEP 8** with these specifics:

```python
# Line length: 100 characters (not 79)
# Use double quotes for strings
# Use type hints

def my_function(arg1: str, arg2: int) -> bool:
    """
    Docstring with description.
    
    Args:
        arg1: First argument description
        arg2: Second argument description
    
    Returns:
        Boolean result
    
    Raises:
        ValueError: If arg2 is negative
    """
    if arg2 < 0:
        raise ValueError("arg2 must be non-negative")
    return True
```

### Formatting

**Use Black**:
```bash
# Format code
black src/ tests/

# Check without modifying
black --check src/
```

**Configuration** (`.pyproject.toml`):
```toml
[tool.black]
line-length = 100
target-version = ['py310']
include = '\.pyi?$'
```

### Linting

**Use flake8**:
```bash
flake8 src/ tests/
```

**Configuration** (`.flake8`):
```ini
[flake8]
max-line-length = 100
exclude = .git,__pycache__,.venv
ignore = E203,W503
```

### Type Hints

**Use mypy**:
```bash
mypy src/
```

**Example**:
```python
from typing import List, Optional, Dict, Any
from pathlib import Path

def parse_env(file: Path) -> Dict[str, Any]:
    """Parse environment file."""
    pass

def build_image(
    env: Dict[str, Any],
    tag: str,
    push: bool = False
) -> Optional[str]:
    """Build container image."""
    pass
```

### Documentation Strings

**Use Google style**:

```python
def complex_function(arg1: str, arg2: int, arg3: Optional[bool] = None) -> Dict[str, Any]:
    """
    Short summary of function.
    
    Longer description with more details about what the function does,
    edge cases, and important notes.
    
    Args:
        arg1: Description of first argument
        arg2: Description of second argument
        arg3: Optional argument description. Defaults to None.
    
    Returns:
        Dictionary containing results with the following keys:
        - 'status': Operation status
        - 'data': Result data
    
    Raises:
        ValueError: If arg2 is negative
        FileNotFoundError: If arg1 references missing file
    
    Example:
        >>> result = complex_function("test", 42)
        >>> print(result['status'])
        'success'
    """
    pass
```

## Documentation

### User Documentation

Located in `docs/`:

```
docs/
├── index.md                  # Landing page
├── getting-started/          # New user guides
├── guides/                   # In-depth guides
├── how-to/                   # Task-focused guides
├── examples/                 # Complete examples
├── reference/                # API/CLI reference
├── architecture/             # Technical design
└── development/              # This section
```

**When to update**:
- New features → Add to guides/how-to
- CLI changes → Update reference/cli.md
- New options → Update reference/environment-files.md
- Examples → Add to examples/

### Code Documentation

**Docstrings for**:
- All public functions
- All classes
- Module-level documentation

**Comments for**:
- Complex logic
- Non-obvious decisions
- TODO/FIXME items

```python
# Good: Explains why
# Use explicit export to reduce image size by ~40%
deploy_mode = 'export-explicit'

# Bad: States the obvious
# Set deploy_mode to export-explicit
deploy_mode = 'export-explicit'
```

### Documentation Style

**Markdown**:
- Use `#` for titles (not underlines)
- Code blocks with language tags
- Link to related docs
- Include examples

**Example**:
````markdown
# Feature Title

Brief description of feature.

## Usage

```bash
absconda command --option value
```

## Options

- `--option`: Description

## Example

Complete working example.

## Related

- [Other Guide](../guides/other.md)
````

## Release Process

See [Release Process](release-process.md) for details.

**Summary**:
1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Tag release: `git tag v1.0.0`
4. Push: `git push --tags`
5. GitHub Actions builds and publishes

## Getting Help

**Stuck?** We're here to help!

- **GitHub Discussions**: Ask questions
- **GitHub Issues**: Report bugs, request features
- **Documentation**: Check existing docs
- **Code Review**: Learn from feedback

## Recognition

Contributors are recognized in:
- README.md contributors section
- CHANGELOG.md release notes
- Git commit history

Thank you for contributing! 🎉

## Additional Resources

- [Architecture Documentation](../architecture/) - Technical design
- [Testing Guide](testing.md) - Testing practices
- [Release Process](release-process.md) - Release workflow
- [Code Style Guide](https://google.github.io/styleguide/pyguide.html) - Python style

## Quick Reference

### Common Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type check
mypy src/

# Build docs locally (if using mkdocs)
mkdocs serve

# Create distribution
python -m build
```

### File Locations

| What | Where |
|------|-------|
| Source code | `src/absconda/` |
| Tests | `tests/` |
| Documentation | `docs/` |
| Templates | `src/absconda/_templates/` |
| Examples | `examples/` |
| Configuration | `pyproject.toml`, `.flake8` |

### Common Issues

**Import errors after installing**:
```bash
pip install -e .  # Reinstall in development mode
```

**Tests fail with Docker errors**:
```bash
docker ps  # Check Docker is running
```

**Type check errors**:
```bash
mypy src/ --show-error-codes  # See specific error codes
```

---

**Questions?** Open a [GitHub Discussion](https://github.com/swarbricklab/absconda/discussions)

**Found a bug?** Open a [GitHub Issue](https://github.com/swarbricklab/absconda/issues)
