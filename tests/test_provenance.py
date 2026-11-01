"""Tests for the build-provenance / publish-metadata helpers (issues #68-#71)."""

from __future__ import annotations

import base64

import pytest

from absconda import provenance as prov


def test_sha256_text_is_prefixed_and_stable():
    assert prov.sha256_text("abc").startswith("sha256:")
    assert prov.sha256_text("abc") == prov.sha256_text("abc")
    assert prov.sha256_text("abc") != prov.sha256_text("abd")


def test_build_provenance_labels_emits_only_present_fields():
    labels = prov.build_provenance_labels(
        env_name="demo",
        absconda_version="0.3.0",
        env_file_name="env.yaml",
        env_file_text="name: demo\n",
        snapshot_text=None,
        builder_base="mambaorg/micromamba:1.5.5",
        runtime_base="debian:bookworm-slim",
        base_image=None,
        created="2026-11-01T00:00:00Z",
        git_revision="abc123",
        git_source="git@github.com:org/repo.git",
    )
    assert labels["org.opencontainers.image.title"] == "demo"
    assert labels["org.absconda.version"] == "0.3.0"
    assert labels["org.opencontainers.image.created"] == "2026-11-01T00:00:00Z"
    assert labels["org.opencontainers.image.revision"] == "abc123"
    assert labels["org.opencontainers.image.source"] == "git@github.com:org/repo.git"
    assert labels["org.absconda.env-file"] == "env.yaml"
    assert labels["org.absconda.env-sha256"] == prov.sha256_text("name: demo\n")
    # Absent inputs produce no label.
    assert "org.absconda.snapshot-sha256" not in labels
    assert "org.opencontainers.image.base.name" not in labels


def test_build_provenance_labels_base_image():
    labels = prov.build_provenance_labels(
        env_name="demo", absconda_version="0.3.0", base_image="nvidia/cuda:11.8.0-runtime"
    )
    assert labels["org.opencontainers.image.base.name"] == "nvidia/cuda:11.8.0-runtime"
    assert labels["org.absconda.base-image"] == "nvidia/cuda:11.8.0-runtime"


def test_dockerfile_embed_label_roundtrips():
    dockerfile = '# Generated\nFROM x\nLABEL a="b"\n'
    line = prov.dockerfile_embed_label(dockerfile)
    assert line.startswith("LABEL org.absconda.dockerfile.base64=")
    encoded = line.split('"')[1]
    assert base64.b64decode(encoded).decode("utf-8") == dockerfile


def test_parse_push_digest():
    out = "latest: digest: sha256:" + "a" * 64 + " size: 1234"
    assert prov.parse_push_digest(out) == "sha256:" + "a" * 64
    assert prov.parse_push_digest("no digest here") is None


def test_select_repo_digest_matches_repo():
    digests = [
        "ghcr.io/org/other@sha256:" + "b" * 64,
        "ghcr.io/org/name@sha256:" + "a" * 64,
    ]
    assert prov.select_repo_digest(digests, "ghcr.io/org/name:v1") == (
        "ghcr.io/org/name@sha256:" + "a" * 64
    )


def test_select_repo_digest_single_fallback():
    digests = ["ghcr.io/org/renamed@sha256:" + "a" * 64]
    assert prov.select_repo_digest(digests, "ghcr.io/org/name:v1").endswith("a" * 64)


def test_digest_reference_from_bare_digest():
    ref = prov.digest_reference("ghcr.io/org/name:v1", "sha256:" + "a" * 64)
    assert ref == "ghcr.io/org/name@sha256:" + "a" * 64
    # Already-complete reference is returned unchanged.
    assert prov.digest_reference("x:1", "ghcr.io/org/name@sha256:x") == "ghcr.io/org/name@sha256:x"


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("ghcr.io/org/name:v1", ("org", "name")),
        ("ghcr.io/org/team/tool:v1", ("org", "team/tool")),
        ("docker.io/org/name:v1", None),
        ("ghcr.io/org", None),
    ],
)
def test_ghcr_owner_and_package(ref, expected):
    assert prov.ghcr_owner_and_package(ref) == expected


def test_visibility_api_paths_encodes_nested_package():
    paths = prov.visibility_api_paths("org", "team/tool")
    assert paths[0] == "/orgs/org/packages/container/team%2Ftool/visibility"
    assert paths[1] == "/user/packages/container/team%2Ftool/visibility"


def test_merge_lockfile_entry_preserves_others_and_drops_none():
    existing = {"old": {"image": "x"}}
    merged = prov.merge_lockfile_entry(
        existing, "demo", {"image": "ghcr.io/o/demo:v1", "digest": None, "built": "t"}
    )
    assert merged["old"] == {"image": "x"}
    assert merged["demo"] == {"image": "ghcr.io/o/demo:v1", "built": "t"}
    assert "digest" not in merged["demo"]  # None dropped


def test_parse_env_assignments():
    assert prov.parse_env_assignments(["A=1", "B=x=y"]) == {"A": "1", "B": "x=y"}
    with pytest.raises(ValueError):
        prov.parse_env_assignments(["noequals"])
    with pytest.raises(ValueError):
        prov.parse_env_assignments(["=novalue"])


def test_env_to_dockerfile_lines_quotes_values():
    lines = prov.env_to_dockerfile_lines({"OMP_NUM_THREADS": "1"})
    assert lines == ['ENV OMP_NUM_THREADS="1"']


def test_build_timestamp_honors_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
    assert prov.build_timestamp() == "1970-01-01T00:00:00Z"
