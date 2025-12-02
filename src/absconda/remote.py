"""Remote builder orchestration helpers."""

from __future__ import annotations

import io
import json
import os
import posixpath
import re
import shlex
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from rich.console import Console

from . import config as cfg

DEFAULT_REMOTE_CONFIG = "absconda-remote.yaml"
DEFAULT_LOCK_DIR = Path.home() / ".cache" / "absconda" / "remote"


class RemoteConfigError(Exception):
    """Raised when the remote builder config is missing or invalid."""


class RemoteError(Exception):
    """Raised when a remote build orchestration step fails."""


@dataclass(slots=True)
class RemoteBuilderDefinition:
    """Concrete configuration for connecting to a remote builder."""

    name: str
    ssh_target: str
    workspace: str
    ssh_port: int
    ssh_key: Optional[Path]
    ssh_options: List[str]
    start_command: Optional[List[str]]
    stop_command: Optional[List[str]]
    lock_file: Path
    provision_command: Optional[List[str]] = None
    health_command: Optional[List[str]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RemoteStatus:
    name: str
    reachable: bool
    busy: bool
    lock_owner: Optional[str]
    lock_path: Path
    health_ok: Optional[bool]
    ssh_error: Optional[str]
    health_error: Optional[str]


def load_remote_definition(
    name: str, *, config_path: Optional[Path] = None
) -> RemoteBuilderDefinition:
    """Resolve a remote builder definition by name."""

    path, builders = _load_builders_section(config_path)
    builder_raw = builders.get(name)
    if builder_raw is None:
        raise RemoteConfigError(
            f"Builder '{name}' not found in '{path}'. Available: {', '.join(sorted(builders))}."
        )
    if not isinstance(builder_raw, dict):
        raise RemoteConfigError(f"Builder '{name}' must be a mapping of options.")

    return _parse_builder_definition(name, builder_raw)


def list_remote_builders(config_path: Optional[Path] = None) -> Tuple[Path, List[str]]:
    path, builders = _load_builders_section(config_path)
    return path, sorted(builders.keys())


def provision_remote_builder(definition: RemoteBuilderDefinition, console: Console) -> None:
    if definition.provision_command is None:
        raise RemoteConfigError(
            f"Builder '{definition.name}' does not define a provision_command."
        )
    console.print(f"Provisioning remote builder [cyan]{definition.name}[/cyan]...")
    _run_subprocess(definition.provision_command)


def start_remote_builder(definition: RemoteBuilderDefinition, console: Console) -> None:
    if definition.start_command is None:
        raise RemoteConfigError(f"Builder '{definition.name}' does not define a start_command.")
    console.print(f"Starting remote builder [cyan]{definition.name}[/cyan]...")
    _run_subprocess(definition.start_command)
    # Wait for instance to be ready for SSH connections
    console.print("Waiting for instance to be ready...")
    time.sleep(30)


def stop_remote_builder(definition: RemoteBuilderDefinition, console: Console) -> None:
    if definition.stop_command is None:
        raise RemoteConfigError(f"Builder '{definition.name}' does not define a stop_command.")
    console.print(f"Stopping remote builder [cyan]{definition.name}[/cyan]...")
    _run_subprocess(definition.stop_command)


def check_remote_status(definition: RemoteBuilderDefinition) -> RemoteStatus:
    lock_path = definition.lock_file.expanduser()
    busy = lock_path.exists()
    lock_owner: Optional[str] = None
    if busy:
        try:
            content = lock_path.read_text(encoding="utf-8").strip()
            lock_owner = content or None
        except OSError:
            lock_owner = None

    ssh_error: Optional[str] = None
    reachable = False
    try:
        _run_subprocess(_remote_shell_command(definition, ":"))
        reachable = True
    except RemoteError as exc:
        ssh_error = str(exc)

    health_ok: Optional[bool] = None
    health_error: Optional[str] = None
    if definition.health_command:
        try:
            _run_subprocess(definition.health_command)
            health_ok = True
        except RemoteError as exc:
            health_ok = False
            health_error = str(exc)

    return RemoteStatus(
        name=definition.name,
        reachable=reachable,
        busy=busy,
        lock_owner=lock_owner,
        lock_path=lock_path,
        health_ok=health_ok,
        ssh_error=ssh_error,
        health_error=health_error,
    )


def _load_builders_section(config_path: Optional[Path]) -> Tuple[Path, dict[str, Any]]:
    """Load builder definitions from config file or XDG config directories.
    
    Search order:
    1. Explicit config_path if provided
    2. Local absconda-remote.yaml file
    3. XDG config directories (system-wide and user)
    """
    
    # If explicit path provided, use only that
    if config_path is not None:
        if not config_path.exists():
            raise RemoteConfigError(f"Config file '{config_path}' not found.")
        data = _read_remote_yaml(config_path)
        builders = data.get("builders")
        if not isinstance(builders, dict) or not builders:
            raise RemoteConfigError(f"No builders defined in '{config_path}'.")
        return config_path, builders
    
    # Try local file first
    path = _discover_remote_config_path(None)
    if path is not None:
        data = _read_remote_yaml(path)
        builders = data.get("builders")
        if isinstance(builders, dict) and builders:
            return path, builders
    
    # Fall back to XDG config
    xdg_config = cfg.load_config()
    if xdg_config.remote_builders:
        # Return a synthetic path for display purposes
        config_dirs = cfg.get_config_dirs()
        display_path = config_dirs[-1] / "config.yaml" if config_dirs else Path("XDG config")
        return display_path, xdg_config.remote_builders
    
    raise RemoteConfigError(
        "Remote builder config not found. Options:\n"
        "  1. Create 'absconda-remote.yaml' in current directory\n"
        "  2. Create '~/.config/absconda/config.yaml' with remote_builders section\n"
        "  3. Pass --remote-config <path>"
    )


def build_remote_image(
    *,
    definition: RemoteBuilderDefinition,
    dockerfile: str,
    context_path: Path,
    image_ref: str,
    push: bool,
    wait_seconds: int,
    shutdown_after: bool,
    manifest: Dict[str, Any],
    console: Console,
) -> None:
    """Send a Docker context to the remote builder and run docker build there."""

    context_path = context_path.resolve()
    if not context_path.exists():
        raise RemoteError(f"Context directory '{context_path}' does not exist.")

    console.print(
        f"Using remote builder [cyan]{definition.name}[/cyan] at {definition.ssh_target}"
    )

    with _RemoteLock(definition.lock_file, wait_seconds, console):
        if definition.start_command:
            start_remote_builder(definition, console)

        session = _RemoteSession(definition, console)
        try:
            session.execute_build(dockerfile, context_path, image_ref, push, manifest)
        finally:
            session.cleanup_local()

        if shutdown_after:
            if definition.stop_command:
                console.print(
                    f"Stopping builder '{definition.name}' (requested by --remote-off)."
                )
                _run_subprocess(definition.stop_command)
            else:
                console.print(
                    "[bold yellow]warning[/bold yellow]: --remote-off requested "
                    "but no stop_command "
                    f"is configured for builder '{definition.name}'. "
                    "Skipping shutdown."
                )


# ---------------------------------------------------------------------------
# Remote config parsing
# ---------------------------------------------------------------------------


def _discover_remote_config_path(explicit: Optional[Path]) -> Optional[Path]:
    if explicit is not None:
        candidate = explicit.expanduser()
        if not candidate.exists():
            raise RemoteConfigError(f"Remote config '{candidate}' was not found.")
        return candidate

    env_path = os.environ.get("ABSCONDA_REMOTE_CONFIG")
    if env_path:
        candidate = Path(env_path).expanduser()
        if not candidate.exists():
            raise RemoteConfigError(
                f"Remote config '{candidate}' (from ABSCONDA_REMOTE_CONFIG) was not found."
            )
        return candidate

    cwd = Path.cwd()
    for current in [cwd, *cwd.parents]:
        candidate = current / DEFAULT_REMOTE_CONFIG
        if candidate.exists():
            return candidate

    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")).expanduser()
    candidate = config_home / "absconda" / DEFAULT_REMOTE_CONFIG
    if candidate.exists():
        return candidate

    return None


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand environment variables in strings, lists, and dicts.
    
    Supports ${VAR} and ${VAR?} syntax (latter raises error if undefined).
    """
    if isinstance(obj, str):
        # Pattern matches ${VAR} or ${VAR?}
        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            required = match.group(2) == "?"
            value = os.environ.get(var_name)
            if value is None and required:
                raise RemoteConfigError(
                    f"Required environment variable '{var_name}' is not set"
                )
            return value if value is not None else match.group(0)
        
        return re.sub(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(\?)?}', replacer, obj)
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: _expand_env_vars(value) for key, value in obj.items()}
    else:
        return obj


def _read_remote_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except FileNotFoundError as exc:  # pragma: no cover - caught earlier
        raise RemoteConfigError(f"Remote config '{path}' not found.") from exc
    except yaml.YAMLError as exc:
        raise RemoteConfigError(f"Failed to parse remote config '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise RemoteConfigError("Remote config must contain a mapping at the root level.")

    # Expand environment variables in the loaded config
    data = _expand_env_vars(data)

    return data


def _parse_builder_definition(name: str, raw: dict[str, Any]) -> RemoteBuilderDefinition:
    ssh_target = _parse_ssh_target(raw)
    workspace = _require_str(raw, "workspace")
    if not workspace:
        raise RemoteConfigError(f"Builder '{name}' workspace must be non-empty.")

    ssh_port = _maybe_int(raw.get("ssh_port"), default=22)
    ssh_key = _maybe_path(raw.get("ssh_key"))
    ssh_options = _string_list(raw.get("ssh_options", []), f"builders.{name}.ssh_options")
    start_command = _parse_command(raw.get("start_command"))
    stop_command = _parse_command(raw.get("stop_command"))
    provision_command = _parse_command(raw.get("provision_command"))
    health_command = _parse_command(raw.get("health_command"))

    lock_value = raw.get("lock_file")
    if lock_value is not None:
        lock_file = Path(str(lock_value)).expanduser()
    else:
        lock_file = (DEFAULT_LOCK_DIR / f"{name}.lock").expanduser()

    known_keys = {
        "ssh_host",
        "host",
        "user",
        "workspace",
        "ssh_key",
        "ssh_port",
        "ssh_options",
        "start_command",
        "stop_command",
        "provision_command",
        "health_command",
        "lock_file",
    }
    metadata = {key: value for key, value in raw.items() if key not in known_keys}

    return RemoteBuilderDefinition(
        name=name,
        ssh_target=ssh_target,
        workspace=workspace,
        ssh_port=ssh_port,
        ssh_key=ssh_key,
        ssh_options=ssh_options,
        start_command=start_command,
        stop_command=stop_command,
        provision_command=provision_command,
        health_command=health_command,
        lock_file=lock_file,
        metadata=metadata,
    )


def _parse_ssh_target(raw: dict[str, Any]) -> str:
    ssh_host = raw.get("ssh_host")
    if ssh_host:
        if not isinstance(ssh_host, str):
            raise RemoteConfigError("ssh_host must be a string.")
        return ssh_host

    host = _require_str(raw, "host")
    user = raw.get("user")
    if user is None:
        return host
    if not isinstance(user, str):
        raise RemoteConfigError("user must be a string when provided.")
    return f"{user}@{host}"


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if value is None:
        raise RemoteConfigError(f"Missing required field '{key}'.")
    if not isinstance(value, str):
        raise RemoteConfigError(f"Field '{key}' must be a string.")
    return value


def _maybe_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    raise RemoteConfigError("Expected an integer for ssh_port.")


def _maybe_path(value: Any) -> Optional[Path]:
    if value is None:
        return None
    if isinstance(value, str):
        return Path(value).expanduser()
    raise RemoteConfigError("Paths must be strings.")


def _string_list(value: Any, path: str) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise RemoteConfigError(f"{path} must be a list of strings.")


def _parse_command(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        return shlex.split(value)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise RemoteConfigError("Commands must be strings or lists of strings.")


# ---------------------------------------------------------------------------
# Remote session + locking helpers
# ---------------------------------------------------------------------------


class _RemoteLock:
    def __init__(self, lock_file: Path, wait_seconds: int, console: Console) -> None:
        self._path = lock_file.expanduser()
        self._wait_seconds = wait_seconds
        self._console = console
        self._acquired = False
        self._token = f"{socket.gethostname()}:{os.getpid()}:{int(time.time())}"

    def __enter__(self) -> "_RemoteLock":
        start = time.monotonic()
        notice_printed = False
        while True:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(self._path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(self._token)
                self._acquired = True
                return self
            except FileExistsError as exc:
                if not notice_printed:
                    self._console.print(
                        (
                            "[yellow]Remote builder busy[/yellow]; waiting up to "
                            f"{self._wait_seconds}s..."
                        )
                    )
                    notice_printed = True
                if time.monotonic() - start >= self._wait_seconds:
                    owner = ""
                    try:
                        existing = self._path.read_text(encoding="utf-8").strip()
                        if existing:
                            owner = f" Current owner: {existing}."
                    except OSError:
                        pass
                    raise RemoteError(
                        f"Timed out waiting for remote builder lock at {self._path}.{owner}"
                    ) from exc
                time.sleep(2)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._acquired:
            try:
                self._path.unlink()
            except FileNotFoundError:  # pragma: no cover - best effort cleanup
                pass


class _RemoteSession:
    def __init__(self, definition: RemoteBuilderDefinition, console: Console) -> None:
        self.definition = definition
        self.console = console
        slug = uuid.uuid4().hex[:8]
        timestamp = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        self.run_id = f"{definition.name}-{timestamp}-{slug}"
        workspace = definition.workspace.rstrip("/") or "/"
        self.remote_dir = posixpath.join(workspace, self.run_id)
        self.remote_tar = f"{self.remote_dir}.tar.gz"
        self._tarball_path: Optional[Path] = None

    def execute_build(
        self,
        dockerfile: str,
        context_path: Path,
        image_ref: str,
        push: bool,
        manifest: Dict[str, Any],
    ) -> None:
        self.console.print("Packaging Docker context for remote transfer...")
        self._tarball_path = _create_context_tarball(context_path, dockerfile, manifest)
        self._ensure_workspace()
        self._upload_tarball()
        try:
            self._extract_context()
            self._run_build(image_ref, push)
        finally:
            self._cleanup_remote()
            # Auto-stop the builder after build completes
            if self.definition.stop_command:
                self.console.print(f"Stopping remote builder [cyan]{self.definition.name}[/cyan]...")
                try:
                    _run_subprocess(self.definition.stop_command)
                except (subprocess.CalledProcessError, OSError) as e:
                    self.console.print(f"[yellow]Warning: Failed to stop builder: {e}[/yellow]")

    def cleanup_local(self) -> None:
        if self._tarball_path and self._tarball_path.exists():
            try:
                self._tarball_path.unlink()
            except OSError:  # pragma: no cover - best effort cleanup
                pass

    # --- remote operations -------------------------------------------------

    def _ensure_workspace(self) -> None:
        cmd = _remote_shell_command(
            self.definition,
            f"set -euo pipefail && mkdir -p {shlex.quote(self.definition.workspace)}",
        )
        _run_subprocess(cmd)

    def _upload_tarball(self) -> None:
        assert self._tarball_path is not None
        cmd = _remote_scp_upload(self.definition, self._tarball_path, self.remote_tar)
        _run_subprocess(cmd)

    def _extract_context(self) -> None:
        cmd = _remote_shell_command(
            self.definition,
            " && ".join(
                [
                    "set -euo pipefail",
                    f"mkdir -p {shlex.quote(self.remote_dir)}",
                    f"tar -xzf {shlex.quote(self.remote_tar)} -C {shlex.quote(self.remote_dir)}",
                    f"rm -f {shlex.quote(self.remote_tar)}",
                ]
            ),
        )
        _run_subprocess(cmd)

    def _run_build(self, image_ref: str, push: bool) -> None:
        commands = [
            "set -euo pipefail",
            f"cd {shlex.quote(self.remote_dir)}",
            # Build the image with BuildKit
            f"DOCKER_BUILDKIT=1 docker build -t {shlex.quote(image_ref)} .",
        ]
        
        # Push if requested (credentials should already be configured via startup script)
        if push:
            commands.append(f"sudo docker push {shlex.quote(image_ref)}")
        
        cmd = _remote_shell_command(self.definition, " && ".join(commands))
        _run_subprocess(cmd)

    def _cleanup_remote(self) -> None:
        cmd = _remote_shell_command(
            self.definition,
            f"rm -rf {shlex.quote(self.remote_dir)} {shlex.quote(self.remote_tar)}",
        )
        try:
            _run_subprocess(cmd)
        except RemoteError:
            # Cleanup failures shouldn't mask the original error path.
            self.console.print(
                (
                    "[bold yellow]warning[/bold yellow]: Failed to remove "
                    f"{self.remote_dir} on remote host."
                )
            )


# ---------------------------------------------------------------------------
# Command helpers
# ---------------------------------------------------------------------------


def _remote_shell_command(defn: RemoteBuilderDefinition, payload: str, env_vars: Optional[Dict[str, str]] = None) -> List[str]:
    # Prepend environment variable exports to the payload if provided
    if env_vars:
        exports = " ".join([f"export {k}={shlex.quote(v)}" for k, v in env_vars.items()])
        payload = f"{exports} && {payload}"
    
    # For GCP builders, use gcloud compute ssh instead of manual SSH with IAP ProxyCommand
    # This avoids IAP tunnel connection issues
    metadata = defn.metadata
    if "project" in metadata and "zone" in metadata:
        # GCP builder - use gcloud compute ssh
        host = defn.ssh_target.split('@')[1] if '@' in defn.ssh_target else defn.ssh_target
        return [
            "gcloud", "compute", "ssh", host,
            f"--zone={metadata['zone']}",
            f"--project={metadata['project']}",
            "--tunnel-through-iap",
            f"--command=bash -lc {shlex.quote(payload)}"
        ]
    
    # Standard SSH for non-GCP builders
    command = ["ssh", *defn.ssh_options]
    if defn.ssh_key:
        command.extend(["-i", str(defn.ssh_key)])
    if defn.ssh_port != 22:
        command.extend(["-p", str(defn.ssh_port)])
    command.extend([defn.ssh_target, f"bash -lc {shlex.quote(payload)}"])
    return command


def _remote_scp_upload(
    defn: RemoteBuilderDefinition, source: Path, remote_path: str
) -> List[str]:
    # For GCP builders, use gcloud compute scp instead of manual scp with IAP
    metadata = defn.metadata
    if "project" in metadata and "zone" in metadata:
        host = defn.ssh_target.split('@')[1] if '@' in defn.ssh_target else defn.ssh_target
        return [
            "gcloud", "compute", "scp", str(source),
            f"{host}:{remote_path}",
            f"--zone={metadata['zone']}",
            f"--project={metadata['project']}",
            "--tunnel-through-iap"
        ]
    
    # Standard SCP for non-GCP builders
    command = ["scp", *defn.ssh_options]
    if defn.ssh_key:
        command.extend(["-i", str(defn.ssh_key)])
    if defn.ssh_port != 22:
        command.extend(["-P", str(defn.ssh_port)])
    command.extend([str(source), f"{defn.ssh_target}:{remote_path}"])
    return command


def _run_subprocess(command: List[str], *, cwd: Optional[Path] = None) -> None:
    try:
        subprocess.run(command, check=True, cwd=str(cwd) if cwd else None, env=os.environ.copy())
    except FileNotFoundError as exc:
        raise RemoteError(f"Command '{command[0]}' not found: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        raise RemoteError(
            f"Command '{' '.join(command)}' failed with exit code {exc.returncode}."
        ) from exc


# ---------------------------------------------------------------------------
# Context packaging helpers
# ---------------------------------------------------------------------------


def _create_context_tarball(
    context_dir: Path, dockerfile: str, manifest: Dict[str, Any]
) -> Path:
    context_dir = context_dir.resolve()
    if not context_dir.exists():
        raise RemoteError(f"Context directory '{context_dir}' does not exist.")

    handle = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
    handle.close()
    tar_path = Path(handle.name)

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    with tarfile.open(tar_path, "w:gz") as archive:
        archive.add(str(context_dir), arcname=".")
        _tar_add_bytes(archive, "Dockerfile", dockerfile.encode("utf-8"))
        _tar_add_bytes(archive, "absconda-manifest.json", manifest_bytes)

    return tar_path


def _tar_add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(time.time())
    archive.addfile(info, io.BytesIO(data))