"""GhostCite: detect hallucinated and wrong academic citations using live Google Scholar data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ghostcite")
except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
