from pathlib import Path

from absconda.environment import EnvSpec
from absconda.policy import PolicyProfile
from absconda.templates import (
    DEFAULT_BUILDER_IMAGE,
    RenderConfig,
    _split_conda_pip,
    render_dockerfile,
)


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


def make_pip_env() -> EnvSpec:
    raw = {
        "name": "with-pip",
        "channels": ["conda-forge"],
        "dependencies": [
            "python=3.12",
            "numpy>=1.24",
            {"pip": ["--extra-index-url https://example/whl", "torch==2.7.1"]},
        ],
    }
    return EnvSpec(
        name="with-pip",
        channels=["conda-forge"],
        dependencies=[
            "python=3.12",
            "numpy>=1.24",
            "pip::--extra-index-url https://example/whl",
            "pip::torch==2.7.1",
        ],
        raw=raw,
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
    assert "COPY --from=builder /opt/conda/envs/tmpl-demo/ /opt/conda/envs/tmpl-demo/" in dockerfile
    assert "micromamba run -n base python" in dockerfile
    assert "conda-unpack" in dockerfile


def test_render_dockerfile_conda_on_base() -> None:
    env = make_env()
    profile = make_profile()
    config = RenderConfig(
        env=env,
        profile=profile,
        multi_stage=True,  # ignored when base_image is set
        builder_base=DEFAULT_BUILDER_IMAGE,
        runtime_base="debian:bookworm-slim",
        base_image="nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04",
        template_path=None,
    )

    dockerfile = render_dockerfile(config)

    # Single stage built directly on the supplied base image.
    assert "FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04" in dockerfile
    assert "AS builder" not in dockerfile
    assert "AS runtime" not in dockerfile
    # micromamba is installed into the base and the env created in place.
    assert "micro.mamba.pm/api/micromamba" in dockerfile
    assert "micromamba create -y -n tmpl-demo" in dockerfile
    assert "--channel conda-forge" in dockerfile
    # No conda-pack / cross-stage copy in this mode.
    assert "conda-pack" not in dockerfile
    assert "COPY --from=builder" not in dockerfile
    # Standard export block still applied.
    assert "ENV CONDA_PREFIX=/opt/conda/envs/tmpl-demo" in dockerfile
    assert 'CMD ["python"]' in dockerfile


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


def test_split_conda_pip_separates_and_adds_pip() -> None:
    conda_yaml, pip_reqs = _split_conda_pip(make_pip_env())

    # pip section is removed from the conda YAML...
    assert "torch" not in conda_yaml
    assert "extra-index-url" not in conda_yaml
    # ...and `pip` is injected so the second phase can run.
    assert "- pip" in conda_yaml
    # pip requirements preserve option lines and order.
    assert pip_reqs is not None
    assert pip_reqs.splitlines() == [
        "--extra-index-url https://example/whl",
        "torch==2.7.1",
    ]


def test_split_conda_pip_no_pip_section() -> None:
    conda_yaml, pip_reqs = _split_conda_pip(make_env())
    assert pip_reqs is None
    assert "- pip" not in conda_yaml  # pip not injected when there is no pip section


def test_split_conda_pip_does_not_duplicate_existing_pip() -> None:
    raw = {
        "name": "e",
        "channels": ["conda-forge"],
        "dependencies": ["python=3.12", "pip", {"pip": ["torch"]}],
    }
    env = EnvSpec(
        name="e", channels=["conda-forge"], dependencies=["python=3.12", "pip::torch"], raw=raw
    )
    conda_yaml, _ = _split_conda_pip(env)
    assert conda_yaml.count("- pip\n") + conda_yaml.count("- pip") == 1


def test_render_installs_pip_constrained_after_conda() -> None:
    dockerfile = render_dockerfile(
        RenderConfig(
            env=make_pip_env(),
            profile=make_profile(),
            multi_stage=False,
            builder_base=DEFAULT_BUILDER_IMAGE,
            runtime_base="debian:bookworm-slim",
            base_image="nvidia/cuda:11.8.0-base-ubuntu22.04",
        )
    )

    # pip deps land in their own requirements file, not the conda env.yaml.
    assert "ABSCONDA_PIP" in dockerfile
    # Constraints are frozen from the solved conda env and passed to pip.
    assert "pip list --format=freeze > /tmp/conda.constraints.txt" in dockerfile
    assert "--constraint /tmp/conda.constraints.txt" in dockerfile
    assert "--requirement /tmp/requirements.txt" in dockerfile
    # Verify the env is internally consistent afterwards.
    assert "python -m pip check" in dockerfile
    # Ordering: conda create precedes the pip install.
    assert dockerfile.index("micromamba create") < dockerfile.index("pip install")


def test_render_no_pip_section_omits_pip_steps() -> None:
    dockerfile = render_dockerfile(
        RenderConfig(
            env=make_env(),
            profile=make_profile(),
            multi_stage=True,
            builder_base=DEFAULT_BUILDER_IMAGE,
            runtime_base="debian:bookworm-slim",
        )
    )
    assert "requirements.txt" not in dockerfile
    assert "pip install" not in dockerfile
    assert "pip check" not in dockerfile


def test_variables_section_rendered_as_env_not_fed_to_conda() -> None:
    raw = {
        "name": "v",
        "channels": ["conda-forge"],
        "dependencies": ["python=3.12"],
        "variables": {"CLOUDSDK_PYTHON_SITEPACKAGES": "1", "FOO": "a b"},
    }
    env = EnvSpec(name="v", channels=["conda-forge"], dependencies=["python=3.12"], raw=raw)
    dockerfile = render_dockerfile(
        RenderConfig(
            env=env,
            profile=make_profile(),
            multi_stage=True,
            builder_base=DEFAULT_BUILDER_IMAGE,
            runtime_base="debian:bookworm-slim",
        )
    )

    # variables become image ENV (quoted so values with spaces survive).
    assert 'ENV CLOUDSDK_PYTHON_SITEPACKAGES="1"' in dockerfile
    assert 'ENV FOO="a b"' in dockerfile
    # ...and are NOT written into the conda env.yaml the solver reads.
    conda_block = dockerfile.split("ABSCONDA_ENV")[1]
    assert "variables" not in conda_block
    assert "CLOUDSDK_PYTHON_SITEPACKAGES" not in conda_block


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
    assert "COPY --from=builder /opt/conda/envs/tmpl-demo/ /opt/conda/envs/tmpl-demo/" in dockerfile
    assert "COPY --from=builder /tmp/absconda-renv/ /opt/absconda/renv/" in dockerfile
    assert "RENV_PATHS_LIBRARY=/opt/absconda/renv/renv/library" in dockerfile
