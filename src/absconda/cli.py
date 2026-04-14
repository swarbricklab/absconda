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
        "generated_at": (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds") + "Z"
        ),
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
        template_path=template,
        renv_lock=renv_lock,
    )

    try:
        return render_dockerfile(config)
    except TemplateRenderError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def generate(
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help=(
            "Path to the Conda environment file "
            "(required unless --tarball or --requirements is specified)."
        ),
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        help="Path to a pre-packed conda tarball (alternative to --file).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to a pip requirements.txt file (alternative to --file).",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional path to write the rendered Dockerfile (stdout if omitted).",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        help="Path to a custom template file (defaults to Absconda's built-in template).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the builder stage base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime stage base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage/--single-stage",
        help="Force enabling or disabling multi-stage builds (defaults to policy profile).",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        help="Path to an renv.lock file to restore alongside the Conda environment.",
    ),
) -> None:
    """Generate a Dockerfile from the provided environment file, tarball, or requirements."""

    _print_policy_banner()

    # Provide default for file if no input is specified
    if file is None and tarball is None and requirements is None:
        file = Path("env.yaml")

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _print_warnings(report)
    _enforce_policy_constraints(report)
    renv_lock_text = _read_optional_text_file(renv_lock, "renv lock")
    dockerfile = _render_dockerfile(
        report,
        template=template,
        builder_override=builder_base,
        runtime_override=runtime_base,
        multi_stage_override=multi_stage,
        renv_lock=renv_lock_text,
    )

    if output is not None:
        output.write_text(dockerfile, encoding="utf-8")
        console.print(f"[green]Dockerfile written to[/green] {output}.")
    else:
        console.print(dockerfile, highlight=False, markup=False, soft_wrap=False)


@app.command()
def validate(
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help=(
            "Environment file to validate "
            "(required unless --tarball or --requirements is specified)."
        ),
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        help="Path to a pre-packed conda tarball (alternative to --file).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to a pip requirements.txt file (alternative to --file).",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
) -> None:
    """Validate the environment and snapshot files without generating output."""

    _print_policy_banner()

    # Provide default for file if no input is specified
    if file is None and tarball is None and requirements is None:
        file = Path("env.yaml")

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _enforce_policy_constraints(report)

    if report.tarball:
        console.print(f"Tarball [green]{report.env_name}[/green] is valid.")
    else:
        console.print(
            f"Environment [green]{report.env_name}[/green] is valid with "
            f"{len(report.env.dependencies) if report.env else 0} dependency entries."  # type: ignore[union-attr]
        )
    _print_warnings(report)


@app.command()
def build(
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Target OCI repository. Defaults to '<registry>/<org>/<env-name>' from config.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Optional image tag. Defaults to 'YYYYMMDD'.",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help=(
            "Path to the Conda environment file "
            "(required unless --tarball or --requirements is specified)."
        ),
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        help="Path to a pre-packed conda tarball (alternative to --file).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to a pip requirements.txt file (alternative to --file).",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        help="Path to a custom template file (defaults to Absconda's built-in template).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the builder stage base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime stage base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage/--single-stage",
        help="Force enabling or disabling multi-stage builds (defaults to policy profile).",
    ),
    context: Path = typer.Option(
        Path("."),
        "--context",
        help="Docker build context directory.",
    ),
    push: bool = typer.Option(False, "--push", help="Push the image after a successful build."),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        help="Path to an renv.lock file to restore alongside the Conda environment.",
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
        help="Seconds to wait for a busy remote builder before failing.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Stop the remote builder after the run (requires stop_command).",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        help="Path to a pre-existing Dockerfile to use (skips generation).",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Docker build argument (KEY=VALUE). Can be repeated.",
    ),
) -> None:
    """Render a Dockerfile and build the container image."""

    _print_policy_banner()

    # Handle --dockerfile mode: use pre-existing Dockerfile
    if dockerfile is not None:
        dockerfile_text = _read_optional_text_file(dockerfile, "Dockerfile")
        if dockerfile_text is None:
            console.print(f"[red]Error:[/red] Dockerfile '{dockerfile}' is empty or unreadable.")
            raise typer.Exit(code=1)

        # When using --dockerfile without an env file, repository is required
        if file is None and tarball is None and requirements is None:
            if repository is None:
                console.print(
                    "[red]Error:[/red] --repository is required when using --dockerfile "
                    "without an environment file."
                )
                raise typer.Exit(code=1)
            report = None
            resolved_repository = repository
            env_name = _slugify(Path(repository).name)  # derive from repo name
        else:
            # Load environment for metadata/env_name but use provided dockerfile
            report = _load_with_feedback(file, tarball, requirements, snapshot)
            _print_warnings(report)
            _enforce_policy_constraints(report)
            resolved_repository = _resolve_repository(repository, report.env_name)
            env_name = report.env_name

        remote_opts = _resolve_remote_options(
            remote_builder, remote_config, remote_wait, remote_off
        )

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
                renv_lock=None,
                remote_options=remote_opts,
                dockerfile_override=dockerfile_text,
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
                renv_lock=None,
                dockerfile_override=dockerfile_text,
                build_args=build_arg,
            )

        console.print(f"[green]Image built:[/green] {image_ref}")
        if push:
            console.print(f"[green]Image pushed:[/green] {image_ref}")
        return

    # Standard mode: generate Dockerfile from environment file
    # Provide default for file if neither file, tarball, nor requirements is specified
    if file is None and tarball is None and requirements is None:
        file = Path("env.yaml")

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _print_warnings(report)
    _enforce_policy_constraints(report)
    renv_lock_text = _read_optional_text_file(renv_lock, "renv lock")

    # Resolve repository with defaults from config
    resolved_repository = _resolve_repository(repository, report.env_name)

    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    if remote_opts:
        image_ref = _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=push,
            renv_lock=renv_lock_text,
            remote_options=remote_opts,
            build_args=build_arg,
        )
    else:
        image_ref = _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=push,
            renv_lock=renv_lock_text,
            build_args=build_arg,
        )

    console.print(f"[green]Image built:[/green] {image_ref}")
    if push:
        console.print(f"[green]Image pushed:[/green] {image_ref}")


