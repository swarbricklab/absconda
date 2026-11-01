import pytest

from absconda.policy import PolicyLoadError, load_policy


def test_load_policy_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = load_policy(None, None)

    assert result.source_path is None
    assert result.profile.name == "default"
    assert result.hooks.before_render is None
    assert result.warnings == []


def test_load_policy_selects_profile_and_hooks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(tmp_path))

    hooks_file = tmp_path / "policy_hooks.py"
    hooks_file.write_text(
        """
from typing import Any

def before_render(context: Any) -> str:
    return f"before:{context}"
""".strip()
    )

    policy_file = tmp_path / "absconda-policy.yaml"
    policy_file.write_text(
        """
version: 1
default_profile: hardened
profiles:
  hardened:
    builder_base: ubuntu:22.04
    runtime_base: ubuntu:22.04
    multi_stage: true
    env_prefix: /opt/policy
    allowed_channels:
      - conda-forge
    required_labels:
      maintainer: team@example.com
    default_fragments:
      - apt_cleanup
hooks:
  module: policy_hooks
  before_render: before_render
        """.strip()
    )

    result = load_policy(None, None)

    assert result.source_path == policy_file
    assert result.profile.name == "hardened"
    assert result.profile.multi_stage is True
    assert result.profile.env_prefix == "/opt/policy"
    assert callable(result.hooks.before_render)
    assert result.hooks.after_validate is None


def test_builtin_reproducible_profile_without_policy_file(tmp_path, monkeypatch):
    """`--profile reproducible` works with no policy file and sets thread vars (#68)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = load_policy(None, "reproducible")

    assert result.source_path is None
    assert result.profile.name == "reproducible"
    assert result.profile.runtime_env["OMP_NUM_THREADS"] == "1"
    assert result.profile.runtime_env["VECLIB_MAXIMUM_THREADS"] == "1"


def test_builtin_default_profile_has_empty_runtime_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = load_policy(None, None)
    assert result.profile.runtime_env == {}


def test_unknown_builtin_profile_falls_back_to_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = load_policy(None, "does-not-exist")
    assert result.profile.name == "default"
    assert result.warnings  # warned about the fallback


def test_policy_file_runtime_env_is_parsed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    policy_file = tmp_path / "absconda-policy.yaml"
    policy_file.write_text(
        """
default_profile: custom
profiles:
  custom:
    runtime_env:
      FOO: bar
        """.strip()
    )

    result = load_policy(None, None)
    assert result.profile.runtime_env == {"FOO": "bar"}
    # Built-in profiles remain available alongside file-defined ones.
    assert load_policy(policy_file, "reproducible").profile.name == "reproducible"


def test_load_policy_unknown_profile_raises(tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text(
        """
profiles:
  base:
    allowed_channels: []
    required_labels: {}
    default_fragments: []
        """.strip()
    )

    with pytest.raises(PolicyLoadError):
        load_policy(policy_file, "nonexistent")


def test_load_policy_respects_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    xdg_home = tmp_path / "xdg"
    policy_path = xdg_home / "absconda" / "absconda-policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text("version: 1")

    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    monkeypatch.setenv("HOME", str(tmp_path / "other-home"))

    result = load_policy(None, None)

    assert result.source_path == policy_path


def test_load_policy_checks_xdg_config_dirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dirs_root = tmp_path / "xdg_dirs"
    dir_one = dirs_root / "one"
    dir_two = dirs_root / "two"
    dir_one.mkdir(parents=True)
    policy_path = dir_two / "absconda" / "absconda-policy.yaml"
    policy_path.parent.mkdir(parents=True)
    policy_path.write_text("version: 1")

    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "other-home"))
    monkeypatch.setenv("XDG_CONFIG_DIRS", f"{dir_one}:{dir_two}")

    result = load_policy(None, None)

    assert result.source_path == policy_path
