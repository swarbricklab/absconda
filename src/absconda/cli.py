"""Command-line entry point built with Typer.

Typer builds on Click but lets us describe commands using regular Python functions
and type hints. Each function decorated with ``@app.command()`` becomes a CLI
subcommand, and type annotations automatically map to option parsing and help text.
"""

# ruff: noqa: B008

from __future__ import annotations

import datetime
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, cast

import click
import typer
from rich.console import Console

from . import __version__, remote
from .environment import (
    EnvironmentLoadError,
    LoadReport,
    load_environment,
    load_requirements,
    load_tarball,
)
from .policy import PolicyLoadError, PolicyResolution, load_policy
from .templates import (
    DEFAULT_BUILDER_IMAGE,
    DEFAULT_RUNTIME_IMAGE,
    RenderConfig,
    TemplateRenderError,
    render_dockerfile,
)

console = Console()
app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    help="Generate container assets from Conda environments.",
)

remote_app = typer.Typer(help="Provision and manage remote build servers.")
app.add_typer(remote_app, name="remote")

config_app = typer.Typer(help="Get and set absconda configuration options.")
app.add_typer(config_app, name="config")

REMOTE_CONFIG_OPTION = typer.Option(
    None,
    "--config",
    "-c",
    help="Path to a remote builder config file (defaults to auto-discovery).",
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        is_flag=True,
        is_eager=True,
        help="Show the Absconda version and exit.",
    ),
    policy: Optional[Path] = typer.Option(
        None,
        "--policy",
        help="Path to a custom absconda-policy.yaml file (auto-discovered if omitted).",
    ),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Policy profile name to activate (falls back to policy default).",
    ),
) -> None:
    """Callback executed before any subcommand.

    We keep the callback lightweight for now, but it is a convenient place to load
    global config or establish logging later on.
    """

    if version:
        console.print(f"Absconda {__version__}")
        raise typer.Exit()

    # ``ctx.obj`` can carry objects (config, clients) to subcommands later.
    state: Dict[str, Any] = ctx.ensure_object(dict)

    try:
        policy_resolution = load_policy(policy, profile)
    except PolicyLoadError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    state["policy"] = policy_resolution
    _print_warning_messages(policy_resolution.warnings)


def _load_with_feedback(
    file: Optional[Path],
    tarball: Optional[Path],
    requirements: Optional[Path],
    snapshot: Optional[Path],
) -> LoadReport:
    """Helper that loads env files, tarballs, or requirements and renders Typer-friendly errors."""

    # Count how many input types were provided
    inputs_provided = sum(
        [
            file is not None,
            tarball is not None,
            requirements is not None,
        ]
    )

    if inputs_provided > 1:
        console.print(
            "[bold yellow]warning[/bold yellow]: Multiple input types provided. "
            "Only one of --file, --tarball, or --requirements should be specified."
        )

    if inputs_provided == 0:
        console.print(
            "[red]Error:[/red] One of --file, --tarball, or --requirements must be provided."
        )
        raise typer.Exit(code=1)

    try:
        if requirements is not None:
            return load_requirements(requirements, snapshot_path=snapshot)
        elif tarball is not None:
            return load_tarball(tarball, file, snapshot)
        else:
            # file is guaranteed to not be None here
            return load_environment(file, snapshot)  # type: ignore[arg-type]
    except EnvironmentLoadError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _read_optional_text_file(path: Optional[Path], label: str) -> Optional[str]:
    if path is None:
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]Error:[/red] Unable to read {label} '{path}': {exc}")
        raise typer.Exit(code=1) from exc

    stripped = content.strip()
    if not stripped:
        console.print(f"[bold yellow]warning[/bold yellow]: {label} '{path}' was empty.")
    return stripped


def _print_warnings(report: LoadReport) -> None:
    _print_warning_messages(report.warnings)


def _print_warning_messages(messages: Iterable[str]) -> None:
    for warning in messages:
        console.print(f"[bold yellow]warning[/bold yellow]: {warning}")


