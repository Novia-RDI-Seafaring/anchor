"""Anchor v2 — agent-first knowledge canvas.

Hexagonal modular monolith:
    core/     pure domain (no I/O)
    infra/    concrete protocol implementations
    adapters/ transport (HTTP, MCP, CLI, SSE)
"""
from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth is the installed distribution's metadata, which
    # hatch derives from pyproject.toml. Reading it here keeps `anchor version`
    # from drifting when the project version is bumped for a release (it was
    # stale at 0.2.0 through both the 0.2.1 and 0.2.2 releases).
    __version__ = version("anchor-kb")
except PackageNotFoundError:  # running from a source tree with no dist metadata
    __version__ = "0.0.0+source"
