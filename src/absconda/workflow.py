"""Snakemake workflow scanning and container substitution.

Discovers ``conda:`` directives across a Snakemake project, hashes the
referenced env files (so two rules pointing at the same env collapse to one
image), and rewrites the workflow to use ``container:`` directives once the
images have been built.

The three operations are exposed as composable steps via a YAML manifest
(``absconda-workflow.yaml``) so that ``scan``/``containerise``/``update`` can
be run independently or chained via ``workflow apply``.
"""

from __future__ import annotations

import datetime
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml


class WorkflowError(Exception):
    """Raised for malformed manifests or unrecoverable scan/update failures."""


SNAKEMAKE_GLOBS = ("Snakefile", "*.smk", "workflow/Snakefile", "workflow/*.smk")

# Captures ``conda: "envs/foo.yaml"`` or ``conda: 'envs/foo.yaml'``.
# We do not match unquoted forms or expressions (``conda: f"...".format(...)``).
_CONDA_RE = re.compile(
    r"""(?P<indent>^[ \t]*)conda:\s*['"](?P<path>[^'"]+\.ya?ml)['"]\s*$""",
    re.MULTILINE,
)

# Rule headers used to attach a ``conda:`` reference back to the rule it lives in.
_RULE_RE = re.compile(r"^(?P<indent>[ \t]*)rule\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:")

MARKER_COMMENT = "# absconda: replaced conda env with container"


@dataclass
class CondaReference:
    """A single ``conda:`` directive discovered in a workflow file."""

    file: Path
    line: int  # 1-indexed
    env_file: Path  # absolute path on disk
    env_file_rel: str  # path string as written in the workflow
    rule: Optional[str]
    indent: str


@dataclass
class EnvEntry:
    """Manifest entry: one image per unique env file (deduped by content hash)."""

    hash: str
    env_file: str  # relative to workflow root
    env_name: str
    rules: list[str] = field(default_factory=list)
    image: Optional[str] = None  # repository, e.g. ghcr.io/org/qc
    tag: Optional[str] = None
    image_ref: Optional[str] = None


@dataclass
class Manifest:
    """Workflow containerisation manifest persisted as YAML on disk."""

    workflow_type: str
    workflow_root: str
    scanned_at: str
    envs: list[EnvEntry] = field(default_factory=list)
    # references kept for `update` so we don't need to re-scan
    references: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Manifest IO
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> Manifest:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowError(f"Could not read manifest '{path}': {exc}") from exc

    workflow = data.get("workflow") or {}
    envs_raw = data.get("envs") or []
    envs = [
        EnvEntry(
            hash=entry["hash"],
            env_file=entry["env_file"],
            env_name=entry.get("env_name", ""),
            rules=list(entry.get("rules") or []),
            image=entry.get("image"),
            tag=entry.get("tag"),
            image_ref=entry.get("image_ref"),
        )
        for entry in envs_raw
    ]
    return Manifest(
        workflow_type=workflow.get("type", "snakemake"),
        workflow_root=workflow.get("root", "."),
        scanned_at=workflow.get("scanned_at", ""),
        envs=envs,
        references=list(data.get("references") or []),
    )


def save_manifest(manifest: Manifest, path: Path) -> None:
    payload = {
        "workflow": {
            "type": manifest.workflow_type,
            "root": manifest.workflow_root,
            "scanned_at": manifest.scanned_at,
        },
        "envs": [
            {
                "hash": entry.hash,
                "env_file": entry.env_file,
                "env_name": entry.env_name,
                "rules": entry.rules,
                "image": entry.image,
                "tag": entry.tag,
                "image_ref": entry.image_ref,
            }
            for entry in manifest.envs
        ],
        "references": manifest.references,
    }
    text = yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def discover_snakemake_files(root: Path) -> list[Path]:
    """Return every Snakefile/*.smk under root, deduped and sorted."""
    seen: set[Path] = set()
    for pattern in SNAKEMAKE_GLOBS:
        for match in root.glob(pattern):
            if match.is_file():
                seen.add(match.resolve())
    # Recursive walk for nested workflow dirs.
    for match in root.rglob("*.smk"):
        if match.is_file():
            seen.add(match.resolve())
    snakefile_root = root / "Snakefile"
    if snakefile_root.is_file():
        seen.add(snakefile_root.resolve())
    return sorted(seen)