@app.command()
def publish(
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Target OCI repository. Defaults to '<registry>/<org>/<env-name>' from config.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Optional image tag. Defaults to 'YYYYMMDD'.",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help=(
            "Path to the Conda environment file "
            "(required unless --tarball or --requirements is specified)."
        ),
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        help="Path to a pre-packed conda tarball (alternative to --file).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to a pip requirements.txt file (alternative to --file).",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        help="Path to a custom template file (defaults to Absconda's built-in template).",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the builder stage base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime stage base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage/--single-stage",
        help="Force enabling or disabling multi-stage builds (defaults to policy profile).",
    ),
    context: Path = typer.Option(
        Path("."),
        "--context",
        help="Docker build context directory.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        help="Path to an renv.lock file to restore alongside the Conda environment.",
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
        help="Seconds to wait for a busy remote builder before failing.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Stop the remote builder after the run (requires stop_command).",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        help="Path to a pre-existing Dockerfile to use (skips generation).",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Docker build argument (KEY=VALUE). Can be repeated.",
    ),
) -> None:
    """Build a container image and push it to a registry."""

    _print_policy_banner()

    # Handle --dockerfile mode: use pre-existing Dockerfile
    if dockerfile is not None:
        dockerfile_text = _read_optional_text_file(dockerfile, "Dockerfile")
        if dockerfile_text is None:
            console.print(f"[red]Error:[/red] Dockerfile '{dockerfile}' is empty or unreadable.")
            raise typer.Exit(code=1)

        # When using --dockerfile without an env file, repository is required
        if file is None and tarball is None and requirements is None:
            if repository is None:
                console.print(
                    "[red]Error:[/red] --repository is required when using --dockerfile "
                    "without an environment file."
                )
                raise typer.Exit(code=1)
            report = None
            resolved_repository = repository
            env_name = _slugify(Path(repository).name)  # derive from repo name
        else:
            # Load environment for metadata/env_name but use provided dockerfile
            report = _load_with_feedback(file, tarball, requirements, snapshot)
            _print_warnings(report)
            _enforce_policy_constraints(report)
            resolved_repository = _resolve_repository(repository, report.env_name)
            env_name = report.env_name

        remote_opts = _resolve_remote_options(
            remote_builder, remote_config, remote_wait, remote_off
        )

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
                renv_lock=None,
                remote_options=remote_opts,
                dockerfile_override=dockerfile_text,
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
                renv_lock=None,
                dockerfile_override=dockerfile_text,
                build_args=build_arg,
            )

        console.print(f"[green]Image pushed:[/green] {image_ref}")
        return

    # Standard mode: generate Dockerfile from environment file
    # Provide default for file if neither file, tarball, nor requirements is specified
    if file is None and tarball is None and requirements is None:
        file = Path("env.yaml")

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _print_warnings(report)
    _enforce_policy_constraints(report)
    renv_lock_text = _read_optional_text_file(renv_lock, "renv lock")

    # Resolve repository with defaults from config
    resolved_repository = _resolve_repository(repository, report.env_name)

    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    if remote_opts:
        image_ref = _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_text,
            remote_options=remote_opts,
            build_args=build_arg,
        )
    else:
        image_ref = _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_text,
            build_args=build_arg,
        )

    console.print(f"[green]Image pushed:[/green] {image_ref}")


