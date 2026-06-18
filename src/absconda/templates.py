"""Dockerfile templating utilities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional, Tuple

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from jinja2 import TemplateError as JinjaTemplateError

from .environment import EnvSpec
from .policy import PolicyProfile

DEFAULT_BUILDER_IMAGE = "mambaorg/micromamba:1.5.5"
DEFAULT_RUNTIME_IMAGE = "debian:bookworm-slim"
DEFAULT_RENV_TARGET = "/opt/absconda/renv"

_TEMPLATE_PACKAGE = "absconda._templates"
_DEFAULT_TEMPLATE_NAME = "default/main.j2"


class TemplateRenderError(Exception):
    """Raised when a template cannot be loaded or rendered."""


@dataclass(slots=True)
class RenderConfig:
    """Configuration inputs required to render a Dockerfile."""

    profile: PolicyProfile
    multi_stage: bool
    builder_base: str
    runtime_base: str
    env: Optional[EnvSpec] = None
    base_image: Optional[str] = None
    tarball_filename: Optional[str] = None
    requirements_filename: Optional[str] = None
    env_name: Optional[str] = None
    template_path: Optional[Path] = None
    renv_lock: Optional[str] = None
    renv_target: str = DEFAULT_RENV_TARGET


def render_dockerfile(config: RenderConfig) -> str:
    """Render a Dockerfile for the provided environment and policy profile."""

    # Determine environment name
    if config.env_name:
        env_name = config.env_name
    elif config.env:
        env_name = config.env.name
    else:
        env_name = "absconda"

    env_prefix = config.profile.env_prefix or "/opt/conda/envs"
    env_dir = _join_path(env_prefix, env_name)
    env_variables = config.env.raw.get("variables") if config.env and config.env.raw else None
    export_block = _build_export_block(env_dir, env_name, env_variables)

    # Handle tarball and requirements modes differently
    pip_requirements: Optional[str] = None
    if config.tarball_filename or config.requirements_filename:
        env_yaml = ""  # No env.yaml in tarball or requirements mode
        conda_env_yaml = ""
    elif config.env:
        env_yaml = _env_yaml(config.env)
        # Split pip deps out of the conda solve so they are installed in a
        # second, constrained step (see _split_conda_pip).
        conda_env_yaml, pip_requirements = _split_conda_pip(config.env)
    else:
        env_yaml = ""
        conda_env_yaml = ""

    context = _build_context(
        config,
        env_prefix=env_prefix,
        env_dir=env_dir,
        export_block=export_block,
        env_yaml=env_yaml,
        conda_env_yaml=conda_env_yaml,
        pip_requirements=pip_requirements,
        env_name=env_name,
    )

    try:
        if config.template_path is None:
            rendered = _render_builtin_template(context)
        else:
            rendered = _render_custom_template(config.template_path, context)
    except (OSError, JinjaTemplateError) as exc:  # pragma: no cover - defensive
        raise TemplateRenderError(str(exc)) from exc

    return rendered.rstrip() + "\n"


def _render_builtin_template(context: Dict[str, Any]) -> str:
    resource = resources.files(_TEMPLATE_PACKAGE)
    with resources.as_file(resource) as template_root:
        loader = FileSystemLoader(str(template_root))
        env = Environment(
            loader=loader,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        template = env.get_template(_DEFAULT_TEMPLATE_NAME)
        return template.render(**context)


def _render_custom_template(template_path: Path, context: Dict[str, Any]) -> str:
    source = template_path.read_text(encoding="utf-8")
    env = Environment(
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    template = env.from_string(source)
    return template.render(**context)


def _env_yaml(env: EnvSpec) -> str:
    data = env.raw or {
        "name": env.name,
        "channels": env.channels,
        "dependencies": env.dependencies,
    }
    return yaml.safe_dump(data, sort_keys=False).strip()


def _dep_name(spec: str) -> str:
    """Best-effort package name from a conda dependency spec.

    Handles channel prefixes ('conda-forge::numpy') and version specifiers
    ('numpy>=1.24', 'python=3.12'). Used only to detect whether 'pip' is
    already present in the conda dependencies.
    """

    without_channel = spec.split("::")[-1]
    return re.split(r"[\s=<>!~\[\(]", without_channel, maxsplit=1)[0].strip().lower()


def _split_conda_pip(env: EnvSpec) -> Tuple[str, Optional[str]]:
    """Split an env into a conda-only YAML and a pip requirements block.

    pip dependencies are pulled out of the env file so they are NOT installed by
    the conda solver's implicit `pip install`, which has no knowledge of conda's
    version pins and will happily upgrade a conda-installed package past them.
    They are installed instead in a second step constrained to the versions
    conda resolved (see the install fragments), so a conflict fails the build
    rather than silently clobbering a pin.

    Returns ``(conda_only_yaml, pip_requirements_text)`` where the second item is
    ``None`` when the environment has no pip section.
    """

    raw = (
        dict(env.raw)
        if env.raw
        else {
            "name": env.name,
            "channels": list(env.channels),
            "dependencies": list(env.dependencies),
        }
    )
    dependencies = raw.get("dependencies") or []

    conda_deps: list[Any] = []
    pip_deps: list[str] = []
    for dep in dependencies:
        if isinstance(dep, dict) and "pip" in dep:
            pip_list = dep.get("pip") or []
            pip_deps.extend(str(item) for item in pip_list)
        else:
            conda_deps.append(dep)

    # `variables:` is realized as image ENV (see _build_export_block), not fed to
    # the conda solver, so drop it from the conda env file.
    conda_raw = {key: value for key, value in raw.items() if key != "variables"}

    if not pip_deps:
        # No pip section: conda owns the whole environment, nothing to split.
        conda_raw["dependencies"] = conda_deps
        return yaml.safe_dump(conda_raw, sort_keys=False).strip(), None

    # Ensure pip is available in the conda env so the second phase can run.
    conda_names = {_dep_name(dep) for dep in conda_deps if isinstance(dep, str)}
    if "pip" not in conda_names:
        conda_deps.append("pip")

    conda_raw["dependencies"] = conda_deps
    return yaml.safe_dump(conda_raw, sort_keys=False).strip(), "\n".join(pip_deps)


def _join_path(prefix: str, name: str) -> str:
    return str(PurePosixPath(prefix) / name)


def _build_export_block(env_dir: str, env_name: str, variables: Any = None) -> list[str]:
    lines = [
        f"ENV CONDA_DEFAULT_ENV={env_name}",
        f"ENV CONDA_PREFIX={env_dir}",
        f"ENV PATH={env_dir}/bin:/opt/conda/bin:${{PATH}}",
    ]
    # Render a conda `variables:` section into image ENV lines. The image runs
    # binaries directly (no `conda activate`), so conda's own variable handling
    # never fires; baking them as ENV is what makes them visible at runtime.
    lines.extend(_env_var_lines(variables))
    return lines


def _env_var_lines(variables: Any) -> list[str]:
    if not isinstance(variables, dict):
        return []
    return [f"ENV {key}={json.dumps(str(value))}" for key, value in variables.items()]


def _needs_git(env: Optional[EnvSpec]) -> bool:
    """Check whether any pip dependency uses a git+ URL."""
    if env is None:
        return False
    return any(dep.startswith("pip::git+") for dep in env.dependencies)


def _build_context(
    config: RenderConfig,
    *,
    env_prefix: str,
    env_dir: str,
    export_block: list[str],
    env_yaml: str,
    conda_env_yaml: str,
    pip_requirements: Optional[str],
    env_name: str,
) -> Dict[str, Any]:
    return {
        "env": config.env,
        "env_name": env_name,
        "env_yaml": env_yaml,
        "conda_env_yaml": conda_env_yaml,
        "pip_requirements": pip_requirements or "",
        "has_pip": bool(pip_requirements),
        "channel_flags": _channel_flags(config.env.channels) if config.env else "",
        "env_prefix": env_prefix,
        "env_dir": env_dir,
        "builder_base": config.builder_base,
        "runtime_base": config.runtime_base,
        "base_image": config.base_image or "",
        "conda_on_base": config.base_image is not None,
        "multi_stage": config.multi_stage,
        "export_block": export_block,
        "runtime_command": '["python"]',
        "renv_lock": config.renv_lock,
        "renv_enabled": config.renv_lock is not None,
        "renv_target_path": config.renv_target,
        "labels": _label_pairs(config.profile.required_labels),
        "tarball_mode": config.tarball_filename is not None,
        "tarball_filename": config.tarball_filename or "",
        "requirements_mode": config.requirements_filename is not None,
        "requirements_filename": config.requirements_filename or "",
        "needs_git": _needs_git(config.env),
    }


def _channel_flags(channels: list[str]) -> str:
    return " ".join(f"--channel {channel}" for channel in channels)


def _label_pairs(labels: dict[str, str]) -> list[str]:
    pairs: list[str] = []
    for key, value in labels.items():
        encoded = json.dumps(value)
        pairs.append(f"{key}={encoded}")
    return pairs