def _enforce_policy_constraints(report: LoadReport) -> None:
    profile = _active_policy().profile
    allowed = profile.allowed_channels

    # Skip channel validation for tarball-only mode (no env YAML)
    if report.env is None:
        return

    if allowed:
        disallowed = [channel for channel in report.env.channels if channel not in allowed]
        if disallowed:
            allowed_list = ", ".join(allowed)
            bad_list = ", ".join(disallowed)
            console.print(
                "[red]Policy violation:[/red] channels "
                f"[{bad_list}] are not permitted by profile '{profile.name}'.\n"
                f"Allowed channels: {allowed_list}"
            )
            raise typer.Exit(code=1)


@dataclass
class RemoteBuildOptions:
    builder: str
    config_path: Optional[Path]
    wait_seconds: int
    shutdown_after: bool


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "env"


def _date_stamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")


def _resolve_repository(repository: Optional[str], env_name: str) -> str:
    """Resolve repository using config defaults if not explicitly provided."""
    if repository is not None:
        return repository

    # Load config to get registry and organization
    from . import config as cfg

    absconda_config = cfg.load_config()

    if absconda_config.organization is None:
        console.print(
            "[red]Error:[/red] No repository specified and no default organization configured.\n"
            "Either:\n"
            "  1. Use --repository flag\n"
            "  2. Set 'organization' in ~/.config/absconda/config.yaml "
            "or /etc/xdg/absconda/config.yaml"
        )
        raise typer.Exit(code=1)

    slug = _slugify(env_name)
    return f"{absconda_config.registry}/{absconda_config.organization}/{slug}"


def _image_reference(repository: str, env_name: str, tag: Optional[str]) -> str:
    final_tag = tag or _date_stamp()
    return f"{repository}:{final_tag}"


def _image_name_tag(image_ref: str) -> str:
    """Extract name/tag from an image reference.

    ghcr.io/swarbricklab/csvkit:20260410 -> csvkit/20260410
    myenv:latest -> myenv/latest
    """
    # Strip registry prefix (anything before the last path component with a /)
    without_registry = re.sub(r"^[^/]+\.(io|com|org)/", "", image_ref)
    # Strip org prefix if present (e.g., swarbricklab/csvkit -> csvkit)
    parts = without_registry.rsplit("/", 1)
    name_and_tag = parts[-1]
    # Split name:tag -> name/tag
    if ":" in name_and_tag:
        name, tag = name_and_tag.split(":", 1)
        return f"{name}/{tag}"
    return name_and_tag


def _resolve_remote_options(
    remote_builder: Optional[str],
    remote_config: Optional[Path],
    remote_wait: int,
    remote_off: bool,
) -> Optional[RemoteBuildOptions]:
    if remote_builder is None:
        from .config import load_config

        config = load_config()
        if config.default_remote_builder:
            remote_builder = config.default_remote_builder
    if remote_builder is None:
        if remote_off:
            console.print(
                "[bold yellow]warning[/bold yellow]: --remote-off ignored because "
                "no remote builder was specified."
            )
        return None

    if remote_wait <= 0:
        console.print("[red]Error:[/red] --remote-wait must be a positive integer.")
        raise typer.Exit(code=1)

    return RemoteBuildOptions(
        builder=remote_builder,
        config_path=remote_config,
        wait_seconds=remote_wait,
        shutdown_after=remote_off,
    )


def _run_command(command: list[str], *, cwd: Optional[Path] = None) -> None:
    try:
        subprocess.run(command, check=True, cwd=str(cwd) if cwd else None)
    except FileNotFoundError as exc:  # pragma: no cover - depends on host setup
        console.print(f"[red]Error:[/red] Command '{command[0]}' not found: {exc}")
        raise typer.Exit(code=1) from exc
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Command failed:[/red] {' '.join(command)}")
        raise typer.Exit(code=exc.returncode) from exc


