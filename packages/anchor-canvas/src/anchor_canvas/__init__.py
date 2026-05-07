"""Anchor Canvas — DEPRECATED.

This package is the v1 split-architecture experiment. Use the consolidated
`anchor` package in `v2/` instead. See `v2/README.md` for the migration path.

The package remains installable so existing `mcp.json` configs that point at
`anchor-canvas-mcp` keep working; new development should target `anchor-mcp`.
"""
import warnings

warnings.warn(
    "anchor-canvas is deprecated; use the consolidated `anchor` package in v2/. "
    "See v2/README.md.",
    DeprecationWarning,
    stacklevel=2,
)
