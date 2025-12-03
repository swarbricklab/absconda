"""Tests for environment module file generation."""

import tempfile
from pathlib import Path
from absconda.modules import (
    ModuleConfig,
    generate_module,
    _parse_module_name,
    _module_base_name,
)


def test_parse_module_name():
    """Test parsing module names into base and version."""
    # With version
    base, version = _parse_module_name("myenv/1.0.0")
    assert base == "myenv"
    assert version == "1.0.0"
    
    # Without version - returns empty string, not None
    base, version = _parse_module_name("myenv")
    assert base == "myenv"
    assert version == ""
    
    # Complex version
    base, version = _parse_module_name("python/3.11.2-gcc-11.2")
    assert base == "python"
    assert version == "3.11.2-gcc-11.2"


def test_module_base_name():
    """Test extracting base name for conflict declarations."""
    assert _module_base_name("myenv/1.0.0") == "myenv"
    assert _module_base_name("python/3.11") == "python"
    assert _module_base_name("standalone") == "standalone"


def test_generate_basic_module():
    """Test basic module file generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="testenv/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Test environment",
            image_ref="ghcr.io/test/image:1.0",
            runtime="singularity",
            commands=["python", "pip"],
        )
        
        module_file = generate_module(config)
        
        # Check file was created
        assert module_file.exists()
        assert module_file == Path(tmpdir) / "testenv" / "1.0"
        
        # Check content
        content = module_file.read_text()
        assert "#%Module1.0" in content
        assert "Test environment" in content
        assert "ghcr.io/test/image:1.0" in content
        assert "singularity" in content
        assert "python, pip" in content
        assert "conflict testenv" in content
        # Check for PATH prepend (may have /private prefix on macOS)
        assert "prepend-path PATH" in content
        assert "/wrappers" in content
        assert "setenv TESTENV_VERSION 1.0" in content
        assert "setenv TESTENV_IMAGE ghcr.io/test/image:1.0" in content
        assert "setenv TESTENV_RUNTIME singularity" in content


def test_generate_module_without_version():
    """Test module generation without version number."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="standalone",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Standalone environment",
            image_ref="test:latest",
            runtime="docker",
            commands=["bash"],
        )
        
        module_file = generate_module(config)
        
        # Module file should be at output_dir/standalone (no version subdir)
        assert module_file == Path(tmpdir) / "standalone"
        assert module_file.exists()
        
        content = module_file.read_text()
        assert "Standalone environment" in content
        assert "docker" in content
        assert "conflict standalone" in content
        # No VERSION env var since no version
        assert "STANDALONE_VERSION" not in content


def test_generate_module_docker_runtime():
    """Test module with Docker runtime."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="dockerenv/2.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Docker environment",
            image_ref="python:3.11",
            runtime="docker",
            commands=["python"],
        )
        
        module_file = generate_module(config)
        content = module_file.read_text()
        
        assert "Runtime: docker" in content
        assert "setenv DOCKERENV_RUNTIME docker" in content


def test_module_help_function():
    """Test ModulesHelp procedure in generated module."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="helptest/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Testing help output",
            image_ref="test:latest",
            runtime="singularity",
            commands=["cmd1", "cmd2", "cmd3"],
        )
        
        module_file = generate_module(config)
        content = module_file.read_text()
        
        assert "proc ModulesHelp { }" in content
        assert "Testing help output" in content
        assert "Containerized environment: test:latest" in content
        assert "Wrapped commands: cmd1, cmd2, cmd3" in content


def test_module_conflict_directive():
    """Test that conflict directive uses base name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="myapp/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="My app v1",
            image_ref="myapp:1.0",
            runtime="singularity",
            commands=["myapp"],
        )
        
        module_file = generate_module(config)
        content = module_file.read_text()
        
        # Should conflict with any version of myapp
        assert "conflict myapp" in content


def test_module_creates_parent_directory():
    """Test that module generation creates parent directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="deep/nested/module/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Deeply nested module",
            image_ref="test:latest",
            runtime="singularity",
            commands=["test"],
        )
        
        module_file = generate_module(config)
        
        # Should create all parent directories
        assert module_file.parent.exists()
        assert module_file.exists()
        assert module_file == Path(tmpdir) / "deep/nested/module" / "1.0"


def test_module_with_special_characters():
    """Test module name sanitization with special characters."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        # Module names with hyphens and underscores are common
        config = ModuleConfig(
            name="my-app_test/1.0.0-beta",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Special characters",
            image_ref="test:latest",
            runtime="singularity",
            commands=["test"],
        )
        
        module_file = generate_module(config)
        
        assert module_file.exists()
        # Env var names should be sanitized (uppercase, replace - with _)
        content = module_file.read_text()
        assert "MY_APP_TEST_VERSION" in content
        assert "MY_APP_TEST_IMAGE" in content
        assert "MY_APP_TEST_RUNTIME" in content


def test_module_with_many_commands():
    """Test module with many wrapped commands."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        commands = [f"cmd{i}" for i in range(20)]
        
        config = ModuleConfig(
            name="bigenv/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Environment with many commands",
            image_ref="test:latest",
            runtime="singularity",
            commands=commands,
        )
        
        module_file = generate_module(config)
        content = module_file.read_text()
        
        # All commands should be listed in help
        command_list = ", ".join(commands)
        assert command_list in content


def test_module_whatis_directive():
    """Test module-whatis directive."""
    with tempfile.TemporaryDirectory() as tmpdir:
        wrapper_dir = Path(tmpdir) / "wrappers"
        wrapper_dir.mkdir()
        
        config = ModuleConfig(
            name="test/1.0",
            wrapper_dir=wrapper_dir,
            output_dir=Path(tmpdir),
            description="Short description",
            image_ref="test:latest",
            runtime="singularity",
            commands=["test"],
        )
        
        module_file = generate_module(config)
        content = module_file.read_text()
        
        assert 'module-whatis "Short description"' in content