def _build_image_local(
    report: Optional[LoadReport],
    *,
    repository: str,
    tag: Optional[str],
    env_name: str,
    template: Optional[Path],
    builder_override: Optional[str],
    runtime_override: Optional[str],
    multi_stage_override: Optional[bool],
    context: Path,
    push: bool,
    renv_lock: Optional[str],
    dockerfile_override: Optional[str] = None,
    build_args: Optional[list[str]] = None,
) -> str:
    if dockerfile_override is not None:
        dockerfile = dockerfile_override
    elif report is not None:
        dockerfile = _render_dockerfile(
            report,
            template=template,
            builder_override=builder_override,
            runtime_override=runtime_override,
            multi_stage_override=multi_stage_override,
            renv_lock=renv_lock,
        )
    else:
        raise RuntimeError("Either dockerfile_override or report must be provided")

    image_ref = _image_reference(repository, env_name, tag)
    context_path = context.resolve()

    with tempfile.TemporaryDirectory(prefix="absconda-build-") as temp_dir:
        dockerfile_path = Path(temp_dir) / "Dockerfile"
        dockerfile_path.write_text(dockerfile, encoding="utf-8")

        # If using tarball, copy it into the build context
        if report is not None and report.tarball:
            import shutil

            tarball_dest = Path(temp_dir) / "conda-env.tar.gz"
            shutil.copy2(report.tarball.path, tarball_dest)

        # If using requirements, copy it into the build context
        if report is not None and report.requirements:
            import shutil

            requirements_dest = Path(temp_dir) / "requirements.txt"
            shutil.copy2(report.requirements.path, requirements_dest)

        # For tarball/requirements modes, use temp_dir as build context (self-contained)
        # Otherwise use the specified context directory (for env.yaml and other files)
        has_tarball_or_requirements = report is not None and (report.tarball or report.requirements)
        build_context = temp_dir if has_tarball_or_requirements else str(context_path)

        # Construct docker build command
        docker_cmd = [
            "docker",
            "build",
            "-t",
            image_ref,
        ]
        # Add build args if provided
        if build_args:
            for arg in build_args:
                docker_cmd.extend(["--build-arg", arg])
        docker_cmd.extend(["-f", str(dockerfile_path), build_context])

        _run_command(docker_cmd)

        if push:
            _run_command(["docker", "push", image_ref])

    return image_ref


