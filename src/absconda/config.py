"""Configuration file discovery and loading using XDG Base Directory specification.

This module implements a hierarchical config system:
1. System-wide: /etc/xdg/absconda/config.yaml (or XDG_CONFIG_DIRS)
2. User-level: ~/.config/absconda/config.yaml (or XDG_CONFIG_HOME)
3. Environment variables override config file settings
4. Command-line arguments override everything

Config files support:
- Remote builder definitions
- Default GCP project/region/zone
- Policy profiles
- Template paths
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class ConfigError(Exception):
    """Raised when configuration loading fails."""


@dataclass
class AbscondaConfig:
    """Merged configuration from all sources."""

    # Remote builder definitions
    remote_builders: Dict[str, Dict[str, Any]]

    # GCP settings (can be overridden by env vars)
    gcp_project: Optional[str] = None
    gcp_region: Optional[str] = None
    gcp_zone: Optional[str] = None

    # Policy settings
    default_policy: Optional[str] = None
    default_profile: Optional[str] = None

    # Template paths
    template_dir: Optional[Path] = None

    # Container registry settings
    registry: str = "ghcr.io"
    organization: Optional[str] = None

    # Wrapper generation settings
    wrapper_default_runtime: str = "singularity"
    wrapper_default_output_dir: Optional[Path] = None
    wrapper_image_cache: Optional[Path] = None
    wrapper_default_mounts: Optional[List[str]] = None
    wrapper_env_passthrough: Optional[List[str]] = None
    wrapper_env_filter: Optional[List[str]] = None

    # Module generation settings
    module_default_output_dir: Optional[Path] = None
    module_format: str = "tcl"

    def __post_init__(self):
        """Initialize default lists."""
        if self.wrapper_default_mounts is None:
            self.wrapper_default_mounts = ["$HOME", "$PWD"]
        if self.wrapper_env_passthrough is None:
            self.wrapper_env_passthrough = ["USER", "HOME", "LANG", "TZ"]
        if self.wrapper_env_filter is None:
            self.wrapper_env_filter = ["PATH", "LD_LIBRARY_PATH", "PYTHONPATH"]

    @classmethod
    def empty(cls) -> AbscondaConfig:
        """Create an empty configuration."""
        return cls(remote_builders={})


def get_config_dirs() -> List[Path]:
    """Return config directories in search order (lowest to highest priority).

    Returns:
        List of directories to search for config files, from lowest to highest priority.
        System-wide configs are searched first, user configs last.
    """
    dirs: List[Path] = []

    # System-wide config directories from XDG_CONFIG_DIRS
    xdg_config_dirs = os.environ.get("XDG_CONFIG_DIRS", "/etc/xdg")
    for dir_str in xdg_config_dirs.split(":"):
        if dir_str:
            dirs.append(Path(dir_str) / "absconda")

    # User config directory from XDG_CONFIG_HOME
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        dirs.append(Path(xdg_config_home) / "absconda")
    else:
        dirs.append(Path.home() / ".config" / "absconda")

    return dirs


def _load_yaml_file(path: Path) -> Dict[str, Any]:
    """Load and parse a YAML config file."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ConfigError(f"Config file {path} must contain a YAML mapping")
            return data
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read {path}: {exc}") from exc


def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two config dictionaries, with override taking precedence."""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def load_config() -> AbscondaConfig:
    """Load configuration from XDG config directories.

    Searches for config.yaml in:
    1. XDG_CONFIG_DIRS directories (e.g., /etc/xdg/absconda/)
    2. XDG_CONFIG_HOME or ~/.config/absconda/

    Later configs override earlier ones. Environment variables override file settings.

    Returns:
        Merged AbscondaConfig from all sources.
    """
    merged_data: Dict[str, Any] = {}

    # Load and merge configs from all directories
    for config_dir in get_config_dirs():
        config_file = config_dir / "config.yaml"
        if config_file.exists():
            try:
                file_data = _load_yaml_file(config_file)
                merged_data = _merge_configs(merged_data, file_data)
            except ConfigError:
                # Silently skip invalid configs (could add logging here)
                pass

    # Extract remote builders
    remote_builders = merged_data.get("remote_builders", {})
    if not isinstance(remote_builders, dict):
        remote_builders = {}

    # Extract GCP settings (environment variables take precedence)
    gcp_project = os.environ.get("GCP_PROJECT") or merged_data.get("gcp_project")
    gcp_region = os.environ.get("GCP_REGION") or merged_data.get("gcp_region")
    gcp_zone = os.environ.get("GCP_ZONE") or merged_data.get("gcp_zone")

    # Extract policy settings
    default_policy = merged_data.get("default_policy")
    default_profile = merged_data.get("default_profile")

    # Extract template dir
    template_dir_str = merged_data.get("template_dir")
    template_dir = Path(template_dir_str) if template_dir_str else None

    # Extract registry settings
    registry = merged_data.get("registry", "ghcr.io")
    organization = merged_data.get("organization")

    # Extract wrapper settings
    wrappers_config = merged_data.get("wrappers", {})
    wrapper_default_runtime = wrappers_config.get("default_runtime", "singularity")
    wrapper_default_output_dir_str = wrappers_config.get("default_output_dir")
    wrapper_default_output_dir = (
        Path(wrapper_default_output_dir_str).expanduser()
        if wrapper_default_output_dir_str
        else None
    )
    wrapper_image_cache_str = wrappers_config.get("image_cache")
    wrapper_image_cache = (
        Path(wrapper_image_cache_str).expanduser() if wrapper_image_cache_str else None
    )
    wrapper_default_mounts = wrappers_config.get("default_mounts")
    wrapper_env_passthrough = wrappers_config.get("env_passthrough")
    wrapper_env_filter = wrappers_config.get("env_filter")

    # Extract module settings
    modules_config = merged_data.get("modules", {})
    module_default_output_dir_str = modules_config.get("default_output_dir")
    module_default_output_dir = (
        Path(module_default_output_dir_str).expanduser() if module_default_output_dir_str else None
    )
    module_format = modules_config.get("format", "tcl")

    return AbscondaConfig(
        remote_builders=remote_builders,
        gcp_project=gcp_project,
        gcp_region=gcp_region,
        gcp_zone=gcp_zone,
        default_policy=default_policy,
        default_profile=default_profile,
        template_dir=template_dir,
        registry=registry,
        organization=organization,
        wrapper_default_runtime=wrapper_default_runtime,
        wrapper_default_output_dir=wrapper_default_output_dir,
        wrapper_image_cache=wrapper_image_cache,
        wrapper_default_mounts=wrapper_default_mounts,
        wrapper_env_passthrough=wrapper_env_passthrough,
        wrapper_env_filter=wrapper_env_filter,
        module_default_output_dir=module_default_output_dir,
        module_format=module_format,
    )


def find_remote_builder_config(builder_name: str) -> Optional[Dict[str, Any]]:
    """Find a specific remote builder definition in the config hierarchy.

    Args:
        builder_name: Name of the remote builder to find.

    Returns:
        Builder config dict if found, None otherwise.
    """
    config = load_config()
    return config.remote_builders.get(builder_name)