def _publish_and_get_ref(
    *,
    file: Optional[Path],
    tarball: Optional[Path],
    requirements: Optional[Path],
    snapshot: Optional[Path],
    repository: Optional[str],
    tag: Optional[str],
    template: Optional[Path],
    builder_base: Optional[str],
    runtime_base: Optional[str],
    multi_stage: Optional[bool],
    context: Path,
    renv_lock: Optional[Path],
    remote_builder: Optional[str],
    remote_config: Optional[Path],
    remote_wait: int,
    remote_off: bool,
    dockerfile: Optional[Path],
    build_arg: Optional[list[str]],
) -> str:
    """Build, push, and return the image reference. Shared by publish and deploy."""

    _print_policy_banner()

    # Handle --dockerfile mode
    if dockerfile is not None:
        dockerfile_text = _read_optional_text_file(dockerfile, "Dockerfile")
        if dockerfile_text is None:
            console.print(f"[red]Error:[/red] Dockerfile '{dockerfile}' is empty or unreadable.")
            raise typer.Exit(code=1)

        if file is None and tarball is None and requirements is None:
            if repository is None:
                console.print(
                    "[red]Error:[/red] --repository is required when using --dockerfile "
                    "without an environment file."
                )
                raise typer.Exit(code=1)
            report = None
            resolved_repository = repository
            env_name = _slugify(Path(repository).name)
        else:
            report = _load_with_feedback(file, tarball, requirements, snapshot)
            _print_warnings(report)
            _enforce_policy_constraints(report)
            resolved_repository = _resolve_repository(repository, report.env_name)
            env_name = report.env_name

        remote_opts = _resolve_remote_options(
            remote_builder, remote_config, remote_wait, remote_off
        )

        if remote_opts:
            return _build_image_remote(
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
                renv_lock=None,
                remote_options=remote_opts,
                dockerfile_override=dockerfile_text,
                build_args=build_arg,
            )
        else:
            return _build_image_local(
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
                renv_lock=None,
                dockerfile_override=dockerfile_text,
                build_args=build_arg,
            )

    # Standard mode
    if file is None and tarball is None and requirements is None:
        file = Path("env.yaml")

    report = _load_with_feedback(file, tarball, requirements, snapshot)
    _print_warnings(report)
    _enforce_policy_constraints(report)
    renv_lock_text = _read_optional_text_file(renv_lock, "renv lock")
    resolved_repository = _resolve_repository(repository, report.env_name)

    remote_opts = _resolve_remote_options(remote_builder, remote_config, remote_wait, remote_off)

    if remote_opts:
        return _build_image_remote(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_text,
            remote_options=remote_opts,
            build_args=build_arg,
        )
    else:
        return _build_image_local(
            report,
            repository=resolved_repository,
            tag=tag,
            env_name=report.env_name,
            template=template,
            builder_override=builder_base,
            runtime_override=runtime_base,
            multi_stage_override=multi_stage,
            context=context,
            push=True,
            renv_lock=renv_lock_text,
            build_args=build_arg,
        )


def _deploy_image(
    image_ref: str,
    *,
    commands: Optional[str],
    runtime: str,
    image_cache: Optional[Path],
    output_dir: Optional[Path],
    module_output_dir: Optional[Path],
    extra_mounts: Optional[str],
    env: Optional[str],
    gpu: bool,
    env_dir: Optional[str],
    shims: Optional[str],
    no_wrap: bool,
    no_module: bool,
) -> None:
    """Pull a SIF, generate wrappers and a module file for an image reference."""
    from .config import load_config
    from .wrappers import WrapperConfig, WrapperError, _sanitize_image_name, generate_wrappers

    config = load_config()

    # Resolve runtime
    if runtime == "singularity":
        runtime = config.wrapper_default_runtime or "singularity"

    # Resolve image cache
    if image_cache is None and runtime == "singularity":
        if config.wrapper_image_cache:
            image_cache = config.wrapper_image_cache
        else:
            image_cache = Path.home() / ".local" / "absconda" / "sif-cache"

    name_tag = _image_name_tag(image_ref)

    # --- Step 1: Pull SIF ---
    if runtime == "singularity":
        sif_filename = f"{_sanitize_image_name(image_ref)}.sif"
        image_cache.mkdir(parents=True, exist_ok=True)
        sif_path = image_cache / sif_filename
        console.print(f"Pulling image to [cyan]{sif_path}[/cyan]...")
        _run_command(["singularity", "pull", "--force", str(sif_path), f"docker://{image_ref}"])
        console.print(f"[green]Singularity image pulled to[/green] {sif_path}")

    # Parse command list (needed by both wrappers and module)
    command_list: list[str] = []
    if commands is not None:
        command_list = [cmd.strip() for cmd in commands.split(",") if cmd.strip()]
    elif not no_wrap:
        console.print(
            "[red]Error:[/red] --commands is required for deploy.\n"
            "Specify commands to wrap, e.g., --commands python,pip,jupyter"
        )
        raise typer.Exit(code=1)

    # --- Step 2: Generate wrappers ---
    if not no_wrap:
        # Determine output directory
        if output_dir is None:
            if config.wrapper_default_output_dir:
                output_dir = config.wrapper_default_output_dir / name_tag
            else:
                output_dir = Path.home() / ".local" / "absconda" / "wrappers" / name_tag

        # Parse mounts
        mount_list = []
        if extra_mounts:
            mount_list = [m.strip() for m in extra_mounts.split(",") if m.strip()]
        if config.wrapper_default_mounts:
            mount_list = config.wrapper_default_mounts + mount_list

        # Parse environment variables
        env_list = []
        if env:
            env_list = [e.strip() for e in env.split(",") if e.strip()]
        if config.wrapper_env_passthrough:
            env_list = config.wrapper_env_passthrough + env_list

        # Parse shim groups
        shim_list = []
        if shims:
            shim_list = [s.strip() for s in shims.split(",") if s.strip()]

        wrapper_config = WrapperConfig(
            image_ref=image_ref,
            commands=command_list,
            runtime=runtime,
            output_dir=output_dir,
            image_cache=image_cache,
            extra_mounts=mount_list,
            env_passthrough=env_list,
            gpu=gpu,
            env_dir=env_dir,
            shims=shim_list,
        )

        try:
            wrapper_paths = generate_wrappers(wrapper_config)
            console.print(
                f"[green]✓[/green] Generated {len(wrapper_paths)} wrapper(s) in {output_dir}"
            )
        except WrapperError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from exc

    # --- Step 3: Generate module file ---
    if not no_module:
        from .modules import ModuleConfig, ModuleError, generate_module

        # Determine wrapper dir for module (same as output_dir above)
        wrapper_dir = output_dir
        if wrapper_dir is None:
            if config.wrapper_default_output_dir:
                wrapper_dir = config.wrapper_default_output_dir / name_tag
            else:
                wrapper_dir = Path.home() / ".local" / "absconda" / "wrappers" / name_tag

        if module_output_dir is None:
            if config.module_default_output_dir:
                module_output_dir = config.module_default_output_dir
            else:
                module_output_dir = Path.home() / ".local" / "absconda" / "modulefiles"

        module_name = name_tag
        description = f"{name_tag.split('/')[0]} environment"

        module_config = ModuleConfig(
            name=module_name,
            wrapper_dir=wrapper_dir,
            output_dir=module_output_dir,
            description=description,
            image_ref=image_ref,
            runtime=runtime,
            commands=command_list or None,
        )

        try:
            module_file = generate_module(module_config)
            console.print(f"[green]✓[/green] Generated module file: {module_file}")
        except ModuleError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1) from exc

    # --- Summary ---
    console.print(f"\n[bold green]Deployed:[/bold green] {image_ref}")
    if not no_module and module_output_dir:
        console.print("\n[bold cyan]Usage:[/bold cyan]")
        console.print(f"  module use {module_output_dir}")
        console.print(f"  module load {name_tag}")