def _build_image_remote(
    report: Optional[LoadReport],
    *,
    repository: str,
    tag: Optional[str],
    env_name: str,
    template: Optional[Path],
    builder_override: Optional[str],
    runtime_override: Optional[str],
    multi_stage_override: Optional[bool],
    context: Path,
    push: bool,
    renv_lock: Optional[str],
    remote_options: RemoteBuildOptions,
    dockerfile_override: Optional[str] = None,
    build_args: Optional[list[str]] = None,
) -> str:
    if dockerfile_override is not None:
        dockerfile = dockerfile_override
    elif report is not None:
        dockerfile = _render_dockerfile(
            report,
            template=template,
            builder_override=builder_override,
            runtime_override=runtime_override,
            multi_stage_override=multi_stage_override,
            renv_lock=renv_lock,
        )
    else:
        raise RuntimeError("Either dockerfile_override or report must be provided")

    image_ref = _image_reference(repository, env_name, tag)
    policy_resolution = _active_policy()
    manifest = {
        "absconda_version": __version__,
        "env_name": env_name,
        "image": image_ref,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + "Z",
        "policy_profile": policy_resolution.profile.name,
        "channels": report.env.channels if report is not None and report.env else [],
        "remote_builder": remote_options.builder,
        "push": push,
        "tarball_mode": report.tarball is not None if report else False,
        "requirements_mode": report.requirements is not None if report else False,
    }

    try:
        definition = remote.load_remote_definition(
            remote_options.builder, config_path=remote_options.config_path
        )
        remote.build_remote_image(
            definition=definition,
            dockerfile=dockerfile,
            context_path=context,
            image_ref=image_ref,
            push=push,
            wait_seconds=remote_options.wait_seconds,
            shutdown_after=remote_options.shutdown_after,
            manifest=manifest,
            console=console,
            build_args=build_args,
        )
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except remote.RemoteError as exc:
        console.print(f"[red]Remote build failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    return image_ref


def _active_policy() -> PolicyResolution:
    ctx = click.get_current_context()
    state = ctx.ensure_object(dict)
    policy = state.get("policy")
    if policy is None:
        raise RuntimeError("Policy state was not initialized. This is a bug; please report it.")
    return cast(PolicyResolution, policy)


def _print_policy_banner() -> None:
    policy_resolution = _active_policy()
    source_path = policy_resolution.source_path
    source = str(source_path) if source_path else "built-in defaults"
    console.print(
        f"Using policy profile [cyan]{policy_resolution.profile.name}[/cyan] from {source}."
    )


def _render_dockerfile(
    report: LoadReport,
    *,
    template: Optional[Path],
    builder_override: Optional[str],
    runtime_override: Optional[str],
    multi_stage_override: Optional[bool],
    renv_lock: Optional[str] = None,
) -> str:
    policy_resolution = _active_policy()
    profile = policy_resolution.profile

    # For requirements mode, use Python base images instead of conda images
    if report.requirements:
        builder_base = builder_override or "python:3.11-slim"
        runtime_default = "python:3.11-slim"
        runtime_base = runtime_override or runtime_default
    else:
        builder_base = builder_override or profile.builder_base or DEFAULT_BUILDER_IMAGE
        runtime_default = profile.runtime_base or DEFAULT_RUNTIME_IMAGE
        runtime_base = runtime_override or runtime_default

    multi_stage_default = profile.multi_stage if profile.multi_stage is not None else True
    multi_stage = multi_stage_override if multi_stage_override is not None else multi_stage_default

    config = RenderConfig(
        env=report.env,
        tarball_filename="conda-env.tar.gz" if report.tarball else None,
        requirements_filename="requirements.txt" if report.requirements else None,
        env_name=report.env_name,
        profile=profile,
        multi_stage=multi_stage,
        builder_base=builder_base,
        runtime_base=runtime_base,
        renv_lock=renv_lock,
    )

    try:
        return render_dockerfile(config, template_path=template)
    except TemplateRenderError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


# ---------------------------------------------------------------------------
# ─── generate ──────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@app.command()
def generate(
    ctx: typer.Context,
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        exists=True,
        readable=True,
        help="Path to environment.yaml file.",
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        exists=True,
        readable=True,
        help="Path to a conda-pack tarball (.tar.gz) for offline/reproducible builds.",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        exists=True,
        readable=True,
        help="Path to a pip requirements.txt file.",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        readable=True,
        help="Path to a snapshot YAML (optional lock file) for reproducible rebuilds.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        exists=True,
        readable=True,
        help="Path to a custom Jinja2 Dockerfile template.",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the multi-stage builder base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage / --single-stage",
        help="Force multi-stage or single-stage mode.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Write the generated Dockerfile to this path instead of stdout.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        exists=True,
        readable=True,
        help="Path to an renv.lock file to embed in the container.",
    ),
) -> None:
    """Generate a Dockerfile from a Conda environment file."""
    _print_policy_banner()

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _print_warnings(report)
    _enforce_policy_constraints(report)

    renv_lock_content = _read_optional_text_file(renv_lock, "renv.lock")

    text = _render_dockerfile(
        report,
        template=template,
        builder_override=builder_base,
        runtime_override=runtime_base,
        multi_stage_override=multi_stage,
        renv_lock=renv_lock_content,
    )

    if output is not None:
        output.write_text(text, encoding="utf-8")
        console.print(f"Wrote Dockerfile to {output}")
    else:
        console.print(text, highlight=False)


