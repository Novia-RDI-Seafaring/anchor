"""`anchor-mcp` stdio entrypoint."""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from mcp.server.stdio import stdio_server

from anchor.adapters.mcp.router import ProjectRouter
from anchor.adapters.mcp.server import build_mcp_server
from anchor.adapters.mcp.services import build_bundle
from anchor.infra.config import AnchorConfig


def _config_for_data_dir(data_dir: Path | None) -> AnchorConfig:
    """Use an explicit MCP flag when present, otherwise defer to AnchorConfig."""
    if data_dir is not None:
        return AnchorConfig(data_dir=data_dir)
    return AnchorConfig()


def _config_for_project(project: Path) -> AnchorConfig:
    """Layer config for an `anchor init` project folder.

    The folder's ``anchor.toml`` marker names the environment + overrides; its
    corpus lives in ``<folder>/.anchor_data``. We resolve the data dir and layer
    env.toml < marker so a single ``--project`` server gets the same config the
    CLI would. A bare ``anchor-mcp`` launched inside the folder resolves the same
    thing via walk-up; this is the explicit handle for when it isn't.
    """
    import sys

    from anchor.infra.environment import DATA_DIRNAME, PROJECT_MARKER_FILENAME, config_for_data_dir

    folder = project.expanduser()
    if not (folder / PROJECT_MARKER_FILENAME).is_file():
        print(
            f"Warning: anchor-mcp: no anchor.toml in {project} — run `anchor init` there. "
            "Falling back to environment / defaults.",
            file=sys.stderr,
        )
        return AnchorConfig()
    return config_for_data_dir(folder / DATA_DIRNAME)


async def _run(
    *,
    env: str | None = None,
    project: Path | None = None,
    data_dir: Path | None = None,
    base_url: str = "http://localhost:8002",
) -> None:
    """Serve MCP over stdio.

    With ``env`` set (an environment NAME), run the multiproject model: one
    server for that environment, projects addressed by per-call name, lifecycle
    tools, and self-correcting resolution errors. Otherwise serve a single
    project bound to a folder (``--project``) or a raw storage root
    (``--data-dir``).
    """
    if env is not None:
        router = ProjectRouter(env_arg=env, base_url=base_url)
        server = build_mcp_server(router=router)
    else:
        config = _config_for_project(project) if project is not None else _config_for_data_dir(data_dir)
        bundle = build_bundle(config, base_url=base_url)
        server = build_mcp_server(bundle=bundle)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description="Anchor v2 MCP (stdio)")
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="An Anchor environment NAME (a profile under ~/.anchor/envs/). "
        "Serves every project in it; name the project per call.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Legacy single-project mode: an `anchor init` folder whose anchor.toml "
        "(data dir, models, zone) binds the whole server. Ignored when --env is set.",
    )
    parser.add_argument(
        "--data-dir",
        "-d",
        type=Path,
        default=None,
        help="Legacy single-project storage root. Defaults to the resolved config "
        "(--project / anchor.toml / ANCHOR_DATA_DIR), else ~/anchor-data.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8002",
        help="URL of the running `anchor serve` the snapshotter loops through.",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    asyncio.run(
        _run(env=args.env, project=args.project, data_dir=args.data_dir, base_url=args.base_url)
    )


if __name__ == "__main__":
    main()