@app.command()
def deploy(
    image: Optional[str] = typer.Argument(
        None,
        help="Container image reference (e.g., ghcr.io/org/env:tag). "
        "Omit to build first with --file.",
    ),
    commands: Optional[str] = typer.Option(
        None,
        "--commands",
        help="Comma-separated list of commands to wrap (e.g., python,pip,jupyter).",
    ),
    runtime: str = typer.Option(
        "singularity",
        "--runtime",
        help="Container runtime: 'singularity' or 'docker' (defaults to config).",
    ),
    image_cache: Optional[Path] = typer.Option(
        None,
        "--image-cache",
        help="Directory to pull the SIF image into (defaults to config).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Directory for wrapper scripts (defaults to config).",
    ),
    module_output_dir: Optional[Path] = typer.Option(
        None,
        "--module-dir",
        help="Directory for module files (defaults to config).",
    ),
    extra_mounts: Optional[str] = typer.Option(
        None,
        "--extra-mounts",
        help="Additional volume mounts (comma-separated paths).",
    ),
    env: Optional[str] = typer.Option(
        None,
        "--env",
        help="Additional environment variables to pass through (comma-separated).",
    ),
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Enable GPU support (--nv for Singularity, --gpus all for Docker).",
    ),
    env_dir: Optional[str] = typer.Option(
        None,
        "--env-dir",
        help="Path to conda environment inside container.",
    ),
    no_wrap: bool = typer.Option(
        False,
        "--no-wrap",
        help="Skip wrapper generation.",
    ),
    no_module: bool = typer.Option(
        False,
        "--no-module",
        help="Skip module file generation.",
    ),
    shims: Optional[str] = typer.Option(
        None,
        "--shims",
        help=(
            "Comma-separated shim groups to inject (e.g., pbs,singularity). "
            "Generates host-command pass-through scripts alongside wrappers."
        ),
    ),
    # --- Build flags (used when --file is provided to build first) ---
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a Conda environment file (triggers build + push before deploy).",
    ),
    repository: Optional[str] = typer.Option(
        None,
        "--repository",
        help="Target OCI repository (used with --file).",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Image tag (used with --file). Defaults to 'YYYYMMDD'.",
    ),
    tarball: Optional[Path] = typer.Option(
        None,
        "--tarball",
        "-t",
        help="Path to a pre-packed conda tarball (alternative to --file).",
    ),
    requirements: Optional[Path] = typer.Option(
        None,
        "--requirements",
        "-r",
        help="Path to a pip requirements.txt file (alternative to --file).",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
    template: Optional[Path] = typer.Option(
        None,
        "--template",
        help="Path to a custom template file.",
    ),
    builder_base: Optional[str] = typer.Option(
        None,
        "--builder-base",
        help="Override the builder stage base image.",
    ),
    runtime_base: Optional[str] = typer.Option(
        None,
        "--runtime-base",
        help="Override the runtime stage base image.",
    ),
    multi_stage: Optional[bool] = typer.Option(
        None,
        "--multi-stage/--single-stage",
        help="Force enabling or disabling multi-stage builds.",
    ),
    context: Path = typer.Option(
        Path("."),
        "--context",
        help="Docker build context directory.",
    ),
    renv_lock: Optional[Path] = typer.Option(
        None,
        "--renv-lock",
        help="Path to an renv.lock file.",
    ),
    remote_builder: Optional[str] = typer.Option(
        None,
        "--remote-builder",
        help="Name of the remote builder.",
    ),
    remote_config: Optional[Path] = typer.Option(
        None,
        "--remote-config",
        help="Path to absconda-remote.yaml.",
    ),
    remote_wait: int = typer.Option(
        900,
        "--remote-wait",
        help="Seconds to wait for a busy remote builder.",
    ),
    remote_off: bool = typer.Option(
        False,
        "--remote-off",
        help="Stop the remote builder after the run.",
    ),
    dockerfile: Optional[Path] = typer.Option(
        None,
        "--dockerfile",
        help="Path to a pre-existing Dockerfile (skips generation).",
    ),
    build_arg: Optional[list[str]] = typer.Option(
        None,
        "--build-arg",
        help="Docker build argument (KEY=VALUE). Can be repeated.",
    ),
) -> None:
    """Pull a container image, generate wrappers, and create a module file.

    Can deploy an existing image by reference, or build+push first
    when --file (or --tarball/--requirements) is provided.

    \b
    Examples:
      # Deploy an existing image:
      absconda deploy ghcr.io/org/myenv:20260412

      # Full pipeline (build + push + deploy):
      absconda deploy --file env.yaml --remote-builder gcp-builder --commands python,pip
    """

    has_build_input = file is not None or tarball is not None or requirements is not None

    if image is None and not has_build_input:
        console.print(
            "[red]Error:[/red] Provide an image reference as an argument, "
            "or use --file/--tarball/--requirements to build first."
        )
        raise typer.Exit(code=1)

    # If build inputs are provided, run publish first
    if has_build_input:
        image_ref = _publish_and_get_ref(
            file=file,
            tarball=tarball,
            requirements=requirements,
            snapshot=snapshot,
            repository=repository,
            tag=tag,
            template=template,
            builder_base=builder_base,
            runtime_base=runtime_base,
            multi_stage=multi_stage,
            context=context,
            renv_lock=renv_lock,
            remote_builder=remote_builder,
            remote_config=remote_config,
            remote_wait=remote_wait,
            remote_off=remote_off,
            dockerfile=dockerfile,
            build_arg=build_arg,
        )
        console.print(f"[green]Image pushed:[/green] {image_ref}")
    else:
        image_ref = image

    # Deploy: pull + wrap + module
    _deploy_image(
        image_ref,
        commands=commands,
        runtime=runtime,
        image_cache=image_cache,
        output_dir=output_dir,
        module_output_dir=module_output_dir,
        extra_mounts=extra_mounts,
        env=env,
        gpu=gpu,
        env_dir=env_dir,
        shims=shims,
        no_wrap=no_wrap,
        no_module=no_module,
    )