# ---------------------------------------------------------------------------
# ─── build ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@app.command()
def build(
    ctx: typer.Context,
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        exists=True,
        readable=True,
        help="Path to environment.yaml file.",
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        exists=True,
        readable=True,
        help="Use a conda-pack tarball (.tar.gz) for offline/reproducible builds.",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        exists=True,
        readable=True,
        help="Path to a pip requirements.txt file.",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        readable=True,
        help="Path to a snapshot YAML (optional lock file) for reproducible rebuilds.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        exists=True,
        readable=True,
        help="Path to a custom Jinja2 Dockerfile template.",
    ),
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Full repository reference, e.g. ghcr.io/org/name.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Image tag (default: YYYYMMDD date stamp).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the multi-stage builder base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage / --single-stage",
        help="Force multi-stage or single-stage mode.",
    ),
    context: Path = typer.Option(
        ".",
        "--context",
        "-C",
        help="Docker build context directory.",
    ),
    push: bool = typer.Option(
        False,
        "--push",
        help="Push the built image to the registry.",
    ),
    remote_builder: Optional[str] = typer.Option(
        None,
        "--remote-builder",
        help="Name of the remote builder defined in absconda-remote.yaml.",
    ),
    remote_config: Optional[Path] = typer.Option(
        None,
        "--remote-config",
        help="Path to absconda-remote.yaml (auto-discovered if omitted).",
    ),
    remote_wait: int = typer.Option(
        900,
        "--remote-wait",
        help="Max seconds to wait for remote builder lock.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Shut down the remote builder after this build.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        exists=True,
        readable=True,
        help="Path to an renv.lock file to embed in the container.",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        "-d",
        exists=True,
        readable=True,
        help="Path to a pre-written Dockerfile (skips generation).",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Pass a build-time variable (KEY=VALUE). May be specified multiple times.",
    ),
) -> None:
    """Build a container image from a Conda environment file."""
    _print_policy_banner()

    dockerfile_override: Optional[str] = None
    report: Optional[LoadReport] = None
    if dockerfile is not None:
        dockerfile_override = dockerfile.read_text(encoding="utf-8")
        if repository is None:
            console.print(
                "[red]Error:[/red] --repository is required when using --dockerfile "
                "(no environment file to derive a name from)."
            )
            raise typer.Exit(code=1)
        env_name = repository.rsplit("/", 1)[-1].split(":")[0]
    else:
        report = _load_with_feedback(file, tarball, requirements, snapshot)
        _print_warnings(report)
        _enforce_policy_constraints(report)
        env_name = report.env_name

    resolved_repository = _resolve_repository(repository, env_name)
    renv_lock_content = _read_optional_text_file(renv_lock, "renv.lock")
    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    if remote_opts:
        image_ref = _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=push,
            renv_lock=renv_lock_content,
            remote_options=remote_opts,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )
    else:
        image_ref = _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=push,
            renv_lock=renv_lock_content,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )

    console.print(f"[green]Built image:[/green] {image_ref}")


# ---------------------------------------------------------------------------
# ─── publish ────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@app.command()
def publish(
    ctx: typer.Context,
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        exists=True,
        readable=True,
        help="Path to environment.yaml file.",
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        exists=True,
        readable=True,
        help="Use a conda-pack tarball (.tar.gz) for offline/reproducible builds.",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        exists=True,
        readable=True,
        help="Path to a pip requirements.txt file.",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        readable=True,
        help="Path to a snapshot YAML (optional lock file) for reproducible rebuilds.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        exists=True,
        readable=True,
        help="Path to a custom Jinja2 Dockerfile template.",
    ),
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Full repository reference, e.g. ghcr.io/org/name.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Image tag (default: YYYYMMDD date stamp).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the multi-stage builder base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage / --single-stage",
        help="Force multi-stage or single-stage mode.",
    ),
    context: Path = typer.Option(
        ".",
        "--context",
        "-C",
        help="Docker build context directory.",
    ),
    remote_builder: Optional[str] = typer.Option(
        None,
        "--remote-builder",
        help="Name of the remote builder defined in absconda-remote.yaml.",
    ),
    remote_config: Optional[Path] = typer.Option(
        None,
        "--remote-config",
        help="Path to absconda-remote.yaml (auto-discovered if omitted).",
    ),
    remote_wait: int = typer.Option(
        900,
        "--remote-wait",
        help="Max seconds to wait for remote builder lock.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Shut down the remote builder after this build.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        exists=True,
        readable=True,
        help="Path to an renv.lock file to embed in the container.",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        "-d",
        exists=True,
        readable=True,
        help="Path to a pre-written Dockerfile (skips generation).",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Pass a build-time variable (KEY=VALUE). May be specified multiple times.",
    ),
) -> None:
    """Build and push a container image (convenience wrapper around build --push)."""
    _print_policy_banner()

    dockerfile_override: Optional[str] = None
    report: Optional[LoadReport] = None
    if dockerfile is not None:
        dockerfile_override = dockerfile.read_text(encoding="utf-8")
        if repository is None:
            console.print(
                "[red]Error:[/red] --repository is required when using --dockerfile "
                "(no environment file to derive a name from)."
            )
            raise typer.Exit(code=1)
        env_name = repository.rsplit("/", 1)[-1].split(":")[0]
    else:
        report = _load_with_feedback(file, tarball, requirements, snapshot)
        _print_warnings(report)
        _enforce_policy_constraints(report)
        env_name = report.env_name

    resolved_repository = _resolve_repository(repository, env_name)
    renv_lock_content = _read_optional_text_file(renv_lock, "renv.lock")
    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    if remote_opts:
        image_ref = _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_content,
            remote_options=remote_opts,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )
    else:
        image_ref = _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_content,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )

    console.print(f"[green]Published image:[/green] {image_ref}")


