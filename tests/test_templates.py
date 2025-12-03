from pathlib import Path

from absconda.environment import EnvSpec
from absconda.policy import PolicyProfile
from absconda.templates import DEFAULT_BUILDER_IMAGE, RenderConfig, render_dockerfile


def make_env() -> EnvSpec:
    return EnvSpec(
        name="tmpl-demo",
        channels=["conda-forge"],
        dependencies=["python=3.11"],
        raw={
            "name": "tmpl-demo",
            "channels": ["conda-forge"],
            "dependencies": ["python=3.11"],
        },
    )


def make_profile() -> PolicyProfile:
    return PolicyProfile(
        name="default",
        builder_base=None,
        runtime_base=None,
        multi_stage=None,
        env_prefix="/opt/conda/envs",
        allowed_channels=[],
        required_labels={},
        default_fragments=[],
        raw={},
    )


def test_render_dockerfile_multi_stage() -> None:
    env = make_env()
    profile = make_profile()
    config = RenderConfig(
        env=env,
        profile=profile,
        multi_stage=True,
        builder_base=DEFAULT_BUILDER_IMAGE,
        runtime_base="debian:bookworm-slim",
        template_path=None,
    )

    dockerfile = render_dockerfile(config)

    assert "FROM mambaorg/micromamba:1.5.5 AS builder" in dockerfile
    assert "FROM debian:bookworm-slim AS runtime" in dockerfile
    assert "ENV CONDA_PREFIX=/opt/conda/envs/tmpl-demo" in dockerfile
    assert "--channel conda-forge" in dockerfile


def test_render_dockerfile_custom_template(tmp_path: Path) -> None:
    env = make_env()
    profile = make_profile()
    template_path = tmp_path / "tmpl.j2"
    template_path.write_text("FROM override\nRUN echo '{{ env.name }}'\n", encoding="utf-8")

    config = RenderConfig(
        env=env,
        profile=profile,
        multi_stage=False,
        builder_base="alpine:3",
        runtime_base="alpine:3",
        template_path=template_path,
    )

    dockerfile = render_dockerfile(config)

    assert "FROM override" in dockerfile
    assert "RUN echo 'tmpl-demo'" in dockerfile


def test_render_dockerfile_with_renv_lock() -> None:
    env = make_env()
    profile = make_profile()
    renv_lock = (Path(__file__).parent / "fixtures" / "sample-renv.lock").read_text(
        encoding="utf-8"
    )

    config = RenderConfig(
        env=env,
        profile=profile,
        multi_stage=True,
        builder_base=DEFAULT_BUILDER_IMAGE,
        runtime_base="debian:bookworm-slim",
        template_path=None,
        renv_lock=renv_lock,
    )

    dockerfile = render_dockerfile(config)

    assert "ABSCONDA_RENV_LOCK" in dockerfile
    assert "renv::restore" in dockerfile
    assert "COPY --from=builder /tmp/absconda-renv/ /opt/absconda/renv/" in dockerfile
    assert "RENV_PATHS_LIBRARY=/opt/absconda/renv/renv/library" in dockerfile