def _load_remote_definition_or_exit(
    builder: str, config: Optional[Path]
) -> remote.RemoteBuilderDefinition:
    try:
        return remote.load_remote_definition(builder, config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _handle_remote_error(prefix: str, exc: remote.RemoteError) -> None:
    console.print(f"[red]{prefix}[/red] {exc}")
    raise typer.Exit(code=1) from exc


@remote_app.command("list")
def remote_list(
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    try:
        config_path, builders = remote.list_remote_builders(config_path=config)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"Remote builders defined in {config_path}:")
    for name in builders:
        console.print(f" • {name}")


@remote_app.command("provision")
def remote_provision(
    builder: str = typer.Argument(..., help="Remote builder name."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    definition = _load_remote_definition_or_exit(builder, config)
    try:
        remote.provision_remote_builder(definition, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except remote.RemoteError as exc:
        _handle_remote_error("Provisioning failed:", exc)


@remote_app.command("start")
def remote_start(
    builder: str = typer.Argument(..., help="Remote builder name."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    definition = _load_remote_definition_or_exit(builder, config)
    try:
        remote.start_remote_builder(definition, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except remote.RemoteError as exc:
        _handle_remote_error("Start failed:", exc)


@remote_app.command("stop")
def remote_stop(
    builder: str = typer.Argument(..., help="Remote builder name."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    definition = _load_remote_definition_or_exit(builder, config)
    try:
        remote.stop_remote_builder(definition, console)
    except remote.RemoteConfigError as exc:
        console.print(f"[red]Remote config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except remote.RemoteError as exc:
        _handle_remote_error("Stop failed:", exc)


@remote_app.command("status")
def remote_status(
    builder: str = typer.Argument(..., help="Remote builder name."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    definition = _load_remote_definition_or_exit(builder, config)
    status = remote.check_remote_status(definition)

    reachability = "reachable" if status.reachable else "unreachable"
    color = "green" if status.reachable else "red"
    console.print(
        f"Builder [cyan]{status.name}[/cyan] is [{color}]{reachability}[/{color}] via SSH."
    )
    if status.ssh_error:
        console.print(f"  ssh: {status.ssh_error}")
        # Provide helpful hint for GCP OS Login authentication issues
        if "Permission denied (publickey)" in status.ssh_error and "gcp" in status.name.lower():
            host = (
                definition.ssh_target.split("@")[1]
                if "@" in definition.ssh_target
                else definition.ssh_target
            )
            console.print(
                "\n[yellow]💡 Tip:[/yellow] For GCP VMs with OS Login, "
                "you may need to authenticate first:"
            )
            console.print(
                f"   gcloud compute ssh {host} --zone=$GCP_ZONE "
                f"--tunnel-through-iap --project=$GCP_PROJECT"
            )

    if status.busy:
        owner = status.lock_owner or "unknown"
        console.print(f"[yellow]Busy[/yellow]: lock file at {status.lock_path} held by {owner}.")
    else:
        console.print("Lock: free")

    if status.health_ok is True:
        console.print("Health check: [green]passing[/green]")
    elif status.health_ok is False:
        console.print("Health check: [red]failing[/red]")
        if status.health_error:
            console.print(f"  details: {status.health_error}")
    else:
        console.print("Health check: not configured")


@remote_app.command("init")
def remote_init(
    builder: str = typer.Argument(..., help="Remote builder name."),
    config: Optional[Path] = REMOTE_CONFIG_OPTION,
) -> None:
    """Initialize SSH access to a remote builder (GCP OS Login setup)."""
    definition = _load_remote_definition_or_exit(builder, config)

    # Check if this looks like a GCP builder
    metadata = definition.metadata
    if "gcp" not in builder.lower() and "project" not in metadata:
        console.print(
            f"[yellow]Warning:[/yellow] This command is designed for GCP builders with OS Login.\n"
            f"Builder '{builder}' may not need initialization."
        )
        if not typer.confirm("Continue anyway?"):
            raise typer.Exit(0)

    # Extract host and build gcloud command
    host = (
        definition.ssh_target.split("@")[1]
        if "@" in definition.ssh_target
        else definition.ssh_target
    )
    zone = metadata.get("zone", "${GCP_ZONE}")
    project = metadata.get("project", "${GCP_PROJECT}")

    console.print(f"Initializing SSH access to [cyan]{builder}[/cyan]...")
    console.print(
        f"This will run: gcloud compute ssh {host} --zone={zone} "
        f"--tunnel-through-iap --project={project}\n"
    )

    cmd = [
        "gcloud",
        "compute",
        "ssh",
        host,
        f"--zone={zone}",
        "--tunnel-through-iap",
        f"--project={project}",
        "--command=echo 'SSH access configured successfully!'",
    ]

    try:
        subprocess.run(cmd, check=True)
        console.print("\n[green]✓[/green] SSH access initialized successfully!")

        # Try to get OS Login username
        try:
            result = subprocess.run(
                [
                    "gcloud",
                    "compute",
                    "os-login",
                    "describe-profile",
                    "--format=value(posixAccounts[0].username)",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            os_login_user = result.stdout.strip()
            if os_login_user:
                console.print(
                    f"\n[yellow]💡 Note:[/yellow] Your OS Login username is: "
                    f"[cyan]{os_login_user}[/cyan]"
                )
                console.print(
                    "Update the 'user' field in your config if it differs from the current setting."
                )
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # Ignore if we can't determine OS Login username

        console.print(f"\nYou can now use: absconda remote status {builder}")
    except subprocess.CalledProcessError as exc:
        console.print(f"\n[red]✗[/red] Initialization failed with exit code {exc.returncode}")
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        console.print("[red]✗[/red] gcloud command not found. Please install the Google Cloud SDK.")
        raise typer.Exit(1) from exc


@app.command()
def wrap(
    image: str = typer.Option(
        ...,
        "--image",
        help="Container image reference (e.g., ghcr.io/org/env:tag).",
    ),
    commands: str = typer.Option(
        ...,
        "--commands",
        help="Comma-separated list of commands to wrap (e.g., python,pip,jupyter).",
    ),
    runtime: str = typer.Option(
        "singularity",
        "--runtime",
        help="Container runtime: 'singularity' or 'docker'.",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help=(
            "Directory for wrapper scripts "
            "(defaults to config or ~/.local/absconda/wrappers/<image-name>)."
        ),
    ),
    image_cache: Optional[Path] = typer.Option(
        None,
        "--image-cache",
        help=(
            "SIF cache directory for Singularity "
            "(defaults to config or ~/.local/absconda/sif-cache)."
        ),
    ),
    extra_mounts: Optional[str] = typer.Option(
        None,
        "--extra-mounts",
        help=(
            "Additional volume mounts "
            "(comma-separated paths, e.g., /scratch/$PROJECT,/g/data/$PROJECT)."
        ),
    ),
    env: Optional[str] = typer.Option(
        None,
        "--env",
        help="Additional environment variables to pass through (comma-separated).",
    ),
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Enable GPU support (--nv for Singularity, --gpus all for Docker).",
    ),
    env_dir: Optional[str] = typer.Option(
        None,
        "--env-dir",
        help=(
            "Path to conda environment inside container "
            "(e.g., /opt/conda/envs/myenv). Required for Singularity PATH setup."
        ),
    ),
    shims: Optional[str] = typer.Option(
        None,
        "--shims",
        help=(
            "Comma-separated shim groups to inject (e.g., pbs,singularity). "
            "Generates host-command pass-through scripts alongside wrappers."
        ),
    ),
) -> None:
    """Generate wrapper scripts for running commands inside containers.

    Creates executable shell scripts that transparently run specified commands
    inside a container runtime, making containerized environments feel like
    native executables on HPC systems.
    """
    from .config import load_config
    from .wrappers import WrapperConfig, WrapperError, generate_wrappers

    # Load configuration
    config = load_config()

    # Parse command list
    command_list = [cmd.strip() for cmd in commands.split(",") if cmd.strip()]
    if not command_list:
        console.print("[red]Error:[/red] No commands specified")
        raise typer.Exit(1)

    # Determine output directory
    if output_dir is None:
        name_tag = _image_name_tag(image)
        if config.wrapper_default_output_dir:
            output_dir = config.wrapper_default_output_dir / name_tag
        else:
            output_dir = Path.home() / ".local" / "absconda" / "wrappers" / name_tag

    # Determine image cache
    if image_cache is None and runtime == "singularity":
        if config.wrapper_image_cache:
            image_cache = config.wrapper_image_cache
        else:
            image_cache = Path.home() / ".local" / "absconda" / "sif-cache"

    # Parse mounts
    mount_list = []
    if extra_mounts:
        mount_list = [m.strip() for m in extra_mounts.split(",") if m.strip()]

    # Add default mounts from config
    if config.wrapper_default_mounts:
        mount_list = config.wrapper_default_mounts + mount_list

    # Parse environment variables
    env_list = []
    if env:
        env_list = [e.strip() for e in env.split(",") if e.strip()]

    # Add default env passthrough from config
    if config.wrapper_env_passthrough:
        env_list = config.wrapper_env_passthrough + env_list

    # Parse shim groups
    shim_list = []
    if shims:
        shim_list = [s.strip() for s in shims.split(",") if s.strip()]

    # Create wrapper config
    wrapper_config = WrapperConfig(
        image_ref=image,
        commands=command_list,
        runtime=runtime,
        output_dir=output_dir,
        image_cache=image_cache,
        extra_mounts=mount_list,
        env_passthrough=env_list,
        gpu=gpu,
        env_dir=env_dir,
        shims=shim_list,
    )

    # Generate wrappers
    try:
        wrapper_paths = generate_wrappers(wrapper_config)

        console.print(
            f"[green]✓[/green] Generated {len(wrapper_paths)} wrapper script(s) in {output_dir}"
        )
        console.print(f"\n[bold]Runtime:[/bold] {runtime}")
        console.print(f"[bold]Image:[/bold] {image}")
        if gpu:
            console.print("[bold]GPU:[/bold] enabled")

        console.print("\n[bold]Wrapped commands:[/bold]")
        for cmd, path in wrapper_paths.items():
            console.print(f"  • {cmd} → {path}")

        console.print("\n[bold cyan]Next steps:[/bold cyan]")
        console.print(f"  1. Add {output_dir} to your PATH, or")
        console.print(
            f"  2. Generate a module file with: absconda module --wrapper-dir {output_dir}"
        )

    except WrapperError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


@app.command()
def module(
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Module name with version (e.g., myenv/1.0). Defaults to <name>/<tag> from --image.",
    ),
    wrapper_dir: Optional[Path] = typer.Option(
        None,
        "--wrapper-dir",
        help="Directory containing wrapper scripts "
        "(defaults to wrappers.default_output_dir/<name>/<tag>).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        help="Directory for module file (defaults to config or ~/.local/absconda/modulefiles).",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        help="Module description for help text. Defaults to '<name> environment'.",
    ),
    image: str = typer.Option(
        ...,
        "--image",
        help="Container image reference (for metadata and deriving defaults).",
    ),
    runtime: str = typer.Option(
        "singularity",
        "--runtime",
        help="Container runtime: 'singularity' or 'docker'.",
    ),
    commands_str: Optional[str] = typer.Option(
        None,
        "--commands",
        help="Comma-separated list of wrapped commands (for help text).",
    ),
) -> None:
    """Generate an environment module file for wrapper scripts.

    Creates a Tcl module file that adds wrapper directories to PATH and sets
    environment variables. Compatible with HPC module systems.
    """
    from .config import load_config
    from .modules import ModuleConfig, ModuleError, generate_module

    # Load configuration
    config = load_config()

    # Derive defaults from image ref
    name_tag = _image_name_tag(image)

    if name is None:
        name = name_tag

    if description is None:
        description = f"{name_tag.split('/')[0]} environment"

    if wrapper_dir is None:
        if config.wrapper_default_output_dir:
            wrapper_dir = config.wrapper_default_output_dir / name_tag
        else:
            wrapper_dir = Path.home() / ".local" / "absconda" / "wrappers" / name_tag

    # Determine output directory
    if output_dir is None:
        if config.module_default_output_dir:
            output_dir = config.module_default_output_dir
        else:
            output_dir = Path.home() / ".local" / "absconda" / "modulefiles"

    # Parse commands list if provided
    commands_list = None
    if commands_str:
        commands_list = [cmd.strip() for cmd in commands_str.split(",") if cmd.strip()]

    # Create module config
    module_config = ModuleConfig(
        name=name,
        wrapper_dir=wrapper_dir,
        output_dir=output_dir,
        description=description,
        image_ref=image,
        runtime=runtime,
        commands=commands_list,
    )

    # Generate module
    try:
        module_file = generate_module(module_config)

        console.print(f"[green]✓[/green] Generated module file: {module_file}")
        console.print(f"\n[bold]Module name:[/bold] {name}")
        console.print(f"[bold]Wrapper directory:[/bold] {wrapper_dir}")
        console.print(f"[bold]Runtime:[/bold] {runtime}")
        console.print(f"[bold]Image:[/bold] {image}")

        console.print("\n[bold cyan]Usage:[/bold cyan]")
        console.print(f"  module use {output_dir}")
        console.print(f"  module load {name}")
        console.print(f"  module help {name}")

    except ModuleError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


# ---------------------------------------------------------------------------
# Config subcommands
# ---------------------------------------------------------------------------


@config_app.command("list")
def config_list(
    show_origin: bool = typer.Option(
        False,
        "--show-origin",
        help="Show the origin file for each config value.",
    ),
) -> None:
    """List all configuration settings.

    Shows the merged configuration from all sources (system, user, environment).
    """
    from . import config as cfg

    if show_origin:
        # Show each config file with its contents
        configs = cfg.load_config_with_origins()
        if not configs:
            console.print("No configuration files found.")
            return

        for path, data in configs:
            console.print(f"\n[bold cyan]{path}[/bold cyan]")
            for key_path, value in cfg.flatten_config(data):
                console.print(f"  {key_path}={value}")
    else:
        # Show merged config
        merged_data: dict = {}
        for _, data in cfg.load_config_with_origins():
            merged_data = cfg._merge_configs(merged_data, data)

        if not merged_data:
            console.print("No configuration set.")
            return

        for key_path, value in cfg.flatten_config(merged_data):
            console.print(f"{key_path}={value}")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(
        ..., help="Configuration key (dot-notation, e.g., wrappers.default_runtime)."
    ),
) -> None:
    """Get a configuration value.

    Use dot-notation for nested keys (e.g., wrappers.default_runtime).
    """
    from . import config as cfg

    value = cfg.get_config_value(key)
    if value is None:
        raise typer.Exit(1)

    if isinstance(value, list):
        for item in value:
            console.print(item)
    elif isinstance(value, dict):
        for k, v in cfg.flatten_config(value, key):
            console.print(f"{k}={v}")
    else:
        console.print(value)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Configuration key (dot-notation)."),
    value: str = typer.Argument(..., help="Value to set."),
    system: bool = typer.Option(
        False,
        "--system",
        help="Write to system-wide config instead of user config.",
    ),
) -> None:
    """Set a configuration value.

    By default, writes to user config (~/.config/absconda/config.yaml).
    Use --system to write to system config (/etc/xdg/absconda/config.yaml).
    """
    # Try to parse value as YAML for proper typing
    import yaml

    from . import config as cfg

    try:
        parsed_value = yaml.safe_load(value)
    except yaml.YAMLError:
        parsed_value = value

    try:
        path = cfg.set_config_value(key, parsed_value, system=system)
        console.print(f"Set {key}={parsed_value} in {path}")
    except cfg.ConfigError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


@config_app.command("unset")
def config_unset(
    key: str = typer.Argument(..., help="Configuration key to remove (dot-notation)."),
    system: bool = typer.Option(
        False,
        "--system",
        help="Remove from system-wide config instead of user config.",
    ),
) -> None:
    """Remove a configuration value.

    By default, removes from user config (~/.config/absconda/config.yaml).
    Use --system to remove from system config (/etc/xdg/absconda/config.yaml).
    """
    from . import config as cfg

    try:
        path = cfg.unset_config_value(key, system=system)
        if path:
            console.print(f"Removed {key} from {path}")
        else:
            console.print(f"Key '{key}' not found.")
            raise typer.Exit(1)
    except cfg.ConfigError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(1) from exc


@config_app.command("edit")
def config_edit(
    system: bool = typer.Option(
        False,
        "--system",
        help="Edit system-wide config instead of user config.",
    ),
) -> None:
    """Open the configuration file in an editor.

    Uses $EDITOR or $VISUAL environment variable, falling back to 'vi'.
    """
    import os
    import subprocess

    from . import config as cfg

    path = cfg.get_system_config_path() if system else cfg.get_user_config_path()

    # Create parent directory and empty file if needed
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Absconda configuration\n# See: https://github.com/swarbricklab/absconda\n\n"
        )

    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"

    try:
        subprocess.run([editor, str(path)], check=True)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] Editor '{editor}' not found.")
        raise typer.Exit(1) from exc
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Error:[/red] Editor exited with code {exc.returncode}")
        raise typer.Exit(1) from exc


@config_app.command("paths")
def config_paths() -> None:
    """Show configuration file paths and their status."""
    from . import config as cfg

    console.print("[bold]Configuration file search order:[/bold]\n")

    for config_dir in cfg.get_config_dirs():
        config_file = config_dir / "config.yaml"
        if config_file.exists():
            console.print(f"  [green]✓[/green] {config_file}")
        else:
            console.print(f"  [dim]✗ {config_file}[/dim]")

    console.print()
    console.print(f"[bold]User config:[/bold] {cfg.get_user_config_path()}")
    console.print(f"[bold]System config:[/bold] {cfg.get_system_config_path()}")


if __name__ == "__main__":  # pragma: no cover
    app()
