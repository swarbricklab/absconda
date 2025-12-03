from pathlib import Path

import pytest

from absconda.environment import EnvironmentLoadError, EnvSpec, load_environment


def write_env(tmp_path: Path, text: str = "") -> Path:
    path = tmp_path / "env.yaml"
    if not text:
        text = """
name: demo
channels:
  - defaults
dependencies:
  - python=3.10
  - pip
  - pip:
      - requests
""".strip()
    path.write_text(text)
    return path


def test_load_environment_success(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    report = load_environment(env_path)
    assert isinstance(report.env, EnvSpec)
    assert report.env.name == "demo"
    assert report.env.channels == ["defaults"]
    assert "pip::requests" in report.env.dependencies
    assert report.warnings == []


def test_load_environment_missing_file(tmp_path: Path) -> None:
    env_path = tmp_path / "missing.yaml"
    with pytest.raises(EnvironmentLoadError):
        load_environment(env_path)


def test_load_environment_snapshot_warning(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    snapshot = tmp_path / "snapshot.yaml"
    report = load_environment(env_path, snapshot)
    assert any("Snapshot" in warning for warning in report.warnings)


def test_load_environment_empty_dependencies_warns(tmp_path: Path) -> None:
    env_path = write_env(tmp_path, text="name: empty")
    report = load_environment(env_path)
    assert any("no dependencies" in warning for warning in report.warnings)
