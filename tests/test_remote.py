import io
from pathlib import Path

import pytest
from rich.console import Console

from absconda import remote


def _write_remote_config(path: Path) -> None:
    path.write_text(
        """
version: 1
builders:
  default-remote:
    host: builder.example.com
    user: absconda
    workspace: /home/absconda/builds
    ssh_key: ~/.ssh/absconda
    ssh_port: 2200
    ssh_options:
      - -o
      - StrictHostKeyChecking=no
    start_command: echo start
    stop_command: echo stop
    provision_command: echo provision
    health_command: echo health
    lock_file: ~/.cache/absconda/remote/default.lock
    project: ml-platform-prod
        """.strip()
    )


def test_load_remote_definition(tmp_path: Path) -> None:
    config_path = tmp_path / "absconda-remote.yaml"
    _write_remote_config(config_path)

    definition = remote.load_remote_definition("default-remote", config_path=config_path)

    assert definition.name == "default-remote"
    assert definition.ssh_target == "absconda@builder.example.com"
    assert definition.workspace == "/home/absconda/builds"
    assert definition.ssh_port == 2200
    assert definition.ssh_key is not None
    assert definition.start_command == ["echo", "start"]
    assert definition.stop_command == ["echo", "stop"]
    assert definition.provision_command == ["echo", "provision"]
    assert definition.health_command == ["echo", "health"]
    assert definition.lock_file.name == "default.lock"
    assert definition.metadata["project"] == "ml-platform-prod"


def test_build_remote_image_invokes_expected_commands(monkeypatch, tmp_path: Path) -> None:
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    (context_dir / "example.txt").write_text("hello")

    definition = remote.RemoteBuilderDefinition(
        name="default-remote",
        ssh_target="absconda@builder.example.com",
        workspace="/home/absconda/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=None,
        stop_command=None,
        lock_file=tmp_path / "builder.lock",
    )

    recorded: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:  # type: ignore[override]
        _ = cwd  # touch parameter to satisfy linters
        recorded.append(command)

    monkeypatch.setattr(remote, "_run_subprocess", fake_run)

    console = Console(file=io.StringIO())

    remote.build_remote_image(
        definition=definition,
        dockerfile="FROM busybox",
        context_path=context_dir,
        image_ref="ghcr.io/example/app:latest",
        push=True,
        wait_seconds=5,
        shutdown_after=False,
        manifest={"example": True},
        console=console,
    )

    assert recorded, "expected remote commands to be executed"
    # Ensure the workflow included ssh workspace creation, scp upload, docker build, and cleanup
    joined = [" ".join(cmd) for cmd in recorded]
    assert any(cmd.startswith("ssh") and "mkdir -p" in cmd for cmd in joined)
    assert any(cmd.startswith("scp") for cmd in joined)
    assert any("docker build" in cmd for cmd in joined)
    assert any("rm -rf" in cmd for cmd in joined)


def test_list_remote_builders_returns_names(tmp_path: Path) -> None:
    config_path = tmp_path / "absconda-remote.yaml"
    _write_remote_config(config_path)

    path, builders = remote.list_remote_builders(config_path=config_path)

    assert path == config_path
    assert builders == ["default-remote"]


def test_provision_remote_builder_runs_configured_command(monkeypatch, tmp_path: Path) -> None:
    recorded: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:  # type: ignore[override]
        _ = cwd
        recorded.append(command)

    monkeypatch.setattr(remote, "_run_subprocess", fake_run)

    definition = remote.RemoteBuilderDefinition(
        name="default",
        ssh_target="absconda@builder",
        workspace="/srv/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=None,
        stop_command=None,
        lock_file=tmp_path / "builder.lock",
        provision_command=["echo", "provision"],
    )

    remote.provision_remote_builder(definition, Console(file=io.StringIO()))

    assert recorded == [["echo", "provision"]]


def test_start_remote_builder_requires_command(tmp_path: Path) -> None:
    definition = remote.RemoteBuilderDefinition(
        name="default",
        ssh_target="absconda@builder",
        workspace="/srv/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=None,
        stop_command=None,
        lock_file=tmp_path / "builder.lock",
    )

    console = Console(file=io.StringIO())
    with pytest.raises(remote.RemoteConfigError):
        remote.start_remote_builder(definition, console)


def test_check_remote_status_reports_lock_and_health(monkeypatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "builder.lock"
    lock_path.write_text("runner@example", encoding="utf-8")

    def fake_run(command: list[str], *, cwd: Path | None = None) -> None:  # type: ignore[override]
        _ = cwd
        if command == ["check-health"]:
            raise remote.RemoteError("health failed")

    monkeypatch.setattr(remote, "_run_subprocess", fake_run)

    definition = remote.RemoteBuilderDefinition(
        name="default",
        ssh_target="absconda@builder",
        workspace="/srv/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=None,
        stop_command=None,
        lock_file=lock_path,
        health_command=["check-health"],
    )

    status = remote.check_remote_status(definition)

    assert status.busy is True
    assert status.lock_owner == "runner@example"
    assert status.reachable is True
    assert status.health_ok is False
    assert status.health_error is not None