# ---------------------------------------------------------------------------
# ─── deploy ─────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@app.command()
def deploy(
    ctx: typer.Context,
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        exists=True,
        readable=True,
        help="Path to environment.yaml file.",
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        exists=True,
        readable=True,
        help="Use a conda-pack tarball (.tar.gz) for offline/reproducible builds.",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        exists=True,
        readable=True,
        help="Path to a pip requirements.txt file.",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        "-s",
        exists=True,
        readable=True,
        help="Path to a snapshot YAML (optional lock file) for reproducible rebuilds.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        exists=True,
        readable=True,
        help="Path to a custom Jinja2 Dockerfile template.",
    ),
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Full repository reference, e.g. ghcr.io/org/name.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Image tag (default: YYYYMMDD date stamp).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the multi-stage builder base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage / --single-stage",
        help="Force multi-stage or single-stage mode.",
    ),
    context: Path = typer.Option(
        ".",
        "--context",
        "-C",
        help="Docker build context directory.",
    ),
    remote_builder: Optional[str] = typer.Option(
        None,
        "--remote-builder",
        help="Name of the remote builder defined in absconda-remote.yaml.",
    ),
    remote_config: Optional[Path] = typer.Option(
        None,
        "--remote-config",
        help="Path to absconda-remote.yaml (auto-discovered if omitted).",
    ),
    remote_wait: int = typer.Option(
        900,
        "--remote-wait",
        help="Max seconds to wait for remote builder lock.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Shut down the remote builder after this build.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        exists=True,
        readable=True,
        help="Path to an renv.lock file to embed in the container.",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        "-d",
        exists=True,
        readable=True,
        help="Path to a pre-written Dockerfile (skips generation).",
    ),
    singularity_dir: Path = typer.Option(
        ...,
        "--singularity-dir",
        help="Directory to store the SIF image.",
    ),
    commands: Optional[str] = typer.Option(
        None,
        "--commands",
        help="Comma-separated list of commands to generate wrappers for (auto-detected if omitted).",
    ),
    shims: Optional[str] = typer.Option(
        None,
        "--shims",
        help="Comma-separated shim modes, e.g. pbs,singularity.",
    ),
    modulefile_dir: Path = typer.Option(
        ...,
        "--modulefile-dir",
        help="Where to install the generated modulefile.",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Pass a build-time variable (KEY=VALUE). May be specified multiple times.",
    ),
) -> None:
    """Build, push, pull-to-SIF, wrap, and install module - all-in-one deploy step."""

    _print_policy_banner()

    dockerfile_override: Optional[str] = None
    report: Optional[LoadReport] = None
    if dockerfile is not None:
        dockerfile_override = dockerfile.read_text(encoding="utf-8")
        if repository is None:
            console.print(
                "[red]Error:[/red] --repository is required when using --dockerfile "
                "(no environment file to derive a name from)."
            )
            raise typer.Exit(code=1)
        env_name = repository.rsplit("/", 1)[-1].split(":")[0]
    else:
        report = _load_with_feedback(file, tarball, requirements, snapshot)
        _print_warnings(report)
        _enforce_policy_constraints(report)
        env_name = report.env_name

    resolved_repository = _resolve_repository(repository, env_name)
    renv_lock_content = _read_optional_text_file(renv_lock, "renv.lock")
    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    # ---------- STEP 1: build + push ----------
    console.print("[bold]Step 1/4:[/bold] Building and pushing container image...")
    if remote_opts:
        image_ref = _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_content,
            remote_options=remote_opts,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )
    else:
        image_ref = _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_content,
            dockerfile_override=dockerfile_override,
            build_args=build_arg,
        )
    console.print(f"  [green]Published image:[/green] {image_ref}")

    # ---------- STEP 2: pull as SIF ----------
    console.print("[bold]Step 2/4:[/bold] Pulling image as Singularity SIF...")
    singularity_dir.mkdir(parents=True, exist_ok=True)
    sif_file = singularity_dir / f"{env_name}.sif"
    sif_uri = f"docker://{image_ref}"
    _run_command(["singularity", "pull", "--force", str(sif_file), sif_uri])
    console.print(f"  [green]SIF image:[/green] {sif_file}")

    # ---------- STEP 3: wrappers ----------
    console.print("[bold]Step 3/4:[/bold] Generating command wrappers...")
    from .wrappers import WrapperConfig, generate_wrappers

    shim_list: Optional[list[str]] = None
    if shims:
        shim_list = [s.strip() for s in shims.split(",") if s.strip()]

    wrapper_config = WrapperConfig(
        sif_path=sif_file,
        commands=commands.split(",") if commands else None,
        shims=shim_list,
    )
    wrappers = generate_wrappers(wrapper_config)
    for cmd_name, wrapper_path in sorted(wrappers.items()):
        console.print(f"  wrapper: [cyan]{cmd_name}[/cyan] -> {wrapper_path}")

    # ---------- STEP 4: modulefile ----------
    console.print("[bold]Step 4/4:[/bold] Installing modulefile...")
    from .modules import ModuleConfig, generate_modulefile

    module_config = ModuleConfig(
        env_name=env_name,
        version=tag or _date_stamp(),
        sif_path=sif_file,
        wrapper_dir=wrapper_config.output_dir,
    )
    module_path = generate_modulefile(module_config, modulefile_dir)
    console.print(f"  [green]Modulefile:[/green] {module_path}")

    console.print(f"\n[bold green]Deploy complete![/bold green] {image_ref}")


