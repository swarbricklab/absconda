"""Policy configuration loader and helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

PolicyHook = Callable[..., Any]


class PolicyLoadError(Exception):
    """Raised when a policy file cannot be parsed or validated."""


@dataclass(slots=True)
class PolicyHooks:
    """Resolved hook callables (if available)."""

    before_render: Optional[PolicyHook] = None
    after_validate: Optional[PolicyHook] = None
    on_build_finished: Optional[PolicyHook] = None


@dataclass(slots=True)
class PolicyProfile:
    """Configuration for a single policy profile."""

    name: str
    builder_base: Optional[str]
    runtime_base: Optional[str]
    multi_stage: Optional[bool]
    env_prefix: Optional[str]
    allowed_channels: List[str]
    required_labels: Dict[str, str]
    default_fragments: List[str]
    raw: dict[str, Any] = field(repr=False)


@dataclass(slots=True)
class PolicyResolution:
    """Result of loading a policy config and selecting a profile."""

    source_path: Optional[Path]
    profile: PolicyProfile
    hooks: PolicyHooks
    warnings: List[str] = field(default_factory=list)


_DEFAULT_PROFILE = PolicyProfile(
    name="default",
    builder_base=None,
    runtime_base=None,
    multi_stage=None,
    env_prefix="/opt/conda/envs",
    allowed_channels=[],
    required_labels={},
    default_fragments=[],
    raw={},
)


def _discover_policy_path(explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        candidate = explicit.expanduser()
        if not candidate.exists():
            raise PolicyLoadError(f"Policy file '{candidate}' was not found.")
        return candidate

    candidates: List[Path] = []

    cwd = Path.cwd()
    for current in [cwd, *cwd.parents]:
        candidate = current / "absconda-policy.yaml"
        if candidate not in candidates:
            candidates.append(candidate)

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        config_home = Path(xdg_config_home).expanduser()
    else:
        config_home = Path.home() / ".config"

    home_candidate = config_home / "absconda" / "absconda-policy.yaml"
    candidates.append(home_candidate)

    xdg_dirs_raw = os.environ.get("XDG_CONFIG_DIRS")
    if xdg_dirs_raw:
        config_dirs = [Path(part).expanduser() for part in xdg_dirs_raw.split(":") if part]
    else:
        config_dirs = [Path("/etc/xdg")]

    for base in config_dirs:
        candidate = base / "absconda" / "absconda-policy.yaml"
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _read_policy_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:  # pragma: no cover - caught earlier
        raise PolicyLoadError(f"Policy file '{path}' not found.") from exc
    except yaml.YAMLError as exc:
        raise PolicyLoadError(f"Failed to parse policy YAML '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise PolicyLoadError("Policy file must contain a mapping at the root level.")

    return data


def _parse_profiles(data: dict[str, Any]) -> dict[str, PolicyProfile]:
    profiles_raw = data.get("profiles")
    if not isinstance(profiles_raw, dict) or not profiles_raw:
        return {"default": _DEFAULT_PROFILE}

    profiles: dict[str, PolicyProfile] = {}
    for name, value in profiles_raw.items():
        if not isinstance(value, dict):
            raise PolicyLoadError(f"Profile '{name}' must be a mapping of settings.")
        profile = PolicyProfile(
            name=name,
            builder_base=_maybe_str(value.get("builder_base")),
            runtime_base=_maybe_str(value.get("runtime_base")),
            multi_stage=_maybe_bool(value.get("multi_stage")),
            env_prefix=_maybe_str(value.get("env_prefix")) or _DEFAULT_PROFILE.env_prefix,
            allowed_channels=_string_list(
                value.get("allowed_channels", []),
                f"profiles.{name}.allowed_channels",
            ),
            required_labels=_string_dict(
                value.get("required_labels", {}),
                f"profiles.{name}.required_labels",
            ),
            default_fragments=_string_list(
                value.get("default_fragments", []),
                f"profiles.{name}.default_fragments",
            ),
            raw=value,
        )
        profiles[name] = profile

    return profiles


def _maybe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise PolicyLoadError("Expected value to be a string.")


def _maybe_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise PolicyLoadError("Expected value to be a boolean.")


def _string_list(value: Any, path: str) -> List[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    if value == []:
        return []
    raise PolicyLoadError(f"{path} must be a list of strings.")


def _string_dict(value: Any, path: str) -> Dict[str, str]:
    if isinstance(value, dict) and all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        return dict(value)
    if value == {}:
        return {}
    raise PolicyLoadError(f"{path} must be a mapping of string keys to string values.")


def _parse_hooks(data: dict[str, Any], warnings: List[str]) -> PolicyHooks:
    hooks_raw = data.get("hooks")
    if not hooks_raw:
        return PolicyHooks()
    if not isinstance(hooks_raw, dict):
        raise PolicyLoadError("'hooks' section must be a mapping.")

    module_name = hooks_raw.get("module")
    if not isinstance(module_name, str):
        raise PolicyLoadError("'hooks.module' must be a string module path.")

    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise PolicyLoadError(f"Failed to import hook module '{module_name}': {exc}") from exc

    resolved = PolicyHooks()
    for attr in ("before_render", "after_validate", "on_build_finished"):
        func_name = hooks_raw.get(attr)
        if func_name is None:
            continue
        if not isinstance(func_name, str):
            raise PolicyLoadError(f"hooks.{attr} must be a string of the function name.")
        func = getattr(module, func_name, None)
        if func is None:
            warnings.append(f"Hook '{func_name}' was not found in module '{module_name}'.")
            continue
        setattr(resolved, attr, func)

    return resolved


def load_policy(policy_path: Optional[Path], profile_name: Optional[str]) -> PolicyResolution:
    """Load the policy config, returning the active profile and hooks."""

    warnings: list[str] = []
    resolved_path = _discover_policy_path(policy_path)

    if resolved_path is None:
        # No policy found; use built-in defaults silently.
        return PolicyResolution(
            source_path=None,
            profile=_DEFAULT_PROFILE,
            hooks=PolicyHooks(),
            warnings=[],
        )

    data = _read_policy_yaml(resolved_path)
    profiles = _parse_profiles(data)

    default_profile = data.get("default_profile")
    if default_profile is not None and not isinstance(default_profile, str):
        raise PolicyLoadError("'default_profile' must be a string.")

    selected_name = profile_name or default_profile or next(iter(profiles))
    if selected_name not in profiles:
        raise PolicyLoadError(
            f"Profile '{selected_name}' was not found in policy file '{resolved_path}'."
        )

    hooks = _parse_hooks(data, warnings)

    return PolicyResolution(
        source_path=resolved_path,
        profile=profiles[selected_name],
        hooks=hooks,
        warnings=warnings,
    )
