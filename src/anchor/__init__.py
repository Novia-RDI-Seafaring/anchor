"""Anchor v2 — agent-first knowledge canvas.

Hexagonal modular monolith:
    core/     pure domain (no I/O)
    infra/    concrete protocol implementations
    adapters/ transport (HTTP, MCP, CLI, SSE)
"""
__version__ = "0.2.0"
