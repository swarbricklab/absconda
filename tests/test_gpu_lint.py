"""Tests for the static GPU environment guardrails (issue #56)."""

from __future__ import annotations

from absconda.environment import _normalize_env
from absconda.gpu_lint import gpu_warnings


def _env(dependencies, channels=None):
    data = {
        "name": "t",
        "channels": channels or ["conda-forge"],
        "dependencies": dependencies,
    }
    return _normalize_env(data, "<test>")


def _joined(env, **kw):
    return "\n".join(gpu_warnings(env, **kw))


def test_floating_python_with_cuda_wheel_warns():
    env = _env(
        [
            "python>=3.11",
            "pip",
            {
                "pip": [
                    "--extra-index-url https://download.pytorch.org/whl/cu118",
                    "torch==2.2.2+cu118",
                ]
            },
        ]
    )
    msg = _joined(env)
    assert "python is floating" in msg
    assert "python=3.12" in msg  # suggests pinning


def test_missing_python_with_cuda_wheel_warns():
    env = _env(["pip", {"pip": ["torch==2.2.2+cu118"]}])
    assert "python is floating" in _joined(env)


def test_pinned_python_with_cuda_wheel_is_clean():
    env = _env(
        [
            "python=3.10",
            "pip",
            {
                "pip": [
                    "--extra-index-url https://download.pytorch.org/whl/cu118",
                    "torch==2.2.2+cu118",
                ]
            },
        ]
    )
    assert gpu_warnings(env) == []


def test_bare_torch_with_cuda_index_warns_silent_cpu():
    env = _env(
        [
            "python=3.10",
            "pip",
            {"pip": ["--extra-index-url https://download.pytorch.org/whl/cu118", "torch"]},
        ]
    )
    msg = _joined(env)
    assert "CPU wheel" in msg
    assert "+cu118" in msg


def test_conda_cuda_stack_warns_and_mentions_base():
    env = _env(
        ["python>=3.10", "pytorch>=2.0", "pytorch-cuda=11.8"], channels=["pytorch", "nvidia"]
    )
    plain = _joined(env)
    assert "conda is resolving the CUDA stack" in plain
    based = _joined(env, base_image="ghcr.io/swarbricklab/gpu-base:20260616")
    assert "building on a CUDA base image" in based


def test_conda_pytorch_without_cuda_metapackage_warns_cpu():
    env = _env(["python=3.10", "pytorch>=2.0"], channels=["pytorch"])
    assert "CPU-only build" in _joined(env)


def test_conda_pytorch_with_cuda_metapackage_no_cpu_warning():
    env = _env(["python=3.10", "pytorch>=2.0", "pytorch-cuda=11.8"], channels=["pytorch", "nvidia"])
    assert "CPU-only build" not in _joined(env)


def test_plain_cpu_env_is_clean():
    env = _env(["python=3.11", "numpy", "pandas", "pip", {"pip": ["rich"]}])
    assert gpu_warnings(env) == []
