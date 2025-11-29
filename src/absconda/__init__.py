"""Absconda package metadata."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("absconda")
except PackageNotFoundError:  # pragma: no cover - during local development
    __version__ = "0.0.0"

__all__ = ["__version__"]
