"""Structured config readers and atomic writers for harness registration."""

from __future__ import annotations

import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    return json.loads(text) if text else {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Back up once, then atomically write a harness JSON config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_once(path)
    temporary = path.parent / (path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").strip()
    return tomllib.loads(text) if text else {}


def render_codex_toml(data: dict[str, Any]) -> str:
    """Serialize nested Codex configuration data as TOML.

    The renderer preserves data but not comments or the original key order.
    Callers therefore use ``write_toml``, which keeps a one-time backup.
    """
    lines: list[str] = []

    def emit_table(path: list[str], table: dict[str, Any]) -> None:
        if lines:
            lines.append("")
        lines.append("[" + ".".join(_toml_key(part) for part in path) + "]")
        nested: list[tuple[str, dict[str, Any]]] = []
        for key, value in table.items():
            if isinstance(value, dict):
                nested.append((key, value))
            else:
                lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
        for key, value in nested:
            emit_table([*path, key], value)

    root_tables: list[tuple[str, dict[str, Any]]] = []
    for key, value in data.items():
        if isinstance(value, dict):
            root_tables.append((key, value))
        else:
            lines.append(f"{_toml_key(key)} = {_toml_value(value)}")
    for key, value in root_tables:
        emit_table([key], value)
    return "\n".join(lines) + "\n"


def write_toml(path: Path, data: dict[str, Any]) -> None:
    """Back up once, then atomically write a Codex TOML config."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup_once(path)
    temporary = path.parent / (path.name + ".tmp")
    temporary.write_text(render_codex_toml(data), encoding="utf-8")
    os.replace(temporary, path)


def _backup_once(path: Path) -> None:
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


_BARE_TOML_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(key: str) -> str:
    return key if _BARE_TOML_KEY.fullmatch(key) else _toml_scalar(key)


def _toml_value(value: Any) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        items = ", ".join(f"{_toml_key(key)} = {_toml_value(item)}" for key, item in value.items())
        return "{ " + items + " }"
    return _toml_scalar(value)