def _find_enclosing_rule(text: str, line_index: int) -> Optional[str]:
    """Walk backwards from ``line_index`` (0-indexed) to find the nearest rule header."""
    lines = text.splitlines()
    for i in range(min(line_index, len(lines) - 1), -1, -1):
        match = _RULE_RE.match(lines[i])
        if match:
            return match.group("name")
    return None


def _normalise_env_text(text: str) -> str:
    """Normalise an env YAML for stable content hashing across whitespace edits."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        # Fall back to raw text if YAML is malformed; user will see a load
        # error later via the build step.
        return text.strip()
    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False)


def _hash_env_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(_normalise_env_text(text).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _extract_env_name(env_path: Path) -> str:
    """Pull the ``name:`` field from a conda env YAML, falling back to the filename stem."""
    try:
        data = yaml.safe_load(env_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return env_path.stem
    name = data.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return env_path.stem


def scan_snakemake(root: Path) -> tuple[list[CondaReference], list[EnvEntry]]:
    """Scan a Snakemake project, returning references and deduped env entries."""
    root = root.resolve()
    references: list[CondaReference] = []
    by_hash: dict[str, EnvEntry] = {}

    for snakefile in discover_snakemake_files(root):
        try:
            text = snakefile.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowError(f"Could not read '{snakefile}': {exc}") from exc

        for match in _CONDA_RE.finditer(text):
            env_rel = match.group("path")
            indent = match.group("indent")
            # Line number of the match start.
            line_no = text.count("\n", 0, match.start()) + 1
            rule_name = _find_enclosing_rule(text, line_no - 1)

            env_abs = (snakefile.parent / env_rel).resolve()
            if not env_abs.is_file():
                raise WorkflowError(
                    f"Referenced env file does not exist: {env_rel} "
                    f"(from {snakefile.relative_to(root)}:{line_no})"
                )

            references.append(
                CondaReference(
                    file=snakefile,
                    line=line_no,
                    env_file=env_abs,
                    env_file_rel=env_rel,
                    rule=rule_name,
                    indent=indent,
                )
            )

            env_hash = _hash_env_file(env_abs)
            if env_hash not in by_hash:
                by_hash[env_hash] = EnvEntry(
                    hash=env_hash,
                    env_file=str(env_abs.relative_to(root)),
                    env_name=_extract_env_name(env_abs),
                )
            entry = by_hash[env_hash]
            if rule_name and rule_name not in entry.rules:
                entry.rules.append(rule_name)

    envs = sorted(by_hash.values(), key=lambda e: e.env_file)
    return references, envs


def build_manifest(root: Path) -> Manifest:
    references, envs = scan_snakemake(root)
    root_resolved = root.resolve()
    return Manifest(
        workflow_type="snakemake",
        workflow_root=str(root_resolved),
        scanned_at=datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        envs=envs,
        references=[
            {
                "file": str(ref.file.relative_to(root_resolved)),
                "line": ref.line,
                "env_file": str(ref.env_file.relative_to(root_resolved)),
                "rule": ref.rule,
            }
            for ref in references
        ],
    )


# ---------------------------------------------------------------------------
# Update (rewrite workflow files)
# ---------------------------------------------------------------------------


@dataclass
class FileChange:
    file: Path
    original: str
    updated: str

    @property
    def changed(self) -> bool:
        return self.original != self.updated


def _env_lookup(manifest: Manifest, root: Path) -> dict[str, EnvEntry]:
    """Map absolute env-file paths to manifest entries."""
    return {str((root / entry.env_file).resolve()): entry for entry in manifest.envs}


def apply_container_replacements(
    root: Path,
    manifest: Manifest,
    *,
    require_image_ref: bool = True,
) -> list[FileChange]:
    """Produce rewritten workflow files swapping conda: for container:.

    Behaviour: comments out the original ``conda:`` line and inserts a
    ``container: "docker://<ref>"`` line at the same indent, prefixed with a
    marker comment. Idempotent on re-runs: an existing block with the marker
    is updated in place rather than duplicated.
    """
    root = root.resolve()
    lookup = _env_lookup(manifest, root)
    changes: list[FileChange] = []

    for snakefile in discover_snakemake_files(root):
        original = snakefile.read_text(encoding="utf-8")
        updated = _rewrite_file(
            original,
            snakefile.parent,
            lookup,
            require_image_ref=require_image_ref,
        )
        changes.append(FileChange(file=snakefile, original=original, updated=updated))

    return changes


def _rewrite_file(
    text: str,
    file_dir: Path,
    lookup: dict[str, EnvEntry],
    *,
    require_image_ref: bool,
) -> str:
    """Apply the replacement to a single file's text."""

    lines = text.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Detect an existing absconda marker block and refresh the container line.
        if MARKER_COMMENT in line and _is_marker_line(line):
            marker_indent = line[: len(line) - len(line.lstrip())]
            # Expect: marker / commented conda / container
            if (
                i + 2 < len(lines)
                and _is_commented_conda(lines[i + 1])
                and _is_container_line(lines[i + 2])
            ):
                env_match = _match_conda_line(_uncomment(lines[i + 1]))
                if env_match:
                    env_rel = env_match.group("path")
                    env_abs = (file_dir / env_rel).resolve()
                    entry = lookup.get(str(env_abs))
                    if entry and entry.image_ref:
                        output.append(line)
                        output.append(lines[i + 1])
                        output.append(f'{marker_indent}container: "docker://{entry.image_ref}"\n')
                        i += 3
                        continue
                # Fall through if we cannot refresh — leave block untouched.
                output.append(line)
                output.append(lines[i + 1])
                output.append(lines[i + 2])
                i += 3
                continue

        match = _match_conda_line(line)
        if match:
            env_rel = match.group("path")
            indent = match.group("indent")
            env_abs = (file_dir / env_rel).resolve()
            entry = lookup.get(str(env_abs))
            if entry is None or (require_image_ref and not entry.image_ref):
                if require_image_ref:
                    raise WorkflowError(
                        f"No image_ref in manifest for env file '{env_rel}'. "
                        f"Run 'absconda workflow containerise' first."
                    )
                output.append(line)
                i += 1
                continue

            newline = _detect_newline(line)
            quote = match.group("quote")
            output.append(f"{indent}{MARKER_COMMENT}{newline}")
            output.append(f"{indent}# conda: {quote}{env_rel}{quote}{newline}")
            output.append(f'{indent}container: "docker://{entry.image_ref}"{newline}')
            i += 1
            continue

        output.append(line)
        i += 1

    return "".join(output)


