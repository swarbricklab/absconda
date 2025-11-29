"""Command-line entry point built with Typer.

Typer builds on Click but lets us describe commands using regular Python functions
and type hints. Each function decorated with ``@app.command()`` becomes a CLI
subcommand, and type annotations automatically map to option parsing and help text.
"""

# ruff: noqa: B008

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, cast

import click
import typer
from rich.console import Console

from . import __version__
from .environment import EnvironmentLoadError, LoadReport, load_environment
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


def _load_with_feedback(file: Path, snapshot: Optional[Path]) -> LoadReport:
    """Helper that loads env files and renders Typer-friendly errors."""

    try:
        return load_environment(file, snapshot)
    except EnvironmentLoadError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


def _print_warnings(report: LoadReport) -> None:
    _print_warning_messages(report.warnings)


def _print_warning_messages(messages: Iterable[str]) -> None:
    for warning in messages:
        console.print(f"[bold yellow]warning[/bold yellow]: {warning}")


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
) -> str:
    policy_resolution = _active_policy()
    profile = policy_resolution.profile

    builder_base = builder_override or profile.builder_base or DEFAULT_BUILDER_IMAGE
    runtime_default = profile.runtime_base or DEFAULT_RUNTIME_IMAGE
    runtime_base = runtime_override or runtime_default

    multi_stage_default = profile.multi_stage if profile.multi_stage is not None else True
    multi_stage = multi_stage_override if multi_stage_override is not None else multi_stage_default

    config = RenderConfig(
        env=report.env,
        profile=profile,
        multi_stage=multi_stage,
        builder_base=builder_base,
        runtime_base=runtime_base,
        template_path=template,
    )

    try:
        return render_dockerfile(config)
    except TemplateRenderError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def generate(
    file: Path = typer.Option(
        Path("env.yaml"),
        "--file",
        "-f",
        help="Path to the Conda environment file.",
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
) -> None:
    """Generate a Dockerfile from the provided environment file."""

    _print_policy_banner()
    report = _load_with_feedback(file, snapshot)
    _print_warnings(report)
    dockerfile = _render_dockerfile(
        report,
        template=template,
        builder_override=builder_base,
        runtime_override=runtime_base,
        multi_stage_override=multi_stage,
    )

    if output is not None:
        output.write_text(dockerfile, encoding="utf-8")
        console.print(f"[green]Dockerfile written to[/green] {output}.")
    else:
        console.print(dockerfile, highlight=False, markup=False, soft_wrap=False)


@app.command()
def validate(
    file: Path = typer.Option(
        Path("env.yaml"),
        "--file",
        "-f",
        help="Environment file to validate.",
    ),
    snapshot: Optional[Path] = typer.Option(
        None,
        "--snapshot",
        help="Optional snapshot generated via 'conda env export'.",
    ),
) -> None:
    """Validate the environment and snapshot files without generating output."""

    _print_policy_banner()
    report = _load_with_feedback(file, snapshot)
    console.print(
        f"Environment [green]{report.env.name}[/green] is valid with "
        f"{len(report.env.dependencies)} dependency entries."
    )
    _print_warnings(report)


@app.command()
def build(
    image: str = typer.Option(
        ...,
        "--image",
        help="Target OCI image reference, e.g. ghcr.io/org/proj:tag",
    ),
    push: bool = typer.Option(False, "--push", help="Push the image after a successful build."),
) -> None:
    """Render a Dockerfile and build the container image."""

    _print_policy_banner()
    console.print(f"[yellow]build[/yellow] would build {image} (push={push}).")


@app.command()
def publish(
    image: str = typer.Option(..., "--image", help="Target OCI image reference"),
    singularity_out: Optional[Path] = typer.Option(
        None,
        "--singularity-out",
        help="Optional path for the resulting Singularity .sif artifact.",
    ),
) -> None:
    """Build (if needed) and push an image, optionally generating a Singularity file."""

    _print_policy_banner()
    console.print(
        f"[yellow]publish[/yellow] would push {image} and emit {singularity_out or 'no .sif'}.")


if __name__ == "__main__":  # pragma: no cover
    app()
