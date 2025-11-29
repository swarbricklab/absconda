from pathlib import Path

from typer.testing import CliRunner

from absconda.cli import app


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


def test_validate_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    runner = CliRunner()
    result = runner.invoke(app, ["validate", "--file", str(missing)], env={"HOME": str(tmp_path)})
    assert result.exit_code == 1
    assert "Error" in result.stdout