def revert_container_replacements(root: Path) -> list[FileChange]:
    """Undo ``apply_container_replacements`` by stripping marker blocks."""
    root = root.resolve()
    changes: list[FileChange] = []
    for snakefile in discover_snakemake_files(root):
        original = snakefile.read_text(encoding="utf-8")
        updated = _revert_file(original)
        changes.append(FileChange(file=snakefile, original=original, updated=updated))
    return changes


def _revert_file(text: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if (
            MARKER_COMMENT in line
            and _is_marker_line(line)
            and i + 2 < len(lines)
            and _is_commented_conda(lines[i + 1])
            and _is_container_line(lines[i + 2])
        ):
            # Re-emit the conda line uncommented.
            output.append(_uncomment(lines[i + 1]))
            i += 3
            continue
        output.append(line)
        i += 1
    return "".join(output)


def _match_conda_line(line: str) -> Optional[re.Match[str]]:
    """Match a single line (without relying on MULTILINE anchors)."""
    stripped = line.rstrip("\r\n")
    return re.match(
        r"""(?P<indent>^[ \t]*)conda:\s*(?P<quote>['"])(?P<path>[^'"]+\.ya?ml)(?P=quote)\s*$""",
        stripped,
    )


def _detect_newline(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return "\n"


def _is_marker_line(line: str) -> bool:
    return line.lstrip().startswith(MARKER_COMMENT)


def _is_commented_conda(line: str) -> bool:
    stripped = line.lstrip()
    if not stripped.startswith("#"):
        return False
    return bool(_match_conda_line(_uncomment(line)))


def _is_container_line(line: str) -> bool:
    return bool(re.match(r"^\s*container:\s*['\"]docker://", line))


def _uncomment(line: str) -> str:
    """Strip a leading ``# `` (or ``#``) from a commented line, preserving indent."""
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    if stripped.startswith("# "):
        return indent + stripped[2:]
    if stripped.startswith("#"):
        return indent + stripped[1:]
    return line


# ---------------------------------------------------------------------------
# Diff helpers
# ---------------------------------------------------------------------------


def unified_diff(change: FileChange) -> str:
    import difflib

    rel = str(change.file)
    diff = difflib.unified_diff(
        change.original.splitlines(keepends=True),
        change.updated.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    return "".join(diff)


def iter_changed(changes: Iterable[FileChange]) -> Iterable[FileChange]:
    return (c for c in changes if c.changed)
