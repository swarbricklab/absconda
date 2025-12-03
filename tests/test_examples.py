from pathlib import Path

from typer.testing import CliRunner

from absconda.cli import app

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _runner() -> CliRunner:
    return CliRunner(mix_stderr=False)


def test_minimal_example_generates(tmp_path):
    runner = _runner()
    env = {"HOME": str(tmp_path)}
    file_path = EXAMPLES_DIR / "minimal-env.yaml"

    result = runner.invoke(app, ["generate", "--file", str(file_path)], env=env)

    assert result.exit_code == 0
    assert "python=3.11" in result.stdout
    assert "rich==13.7.1" in result.stdout
    assert "FROM mambaorg/micromamba" in result.stdout


def test_data_science_example_single_stage(tmp_path):
    runner = _runner()
    env = {"HOME": str(tmp_path)}
    file_path = EXAMPLES_DIR / "data-science-env.yaml"

    result = runner.invoke(
        app,
        ["generate", "--file", str(file_path), "--single-stage"],
        env=env,
    )

    assert result.exit_code == 0
    assert result.stdout.count("FROM") == 1
    assert "numpy=1.26" in result.stdout
    assert 'CMD ["python"]' in result.stdout
