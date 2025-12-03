"""Environment loading and validation helpers."""

from __future__ import annotations

import tarfile
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
class TarballSpec:
    """Representation of a pre-packed conda environment tarball."""

    name: str
    path: Path
    extracted_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RequirementsSpec:
    """Representation of a pip requirements.txt file."""

    name: str
    path: Path
    requirements: List[str] = field(default_factory=list)


@dataclass(slots=True)
class Snapshot:
    """Basic snapshot metadata."""

    raw: dict[str, Any]
    source_path: Path


@dataclass(slots=True)
class LoadReport:
    """Result of loading an environment and optional snapshot."""

    env: Optional[EnvSpec]
    tarball: Optional[TarballSpec]
    requirements: Optional[RequirementsSpec]
    snapshot: Optional[Snapshot]
    warnings: List[str] = field(default_factory=list)
    
    @property
    def env_name(self) -> str:
        """Get the environment name from env, tarball, or requirements."""
        if self.requirements:
            return self.requirements.name
        if self.tarball:
            return self.tarball.name
        if self.env:
            return self.env.name
        return "absconda"


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


def _validate_tarball(tarball_path: Path) -> None:
    """Validate that the tarball appears to be a conda-pack tarball."""
    if not tarball_path.exists():
        raise EnvironmentLoadError(f"Tarball '{tarball_path}' was not found.")
    
    if not tarball_path.is_file():
        raise EnvironmentLoadError(f"Tarball path '{tarball_path}' is not a file.")
    
    # Check if it's a valid tar file
    if not tarfile.is_tarfile(tarball_path):
        raise EnvironmentLoadError(f"File '{tarball_path}' is not a valid tar archive.")
    
    # Check for conda-meta directory which indicates a conda environment
    try:
        with tarfile.open(tarball_path, "r:*") as tar:
            members = [m.name for m in tar.getmembers()]
            has_conda_meta = any("conda-meta/" in m for m in members)
            
            if not has_conda_meta:
                raise EnvironmentLoadError(
                    f"Tarball '{tarball_path}' does not appear to be a conda-pack tarball "
                    "(missing conda-meta directory)."
                )
    except (tarfile.TarError, OSError) as exc:
        raise EnvironmentLoadError(f"Failed to read tarball '{tarball_path}': {exc}") from exc


def _load_tarball(tarball_path: Path, env_name: Optional[str] = None) -> TarballSpec:
    """Load a conda-pack tarball and extract basic metadata."""
    _validate_tarball(tarball_path)
    
    # Use provided name or derive from filename
    if env_name is None:
        env_name = tarball_path.stem
        # Remove .tar from .tar.gz
        if env_name.endswith(".tar"):
            env_name = env_name[:-4]
    
    metadata: dict[str, Any] = {}
    
    # Try to extract environment info from conda-meta if possible
    try:
        with tarfile.open(tarball_path, "r:*") as tar:
            # Look for history file or other metadata
            for member in tar.getmembers():
                if "conda-meta/history" in member.name:
                    metadata["has_history"] = True
                    break
    except (tarfile.TarError, OSError):  # pragma: no cover - best effort metadata extraction
        pass
    
    return TarballSpec(name=env_name, path=tarball_path, extracted_metadata=metadata)


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

    return LoadReport(env=env_spec, tarball=None, requirements=None, snapshot=snapshot, warnings=warnings)


def load_tarball(
    tarball_path: Path, 
    env_path: Optional[Path] = None,
    snapshot_path: Optional[Path] = None
) -> LoadReport:
    """Load a pre-packed conda tarball, with optional YAML for metadata.
    
    Args:
        tarball_path: Path to the conda-pack tarball
        env_path: Optional environment YAML for metadata (name, labels)
        snapshot_path: Optional snapshot for documentation
        
    Returns:
        LoadReport with tarball spec and optional env metadata
    """
    
    warnings: list[str] = []
    
    # Load tarball (required)
    tarball_spec = _load_tarball(tarball_path)
    
    # Optionally load env YAML for metadata
    env_spec: Optional[EnvSpec] = None
    if env_path is not None and env_path.exists():
        try:
            env_data = _read_yaml(env_path)
            env_spec = _normalize_env(env_data, env_path)
            # Use env name if provided
            tarball_spec = TarballSpec(
                name=env_spec.name,
                path=tarball_spec.path,
                extracted_metadata=tarball_spec.extracted_metadata
            )
        except EnvironmentLoadError as exc:
            warnings.append(f"Could not load environment file for metadata: {exc}")
    
    # Optionally load snapshot
    snapshot: Optional[Snapshot] = None
    if snapshot_path is not None:
        if not snapshot_path.exists():
            warnings.append(f"Snapshot '{snapshot_path}' was not found; continuing without it.")
        else:
            try:
                snapshot = _load_snapshot(snapshot_path)
            except EnvironmentLoadError as exc:
                warnings.append(str(exc))
    
    return LoadReport(env=env_spec, tarball=tarball_spec, requirements=None, snapshot=snapshot, warnings=warnings)


def _load_requirements(requirements_path: Path, env_name: Optional[str] = None) -> RequirementsSpec:
    """Load a pip requirements.txt file."""
    if not requirements_path.exists():
        raise EnvironmentLoadError(f"Requirements file '{requirements_path}' not found.")
    
    if not requirements_path.is_file():
        raise EnvironmentLoadError(f"Requirements path '{requirements_path}' is not a file.")
    
    try:
        content = requirements_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EnvironmentLoadError(f"Failed to read '{requirements_path}': {exc}") from exc
    
    # Parse requirements (basic - just non-empty, non-comment lines)
    requirements = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            requirements.append(stripped)
    
    # Use provided name or derive from filename
    if env_name is None:
        env_name = requirements_path.stem
        if env_name == "requirements":
            env_name = "python-app"
    
    return RequirementsSpec(name=env_name, path=requirements_path, requirements=requirements)


def load_requirements(
    requirements_path: Path,
    env_name: Optional[str] = None,
    snapshot_path: Optional[Path] = None,
) -> LoadReport:
    """Load a pip requirements.txt file.
    
    Args:
        requirements_path: Path to the requirements.txt file
        env_name: Optional name for the environment (derived from filename if not provided)
        snapshot_path: Optional snapshot for documentation
        
    Returns:
        LoadReport with requirements spec
    """
    
    warnings: list[str] = []
    
    # Load requirements (required)
    requirements_spec = _load_requirements(requirements_path, env_name)
    
    # Optionally load snapshot
    snapshot: Optional[Snapshot] = None
    if snapshot_path is not None:
        if not snapshot_path.exists():
            warnings.append(f"Snapshot '{snapshot_path}' was not found; continuing without it.")
        else:
            try:
                snapshot = _load_snapshot(snapshot_path)
            except EnvironmentLoadError as exc:
                warnings.append(str(exc))
    
    if not requirements_spec.requirements:
        warnings.append(
            "Requirements file is empty; resulting image will contain only the base Python image."
        )
    
    return LoadReport(
        env=None, 
        tarball=None, 
        requirements=requirements_spec, 
        snapshot=snapshot, 
        warnings=warnings
    )
