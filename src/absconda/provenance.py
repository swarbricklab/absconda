"""Build provenance, image digests, lockfiles, and GHCR visibility helpers.

These back the publish-time features in issues #69 (image digest + lockfile),
#70 (OCI/absconda provenance labels + optional embedded Dockerfile) and #71
(GHCR package visibility). The pure helpers here (label computation, hashing,
digest parsing, lockfile merge, registry-ref parsing, visibility endpoints) are
kept free of side effects so they can be unit-tested without Docker or network;
the subprocess-driven callers live in ``cli.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Label namespaces.
_OCI = "org.opencontainers.image"
_ABS = "org.absconda"

# The image reference digest, e.g. "ghcr.io/org/name@sha256:abc...".
_DIGEST_RE = re.compile(r"\bsha256:[0-9a-f]{64}\b")
# `docker push` trailing line: "<tag>: digest: sha256:... size: 1234".
_PUSH_DIGEST_RE = re.compile(r"digest:\s*(sha256:[0-9a-f]{64})")


def sha256_text(text: str) -> str:
    """Return the ``sha256:...`` digest of ``text`` (utf-8)."""
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_timestamp() -> str:
    """Return an RFC3339 build time, honoring ``SOURCE_DATE_EPOCH`` when set.

    Respecting ``SOURCE_DATE_EPOCH`` lets a caller pin the ``created`` label for
    reproducible image builds. Falls back to the current UTC time otherwise.
    """
    import datetime

    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and epoch.strip().isdigit():
        dt = datetime.datetime.fromtimestamp(int(epoch), tz=datetime.timezone.utc)
    else:
        dt = datetime.datetime.now(datetime.timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def build_provenance_labels(
    *,
    env_name: str,
    absconda_version: str,
    env_file_name: Optional[str] = None,
    env_file_text: Optional[str] = None,
    snapshot_text: Optional[str] = None,
    builder_base: Optional[str] = None,
    runtime_base: Optional[str] = None,
    base_image: Optional[str] = None,
    created: Optional[str] = None,
    git_revision: Optional[str] = None,
    git_source: Optional[str] = None,
) -> Dict[str, str]:
    """Compute the OCI + absconda provenance labels for an image (issue #70).

    All inputs are optional so the same function serves conda/tarball/requirements
    builds; a label is only emitted when its source value is present. The result
    is deterministic given its inputs (``created``/git are passed in, not read
    here) so it is safe to render into the Dockerfile and to unit-test.
    """
    labels: Dict[str, str] = {
        f"{_OCI}.title": env_name,
        f"{_ABS}.version": absconda_version,
    }
    if created:
        labels[f"{_OCI}.created"] = created
    if git_source:
        labels[f"{_OCI}.source"] = git_source
    if git_revision:
        labels[f"{_OCI}.revision"] = git_revision
    if base_image:
        labels[f"{_OCI}.base.name"] = base_image
        labels[f"{_ABS}.base-image"] = base_image
    if builder_base:
        labels[f"{_ABS}.builder-base"] = builder_base
    if runtime_base:
        labels[f"{_ABS}.runtime-base"] = runtime_base
    if env_file_name:
        labels[f"{_ABS}.env-file"] = env_file_name
    if env_file_text is not None:
        labels[f"{_ABS}.env-sha256"] = sha256_text(env_file_text)
    if snapshot_text is not None:
        labels[f"{_ABS}.snapshot-sha256"] = sha256_text(snapshot_text)
    return labels


def dockerfile_embed_label(dockerfile_text: str) -> str:
    """Return a ``LABEL`` line embedding ``dockerfile_text`` base64-encoded.

    The rendered Dockerfile is base64-encoded (not quoted inline) to avoid
    newline/quote escaping and the circularity of embedding the file within
    itself — the value encodes the Dockerfile *as rendered before this line is
    appended*. Decode with ``base64 -d`` on ``org.absconda.dockerfile.base64``.
    """
    encoded = base64.b64encode(dockerfile_text.encode("utf-8")).decode("ascii")
    return f'LABEL {_ABS}.dockerfile.base64="{encoded}"'


def parse_push_digest(push_output: str) -> Optional[str]:
    """Extract the ``sha256:...`` digest from ``docker push`` stdout, if present."""
    match = _PUSH_DIGEST_RE.search(push_output)
    return match.group(1) if match else None


def select_repo_digest(repo_digests: List[str], image_ref: str) -> Optional[str]:
    """Pick the ``repo@sha256:...`` entry matching ``image_ref``'s repository.

    ``docker inspect`` reports ``RepoDigests`` as ``repo@sha256:...`` strings;
    there may be several if the local image is tagged for multiple repos.
    """
    repo = image_ref.split("@", 1)[0].rsplit(":", 1)[0]
    for entry in repo_digests:
        if entry.split("@", 1)[0] == repo:
            return entry
    # Fall back to the sole entry when the repo can't be matched exactly.
    return repo_digests[0] if len(repo_digests) == 1 else None


def digest_reference(image_ref: str, digest: str) -> str:
    """Compose a ``repo@sha256:...`` reference from a tag ref and a digest.

    ``digest`` may be a bare ``sha256:...`` or an already-complete ``repo@sha...``.
    """
    if "@sha256:" in digest:
        return digest
    repo = image_ref.split("@", 1)[0].rsplit(":", 1)[0]
    return f"{repo}@{digest}"


def is_ghcr(image_ref: str) -> bool:
    return image_ref.split("/", 1)[0].lower() == "ghcr.io"


def ghcr_owner_and_package(image_ref: str) -> Optional[Tuple[str, str]]:
    """Split a ``ghcr.io/<owner>/<package...>`` ref into ``(owner, package)``.

    GHCR package names may contain ``/`` (e.g. ``ghcr.io/org/team/tool``); the
    GitHub packages API expects the full ``team/tool`` as the (URL-encoded)
    package name. Returns ``None`` for non-ghcr or malformed refs.
    """
    if not is_ghcr(image_ref):
        return None
    without_tag = image_ref.split("@", 1)[0].rsplit(":", 1)[0]
    parts = without_tag.split("/")
    if len(parts) < 3:  # need host + owner + at least one package segment
        return None
    owner = parts[1]
    package = "/".join(parts[2:])
    return owner, package


def visibility_api_paths(owner: str, package: str) -> List[str]:
    """Candidate GitHub API paths to set a container package's visibility.

    We don't know whether ``owner`` is an org or a user, so return both the
    org-scoped and user-scoped endpoints to try in order (best-effort).
    """
    from urllib.parse import quote

    pkg = quote(package, safe="")
    return [
        f"/orgs/{owner}/packages/container/{pkg}/visibility",
        f"/user/packages/container/{pkg}/visibility",
    ]


def merge_lockfile_entry(
    existing: Optional[Dict[str, Any]],
    env_name: str,
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a new lockfile mapping with ``env_name`` set/updated to ``entry``.

    The lockfile is ``{env_name: {image, digest, ...}}``. ``None`` values in
    ``entry`` are dropped so an absent field (e.g. no snapshot) isn't recorded as
    null. Other environments in ``existing`` are preserved.
    """
    data: Dict[str, Any] = dict(existing or {})
    clean = {key: value for key, value in entry.items() if value is not None}
    data[env_name] = clean
    return data


def dumps_lockfile(data: Dict[str, Any]) -> str:
    """Serialize a lockfile mapping to stable (sorted) YAML text."""
    import yaml

    return yaml.safe_dump(data, sort_keys=True, default_flow_style=False)


# Thread-limiting variables for bit-reproducible numerical results (issue #68).
# Baking these as image ENV makes single-threaded BLAS/OMP travel with the image
# so determinism holds on hosts where OMP otherwise defaults to >1.
REPRODUCIBLE_RUNTIME_ENV: Dict[str, str] = {
    "OMP_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
    "VECLIB_MAXIMUM_THREADS": "1",
}


def parse_env_assignments(pairs: List[str]) -> Dict[str, str]:
    """Parse ``KEY=VALUE`` strings (from repeatable ``--env``) into a dict.

    Raises ``ValueError`` on a malformed entry (missing ``=`` or empty key).
    """
    result: Dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise ValueError(f"Invalid --env '{item}': expected KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Invalid --env '{item}': empty key.")
        result[key] = value
    return result


def env_to_dockerfile_lines(env: Dict[str, str]) -> List[str]:
    """Render ``{KEY: VALUE}`` as quoted ``ENV KEY="VALUE"`` Dockerfile lines."""
    return [f"ENV {key}={json.dumps(str(value))}" for key, value in env.items()]
