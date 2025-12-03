# Testing Guide

Comprehensive guide to testing in Absconda.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Coverage](#test-coverage)
- [Testing Strategies](#testing-strategies)
- [Continuous Integration](#continuous-integration)
- [Troubleshooting](#troubleshooting)

## Testing Philosophy

**Goals**:
- Prevent regressions
- Document expected behavior
- Enable confident refactoring
- Catch errors early

**Principles**:
- Tests should be fast
- Tests should be isolated
- Tests should be deterministic
- Tests should be readable

## Test Structure

### Directory Layout

```
tests/
├── conftest.py                # Shared fixtures
├── test_cli.py                # CLI tests
├── test_environment.py        # Environment parsing
├── test_templates.py          # Template engine
├── test_policy.py             # Policy validation
├── test_remote.py             # Remote execution
├── test_modules.py            # Module generation
├── test_wrappers.py           # Wrapper scripts
├── test_integration_smoke.py  # Integration tests
├── test_examples.py           # Example validation
└── fixtures/                  # Test data
    ├── minimal-env.yaml
    ├── data-science-env.yaml
    └── custom-template.j2
```

### Test Organization

Each test file follows this structure:

```python
"""
Test module for X functionality.

Tests cover:
- Basic functionality
- Edge cases
- Error conditions
- Integration with other components
"""

import pytest
from absconda.module import Class


class TestClass:
    """Tests for Class."""
    
    def test_basic_case(self):
        """Test basic functionality."""
        pass
    
    def test_edge_case(self):
        """Test edge case."""
        pass
    
    def test_error_handling(self):
        """Test error conditions."""
        pass


class TestIntegration:
    """Integration tests."""
    
    def test_workflow(self):
        """Test complete workflow."""
        pass
```

## Running Tests

### Basic Usage

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_environment.py

# Run specific test
pytest tests/test_environment.py::test_parse_valid_env

# Run specific test class
pytest tests/test_environment.py::TestEnvironment

# Run tests matching pattern
pytest -k "test_parse"
```

### Test Options

```bash
# Verbose output
pytest -v

# Very verbose (show print statements)
pytest -vv

# Stop on first failure
pytest -x

# Show local variables on failure
pytest -l

# Run last failed tests
pytest --lf

# Run failed tests first
pytest --ff

# Parallel execution (requires pytest-xdist)
pytest -n auto
```

### Test Selection

```bash
# By marker
pytest -m "unit"
pytest -m "integration"
pytest -m "slow"

# By keyword
pytest -k "environment"
pytest -k "not slow"

# Specific test
pytest tests/test_cli.py::test_build_command
```

## Writing Tests

### Unit Tests

Test individual functions/classes in isolation:

```python
# tests/test_environment.py

from absconda.environment import Environment
import pytest


class TestEnvironment:
    """Tests for Environment class."""
    
    def test_from_dict_minimal(self):
        """Test creating environment from minimal dict."""
        data = {
            "name": "test-env",
            "channels": ["conda-forge"],
            "dependencies": ["python=3.11"]
        }
        env = Environment.from_dict(data)
        
        assert env.name == "test-env"
        assert env.channels == ["conda-forge"]
        assert "python=3.11" in env.dependencies
    
    def test_from_dict_invalid(self):
        """Test invalid environment data."""
        data = {"name": "test"}  # Missing required fields
        
        with pytest.raises(ValueError, match="Missing required fields"):
            Environment.from_dict(data)
    
    def test_parse_dependencies(self):
        """Test dependency parsing."""
        data = {
            "name": "test",
            "dependencies": [
                "python=3.11",
                "numpy>=1.26",
                {"pip": ["requests==2.31.0"]}
            ]
        }
        env = Environment.from_dict(data)
        
        assert len(env.conda_deps) == 2
        assert len(env.pip_deps) == 1
        assert env.pip_deps[0] == "requests==2.31.0"
```

### Integration Tests

Test component interactions:

```python
# tests/test_integration_smoke.py

from absconda.environment import Environment
from absconda.templates import TemplateEngine
import pytest


class TestBuildWorkflow:
    """Integration tests for build workflow."""
    
    def test_environment_to_dockerfile(self, sample_env_file):
        """Test generating Dockerfile from environment."""
        # Parse environment
        env = Environment.from_file(sample_env_file)
        
        # Generate Dockerfile
        engine = TemplateEngine()
        dockerfile = engine.render(env, deploy_mode="full-env")
        
        # Verify Dockerfile content
        assert "FROM mambaorg/micromamba" in dockerfile
        assert f"COPY {env.name}.yaml /tmp/env.yaml" in dockerfile
        assert "micromamba create" in dockerfile
    
    def test_custom_template_workflow(self, tmp_path):
        """Test using custom templates."""
        # Create custom template
        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "Dockerfile.j2").write_text("""
FROM {{ builder_base }}
RUN echo "Custom template"
        """)
        
        # Use custom template
        env = Environment.from_dict({
            "name": "test",
            "dependencies": ["python=3.11"]
        })
        
        engine = TemplateEngine(template_dir=template_dir)
        dockerfile = engine.render(env)
        
        assert "Custom template" in dockerfile
```

### End-to-End Tests

Test complete CLI workflows:

```python
# tests/test_examples.py

import subprocess
import pytest
from pathlib import Path


@pytest.mark.slow
class TestExampleWorkflows:
    """E2E tests using example environment files."""
    
    def test_minimal_build(self, tmp_path):
        """Test building minimal example."""
        result = subprocess.run(
            [
                "absconda", "build",
                "--file", "examples/minimal-env.yaml",
                "--tag", "test-minimal:latest",
                "--no-push"
            ],
            capture_output=True,
            text=True,
            timeout=300
        )
        
        assert result.returncode == 0
        assert "Successfully built" in result.stdout
        
        # Verify image exists
        docker_check = subprocess.run(
            ["docker", "images", "-q", "test-minimal:latest"],
            capture_output=True,
            text=True
        )
        assert docker_check.stdout.strip() != ""
    
    @pytest.mark.docker
    def test_run_container(self):
        """Test running built container."""
        # Build image first
        subprocess.run(
            ["absconda", "build", "--file", "examples/minimal-env.yaml", "--tag", "test:latest"],
            check=True,
            capture_output=True
        )
        
        # Run container
        result = subprocess.run(
            ["docker", "run", "--rm", "test:latest", "python", "--version"],
            capture_output=True,
            text=True
        )
        
        assert result.returncode == 0
        assert "Python 3." in result.stdout
```

### Fixtures

Use pytest fixtures for common setup:

```python
# conftest.py

import pytest
from pathlib import Path
import tempfile
import yaml


@pytest.fixture
def tmp_env_file(tmp_path):
    """Create temporary environment file."""
    env_file = tmp_path / "test-env.yaml"
    env_data = {
        "name": "test-env",
        "channels": ["conda-forge"],
        "dependencies": ["python=3.11", "numpy=1.26"]
    }
    env_file.write_text(yaml.dump(env_data))
    return env_file


@pytest.fixture
def sample_env_file():
    """Use existing sample environment file."""
    return Path("examples/minimal-env.yaml")


@pytest.fixture
def docker_available():
    """Check if Docker is available."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "ps"],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


@pytest.fixture
def gcp_credentials():
    """Check for GCP credentials."""
    import os
    return (
        "GCP_PROJECT" in os.environ and
        "GCP_REGION" in os.environ
    )


@pytest.fixture(autouse=True)
def cleanup_docker_images():
    """Cleanup test Docker images after tests."""
    yield
    # Cleanup after test
    import subprocess
    subprocess.run(
        ["docker", "rmi", "-f", "test:latest"],
        capture_output=True
    )
```

### Parametrized Tests

Test multiple cases with parameters:

```python
@pytest.mark.parametrize("deploy_mode,expected", [
    ("full-env", "COPY env.yaml"),
    ("tarball", "conda-pack"),
    ("requirements", "conda env export"),
    ("export-explicit", "conda list --explicit"),
])
def test_deploy_modes(deploy_mode, expected):
    """Test different deployment modes."""
    env = Environment.from_dict({"name": "test", "dependencies": ["python=3.11"]})
    engine = TemplateEngine()
    dockerfile = engine.render(env, deploy_mode=deploy_mode)
    assert expected in dockerfile


@pytest.mark.parametrize("python_version", ["3.9", "3.10", "3.11", "3.12"])
def test_python_versions(python_version):
    """Test different Python versions."""
    env = Environment.from_dict({
        "name": "test",
        "dependencies": [f"python={python_version}"]
    })
    assert env.python_version == python_version
```

### Mocking

Mock external dependencies:

```python
from unittest.mock import Mock, patch, MagicMock


def test_remote_build_with_mock():
    """Test remote build using mocks."""
    with patch('absconda.remote.subprocess.run') as mock_run:
        # Setup mock
        mock_run.return_value = Mock(returncode=0, stdout="Success")
        
        # Run test
        remote = RemoteBuilder("test-builder")
        result = remote.build("env.yaml", "test:latest")
        
        # Verify
        assert result.success
        mock_run.assert_called_once()


def test_docker_build_failure():
    """Test handling Docker build failure."""
    with patch('absconda.build.subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=1, stderr="Build failed")
        
        with pytest.raises(BuildError, match="Build failed"):
            build_image("test-env.yaml", "test:latest")
```

## Test Coverage

### Measuring Coverage

```bash
# Run with coverage
pytest --cov=absconda

# Generate HTML report
pytest --cov=absconda --cov-report=html

# View report
open htmlcov/index.html

# Terminal report
pytest --cov=absconda --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=absconda --cov-fail-under=80
```

### Coverage Configuration

Add to `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src"]
omit = [
    "*/tests/*",
    "*/test_*.py",
    "*/__pycache__/*",
    "*/site-packages/*"
]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
    "@abstract"
]
```

### Coverage Goals

| Component | Target Coverage |
|-----------|----------------|
| Core logic | 90%+ |
| CLI | 80%+ |
| Templates | 85%+ |
| Integration | 70%+ |
| Overall | 85%+ |

## Testing Strategies

### Test Pyramid

```
       /\
      /  \    E2E Tests (Few, Slow, High-level)
     /____\
    /      \  Integration Tests (Some, Medium)
   /        \
  /__________\ Unit Tests (Many, Fast, Focused)
```

**Distribution**:
- 70% Unit tests
- 20% Integration tests
- 10% E2E tests

### Test Types

#### 1. Unit Tests

Fast, isolated, focused:

```python
def test_parse_conda_dep():
    """Test parsing conda dependency."""
    dep = parse_dependency("python=3.11")
    assert dep.name == "python"
    assert dep.version == "3.11"
    assert dep.type == "conda"
```

#### 2. Integration Tests

Test component interactions:

```python
def test_template_with_policy():
    """Test template generation with policy validation."""
    env = Environment.from_file("test-env.yaml")
    policy = Policy.from_file("policy.yaml")
    
    policy.validate(env)  # May raise
    
    engine = TemplateEngine()
    dockerfile = engine.render(env)
    assert dockerfile is not None
```

#### 3. E2E Tests

Complete workflows:

```python
@pytest.mark.slow
def test_full_workflow():
    """Test complete build and deploy workflow."""
    # Build
    subprocess.run(["absconda", "build", ...], check=True)
    
    # Convert to Singularity
    subprocess.run(["absconda", "singularity", ...], check=True)
    
    # Generate module
    subprocess.run(["absconda", "module", ...], check=True)
    
    # Verify module works
    result = subprocess.run(["modulecmd", "python", "load", ...])
    assert result.returncode == 0
```

### Test Markers

Mark tests for selective execution:

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Fast unit tests",
    "integration: Integration tests",
    "slow: Slow tests requiring Docker/network",
    "docker: Tests requiring Docker",
    "gcp: Tests requiring GCP credentials",
    "hpc: Tests for HPC features",
]
```

Use markers:

```python
@pytest.mark.unit
def test_fast_unit():
    """Fast unit test."""
    pass


@pytest.mark.slow
@pytest.mark.docker
def test_docker_build():
    """Slow test requiring Docker."""
    pass


@pytest.mark.gcp
def test_remote_build():
    """Test requiring GCP credentials."""
    pass
```

Run marked tests:

```bash
# Only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Only Docker tests
pytest -m docker
```

## Continuous Integration

### GitHub Actions

`.github/workflows/test.yml`:

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run tests
        run: |
          pytest --cov=absconda --cov-report=xml
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  docker-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker
        uses: docker/setup-buildx-action@v3
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Run Docker tests
        run: pytest -m docker
```

### Pre-commit Hooks

`.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
  
  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
  
  - repo: local
    hooks:
      - id: pytest-unit
        name: pytest-unit
        entry: pytest -m unit
        language: system
        pass_filenames: false
        always_run: true
```

Install:

```bash
pip install pre-commit
pre-commit install
```

## Troubleshooting

### Common Issues

**Tests fail with "Docker not found"**:

```bash
# Check Docker is running
docker ps

# Skip Docker tests
pytest -m "not docker"
```

**Import errors**:

```bash
# Install in development mode
pip install -e .

# Or add to PYTHONPATH
export PYTHONPATH=$PWD/src:$PYTHONPATH
```

**Fixture not found**:

```python
# Make sure conftest.py is in tests/ directory
# Or import fixture explicitly
from conftest import my_fixture
```

**Tests hang**:

```bash
# Add timeout
pytest --timeout=300

# Find hanging test
pytest -v  # See which test is running
```

**Flaky tests**:

```python
# Use pytest-retry
@pytest.mark.flaky(reruns=3)
def test_sometimes_fails():
    pass
```

### Debugging Tests

```bash
# Show print statements
pytest -s

# Drop into debugger on failure
pytest --pdb

# Drop into debugger at start
pytest --trace

# Verbose output
pytest -vv

# Show local variables on failure
pytest -l
```

In code:

```python
def test_something():
    result = do_something()
    
    # Drop into debugger
    import pdb; pdb.set_trace()
    
    assert result == expected
```

### Test Performance

```bash
# Show slowest tests
pytest --durations=10

# Profile tests
pytest --profile

# Parallel execution
pytest -n auto
```

## Best Practices

### Do's

✅ Write tests first (TDD when possible)
✅ Keep tests simple and focused
✅ Use descriptive test names
✅ Test edge cases and errors
✅ Use fixtures for common setup
✅ Mock external dependencies
✅ Keep tests fast
✅ Run tests before committing

### Don'ts

❌ Don't test implementation details
❌ Don't write flaky tests
❌ Don't skip cleanup
❌ Don't hardcode paths/credentials
❌ Don't test external services directly
❌ Don't make tests dependent on each other
❌ Don't ignore test failures

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Test-Driven Development](https://www.obeythetestinggoat.com/)

## Quick Reference

```bash
# Run tests
pytest                              # All tests
pytest tests/test_cli.py            # Specific file
pytest -k "environment"             # By keyword
pytest -m unit                      # By marker

# Options
pytest -v                           # Verbose
pytest -x                           # Stop on failure
pytest --lf                         # Last failed
pytest -n auto                      # Parallel

# Coverage
pytest --cov=absconda               # With coverage
pytest --cov-report=html            # HTML report

# Debug
pytest -s                           # Show prints
pytest --pdb                        # Debug on failure
pytest -l                           # Show locals
```

---

**Questions?** See [Contributing Guide](contributing.md) or open a [Discussion](https://github.com/swarbricklab/absconda/discussions)
