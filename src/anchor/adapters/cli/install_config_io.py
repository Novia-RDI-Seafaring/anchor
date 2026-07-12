"""Atomic config-file I/O shared by AI harness installers."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object, returning an empty config for a missing file."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config root must be an object: {path}")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Back up an existing config once, then replace it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _back_up_once(path)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_toml(path: Path) -> dict[str, Any]:
    """Load one TOML object, returning an empty config for a missing file."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    return tomllib.loads(text)


def write_codex_toml(path: Path, data: dict[str, Any]) -> None:
    """Back up and atomically write the supported Codex TOML shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _back_up_once(path)
    tmp = path.parent / (path.name + ".tmp")
    tmp.write_text(_render_codex_toml(data), encoding="utf-8")
    os.replace(tmp, path)


def _back_up_once(path: Path) -> None:
    if not path.exists():
        return
    backup = path.parent / (path.name + ".anchorbak")
    if not backup.exists():
        backup.write_bytes(path.read_bytes())


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    raise TypeError(f"Unsupported TOML scalar: {value!r}")


def _toml_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    return _toml_scalar(value)


def _render_codex_toml(data: dict[str, Any]) -> str:
    """Render Codex config values and arbitrarily nested tables."""
    lines: list[str] = []
    _append_mapping(lines, (), data)
    return "\n".join(lines) + "\n"


def _toml_key(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        return value
    return _toml_scalar(value)


def _append_mapping(
    lines: list[str],
    path: tuple[str, ...],
    values: dict[str, Any],
) -> None:
    scalar_values = {
        key: value for key, value in values.items() if not isinstance(value, dict)
    }
    child_tables = {
        key: value for key, value in values.items() if isinstance(value, dict)
    }

    if path:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{'.'.join(_toml_key(part) for part in path)}]")
    lines.extend(
        f"{_toml_key(key)} = {_toml_value(value)}"
        for key, value in scalar_values.items()
    )

    for key, table in child_tables.items():
        _append_mapping(lines, (*path, key), table)
