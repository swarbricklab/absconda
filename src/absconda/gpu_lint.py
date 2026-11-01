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
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

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
# Captures the X.Y of an exact python pin for the cpXY wheel tag.
_PYTHON_VERSION_RE = re.compile(r"^python\s*(?:==?|\s)\s*(\d+)\.(\d+)", re.IGNORECASE)
# An exact pip version pin: torch==2.2.2+cu118 -> "2.2.2" (public version, sans local).
_EXACT_PIN_RE = re.compile(r"==\s*([0-9][^,;\s]*)")

_VERSION_SPLIT_RE = re.compile(r"[=<>!~\[\s@]")

# Packages served by the download.pytorch.org wheel index (queried by the online
# wheel-triple check). The index path is /whl/<cuda>/<package>/.
_PYTORCH_INDEX_PKGS = ("torch", "torchvision", "torchaudio")


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


# ---------------------------------------------------------------------------
# Online (python, torch, cuda) wheel-triple validation (issues #56 / #59)
# ---------------------------------------------------------------------------
#
# The static checks above cannot catch a *pinned-but-wrong* interpreter, e.g.
# ``python=3.13`` + ``torch==2.2.2+cu118`` which only ships through cp312. That
# only surfaces ~60s into the pip layer with "No matching distribution found".
# This check queries the wheel index before the build and fails fast.

# The build-tag for each wheel on the index, e.g. ...-cp312-cp312-linux...
_WHEEL_PYTAG_RE = re.compile(r"-cp(\d+)-", re.IGNORECASE)


@dataclass
class WheelCheck:
    """Result of validating one pinned CUDA wheel against the online index."""

    package: str
    version: str
    cuda: str
    python_tag: str  # the required cpXY, or "" when python is not exactly pinned
    status: str  # "ok" | "missing" | "skipped" | "not_applicable"
    detail: str
    available_tags: List[str] = field(default_factory=list)


def _python_cp_tag(conda_deps: List[str]) -> Optional[str]:
    """Return the cpXY wheel tag for an exactly-pinned python, else None."""
    spec = _python_spec(conda_deps)
    if spec is None:
        return None
    match = _PYTHON_VERSION_RE.match(spec)
    if not match:
        return None
    return f"cp{match.group(1)}{match.group(2)}"


def _pinned_public_version(dep: str) -> Optional[str]:
    """Return the exact-pinned public version (sans +local) from a pip spec."""
    match = _EXACT_PIN_RE.search(dep)
    if not match:
        return None
    return match.group(1).split("+", 1)[0]


def _default_fetch(url: str, timeout: float) -> str:
    request = Request(url, headers={"User-Agent": "absconda-wheel-check"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _available_python_tags(html: str, package: str, version: str, cuda: str) -> List[str]:
    """Parse the cpXY tags published for ``package``-``version``+``cuda``.

    The index encodes the ``+`` of the local version as ``%2B``; accept either.
    """
    tags: set[str] = set()
    for sep in ("%2B", "+"):
        needle = f"{package}-{version}{sep}{cuda}-"
        for match in re.finditer(re.escape(needle) + r"cp(\d+)-", html, re.IGNORECASE):
            tags.add(f"cp{match.group(1)}")
    return sorted(tags, key=lambda t: (len(t), t))


def check_wheel_triples(
    env: EnvSpec,
    *,
    timeout: float = 10.0,
    fetch: Optional[Callable[[str, float], str]] = None,
) -> List[WheelCheck]:
    """Validate each pinned CUDA wheel's (python, version, cuda) triple online.

    For every pip dep that pins a ``download.pytorch.org`` package to an exact
    ``<version>+cuXXX``, confirm the index actually publishes a wheel for the
    exactly-pinned interpreter's ``cpXY`` tag. Returns one :class:`WheelCheck`
    per such dep. Network failures degrade to ``status="skipped"`` so an offline
    or unreachable index never blocks the build. When python is not exactly
    pinned the triple is unknowable here (``status="not_applicable"``); the
    static floating-python warning already covers that case.
    """
    fetch = fetch or _default_fetch
    conda_deps, pip_deps = _split_deps(env)
    python_tag = _python_cp_tag(conda_deps)

    results: List[WheelCheck] = []
    for dep in pip_deps:
        name = _pkg_name(dep)
        if name not in _PYTORCH_INDEX_PKGS:
            continue
        local = _CUDA_LOCAL_RE.search(dep)
        version = _pinned_public_version(dep)
        if not local or version is None:
            continue  # not an exact +cuXXX pin — nothing to validate online
        cuda = local.group(0).lstrip("+").lower()

        if python_tag is None:
            results.append(
                WheelCheck(
                    package=name,
                    version=version,
                    cuda=cuda,
                    python_tag="",
                    status="not_applicable",
                    detail=(
                        f"'{name}=={version}+{cuda}' pins a CUDA wheel but python is "
                        "not exactly pinned, so the required cpXY tag is unknown. "
                        "Pin 'python=X.Y' to enable the online wheel check."
                    ),
                )
            )
            continue

        url = f"https://download.pytorch.org/whl/{cuda}/{name}/"
        try:
            html = fetch(url, timeout)
        except (URLError, OSError, ValueError) as exc:
            results.append(
                WheelCheck(
                    package=name,
                    version=version,
                    cuda=cuda,
                    python_tag=python_tag,
                    status="skipped",
                    detail=f"could not reach {url} ({exc}); skipping wheel check.",
                )
            )
            continue

        available = _available_python_tags(html, name, version, cuda)
        if python_tag in available:
            results.append(
                WheelCheck(
                    package=name,
                    version=version,
                    cuda=cuda,
                    python_tag=python_tag,
                    status="ok",
                    detail=f"{name}=={version}+{cuda} has a {python_tag} wheel.",
                    available_tags=available,
                )
            )
        else:
            avail = ", ".join(available) if available else "(no wheels for this version)"
            results.append(
                WheelCheck(
                    package=name,
                    version=version,
                    cuda=cuda,
                    python_tag=python_tag,
                    status="missing",
                    detail=(
                        f"no {python_tag} wheel for {name}=={version}+{cuda} on the "
                        f"CUDA index. Available Python tags: {avail}. Pin 'python' to "
                        "a version with a matching wheel, or change the wheel version."
                    ),
                    available_tags=available,
                )
            )
    return results
