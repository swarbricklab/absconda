"""Container wrapper script generation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Optional

from jinja2 import Environment, StrictUndefined


class WrapperError(Exception):
    """Raised when wrapper generation fails."""


# Host dynamic linker path inside the container (bind-mounted from /lib64).
HOST_LIB64 = "/lib64"
HOST_LIB64_MOUNT = "/host-lib64"
HOST_LD_SO = "/host-lib64/ld-linux-x86-64.so.2"

# Path to the shared PBS container environment file.
PBS_CONTAINER_ENV = "/g/data/a56/software/singularity/pbs-container.env"

# Well-known shim groups.
#
# "pbs"         – sources pbs-container.env (no per-wrapper scripts generated).
# "singularity" – generates per-wrapper shim scripts for running host
#                 singularity (Go binary, direct exec) and mksquashfs
#                 (C binary, host-linker shim bound to /usr/sbin/mksquashfs).

SHIM_GROUPS: set[str] = {"pbs", "singularity"}


def _generate_singularity_shims(output_dir: Path) -> tuple[list[str], list[str]]:
    """Create shim scripts for running singularity inside a container.

    Returns ``(bind_mounts, path_dirs)``.
    """
    shim_dir = output_dir / "singularity-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)

    # singularity — Go binary, no host-linker needed
    singularity_shim = shim_dir / "singularity"
    singularity_shim.write_text(
        '#!/bin/bash\nexec /opt/singularity/bin/singularity "$@"\n',
        encoding="utf-8",
    )
    singularity_shim.chmod(0o755)

    # mksquashfs — C binary, needs host-linker + host libs
    mksquashfs_shim = shim_dir / "mksquashfs"
    mksquashfs_shim.write_text(
        f"#!/bin/bash\n"
        f"exec {HOST_LD_SO} --library-path {HOST_LIB64_MOUNT}"
        f' /half-root/usr/sbin/mksquashfs "$@"\n',
        encoding="utf-8",
    )
    mksquashfs_shim.chmod(0o755)

    container_shim_path = "/singularity-shims"

    bind_mounts = [
        f"{HOST_LIB64}:{HOST_LIB64_MOUNT}:ro",
        "/half-root:/half-root:ro",
        "/opt/singularity:/opt/singularity:ro",
        f"{shim_dir}:{container_shim_path}:ro",
        # singularity.conf hardcodes mksquashfs path = /usr/sbin/mksquashfs
        f"{shim_dir}/mksquashfs:/usr/sbin/mksquashfs:ro",
    ]
    path_dirs = [container_shim_path]

    return bind_mounts, path_dirs


@dataclass(slots=True)
class WrapperConfig:
    """Configuration for wrapper script generation."""

    image_ref: str
    commands: list[str]
    runtime: str  # "singularity" or "docker"
    output_dir: Path
    image_cache: Optional[Path] = None
    extra_mounts: Optional[list[str]] = None
    env_passthrough: Optional[list[str]] = None
    gpu: bool = False
    env_dir: Optional[str] = None  # Conda env path inside container
    shims: list[str] = field(default_factory=list)  # e.g. ["pbs", "singularity"]

    def __post_init__(self):
        if self.extra_mounts is None:
            self.extra_mounts = []
        if self.env_passthrough is None:
            self.env_passthrough = []


def _sanitize_image_name(image_ref: str) -> str:
    """
    Convert image reference to safe filename.

    ghcr.io/lab/myenv:1.0 -> lab_myenv_1.0
    """
    # Remove registry prefix
    without_registry = re.sub(r"^[^/]+\.(io|com|org)/", "", image_ref)
    # Replace special chars with underscores
    sanitized = re.sub(r"[/:@]", "_", without_registry)
    return sanitized


def _load_wrapper_template(runtime: str) -> str:
    """Load wrapper template from package resources."""
    template_pkg = files("absconda._templates.wrappers")
    template_file = template_pkg / f"{runtime}.sh.j2"
    return template_file.read_text(encoding="utf-8")


def _resolve_shim_groups(shim_names: list[str]) -> None:
    """Validate shim group names. Raises WrapperError for unknown names."""
    unknown = [g for g in shim_names if g not in SHIM_GROUPS]
    if unknown:
        available = ", ".join(sorted(SHIM_GROUPS))
        raise WrapperError(f"Unknown shim group(s): {', '.join(unknown)}. Available: {available}")


def generate_shims(
    shim_names: list[str],
    output_dir: Path,
) -> tuple[list[str], list[str], bool]:
    """
    Generate shim scripts and return bind-mount, PATH, and PBS info.

    The ``pbs`` shim group does not generate scripts — it signals the
    template to ``source`` the shared ``pbs-container.env`` file.

    The ``singularity`` shim group generates per-wrapper shim scripts.

    Returns ``(bind_mounts, path_dirs, use_pbs_env)`` where *bind_mounts*
    is a list of ``-B`` flag values, *path_dirs* are container-side
    directories to prepend to ``$PATH``, and *use_pbs_env* indicates
    whether the wrapper should source ``pbs-container.env``.
    """
    _resolve_shim_groups(shim_names)

    bind_mounts: list[str] = []
    path_dirs: list[str] = []
    use_pbs_env = "pbs" in shim_names

    if "singularity" in shim_names:
        sing_binds, sing_paths = _generate_singularity_shims(output_dir)
        # If PBS is also requested, pbs-container.env already includes
        # /lib64:/host-lib64:ro and /half-root:/half-root:ro — skip duplicates.
        if use_pbs_env:
            sing_binds = [
                b
                for b in sing_binds
                if not b.startswith(f"{HOST_LIB64}:{HOST_LIB64_MOUNT}")
                and not b.startswith("/half-root:/half-root")
            ]
        bind_mounts.extend(sing_binds)
        path_dirs.extend(sing_paths)

    return bind_mounts, path_dirs, use_pbs_env


def generate_wrappers(config: WrapperConfig) -> dict[str, Path]:
    """
    Generate wrapper scripts for specified commands.

    Returns a dict mapping command names to their wrapper script paths.
    """
    if not config.commands:
        raise WrapperError("No commands specified for wrapping")

    if config.runtime not in ("singularity", "docker"):
        raise WrapperError(f"Unsupported runtime: {config.runtime}")

    # Create output directory
    config.output_dir.mkdir(parents=True, exist_ok=True)

    # Generate shim scripts and collect bind-mount / PATH info
    shim_bind_mounts: list[str] = []
    shim_path_dirs: list[str] = []
    use_pbs_env = False
    if config.shims:
        shim_bind_mounts, shim_path_dirs, use_pbs_env = generate_shims(
            config.shims, config.output_dir
        )

    # Load template based on runtime
    template_str = _load_wrapper_template(config.runtime)
    sif_filename = (
        f"{_sanitize_image_name(config.image_ref)}.sif" if config.runtime == "singularity" else None
    )

    # Prepare Jinja2 environment
    env = Environment(
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.from_string(template_str)

    # Generate wrappers
    wrapper_paths = {}
    for command in config.commands:
        context = {
            "image_ref": config.image_ref,
            "command": command,
            "mounts": config.extra_mounts,
            "gpu": config.gpu,
            "sif_filename": sif_filename,
            "image_cache": str(config.image_cache) if config.image_cache else None,
            "env_dir": config.env_dir,
            "shim_bind_mounts": shim_bind_mounts,
            "shim_path_dirs": shim_path_dirs,
            "use_pbs_env": use_pbs_env,
            "pbs_container_env": PBS_CONTAINER_ENV,
        }

        wrapper_content = template.render(**context)
        wrapper_path = config.output_dir / command
        wrapper_path.write_text(wrapper_content, encoding="utf-8")
        wrapper_path.chmod(0o755)  # Make executable

        wrapper_paths[command] = wrapper_path

    return wrapper_paths


def expand_mount_paths(mount_specs: list[str]) -> list[str]:
    """
    Expand environment variables in mount path specifications.

    Note: Expansion happens at wrapper generation time for validation,
    but wrappers will re-expand at runtime for dynamic values like $PWD.
    """
    expanded = []
    for spec in mount_specs:
        # Keep the original spec with env vars for runtime expansion
        # But validate that required env vars exist now
        if "$" in spec:
            # Extract env var names for validation
            env_vars = re.findall(r"\$(\w+)", spec)
            for var in env_vars:
                if var not in os.environ and var not in ("PWD", "HOME", "USER"):
                    # Warn but don't fail - these might be set at runtime
                    pass
        expanded.append(spec)
    return expanded
