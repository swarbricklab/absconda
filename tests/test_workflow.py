"""Tests for the ``absconda workflow`` subcommand and supporting module."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from absconda import workflow as wf
from absconda.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "snakemake_basic"


@pytest.fixture
def workflow_dir(tmp_path: Path) -> Path:
    """Copy the snakemake_basic fixture into a tmpdir we can mutate."""
    dest = tmp_path / "wf"
    shutil.copytree(FIXTURES, dest)
    return dest


# ---------------------------------------------------------------------------
# workflow.py — direct unit tests
# ---------------------------------------------------------------------------


def test_discover_snakemake_files(workflow_dir: Path) -> None:
    files = wf.discover_snakemake_files(workflow_dir)
    names = {f.name for f in files}
    assert "Snakefile" in names
    assert "rules.smk" in names


def test_scan_dedupes_shared_envs(workflow_dir: Path) -> None:
    references, envs = wf.scan_snakemake(workflow_dir)

    # 4 references: fastqc + multiqc + align + bonus
    assert len(references) == 4

    # 2 unique envs (qc.yaml shared by 3 rules)
    assert len(envs) == 2
    by_name = {e.env_name: e for e in envs}
    assert set(by_name) == {"qc", "align"}
    assert set(by_name["qc"].rules) == {"fastqc", "multiqc", "bonus"}
    assert by_name["align"].rules == ["align"]


def test_scan_raises_on_missing_env(tmp_path: Path) -> None:
    snake = tmp_path / "Snakefile"
    snake.write_text(
        'rule x:\n    conda: "envs/missing.yaml"\n    shell: "echo"\n',
        encoding="utf-8",
    )
    with pytest.raises(wf.WorkflowError, match="does not exist"):
        wf.scan_snakemake(tmp_path)


def test_build_and_save_load_manifest_roundtrip(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    out = workflow_dir / "absconda-workflow.yaml"
    wf.save_manifest(manifest, out)

    loaded = wf.load_manifest(out)
    assert loaded.workflow_type == "snakemake"
    assert len(loaded.envs) == 2
    assert {e.env_name for e in loaded.envs} == {"qc", "align"}


def test_apply_container_replacements_inserts_block(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    for entry in manifest.envs:
        entry.image = f"ghcr.io/example/{entry.env_name}"
        entry.tag = "20260528"
        entry.image_ref = f"{entry.image}:{entry.tag}"

    changes = wf.apply_container_replacements(workflow_dir, manifest)
    snakefile_change = next(c for c in changes if c.file.name == "Snakefile")
    assert snakefile_change.changed
    assert wf.MARKER_COMMENT in snakefile_change.updated
    assert 'container: "docker://ghcr.io/example/qc:20260528"' in snakefile_change.updated
    assert 'container: "docker://ghcr.io/example/align:20260528"' in snakefile_change.updated
    # Original conda lines should be commented, not removed.
    assert '# conda: "envs/qc.yaml"' in snakefile_change.updated
    assert '# conda: "envs/align.yaml"' in snakefile_change.updated


def test_apply_is_idempotent(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    for entry in manifest.envs:
        entry.image_ref = f"ghcr.io/example/{entry.env_name}:v1"

    changes = wf.apply_container_replacements(workflow_dir, manifest)
    for change in changes:
        change.file.write_text(change.updated, encoding="utf-8")

    # Bump the tag and reapply — should update in place, not stack blocks.
    for entry in manifest.envs:
        entry.image_ref = f"ghcr.io/example/{entry.env_name}:v2"

    changes2 = wf.apply_container_replacements(workflow_dir, manifest)
    snakefile_change = next(c for c in changes2 if c.file.name == "Snakefile")
    assert snakefile_change.updated.count(wf.MARKER_COMMENT) == 3  # fastqc, multiqc, align
    assert 'container: "docker://ghcr.io/example/qc:v2"' in snakefile_change.updated
    assert 'container: "docker://ghcr.io/example/qc:v1"' not in snakefile_change.updated


def test_apply_errors_without_image_ref(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    # No image_ref set on entries.
    with pytest.raises(wf.WorkflowError, match="No image_ref"):
        wf.apply_container_replacements(workflow_dir, manifest)


def test_multiline_conda_directive_is_rewritten(tmp_path: Path) -> None:
    """Snakemake allows ``conda:`` and the YAML path on two separate lines."""
    envs = tmp_path / "envs"
    envs.mkdir()
    (envs / "tools.yaml").write_text(
        "name: tools\nchannels: [conda-forge]\ndependencies: [python=3.11]\n",
        encoding="utf-8",
    )
    snake = tmp_path / "Snakefile"
    snake.write_text(
        "rule run_tool:\n"
        '    input: "in.txt"\n'
        '    output: "out.txt"\n'
        "    conda:\n"
        '        "envs/tools.yaml"\n'
        '    shell: "echo {input} > {output}"\n',
        encoding="utf-8",
    )

    references, envs_entries = wf.scan_snakemake(tmp_path)
    assert len(references) == 1
    assert references[0].rule == "run_tool"
    assert len(envs_entries) == 1
    entry = envs_entries[0]
    entry.image_ref = "ghcr.io/example/tools:v1"

    manifest = wf.build_manifest(tmp_path)
    manifest.envs[0].image_ref = "ghcr.io/example/tools:v1"
    changes = wf.apply_container_replacements(tmp_path, manifest)
    snake_change = next(c for c in changes if c.file.name == "Snakefile")
    assert snake_change.changed

    expected = (
        "rule run_tool:\n"
        '    input: "in.txt"\n'
        '    output: "out.txt"\n'
        "    # absconda: replaced conda env with container\n"
        "    # conda:\n"
        '        # "envs/tools.yaml"\n'
        '    container: "docker://ghcr.io/example/tools:v1"\n'
        '    shell: "echo {input} > {output}"\n'
    )
    assert snake_change.updated == expected

    # Revert restores the multi-line form byte-identically.
    snake.write_text(snake_change.updated, encoding="utf-8")
    reverts = wf.revert_container_replacements(tmp_path)
    snake_revert = next(c for c in reverts if c.file.name == "Snakefile")
    assert snake_revert.updated == snake_change.original


def test_revert_restores_conda_directive(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    for entry in manifest.envs:
        entry.image_ref = f"ghcr.io/example/{entry.env_name}:v1"

    original_snakefile = (workflow_dir / "Snakefile").read_text(encoding="utf-8")

    changes = wf.apply_container_replacements(workflow_dir, manifest)
    for change in changes:
        change.file.write_text(change.updated, encoding="utf-8")

    reverts = wf.revert_container_replacements(workflow_dir)
    for change in reverts:
        change.file.write_text(change.updated, encoding="utf-8")

    restored = (workflow_dir / "Snakefile").read_text(encoding="utf-8")
    assert restored == original_snakefile


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _invoke(args: list[str], cwd: Path, env_extra: dict[str, str] | None = None):
    runner = CliRunner()
    base_env = {"HOME": str(cwd)}
    if env_extra:
        base_env.update(env_extra)
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(cwd)
        return runner.invoke(app, args, env=base_env)
    finally:
        os.chdir(old_cwd)


def test_cli_scan_writes_manifest(workflow_dir: Path) -> None:
    result = _invoke(["workflow", "scan", str(workflow_dir)], workflow_dir)
    assert result.exit_code == 0, result.output
    manifest_path = workflow_dir / "absconda-workflow.yaml"
    assert manifest_path.exists()
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert data["workflow"]["type"] == "snakemake"
    assert len(data["envs"]) == 2


def test_cli_scan_refuses_overwrite_without_force(workflow_dir: Path) -> None:
    (workflow_dir / "absconda-workflow.yaml").write_text("placeholder", encoding="utf-8")
    result = _invoke(["workflow", "scan", str(workflow_dir)], workflow_dir)
    assert result.exit_code != 0
    assert "already exists" in result.output

    result = _invoke(
        ["workflow", "scan", str(workflow_dir), "--force"],
        workflow_dir,
    )
    assert result.exit_code == 0, result.output


def test_cli_scan_dry_run_does_not_write(workflow_dir: Path) -> None:
    result = _invoke(["workflow", "scan", str(workflow_dir), "--dry-run"], workflow_dir)
    assert result.exit_code == 0
    assert not (workflow_dir / "absconda-workflow.yaml").exists()


def test_cli_update_requires_manifest(workflow_dir: Path) -> None:
    result = _invoke(["workflow", "update", str(workflow_dir)], workflow_dir)
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_cli_update_dry_run_prints_diff(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    for entry in manifest.envs:
        entry.image_ref = f"ghcr.io/example/{entry.env_name}:v1"
    wf.save_manifest(manifest, workflow_dir / "absconda-workflow.yaml")

    result = _invoke(["workflow", "update", str(workflow_dir), "--dry-run"], workflow_dir)
    assert result.exit_code == 0, result.output
    assert "container:" in result.output
    assert wf.MARKER_COMMENT in result.output
    # Files unchanged on dry run.
    snakefile_text = (workflow_dir / "Snakefile").read_text(encoding="utf-8")
    assert wf.MARKER_COMMENT not in snakefile_text


def test_cli_update_applies_and_reverts(workflow_dir: Path) -> None:
    manifest = wf.build_manifest(workflow_dir)
    for entry in manifest.envs:
        entry.image_ref = f"ghcr.io/example/{entry.env_name}:v1"
    wf.save_manifest(manifest, workflow_dir / "absconda-workflow.yaml")

    original = (workflow_dir / "Snakefile").read_text(encoding="utf-8")

    result = _invoke(["workflow", "update", str(workflow_dir)], workflow_dir)
    assert result.exit_code == 0, result.output
    updated = (workflow_dir / "Snakefile").read_text(encoding="utf-8")
    assert wf.MARKER_COMMENT in updated
    assert 'container: "docker://ghcr.io/example/qc:v1"' in updated

    result = _invoke(["workflow", "update", str(workflow_dir), "--revert"], workflow_dir)
    assert result.exit_code == 0, result.output
    reverted = (workflow_dir / "Snakefile").read_text(encoding="utf-8")
    assert reverted == original


def test_cli_containerise_calls_publish_per_unique_env(
    monkeypatch: pytest.MonkeyPatch, workflow_dir: Path
) -> None:
    """Verify containerise routes each unique env to _publish_and_get_ref once."""
    from absconda import cli as cli_mod

    calls: list[dict[str, Any]] = []

    def fake_publish(**kwargs: Any) -> str:
        calls.append(kwargs)
        env_path = kwargs["file"]
        name = env_path.stem
        return f"ghcr.io/test/{name}:20260528"

    monkeypatch.setattr(cli_mod, "_publish_and_get_ref", fake_publish)

    result = _invoke(
        ["workflow", "containerise", str(workflow_dir)],
        workflow_dir,
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 2  # one per unique env, not per reference

    manifest_path = workflow_dir / "absconda-workflow.yaml"
    manifest = wf.load_manifest(manifest_path)
    refs = {e.env_name: e.image_ref for e in manifest.envs}
    assert refs["qc"] == "ghcr.io/test/qc:20260528"
    assert refs["align"] == "ghcr.io/test/align:20260528"


def test_cli_containerise_skips_already_published(
    monkeypatch: pytest.MonkeyPatch, workflow_dir: Path
) -> None:
    from absconda import cli as cli_mod

    # Pre-populate manifest with one env already published.
    manifest = wf.build_manifest(workflow_dir)
    qc_entry = next(e for e in manifest.envs if e.env_name == "qc")
    qc_entry.image_ref = "ghcr.io/test/qc:existing"
    qc_entry.image = "ghcr.io/test/qc"
    qc_entry.tag = "existing"
    wf.save_manifest(manifest, workflow_dir / "absconda-workflow.yaml")

    calls: list[dict[str, Any]] = []

    def fake_publish(**kwargs: Any) -> str:
        calls.append(kwargs)
        return f"ghcr.io/test/{kwargs['file'].stem}:fresh"

    monkeypatch.setattr(cli_mod, "_publish_and_get_ref", fake_publish)

    result = _invoke(["workflow", "containerise", str(workflow_dir)], workflow_dir)
    assert result.exit_code == 0, result.output
    assert len(calls) == 1  # only align gets built
    assert calls[0]["file"].name == "align.yaml"