# ---------------------------------------------------------------------------
# ─── remote subcommands ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@remote_app.command("list")
def remote_list(
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """List all configured remote builders."""
    try:
        path, names = remote.list_remote_builders(config)
    except remote.RemoteConfigError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"Configured builders in [cyan]{path}[/cyan]:")
    for name in names:
        console.print(f"  - {name}")


@remote_app.command("status")
def remote_status(
    name: str = typer.Argument(help="Name of the remote builder to inspect."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """Check whether a remote builder is reachable and idle."""
    try:
        defn = remote.load_remote_definition(name, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"Checking status of [cyan]{name}[/cyan]...")
    st = remote.check_remote_status(defn)

    console.print(f"  Reachable: {'yes' if st.reachable else 'no'}")
    if st.ssh_error:
        console.print(f"  SSH error: {st.ssh_error}")
    console.print(f"  Busy:      {'yes' if st.busy else 'no'}")
    if st.lock_owner:
        console.print(f"  Lock owner: {st.lock_owner}")
    if st.health_ok is not None:
        console.print(f"  Health:    {'ok' if st.health_ok else 'FAIL'}")
    if st.health_error:
        console.print(f"  Health error: {st.health_error}")


@remote_app.command("provision")
def remote_provision(
    name: str = typer.Argument(help="Name of the remote builder."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """Provision infrastructure for a remote builder."""
    try:
        defn = remote.load_remote_definition(name, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        remote.provision_remote_builder(defn, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except remote.RemoteError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Provisioned builder '{name}'[/green]")


@remote_app.command("start")
def remote_start(
    name: str = typer.Argument(help="Name of the remote builder."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """Start a remote builder VM."""
    try:
        defn = remote.load_remote_definition(name, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        remote.start_remote_builder(defn, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except remote.RemoteError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Started builder '{name}'[/green]")


@remote_app.command("stop")
def remote_stop(
    name: str = typer.Argument(help="Name of the remote builder."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """Stop a remote builder VM."""
    try:
        defn = remote.load_remote_definition(name, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        remote.stop_remote_builder(defn, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except remote.RemoteError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Stopped builder '{name}'[/green]")


@remote_app.command("init")
def remote_init(
    name: str = typer.Argument(help="Name of the remote builder to initialise."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """First-time SSH setup for a remote builder (e.g. OS Login key sync)."""
    try:
        defn = remote.load_remote_definition(name, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    console.print(f"Initialising SSH for remote builder [cyan]{name}[/cyan]...")

    # Use gcloud to push SSH keys and verify connectivity
    meta = defn.metadata
    project = meta.get("project")
    zone = meta.get("zone")
    if not project or not zone:
        console.print(
            "[red]Error:[/red] Builder metadata must include 'project' and 'zone' for init."
        )
        raise typer.Exit(code=1)

    ssh_target = defn.ssh_target.split("@")[-1]  # extract hostname
    _run_command([
        "gcloud", "compute", "ssh",
        ssh_target,
        f"--project={project}",
        f"--zone={zone}",
        "--tunnel-through-iap",
        "--command=echo SSH connection successful",
    ])

    console.print(f"[green]SSH initialised for builder '{name}'[/green]")


# ---------------------------------------------------------------------------
# ─── config subcommands ────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@config_app.command("show")
def config_show() -> None:
    """Display the resolved absconda configuration."""
    from . import config as cfg

    absconda_config = cfg.load_config()
    console.print("[bold]Absconda Configuration[/bold]")
    console.print(f"  Registry:     {absconda_config.registry}")
    console.print(f"  Organization: {absconda_config.organization or '(not set)'}")
    console.print(f"  Default remote builder: {absconda_config.default_remote_builder or '(not set)'}")

    config_dirs = cfg.get_config_dirs()
    console.print("\n[bold]Config search paths:[/bold]")
    for d in config_dirs:
        exists = d.exists()
        marker = "[green]✓[/green]" if exists else "[dim]✗[/dim]"
        console.print(f"  {marker} {d}")


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Configuration key (e.g. 'organization', 'registry')."),
    value: str = typer.Argument(help="Value to set."),
) -> None:
    """Set an absconda configuration value in ~/.config/absconda/config.yaml."""
    from . import config as cfg

    allowed_keys = {"registry", "organization", "default_remote_builder"}
    if key not in allowed_keys:
        console.print(
            f"[red]Error:[/red] Unknown config key '{key}'. "
            f"Allowed keys: {', '.join(sorted(allowed_keys))}"
        )
        raise typer.Exit(code=1)

    cfg.set_config_value(key, value)
    console.print(f"Set [cyan]{key}[/cyan] = [green]{value}[/green]")


@config_app.command("path")
def config_path() -> None:
    """Show the path to the user configuration file."""
    from . import config as cfg

    path = cfg.get_user_config_path()
    console.print(str(path))


# ---------------------------------------------------------------------------
# ─── singularity subcommand ────────────────────────────────────────────────
# ---------------------------------------------------------------------------


@app.command()
def pull(
    repository: str = typer.Option(
        ...,
        "--repository",
        help="Full image reference to pull, e.g. ghcr.io/org/name:tag.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="Path for the SIF output file.",
    ),
) -> None:
    """Pull a container image and convert to Singularity SIF."""
    sif_uri = f"docker://{repository}"
    output.parent.mkdir(parents=True, exist_ok=True)
    _run_command(["singularity", "pull", "--force", str(output), sif_uri])
    console.print(f"[green]Pulled SIF:[/green] {output}")
