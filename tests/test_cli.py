from pathlib import Path
from typing import Any, List, Tuple

from typer.testing import CliRunner

from absconda import remote
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


def write_policy(tmp_path: Path, content: str) -> Path:
    policy_path = tmp_path / "absconda-policy.yaml"
    policy_path.write_text(content.strip(), encoding="utf-8")
    return policy_path


def write_remote_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "absconda-remote.yaml"
    config_path.write_text(
        """
version: 1
builders:
  default-remote:
    host: builder.example.com
    user: absconda
    workspace: /srv/absconda
    start_command: echo start
    stop_command: echo stop
    provision_command: echo provision
    health_command: echo health
    lock_file: ~/.cache/absconda/remote/default.lock
        """.strip()
    )
    return config_path


def test_cli_shows_help_by_default(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, [], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0
    assert "Generate container assets" in result.stdout


def test_version_option(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"], env={"HOME": str(tmp_path)})
    assert result.exit_code == 0


def test_build_uses_remote_builder_when_requested(monkeypatch, tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    builder_definition = remote.RemoteBuilderDefinition(
        name="default-remote",
        ssh_target="absconda@builder.example.com",
        workspace="/home/absconda/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=None,
        stop_command=None,
        lock_file=tmp_path / "remote.lock",
    )

    calls: dict[str, Any] = {}

    def fake_load(name: str, *, config_path: Path | None = None) -> remote.RemoteBuilderDefinition:
        calls["builder_name"] = name
        calls["config_path"] = config_path
        return builder_definition

    def fake_build(**kwargs: Any) -> None:
        calls["remote_invoked"] = True
        calls["args"] = kwargs

    monkeypatch.setattr(remote, "load_remote_definition", fake_load)
    monkeypatch.setattr(remote, "build_remote_image", fake_build)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20250101")

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
            "--remote-builder",
            "default-remote",
            "--remote-config",
            str(tmp_path / "custom-remote.yaml"),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert calls.get("remote_invoked") is True
    assert calls.get("builder_name") == "default-remote"
    assert calls.get("config_path") == tmp_path / "custom-remote.yaml"
    assert calls["args"]["image_ref"] == "ghcr.io/example/absconda:20250101"


def test_remote_list_shows_builders(tmp_path: Path) -> None:
    config_path = write_remote_config(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["remote", "list", "--config", str(config_path)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "default-remote" in result.stdout


def test_remote_provision_invokes_helper(monkeypatch, tmp_path: Path) -> None:
    config_path = write_remote_config(tmp_path)
    invoked: dict[str, str] = {}

    def fake_provision(definition: remote.RemoteBuilderDefinition, console: Any) -> None:
        invoked["builder"] = definition.name
        _ = console

    monkeypatch.setattr(remote, "provision_remote_builder", fake_provision)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["remote", "provision", "default-remote", "--config", str(config_path)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert invoked.get("builder") == "default-remote"


def test_remote_status_prints_summary(monkeypatch, tmp_path: Path) -> None:
    config_path = write_remote_config(tmp_path)
    status = remote.RemoteStatus(
        name="default-remote",
        reachable=False,
        busy=True,
        lock_owner="runner",
        lock_path=tmp_path / "builder.lock",
        health_ok=None,
        ssh_error="ssh failed",
        health_error=None,
    )

    monkeypatch.setattr(remote, "check_remote_status", lambda definition: status)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["remote", "status", "default-remote", "--config", str(config_path)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "unreachable" in result.stdout
    assert "runner" in result.stdout


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


def test_generate_base_image(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "generate",
            "--file",
            str(env_path),
            "--base",
            "nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04",
        ],
        env={"HOME": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert result.stdout.count("FROM") == 1
    assert "FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04" in result.stdout
    assert "micromamba create -y -n cli-demo" in result.stdout


def test_generate_base_rejects_builder_base(tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "generate",
            "--file",
            str(env_path),
            "--base",
            "nvidia/cuda:11.8.0-runtime-ubuntu22.04",
            "--builder-base",
            "mambaorg/micromamba:1.5.5",
        ],
        env={"HOME": str(tmp_path)},
    )
    assert result.exit_code == 1
    assert "--base cannot be combined with --builder-base" in result.stdout


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
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

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
    assert "ghcr.io/example/absconda:20251129" in build_cmd
    assert build_cmd[-1] == str(tmp_path.resolve())


def test_publish_pushes_image(monkeypatch, tmp_path: Path) -> None:
    """Test that publish builds and pushes (no pull — that's deploy's job now)."""
    env_path = write_env(tmp_path)
    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20251129")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

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
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 2  # build + push
    image_ref = "ghcr.io/example/absconda:20251129"
    assert commands[0][0][0:2] == ["docker", "build"]
    assert commands[1][0] == ["docker", "push", image_ref]


def test_generate_rejects_disallowed_channel(monkeypatch, tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    write_policy(
        tmp_path,
        """
version: 1
profiles:
    default:
        allowed_channels:
            - defaults
        required_labels: {}
        """,
    )
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate", "--file", str(env_path)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "Policy violation" in result.stdout


def test_generate_applies_required_labels(monkeypatch, tmp_path: Path) -> None:
    env_path = write_env(tmp_path)
    write_policy(
        tmp_path,
        """
version: 1
profiles:
    default:
        allowed_channels:
            - conda-forge
        required_labels:
            maintainer: team@example.com
            owner: data-platform
        """,
    )
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["generate", "--file", str(env_path)],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert 'LABEL maintainer="team@example.com"' in result.stdout
    assert 'LABEL owner="data-platform"' in result.stdout


def test_build_with_dockerfile_skips_generation(monkeypatch, tmp_path: Path) -> None:
    """Test that --dockerfile uses the provided Dockerfile instead of generating one."""
    dockerfile_path = tmp_path / "Dockerfile.custom"
    dockerfile_path.write_text(
        """FROM python:3.11-slim
RUN echo "Custom Dockerfile content"
"""
    )

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--dockerfile",
            str(dockerfile_path),
            "--repository",
            "ghcr.io/example/custom-image",
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 1
    assert commands[0][0][0:2] == ["docker", "build"]
    assert "ghcr.io/example/custom-image:20260410" in commands[0][0]


def test_build_with_dockerfile_requires_repository_or_env_name(tmp_path: Path) -> None:
    """Test that --dockerfile without --file and without a detectable env name errors."""
    dockerfile_path = tmp_path / "Dockerfile.custom"
    dockerfile_path.write_text("FROM python:3.11")  # no CONDA_DEFAULT_ENV line

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--dockerfile",
            str(dockerfile_path),
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 1
    assert "--repository or --env-name is required" in result.stdout


def test_build_with_dockerfile_auto_detects_env_name(monkeypatch, tmp_path: Path) -> None:
    """Test that --dockerfile auto-detects env name from CONDA_DEFAULT_ENV line."""
    dockerfile_path = tmp_path / "Dockerfile"
    dockerfile_path.write_text(
        "FROM mambaorg/micromamba:1.5.5 AS builder\n"
        "ENV CONDA_DEFAULT_ENV=my-detected-env\n"
        "ENV CONDA_PREFIX=/opt/conda/envs/my-detected-env\n"
    )

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--dockerfile",
            str(dockerfile_path),
            "--repository",
            "ghcr.io/example/my-detected-env",
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 1
    assert "ghcr.io/example/my-detected-env:20260410" in commands[0][0]


def test_build_with_dockerfile_and_env_name(monkeypatch, tmp_path: Path) -> None:
    """Test that --dockerfile with --env-name derives repository from env name."""
    dockerfile_path = tmp_path / "Dockerfile.custom"
    dockerfile_path.write_text("FROM python:3.11-slim\nRUN echo 'custom'")

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--dockerfile",
            str(dockerfile_path),
            "--env-name",
            "my-env",
            "--repository",
            "ghcr.io/example/my-env",
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 1
    assert "ghcr.io/example/my-env:20260410" in commands[0][0]


def test_build_with_dockerfile_and_file_uses_env_name(monkeypatch, tmp_path: Path) -> None:
    """Test that --dockerfile with --file uses env name for repository resolution."""
    env_path = write_env(tmp_path)
    dockerfile_path = tmp_path / "Dockerfile.custom"
    dockerfile_path.write_text("FROM python:3.11-slim\nRUN echo 'edited'")

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--dockerfile",
            str(dockerfile_path),
            "--file",
            str(env_path),
            "--repository",
            "ghcr.io/example/cli-demo",
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 1
    assert "ghcr.io/example/cli-demo:20260410" in commands[0][0]


def test_publish_with_dockerfile(monkeypatch, tmp_path: Path) -> None:
    """Test that publish --dockerfile works for pushed images."""
    dockerfile_path = tmp_path / "Dockerfile.custom"
    dockerfile_path.write_text("FROM python:3.11-slim\nRUN pip install flask")

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "publish",
            "--dockerfile",
            str(dockerfile_path),
            "--repository",
            "ghcr.io/example/flask-app",
            "--context",
            str(tmp_path),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert len(commands) == 2  # build + push
    assert commands[0][0][0:2] == ["docker", "build"]
    assert commands[1][0] == ["docker", "push", "ghcr.io/example/flask-app:20260410"]


def test_build_with_build_args(monkeypatch, tmp_path: Path) -> None:
    """Test that --build-arg passes arguments to docker build."""
    env_path = write_env(tmp_path)

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "build",
            "--file",
            str(env_path),
            "--repository",
            "ghcr.io/example/testimage",
            "--context",
            str(tmp_path),
            "--build-arg",
            "PYTHON_VERSION=3.11",
            "--build-arg",
            "CACHEBUST=123",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    build_cmd = commands[0][0]
    assert "--build-arg" in build_cmd
    assert "PYTHON_VERSION=3.11" in build_cmd
    assert "CACHEBUST=123" in build_cmd


def test_publish_with_build_args(monkeypatch, tmp_path: Path) -> None:
    """Test that publish --build-arg passes arguments to docker build."""
    env_path = write_env(tmp_path)

    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._date_stamp", lambda: "20260410")
    monkeypatch.setattr("absconda.cli._resolve_remote_options", lambda *a, **kw: None)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "publish",
            "--file",
            str(env_path),
            "--repository",
            "ghcr.io/example/testimage",
            "--context",
            str(tmp_path),
            "--build-arg",
            "BUILD_DATE=2026-04-10",
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    build_cmd = commands[0][0]
    assert "--build-arg" in build_cmd
    assert "BUILD_DATE=2026-04-10" in build_cmd


def test_deploy_pulls_and_wraps(monkeypatch, tmp_path: Path) -> None:
    """Test that deploy pulls a SIF, generates wrappers, and creates a module."""
    commands: List[Tuple[list[str], Path | None]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:
        commands.append((command, cwd))

    def fake_run_filtered(
        command: list[str], *, cwd: Path | None = None, noise_re=None, env=None
    ) -> None:
        commands.append((command, cwd))

    monkeypatch.setattr("absconda.cli._run_command", fake_run)
    monkeypatch.setattr("absconda.cli._run_command_filtered", fake_run_filtered)

    wrapper_dir = tmp_path / "wrappers"
    module_dir = tmp_path / "modules"
    cache_dir = tmp_path / "sif-cache"

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "deploy",
            "ghcr.io/example/myenv:20260412",
            "--commands",
            "python,pip",
            "--output-dir",
            str(wrapper_dir),
            "--module-dir",
            str(module_dir),
            "--image-cache",
            str(cache_dir),
        ],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0, result.stdout

    # Should have called singularity pull
    pull_cmds = [c for c, _ in commands if c[0] == "singularity"]
    assert len(pull_cmds) == 1
    assert pull_cmds[0][1] == "pull"

    # Should have created wrapper scripts
    assert wrapper_dir.exists()

    # Should have created a module file
    assert module_dir.exists()


def test_deploy_requires_image_or_file(tmp_path: Path) -> None:
    """Test that deploy errors when neither image nor --file is provided."""
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["deploy"],
        env={"HOME": str(tmp_path)},
    )
    assert result.exit_code == 1
    assert "image reference" in result.stdout.lower() or "Error" in result.stdout


def test_ghcr_pull_env_disabled_by_default() -> None:
    from absconda import cli
    from absconda.config import AbscondaConfig

    assert cli._ghcr_pull_env(AbscondaConfig(remote_builders={})) == {}


def test_ghcr_pull_env_fetches_secrets(monkeypatch) -> None:
    from absconda import cli
    from absconda.config import AbscondaConfig

    config = AbscondaConfig(
        remote_builders={},
        gcp_project="proj",
        ghcr_auth_source="gcp-secret-manager",
        ghcr_user_secret="user-secret",
        ghcr_token_secret="token-secret",
    )
    for var in (
        "SINGULARITY_DOCKER_USERNAME",
        "SINGULARITY_DOCKER_PASSWORD",
        "APPTAINER_DOCKER_USERNAME",
        "APPTAINER_DOCKER_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)

    calls: list[tuple[str, str | None]] = []

    def fake_fetch(secret: str, *, project: str | None) -> str:
        calls.append((secret, project))
        return {"user-secret": "alice", "token-secret": "ghp_xxx"}[secret]

    monkeypatch.setattr(cli, "_fetch_gcp_secret", fake_fetch)

    assert cli._ghcr_pull_env(config) == {
        "SINGULARITY_DOCKER_USERNAME": "alice",
        "SINGULARITY_DOCKER_PASSWORD": "ghp_xxx",
        "APPTAINER_DOCKER_USERNAME": "alice",
        "APPTAINER_DOCKER_PASSWORD": "ghp_xxx",
    }
    assert calls == [("user-secret", "proj"), ("token-secret", "proj")]


def test_ghcr_pull_env_respects_existing_env(monkeypatch) -> None:
    from absconda import cli
    from absconda.config import AbscondaConfig

    config = AbscondaConfig(remote_builders={}, ghcr_auth_source="gcp-secret-manager")
    monkeypatch.setenv("SINGULARITY_DOCKER_USERNAME", "preset")

    def boom(*args: object, **kwargs: object) -> str:
        raise AssertionError("must not fetch secrets when env is already set")

    monkeypatch.setattr(cli, "_fetch_gcp_secret", boom)
    assert cli._ghcr_pull_env(config) == {}


def test_fetch_gcp_secret_strips_trailing_newline(monkeypatch) -> None:
    from absconda import cli

    class _Result:
        stdout = "ghp_token\n"

    def fake_run(command, check, capture_output, text):  # type: ignore[no-untyped-def]
        assert command[:5] == ["gcloud", "secrets", "versions", "access", "latest"]
        assert "--secret=my-secret" in command
        assert "--project=proj" in command
        return _Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._fetch_gcp_secret("my-secret", project="proj") == "ghp_token"
