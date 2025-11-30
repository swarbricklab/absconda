from pathlib import Path
from typing import List, Tuple

from typer.testing import CliRunner

from absconda.cli import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RENV_LOCK_PATH = FIXTURES_DIR / "sample-renv.lock"


def write_env(tmp_path: Path) -> Path:
    path = tmp_path / "env.yaml"
    path.write_text(
        """
name: cli-demo
channels:
    - conda-forge
dependencies:
    - python=3.11
    - pip
""".strip()
    )
    return path


def test_cli_shows_help_by_default(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, [], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0
    assert "Generate container assets" in result.stdout


def test_version_option(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0
    assert "Absconda" in result.stdout


def test_generate_renders_dockerfile(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["generate", "--file", str(env_path)], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0
    assert "FROM mambaorg/micromamba:1.5.5 AS builder" in result.stdout
    assert "ENV CONDA_PREFIX=/opt/conda/envs/cli-demo" in result.stdout
    assert "Using policy profile" in result.stdout


def test_generate_single_stage_flag(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate", "--file", str(env_path), "--single-stage"],
        env={"HOME": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert result.stdout.count("FROM") == 1


def test_generate_uses_custom_template(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    template = tmp_path / "template.j2"
    template.write_text("FROM custom\n# {{ env.name }}\n")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate", "--file", str(env_path), "--template", str(template)],
        env={"HOME": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert "FROM custom" in result.stdout
    assert "# cli-demo" in result.stdout


def test_generate_with_renv_lock(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "generate",
            "--file",
            str(env_path),
            "--renv-lock",
            str(RENV_LOCK_PATH),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "ABSCONDA_RENV_LOCK" in result.stdout
    assert "renv::restore" in result.stdout


def test_generate_missing_renv_lock_errors(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    missing = tmp_path / "renv.lock"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "generate",
            "--file",
            str(env_path),
            "--renv-lock",
            str(missing),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "Unable to read renv lock" in result.stdout


def test_validate_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    runner = CliRunner()
    result = runner.invoke(app, ["validate", "--file", str(missing)], env={"HOME": str(tmp_path)})
    assert result.exit_code == 1
    assert "Error" in result.stdout


def test_build_invokes_docker_with_expected_tag(monkeypatch, tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20251129")

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--repository",
            "ghcr.io/example/absconda",
            "--file",
            str(env_path),
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert commands, "docker build should have been invoked"
    build_cmd, build_cwd = commands[0]
    assert build_cwd is None
    assert build_cmd[0:2] == ["docker", "build"]
    assert "ghcr.io/example/absconda:cli-demo-20251129" in build_cmd
    assert build_cmd[-1] == str(tmp_path.resolve())


def test_publish_pushes_and_generates_singularity(monkeypatch, tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20251129")

    sif_path = tmp_path / "artifacts" / "env.sif"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "publish",
            "--repository",
            "ghcr.io/example/absconda",
            "--file",
            str(env_path),
            "--context",
            str(tmp_path),
            "--singularity-out",
            str(sif_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 3
    image_ref = "ghcr.io/example/absconda:cli-demo-20251129"
    assert commands[0][0][0:2] == ["docker", "build"]
    assert commands[1][0] == ["docker", "push", image_ref]
    assert commands[2][0] == ["singularity", "pull", str(sif_path), f"docker://{image_ref}"]
