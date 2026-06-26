"""Server self-identification endpoint.

``GET /api/whoami`` answers "which project (and env) does this server host, and
where is it actually bound?" so an agent or the viewer never has to guess that
``localhost:8002`` is its project (anchor#177, anchor#179). The payload names
the bound env + project, the data dir, and the real host:port the process is
listening on (after any free-port bump), plus the canvas URL prefix to build
``{base_url}/c/<slug>`` links that resolve to *this* server.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from anchor.infra.config import AnchorConfig
from anchor.infra.environment import identify_data_dir

router = APIRouter(prefix="/api", tags=["whoami"])


@router.get("/whoami")
async def whoami(request: Request) -> dict:
    binding = getattr(request.app.state, "serve_binding", None)
    config = getattr(request.app.state, "anchor_config", None)
    if config is None:
        config = AnchorConfig()

    if binding is not None:
        host = binding.get("host") or config.http_host
        port = int(binding.get("port") or config.http_port)
        data_dir = binding.get("data_dir") or str(config.data_dir)
        env = binding.get("env")
        project = binding.get("project")
        started_at = binding.get("started_at")
    else:
        # Built without `anchor serve` (tests, embedding): fall back to the
        # config, and resolve env/project from the data dir.
        host = config.http_host
        port = config.http_port
        data_dir = str(config.data_dir)
        env, project = identify_data_dir(config.data_dir)
        started_at = None

    url_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    base_url = f"http://{url_host}:{port}"
    return {
        "env": env,
        "project": project,
        "data_dir": data_dir,
        "host": host,
        "port": port,
        "base_url": base_url,
        "canvas_url_prefix": f"{base_url}/c/",
        "started_at": started_at,
    }
