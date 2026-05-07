"""Anchor Ingest — DEPRECATED.

This package is the v1 split-architecture experiment. Use the consolidated
`anchor` package in `v2/` instead. See `v2/README.md` for the migration path.

The package remains installable so existing CLI scripts and `mcp.json` configs
that point at `anchor-ingest` / `anchor-ingest-mcp` keep working; new
development should target `anchor` / `anchor-mcp`.
"""
import warnings

warnings.warn(
    "anchor-ingest is deprecated; use the consolidated `anchor` package in v2/. "
    "See v2/README.md.",
    DeprecationWarning,
    stacklevel=2,
)
