"""Tests for the static GPU environment guardrails (issue #56)."""

from __future__ import annotations

from absconda.environment import _normalize_env
from absconda.gpu_lint import check_wheel_triples, gpu_warnings

# A trimmed download.pytorch.org/whl/cu118/torch/ listing: torch 2.2.2 ships
# cp38-cp312, not cp313 (the real-world case from issue #56).
_TORCH_CU118_INDEX = """
<a href="/whl/cu118/torch-2.2.2%2Bcu118-cp310-cp310-linux_x86_64.whl">torch-2.2.2+cu118-cp310</a>
<a href="/whl/cu118/torch-2.2.2%2Bcu118-cp311-cp311-linux_x86_64.whl">torch-2.2.2+cu118-cp311</a>
<a href="/whl/cu118/torch-2.2.2%2Bcu118-cp312-cp312-linux_x86_64.whl">torch-2.2.2+cu118-cp312</a>
"""


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


# ---------------------------------------------------------------------------
# Online wheel-triple validation (issue #59)
# ---------------------------------------------------------------------------


def _ok_fetch(url, timeout):
    return _TORCH_CU118_INDEX


def _fail_fetch(url, timeout):
    raise OSError("network down")


def test_check_wheels_missing_cp_tag_is_error():
    # python=3.13 -> cp313, which torch 2.2.2+cu118 does not publish.
    env = _env(["python=3.13", "pip", {"pip": ["torch==2.2.2+cu118"]}])
    results = check_wheel_triples(env, fetch=_ok_fetch)
    assert len(results) == 1
    assert results[0].status == "missing"
    assert results[0].python_tag == "cp313"
    assert "cp312" in results[0].available_tags


def test_check_wheels_present_cp_tag_is_ok():
    env = _env(["python=3.12", "pip", {"pip": ["torch==2.2.2+cu118"]}])
    results = check_wheel_triples(env, fetch=_ok_fetch)
    assert len(results) == 1
    assert results[0].status == "ok"


def test_check_wheels_unreachable_index_is_skipped():
    env = _env(["python=3.12", "pip", {"pip": ["torch==2.2.2+cu118"]}])
    results = check_wheel_triples(env, fetch=_fail_fetch)
    assert results[0].status == "skipped"


def test_check_wheels_floating_python_is_not_applicable():
    env = _env(["python>=3.11", "pip", {"pip": ["torch==2.2.2+cu118"]}])
    results = check_wheel_triples(env, fetch=_ok_fetch)
    assert results[0].status == "not_applicable"


def test_check_wheels_no_cuda_pin_yields_nothing():
    # A bare torch (no +cuXXX) has no triple to validate online.
    env = _env(["python=3.12", "pip", {"pip": ["torch==2.2.2"]}])
    assert check_wheel_triples(env, fetch=_ok_fetch) == []
