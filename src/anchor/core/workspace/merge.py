"""Deep-merge for node / edge ``data`` patches — pure, no I/O.

``update_node`` / ``update_edge`` patch the ``data`` dict. The historic
behaviour replaced the whole dict, silently dropping unmentioned keys
(provenance like ``source_ref`` vanished — see issue #192). ``deep_merge``
fixes that: a patch merges INTO the existing data, recursing into nested
dicts so a deep field can be touched without rewriting its siblings.

Key deletion is explicit: a value of ``None`` in the patch removes that
key from the base. This is the documented escape hatch for "drop this
field" now that the default is merge-not-replace. (A node-data value that
should literally be JSON null is vanishingly rare on the canvas; callers
that truly need one can omit the key and let the renderer treat absence
and null identically.)
"""
from __future__ import annotations

from typing import Any


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` deep-merged with ``patch``.

    Rules:
      - A key present in ``patch`` but not ``base`` is added.
      - Two dict values at the same key are merged recursively.
      - Any other value in ``patch`` overwrites ``base``'s value.
      - A ``patch`` value of ``None`` DELETES the key from the result
        (the documented way to drop a field under merge semantics).

    Neither input is mutated; a fresh dict is returned.
    """
    out: dict[str, Any] = dict(base)
    for key, pv in patch.items():
        if pv is None:
            out.pop(key, None)
            continue
        bv = out.get(key)
        if isinstance(bv, dict) and isinstance(pv, dict):
            out[key] = deep_merge(bv, pv)
        else:
            out[key] = pv
    return out
