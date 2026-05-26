"""Hatch wheel hook for packaging the prebuilt frontend bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Include the UI only in distributable wheels, not editable installs."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable":
            return

        frontend_dist = Path(self.root) / "web" / "dist"
        if not (frontend_dist / "index.html").is_file():
            raise FileNotFoundError(
                "Frontend bundle not found: run `pnpm --dir web build` before building a wheel."
            )

        build_data["force_include"][str(frontend_dist)] = "anchor/_web_dist"
