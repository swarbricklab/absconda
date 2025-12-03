"""Tests for wrapper script generation."""

import os
import tempfile
from pathlib import Path

import pytest

from absconda.wrappers import (
    WrapperConfig,
    WrapperError,
    _sanitize_image_name,
    expand_mount_paths,
    generate_wrappers,
)


def test_sanitize_image_name():
    """Test image name sanitization for SIF filenames."""
    assert _sanitize_image_name("ghcr.io/owner/image:tag") == "owner_image_tag"
    assert _sanitize_image_name("docker.io/python:3.11") == "python_3.11"
    assert _sanitize_image_name("my-image") == "my-image"
    assert _sanitize_image_name("owner/repo:latest") == "owner_repo_latest"


def test_expand_mount_paths():
    """Test mount path expansion with environment variables."""
    os.environ["TEST_VAR"] = "/test/path"
    os.environ["ANOTHER_VAR"] = "/another/path"

    mounts = ["$HOME", "$PWD", "$TEST_VAR", "/literal/path"]
    expanded = expand_mount_paths(mounts)

    # expand_mount_paths keeps the original specs for runtime expansion
    assert "$HOME" in expanded
    assert "$PWD" in expanded
    assert "$TEST_VAR" in expanded
    assert "/literal/path" in expanded


def test_generate_singularity_wrappers():
    """Test Singularity wrapper generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python", "pip"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=False,
        )

        result = generate_wrappers(config)

        assert len(result) == 2
        assert "python" in result
        assert "pip" in result

        # Check python wrapper
        python_path = Path(tmpdir) / "python"
        assert python_path.exists()
        assert os.access(python_path, os.X_OK)

        content = python_path.read_text()
        assert "#!/bin/bash" in content
        assert "ghcr.io/test/image:1.0" in content
        assert "singularity exec" in content
        assert 'python "$@"' in content

        # Check pip wrapper
        pip_path = Path(tmpdir) / "pip"
        assert pip_path.exists()
        assert os.access(pip_path, os.X_OK)


def test_generate_docker_wrappers():
    """Test Docker wrapper generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="docker",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=False,
        )

        result = generate_wrappers(config)

        assert len(result) == 1
        assert "python" in result

        python_path = Path(tmpdir) / "python"
        assert python_path.exists()
        assert os.access(python_path, os.X_OK)

        content = python_path.read_text()
        assert "#!/bin/bash" in content
        assert "ghcr.io/test/image:1.0" in content
        assert "docker run" in content
        assert 'python "$@"' in content


def test_wrapper_with_gpu():
    """Test wrapper generation with GPU support."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test Singularity GPU
        config = WrapperConfig(
            image_ref="test:latest",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=True,
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()
        assert "--nv" in content

        # Test Docker GPU
        config2 = WrapperConfig(
            image_ref="test:latest",
            commands=["python"],
            runtime="docker",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=True,
        )

        generate_wrappers(config2)
        content = (Path(tmpdir) / "python").read_text()
        assert "--gpus all" in content


def test_wrapper_with_custom_mounts():
    """Test wrapper with extra mount points."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="test:latest",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=["/data", "/scratch"],
            env_passthrough=[],
            gpu=False,
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()
        assert '"-B" "/data"' in content
        assert '"-B" "/scratch"' in content


def test_wrapper_with_env_passthrough():
    """Test wrapper with environment variable passthrough."""
    # NOTE: env_passthrough is currently defined but not implemented in templates
    # This test documents the intended behavior for future implementation
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="test:latest",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=["MY_VAR", "ANOTHER_VAR"],
            gpu=False,
        )

        # env_passthrough not yet in templates, just check wrapper works
        result = generate_wrappers(config)
        assert "python" in result
        # TODO: Once env passthrough is implemented, check for SINGULARITYENV_MY_VAR etc


def test_wrapper_with_custom_image_cache():
    """Test wrapper with custom image cache location."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=Path("/custom/cache"),
            extra_mounts=[],
            env_passthrough=[],
            gpu=False,
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()
        assert 'SIF_CACHE="/custom/cache"' in content


def test_empty_commands_list():
    """Test that empty commands list raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="test:latest",
            commands=[],
            runtime="singularity",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=False,
        )

        with pytest.raises(WrapperError, match="No commands specified"):
            generate_wrappers(config)


def test_invalid_runtime():
    """Test that invalid runtime raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="test:latest",
            commands=["python"],
            runtime="invalid",
            output_dir=Path(tmpdir),
            image_cache=None,
            extra_mounts=[],
            env_passthrough=[],
            gpu=False,
        )

        with pytest.raises(WrapperError, match="Unsupported runtime"):
            generate_wrappers(config)
