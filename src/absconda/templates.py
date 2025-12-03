"""Dockerfile templating utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

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
    export_block = _build_export_block(env_dir, env_name)

    # Handle tarball and requirements modes differently
    if config.tarball_filename or config.requirements_filename:
        env_yaml = ""  # No env.yaml in tarball or requirements mode
    elif config.env:
        env_yaml = _env_yaml(config.env)
    else:
        env_yaml = ""

    context = _build_context(
        config,
        env_prefix=env_prefix,
        env_dir=env_dir,
        export_block=export_block,
        env_yaml=env_yaml,
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


def _join_path(prefix: str, name: str) -> str:
    return str(PurePosixPath(prefix) / name)


def _build_export_block(env_dir: str, env_name: str) -> list[str]:
    return [
        f"ENV CONDA_DEFAULT_ENV={env_name}",
        f"ENV CONDA_PREFIX={env_dir}",
        f"ENV PATH={env_dir}/bin:/opt/conda/bin:${{PATH}}",
    ]


def _build_context(
    config: RenderConfig,
    *,
    env_prefix: str,
    env_dir: str,
    export_block: list[str],
    env_yaml: str,
    env_name: str,
) -> Dict[str, Any]:
    return {
        "env": config.env,
        "env_name": env_name,
        "env_yaml": env_yaml,
        "channel_flags": _channel_flags(config.env.channels) if config.env else "",
        "env_prefix": env_prefix,
        "env_dir": env_dir,
        "builder_base": config.builder_base,
        "runtime_base": config.runtime_base,
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
    }


def _channel_flags(channels: list[str]) -> str:
    return " ".join(f"--channel {channel}" for channel in channels)


def _label_pairs(labels: dict[str, str]) -> list[str]:
    pairs: list[str] = []
    for key, value in labels.items():
        encoded = json.dumps(value)
        pairs.append(f"{key}={encoded}")
    return pairs
