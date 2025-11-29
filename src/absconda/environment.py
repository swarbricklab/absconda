"""Environment loading and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import yaml


class EnvironmentLoadError(Exception):
    """Raised when an environment file or snapshot cannot be parsed."""


@dataclass(slots=True)
class EnvSpec:
    """Normalized representation of a Conda environment file."""

    name: str
    channels: List[str]
    dependencies: List[str]
    raw: dict[str, Any] = field(repr=False)


@dataclass(slots=True)
class Snapshot:
    """Basic snapshot metadata."""

    raw: dict[str, Any]
    source_path: Path


@dataclass(slots=True)
class LoadReport:
    """Result of loading an environment and optional snapshot."""

    env: EnvSpec
    snapshot: Optional[Snapshot]
    warnings: List[str] = field(default_factory=list)


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:  # pragma: no cover - handled earlier
        raise EnvironmentLoadError(f"Environment file '{path}' not found.") from exc
    except yaml.YAMLError as exc:
        raise EnvironmentLoadError(f"Failed to parse YAML from '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise EnvironmentLoadError(
            f"Expected '{path}' to contain a mapping, got {type(data).__name__}."
        )

    return data


def _normalize_env(data: dict[str, Any], path: Path) -> EnvSpec:
    name = data.get("name") or "absconda"
    channels = data.get("channels") or ["conda-forge"]
    dependencies = data.get("dependencies") or []

    if not isinstance(channels, list) or not all(isinstance(item, str) for item in channels):
        raise EnvironmentLoadError(f"'channels' in '{path}' must be a list of strings.")

    if not isinstance(dependencies, list):
        raise EnvironmentLoadError(f"'dependencies' in '{path}' must be a list.")

    normalized_dependencies: list[str] = []
    for dep in dependencies:
        if isinstance(dep, str):
            normalized_dependencies.append(dep)
        elif isinstance(dep, dict) and "pip" in dep:
            # Flatten pip dependencies into "pip:<pkg>" placeholders for now.
            pip_deps = dep.get("pip")
            if isinstance(pip_deps, list) and all(isinstance(item, str) for item in pip_deps):
                normalized_dependencies.extend([f"pip::{item}" for item in pip_deps])
            else:
                raise EnvironmentLoadError(
                    "Pip dependencies must be a list of strings when specified as a mapping."
                )
        else:
            raise EnvironmentLoadError(
                "Dependencies must be strings or pip mappings (e.g., {'pip': ['pkg']} )."
            )

    return EnvSpec(
        name=name,
        channels=[str(ch) for ch in channels],
        dependencies=normalized_dependencies,
        raw=data,
    )


def _load_snapshot(path: Path) -> Snapshot:
    data = _read_yaml(path)
    return Snapshot(raw=data, source_path=path)


def load_environment(env_path: Path, snapshot_path: Optional[Path] = None) -> LoadReport:
    """Load an environment file and optional snapshot, returning warnings if applicable."""

    if not env_path.exists():
        raise EnvironmentLoadError(f"Environment file '{env_path}' was not found.")

    env_data = _read_yaml(env_path)
    env_spec = _normalize_env(env_data, env_path)

    snapshot: Optional[Snapshot] = None
    warnings: list[str] = []

    if snapshot_path is not None:
        if not snapshot_path.exists():
            warnings.append(f"Snapshot '{snapshot_path}' was not found; continuing without it.")
        else:
            try:
                snapshot = _load_snapshot(snapshot_path)
            except EnvironmentLoadError as exc:
                warnings.append(str(exc))

    if not env_spec.dependencies:
        warnings.append(
            "Environment has no dependencies; resulting image will contain only the base image."
        )

    return LoadReport(env=env_spec, snapshot=snapshot, warnings=warnings)
