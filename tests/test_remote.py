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


def test_build_authenticates_private_base_before_build(monkeypatch, tmp_path: Path) -> None:
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
    monkeypatch.setattr(remote, "_run_subprocess", lambda command, **_: recorded.append(command))

    remote.build_remote_image(
        definition=definition,
        dockerfile="FROM ghcr.io/swarbricklab/gpu-base:20260616",
        context_path=context_dir,
        image_ref="ghcr.io/swarbricklab/flash-scope:20260617",
        push=False,
        wait_seconds=5,
        shutdown_after=False,
        manifest={"example": True},
        console=Console(file=io.StringIO()),
        base_image="ghcr.io/swarbricklab/gpu-base:20260616",
    )

    # The build is a single SSH invocation; the GHCR login must come before
    # `docker build` so the private base image (FROM) can be pulled.
    build_cmd = next(" ".join(c) for c in recorded if "docker build" in " ".join(c))
    assert "docker login ghcr.io" in build_cmd
    assert build_cmd.index("docker login ghcr.io") < build_cmd.index("docker build")
    # No push requested, so no push happens, but credentials are still cleaned up.
    assert "docker push" not in build_cmd
    assert "docker logout ghcr.io" in build_cmd


def test_ghcr_registry_only_matches_ghcr() -> None:
    assert remote._ghcr_registry("ghcr.io/org/img:tag") == "ghcr.io"
    # Public/other registries and registry-less refs are left untouched.
    assert remote._ghcr_registry("nvidia/cuda:12.2.0-base") is None
    assert remote._ghcr_registry("python:3.11-slim") is None
    assert remote._ghcr_registry("quay.io/org/img:tag") is None
    assert remote._ghcr_registry(None) is None


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


def _builder_with_start(tmp_path: Path) -> remote.RemoteBuilderDefinition:
    return remote.RemoteBuilderDefinition(
        name="gcp-builder",
        ssh_target="sa@absconda-builder",
        workspace="/srv/builds",
        ssh_port=22,
        ssh_key=None,
        ssh_options=[],
        start_command=["echo", "start"],
        stop_command=None,
        lock_file=tmp_path / "builder.lock",
    )


def test_start_remote_builder_polls_ssh_until_ready(monkeypatch, tmp_path: Path) -> None:
    """A cold boot: SSH fails a few times, then succeeds — no fixed sleep race (#deploy)."""
    definition = _builder_with_start(tmp_path)
    monkeypatch.setattr(remote, "_run_subprocess", lambda *a, **k: None)
    monkeypatch.setattr(remote.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    def fake_ready(defn):
        calls["n"] += 1
        # Not ready for the first two probes, then ready.
        return (calls["n"] >= 3, "" if calls["n"] >= 3 else "port 22: connection refused")

    monkeypatch.setattr(remote, "_ssh_ready", fake_ready)

    console = Console(file=io.StringIO())
    remote.start_remote_builder(definition, console)
    assert calls["n"] == 3  # retried until ready


def test_wait_for_ssh_times_out(monkeypatch, tmp_path: Path) -> None:
    definition = _builder_with_start(tmp_path)
    monkeypatch.setattr(remote.time, "sleep", lambda _s: None)
    # A monotonic clock that jumps past the deadline after the first failed probe.
    ticks = iter([0.0, 1.0, 10_000.0, 10_001.0, 10_002.0])
    monkeypatch.setattr(remote.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        remote, "_ssh_ready", lambda defn: (False, "4003: failed to connect to backend")
    )

    console = Console(file=io.StringIO())
    with pytest.raises(remote.RemoteError, match="did not accept SSH"):
        remote._wait_for_ssh(definition, console, timeout=60, interval=1)


def test_ssh_ready_uses_noop_command(monkeypatch, tmp_path: Path) -> None:
    """_ssh_ready probes with a trivial ':' command and maps exit code to readiness."""
    definition = _builder_with_start(tmp_path)
    recorded = {}

    class _Result:
        def __init__(self, rc):
            self.returncode = rc
            self.stdout = ""
            self.stderr = "boom" if rc else ""

    def fake_run(command, **kwargs):
        recorded["command"] = command
        return _Result(0)

    monkeypatch.setattr(remote.subprocess, "run", fake_run)
    ready, detail = remote._ssh_ready(definition)
    assert ready is True and detail == ""
    assert recorded["command"][-1].endswith("bash -lc :") or recorded["command"][-1] == "bash -lc :"


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
