"""Tests for wrapper script generation."""

import os
import tempfile
from pathlib import Path

import pytest

from absconda.wrappers import (
    PBS_CONTAINER_ENV,
    SHIM_GROUPS,
    WrapperConfig,
    WrapperError,
    _resolve_shim_groups,
    _sanitize_image_name,
    expand_mount_paths,
    generate_shims,
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
        # Mounts are conditionally added if they exist
        assert '_mount="/data"' in content
        assert '_mount="/scratch"' in content
        assert 'MOUNTS+=("-B" "$_mount")' in content


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


def test_wrapper_with_env_dir():
    """Test Singularity wrapper sets PATH when env_dir is provided."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            env_dir="/opt/conda/envs/myenv",
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()
        assert "SINGULARITYENV_PATH" in content
        assert "/opt/conda/envs/myenv/bin" in content
        assert "SINGULARITYENV_CONDA_PREFIX" in content


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


# ---- Shim tests ----


def test_resolve_unknown_shim_group_raises_error():
    """Test that an unknown shim group raises WrapperError."""
    with pytest.raises(WrapperError, match="Unknown shim group"):
        _resolve_shim_groups(["nonexistent"])


def test_generate_pbs_shims_returns_use_pbs_env():
    """Test PBS shim group signals template to source pbs-container.env."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bind_mounts, path_dirs, use_pbs_env = generate_shims(["pbs"], Path(tmpdir))

        # PBS does not create per-wrapper shim scripts
        assert not (Path(tmpdir) / "pbs-shims").exists()

        # No extra bind mounts or path dirs from PBS alone
        assert bind_mounts == []
        assert path_dirs == []

        # Signals the template to source pbs-container.env
        assert use_pbs_env is True


def test_generate_singularity_shims():
    """Test singularity shim script generation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bind_mounts, path_dirs, use_pbs_env = generate_shims(
            ["singularity"], Path(tmpdir)
        )

        assert use_pbs_env is False

        shim_dir = Path(tmpdir) / "singularity-shims"
        assert shim_dir.is_dir()

        # singularity shim — direct exec (Go binary, no host-linker)
        singularity_shim = shim_dir / "singularity"
        assert singularity_shim.exists()
        assert os.access(singularity_shim, os.X_OK)
        content = singularity_shim.read_text()
        assert "/opt/singularity/bin/singularity" in content
        assert "ld-linux" not in content  # No host-linker for Go binary

        # mksquashfs shim — host-linker pattern (C binary)
        mksquashfs_shim = shim_dir / "mksquashfs"
        assert mksquashfs_shim.exists()
        content = mksquashfs_shim.read_text()
        assert "ld-linux-x86-64.so.2" in content
        assert "--library-path /host-lib64" in content
        assert "/half-root/usr/sbin/mksquashfs" in content

        # Bind mounts include host libs, singularity install, shim dir, and mksquashfs overlay
        assert any("/lib64:/host-lib64:ro" in m for m in bind_mounts)
        assert any("/opt/singularity:/opt/singularity:ro" in m for m in bind_mounts)
        assert any("singularity-shims" in m for m in bind_mounts)
        assert any("mksquashfs:/usr/sbin/mksquashfs:ro" in m for m in bind_mounts)

        assert "/singularity-shims" in path_dirs


def test_generate_pbs_and_singularity_shims():
    """Test combined PBS + singularity shims avoid duplicate bind mounts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        bind_mounts, path_dirs, use_pbs_env = generate_shims(
            ["pbs", "singularity"], Path(tmpdir)
        )

        assert use_pbs_env is True
        assert (Path(tmpdir) / "singularity-shims" / "singularity").exists()
        assert (Path(tmpdir) / "singularity-shims" / "mksquashfs").exists()

        # /lib64:/host-lib64:ro and /half-root should NOT be in bind_mounts
        # because they are already provided by pbs-container.env
        assert not any(
            m.startswith("/lib64:/host-lib64") for m in bind_mounts
        )
        assert not any(
            m.startswith("/half-root:/half-root") for m in bind_mounts
        )

        # Singularity-specific mounts should still be present
        assert any("/opt/singularity:/opt/singularity:ro" in m for m in bind_mounts)
        assert any("singularity-shims" in m for m in bind_mounts)
        assert "/singularity-shims" in path_dirs


def test_wrapper_with_pbs_shims():
    """Test that --shims pbs sources pbs-container.env in wrapper scripts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            shims=["pbs"],
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()

        assert f"source {PBS_CONTAINER_ENV}" in content
        assert "${PBS_MOUNTS[@]}" in content
        assert "${PBS_PATH}" in content


def test_wrapper_shims_with_env_dir():
    """Test that shim PATH dirs are merged into SINGULARITYENV_PATH when env_dir is set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            env_dir="/opt/conda/envs/myenv",
            shims=["pbs"],
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()

        assert "SINGULARITYENV_PATH" in content
        assert "/opt/conda/envs/myenv/bin" in content
        assert "${PBS_PATH}" in content


def test_wrapper_no_shims_no_bind_mounts():
    """Test that without shims, no shim bind mounts appear."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["python"],
            runtime="singularity",
            output_dir=Path(tmpdir),
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "python").read_text()

        assert "pbs-container.env" not in content
        assert "PBS_MOUNTS" not in content
        assert "/host-lib64" not in content
        assert "pbs-shims" not in content


def test_wrapper_with_pbs_and_singularity_shims():
    """Test wrapper with both PBS and singularity shims."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = WrapperConfig(
            image_ref="ghcr.io/test/image:1.0",
            commands=["myapp"],
            runtime="singularity",
            output_dir=Path(tmpdir),
            shims=["pbs", "singularity"],
        )

        generate_wrappers(config)
        content = (Path(tmpdir) / "myapp").read_text()

        # PBS env sourced
        assert f"source {PBS_CONTAINER_ENV}" in content
        assert "${PBS_MOUNTS[@]}" in content

        # Singularity shim bind mounts present
        assert "/opt/singularity:/opt/singularity:ro" in content
        assert "singularity-shims" in content
        assert "mksquashfs:/usr/sbin/mksquashfs:ro" in content

        # PATH includes both PBS and singularity shim dirs
        assert "${PBS_PATH}" in content
        assert "/singularity-shims" in content

        # Shim scripts exist
        assert (Path(tmpdir) / "singularity-shims" / "singularity").exists()
        assert (Path(tmpdir) / "singularity-shims" / "mksquashfs").exists()
