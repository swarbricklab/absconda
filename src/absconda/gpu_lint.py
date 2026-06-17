"""Static guardrails for common GPU environment pitfalls.

These catch the footguns behind cryptic GPU container build failures (see
issue #56) before the build starts, rather than ~60s deep in the pip layer:

* A floating Python interpreter (``python>=3.11`` / unpinned) combined with a
  pinned CUDA wheel. "Newest python" is frequently the one combination with no
  matching wheel, because binary wheels (torch, jax, cupy, tensorflow) lag new
  Python releases by months.
* A bare binary wheel alongside a CUDA ``--extra-index-url`` but with no
  ``+cuXXX`` local version — which can silently resolve to the CPU wheel from
  PyPI (a build that "succeeds" but where ``torch.cuda.is_available()`` is
  False).
* CUDA resolved by conda (``pytorch-cuda``/``cudatoolkit``/``cuda-*``). This is
  fragile on its own and outright redundant when building on a CUDA ``--base``
  image, where CUDA already comes from the base.

All checks are static (no network) and return warning strings. They never block
a build — they point at the fix.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .environment import EnvSpec

_PIP_PREFIX = "pip::"

# Binary wheels that ship per-CPython-tag builds and lag new Python releases.
_BINARY_WHEELS = ("torch", "torchvision", "torchaudio", "jax", "jaxlib", "cupy", "tensorflow")

# A CUDA pip index, e.g. --extra-index-url https://download.pytorch.org/whl/cu118
_CUDA_INDEX_RE = re.compile(r"download\.pytorch\.org/whl/(cu\d+)", re.IGNORECASE)
# A CUDA local-version tag, e.g. torch==2.2.2+cu118
_CUDA_LOCAL_RE = re.compile(r"\+cu\d+", re.IGNORECASE)
# An exact python pin: python=3.10 / python==3.10 / python 3.10 (no range ops).
_PYTHON_EXACT_RE = re.compile(r"^python\s*(?:==?|\s)\s*\d+\.\d+", re.IGNORECASE)

_VERSION_SPLIT_RE = re.compile(r"[=<>!~\[\s@]")


def _split_deps(env: EnvSpec) -> tuple[list[str], list[str]]:
    """Return (conda_deps, pip_deps) from a normalized EnvSpec."""
    conda_deps: list[str] = []
    pip_deps: list[str] = []
    for dep in env.dependencies:
        if dep.startswith(_PIP_PREFIX):
            pip_deps.append(dep[len(_PIP_PREFIX) :])
        else:
            conda_deps.append(dep)
    return conda_deps, pip_deps


def _pkg_name(spec: str) -> str:
    """Extract the package name from a conda/pip requirement string."""
    return _VERSION_SPLIT_RE.split(spec.strip(), 1)[0].strip().lower()


def _python_spec(conda_deps: list[str]) -> Optional[str]:
    for dep in conda_deps:
        if _pkg_name(dep) == "python":
            return dep.strip()
    return None


def _python_is_floating(conda_deps: list[str]) -> bool:
    """True when the interpreter is unpinned or only range-constrained.

    A missing ``python`` entry counts as floating: the solver picks the newest
    compatible interpreter, which is the dangerous case for binary wheels.
    """
    spec = _python_spec(conda_deps)
    if spec is None:
        return True
    return _PYTHON_EXACT_RE.match(spec) is None


def _cuda_index(pip_deps: list[str]) -> Optional[str]:
    for dep in pip_deps:
        match = _CUDA_INDEX_RE.search(dep)
        if match:
            return match.group(1)  # e.g. "cu118"
    return None


def _has_cuda_wheel(pip_deps: list[str]) -> bool:
    return any(_CUDA_LOCAL_RE.search(dep) for dep in pip_deps)


def gpu_warnings(env: EnvSpec, *, base_image: Optional[str] = None) -> List[str]:
    """Return warnings for likely GPU-build pitfalls in ``env``."""
    warnings: List[str] = []
    conda_deps, pip_deps = _split_deps(env)

    cuda_variant = _cuda_index(pip_deps)
    has_cuda_wheel = _has_cuda_wheel(pip_deps)
    targets_gpu_via_pip = bool(cuda_variant) or has_cuda_wheel

    # (1) Floating python + a pinned CUDA wheel: the classic "no wheel for the
    # newest interpreter" trap. Binary wheels lag new Python releases.
    if targets_gpu_via_pip and _python_is_floating(conda_deps):
        spec = _python_spec(conda_deps) or "(python not pinned)"
        warnings.append(
            f"GPU env: python is floating ('{spec}') but a CUDA wheel is pinned. "
            "Binary wheels (torch/jax/cupy) lag new Python releases, so the "
            "solver may pick an interpreter with no matching wheel and fail deep "
            "in the pip layer. Pin the interpreter, e.g. 'python=3.12'."
        )

    # (3) Bare binary wheel + CUDA index but no +cuXXX: may silently install the
    # CPU wheel from PyPI. The explicit local version only exists on the CUDA
    # index, so it is unambiguous.
    if cuda_variant:
        for dep in pip_deps:
            name = _pkg_name(dep)
            if name in _BINARY_WHEELS and not _CUDA_LOCAL_RE.search(dep):
                warnings.append(
                    f"GPU env: '{dep}' is listed with a CUDA index "
                    f"(/{cuda_variant}) but without a '+{cuda_variant}' local "
                    "version, so pip may resolve the CPU wheel instead "
                    "(torch.cuda.is_available() == False). Pin it explicitly, "
                    f"e.g. '{name}==<version>+{cuda_variant}'."
                )

    # CUDA resolved by conda: fragile, and redundant when building on a CUDA base.
    conda_cuda = [
        dep
        for dep in conda_deps
        if (n := _pkg_name(dep)) in ("pytorch-cuda", "cudatoolkit", "cudnn", "cuda")
        or n.startswith("cuda-")
    ]
    if conda_cuda:
        names = ", ".join(sorted({_pkg_name(d) for d in conda_cuda}))
        if base_image:
            warnings.append(
                f"GPU env: building on a CUDA base image (--base {base_image}) but "
                f"conda still resolves the CUDA stack ({names}). CUDA already comes "
                "from the base — drop these conda deps and install the framework "
                "from pip CUDA wheels (e.g. torch==<ver>+cu118) so conda only "
                "solves the lightweight stack."
            )
        else:
            warnings.append(
                f"GPU env: conda is resolving the CUDA stack ({names}). This solve "
                "is often slow/fragile; consider a CUDA --base image plus pip CUDA "
                "wheels (e.g. torch==<ver>+cu118) instead."
            )

    # (4) Bare conda 'pytorch' is CPU-only unless a CUDA metapackage is present.
    has_conda_pytorch = any(_pkg_name(d) == "pytorch" for d in conda_deps)
    has_cuda_metapkg = any(_pkg_name(d) in ("pytorch-cuda", "cudatoolkit") for d in conda_deps)
    if has_conda_pytorch and not has_cuda_metapkg:
        warnings.append(
            "GPU env: conda 'pytorch' without 'pytorch-cuda'/'cudatoolkit' "
            "installs a CPU-only build. Add the CUDA metapackage (and the "
            "'nvidia' channel) or install torch from a pip CUDA wheel."
        )

    return warnings
