"""Integration-style smoke tests for the Absconda CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = PROJECT_ROOT / "examples"
FIXTURES_DIR = Path(__file__).parent / "fixtures"
BUSYBOX_TEMPLATE = FIXTURES_DIR / "busybox-template.j2"
RENV_LOCK = FIXTURES_DIR / "sample-renv.lock"

pytestmark = pytest.mark.integration


def _base_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = os.environ.get("HOME", str(tmp_path))
    env.setdefault("DOCKER_BUILDKIT", "1")
    src_path = PROJECT_ROOT / "src"
    existing = env.get("PYTHONPATH")
    if existing:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = str(src_path)
    return env


def test_generate_minimal_example_via_subprocess(tmp_path: Path) -> None:
    """Run the CLI through `python -m absconda` to mirror user usage."""

    output_path = tmp_path / "Dockerfile.generated"
    command = [
        sys.executable,
        "-m",
        "absconda",
        "generate",
        "--file",
        str(EXAMPLES_DIR / "minimal-env.yaml"),
        "--output",
        str(output_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=_base_env(tmp_path),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()

    dockerfile_text = output_path.read_text(encoding="utf-8")
    assert "mambaorg/micromamba" in dockerfile_text
    assert "rich==13.7.1" in dockerfile_text


def _ensure_docker_ready() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not available on this host.")

    probe = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if probe.returncode != 0:
        pytest.skip("Docker daemon is not available (docker info failed).")


def _ensure_buildkit_ready(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile.buildkit-probe"
    dockerfile.write_text(
        "FROM scratch\nCOPY <<'EOF' /probe\nhello\nEOF\n",
        encoding="utf-8",
    )

    image_ref = f"absconda/buildkit-probe:{uuid.uuid4().hex[:8]}"

    env = os.environ.copy()
    env.setdefault("DOCKER_BUILDKIT", "1")

    try:
        probe = subprocess.run(
            [
                "docker",
                "build",
                "-t",
                image_ref,
                "-f",
                str(dockerfile),
                str(tmp_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=env,
        )
        if probe.returncode != 0:
            pytest.skip("Docker BuildKit inline COPY is unavailable on this host.")
    finally:
        subprocess.run(["docker", "image", "rm", "-f", image_ref], check=False)


@pytest.mark.skipif(not BUSYBOX_TEMPLATE.exists(), reason="Busybox template missing")
def test_build_command_creates_busybox_image(tmp_path: Path) -> None:
    """Exercise `absconda build` against a tiny BusyBox template via Docker."""

    _ensure_docker_ready()

    env = _base_env(tmp_path)
    context_dir = tmp_path / "build-context"
    context_dir.mkdir()

    repository = "absconda/test-integration"
    tag = f"busybox-{uuid.uuid4().hex[:8]}"
    image_ref = f"{repository}:{tag}"

    command = [
        sys.executable,
        "-m",
        "absconda",
        "build",
        "--repository",
        repository,
        "--tag",
        tag,
        "--file",
        str(EXAMPLES_DIR / "minimal-env.yaml"),
        "--template",
        str(BUSYBOX_TEMPLATE),
        "--context",
        str(context_dir),
    ]

    try:
        subprocess.run(command, check=True, env=env)

        inspect = subprocess.run(
            ["docker", "image", "inspect", image_ref],
            capture_output=True,
            text=True,
            check=False,
        )
        assert inspect.returncode == 0, inspect.stderr
    finally:
        subprocess.run(["docker", "image", "rm", "-f", image_ref], check=False)


@pytest.mark.skipif(not RENV_LOCK.exists(), reason="renv lock fixture missing")
def test_build_with_renv_restores_packages(tmp_path: Path) -> None:
    """Build the renv example image and verify R packages are ready at runtime."""

    _ensure_docker_ready()
    _ensure_buildkit_ready(tmp_path)

    env = _base_env(tmp_path)

    repository = "absconda/test-integration"
    tag = f"renv-{uuid.uuid4().hex[:8]}"
    image_ref = f"{repository}:{tag}"

    command = [
        sys.executable,
        "-m",
        "absconda",
        "build",
        "--repository",
        repository,
        "--tag",
        tag,
        "--file",
        str(EXAMPLES_DIR / "renv-env.yaml"),
        "--renv-lock",
        str(RENV_LOCK),
        "--context",
        str(PROJECT_ROOT),
    ]

    try:
        subprocess.run(command, check=True, env=env)

        run = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                image_ref,
                "R",
                "-q",
                "-e",
                'library(dplyr); cat("renv ok\\n")',
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert run.returncode == 0, run.stderr
        assert "renv ok" in run.stdout
    finally:
        subprocess.run(["docker", "image", "rm", "-f", image_ref], check=False)
