"""Anchor Canvas Server — HTTP API + WebSocket for real-time canvas sync.

Start with:
    anchor-canvas --state-file ./canvas.json --data-dir ./data --port 8002
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .state import Canvas, CanvasNode, CanvasEdge

logger = logging.getLogger(__name__)

app = FastAPI(title="Anchor Canvas")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton canvas — set at startup
_canvas: Canvas | None = None
_data_dir: Path | None = None
_ws_clients: set[WebSocket] = set()


def get_canvas() -> Canvas:
    assert _canvas is not None, "Canvas not initialized"
    return _canvas


# --- WebSocket broadcast ---

def _broadcast(msg: dict) -> None:
    """Queue broadcast to all connected WebSocket clients."""
    global _ws_clients
    text = json.dumps(msg)
    disconnected = set()
    for ws in _ws_clients:
        try:
            asyncio.get_event_loop().create_task(ws.send_text(text))
        except Exception:
            disconnected.add(ws)
    if disconnected:
        _ws_clients -= disconnected


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    # Send current state on connect
    canvas = get_canvas()
    await ws.send_text(json.dumps({"event": "state", **canvas.get_state()}))
    try:
        while True:
            # Listen for client messages (e.g. user interactions)
            data = await ws.receive_text()
            msg = json.loads(data)
            _handle_client_message(msg)
    except WebSocketDisconnect:
        _ws_clients.discard(ws)


def _handle_client_message(msg: dict) -> None:
    """Handle messages from the web UI (user interactions)."""
    canvas = get_canvas()
    action = msg.get("action")

    if action == "move_node":
        canvas.update_node(msg["id"], x=msg["x"], y=msg["y"])
    elif action == "resize_node":
        canvas.update_node(msg["id"], width=msg["width"], height=msg["height"])
    elif action == "update_label":
        canvas.update_node(msg["id"], label=msg["label"])
    elif action == "remove_node":
        canvas.remove_node(msg["id"])
    elif action == "remove_edge":
        canvas.remove_edge(msg["id"])


# --- HTTP API (used by MCP server and direct clients) ---

class AddNodeRequest(BaseModel):
    id: str | None = None
    node_type: str = "concept"
    label: str = ""
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] = {}


class UpdateNodeRequest(BaseModel):
    label: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None
    parent: str | None = None
    data: dict[str, Any] | None = None


class AddEdgeRequest(BaseModel):
    id: str | None = None
    source: str
    target: str
    label: str = ""
    edge_type: str = "floating"
    data: dict[str, Any] = {}


@app.get("/api/state")
async def get_state():
    return get_canvas().get_state()


@app.post("/api/nodes")
async def add_node(req: AddNodeRequest):
    kwargs = req.model_dump(exclude_none=True)
    node = get_canvas().add_node(**kwargs)
    return node.model_dump()


@app.patch("/api/nodes/{node_id}")
async def update_node(node_id: str, req: UpdateNodeRequest):
    kwargs = {k: v for k, v in req.model_dump().items() if v is not None}
    if req.data:
        kwargs["data"] = req.data
    node = get_canvas().update_node(node_id, **kwargs)
    if not node:
        return {"error": "Node not found"}, 404
    return node.model_dump()


@app.delete("/api/nodes/{node_id}")
async def remove_node(node_id: str):
    ok = get_canvas().remove_node(node_id)
    return {"removed": ok}


@app.post("/api/edges")
async def add_edge(req: AddEdgeRequest):
    kwargs = req.model_dump(exclude_none=True)
    edge = get_canvas().add_edge(**kwargs)
    if not edge:
        return {"error": "Source or target node not found"}, 400
    return edge.model_dump()


@app.delete("/api/edges/{edge_id}")
async def remove_edge(edge_id: str):
    ok = get_canvas().remove_edge(edge_id)
    return {"removed": ok}


@app.post("/api/clear")
async def clear():
    get_canvas().clear()
    return {"cleared": True}


# --- Document data API (reads from anchor-ingest data dir) ---

@app.get("/api/documents")
async def list_documents():
    """List all ingested documents from the data directory."""
    if not _data_dir:
        return []
    silver = _data_dir / "silver"
    if not silver.is_dir():
        return []
    docs = []
    for d in sorted(silver.iterdir()):
        if not d.is_dir():
            continue
        slug = d.name
        index_path = d / "index.json"
        info = {"slug": slug, "title": slug, "pages": 0, "has_gold": False}
        if index_path.exists():
            idx = json.loads(index_path.read_text())
            info["title"] = idx.get("document", {}).get("title", slug)
            info["pages"] = idx.get("document", {}).get("page_count", 0)
        gold_dir = _data_dir / "gold" / slug / "pages"
        info["has_gold"] = gold_dir.is_dir()
        docs.append(info)
    return docs


@app.get("/api/documents/{slug}/index")
async def get_document_index(slug: str):
    """Get the silver index for a document (outline, tables, figures)."""
    if not _data_dir:
        return {"error": "No data directory configured"}
    index_path = _data_dir / "silver" / slug / "index.json"
    if not index_path.exists():
        return {"error": f"No index for '{slug}'"}
    return json.loads(index_path.read_text())


@app.get("/api/documents/{slug}/regions")
async def get_document_regions(slug: str, page: int | None = None):
    """Get gold regions for a document, optionally filtered by page."""
    if not _data_dir:
        return {"error": "No data directory configured"}
    gold_pages = _data_dir / "gold" / slug / "pages"
    if not gold_pages.is_dir():
        return {"slug": slug, "pages": {}}
    result: dict = {"slug": slug, "pages": {}}
    for rf in sorted(gold_pages.glob("*.regions.json")):
        rdata = json.loads(rf.read_text())
        pg = rdata.get("page", 0)
        if page is not None and pg != page:
            continue
        result["pages"][str(pg)] = rdata.get("regions", [])
    return result


@app.get("/api/documents/{slug}/gold-map")
async def get_gold_map(slug: str):
    """Get all gold regions + page dimensions for rendering region map overlay.

    Returns page_width, page_height (PDF points), page_count, and regions per page.
    Same format as the React app's gold-map endpoint.
    """
    if not _data_dir:
        return {"error": "No data directory"}

    # Load gold regions
    gold_pages = _data_dir / "gold" / slug / "pages"
    pages_data: dict = {}
    if gold_pages.is_dir():
        for rf in sorted(gold_pages.glob("*.regions.json")):
            try:
                data = json.loads(rf.read_text())
            except Exception:
                continue
            page_no = data.get("page", 0)
            pages_data[page_no] = data.get("regions", [])

    # Get page count from index
    page_count = 0
    index_path = _data_dir / "silver" / slug / "index.json"
    if index_path.exists():
        try:
            idx = json.loads(index_path.read_text())
            page_count = idx.get("document", {}).get("page_count", 0)
        except Exception:
            pass

    # Default A4 in points
    page_width = 595.0
    page_height = 842.0

    # Try actual page dimensions from pages.meta.json bbox_union
    meta_path = _data_dir / "silver" / slug / "pages.meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            pages_meta = meta.get("pages", {})
            if pages_meta:
                first_key = next(iter(pages_meta))
                bbox_union = pages_meta[first_key].get("bbox_union", [])
                if len(bbox_union) == 4:
                    page_width = max(bbox_union[2], page_width)
                    page_height = max(bbox_union[1], page_height)
        except Exception:
            pass

    return {
        "slug": slug,
        "page_count": page_count,
        "page_width": page_width,
        "page_height": page_height,
        "pages": pages_data,
    }


@app.get("/api/documents/{slug}/pages/{page_num}/image")
async def get_page_image(slug: str, page_num: int):
    """Get the PNG image for a document page."""
    if not _data_dir:
        return Response(status_code=404)
    img_path = _data_dir / "silver" / slug / "pages" / f"{page_num}.png"
    if not img_path.exists():
        return Response(status_code=404)
    return FileResponse(img_path, media_type="image/png")


@app.get("/api/documents/{slug}/pages/{page_num}/text")
async def get_page_text(slug: str, page_num: int):
    """Get the markdown text for a document page."""
    if not _data_dir:
        return {"error": "No data directory"}
    md_path = _data_dir / "silver" / slug / "pages" / f"{page_num}.md"
    if not md_path.exists():
        md_path = _data_dir / "silver" / slug / "pages" / f"{page_num}.raw.md"
    if not md_path.exists():
        return {"error": f"No text for page {page_num}"}
    return {"text": md_path.read_text()}


@app.get("/api/documents/{slug}/crops/{path:path}")
async def get_crop(slug: str, path: str):
    """Serve a gold region crop (SVG or PNG)."""
    if not _data_dir:
        return Response(status_code=404)
    crop_path = _data_dir / "gold" / slug / "pages" / path
    if not crop_path.exists():
        return Response(status_code=404)
    media = "image/svg+xml" if crop_path.suffix == ".svg" else "image/png"
    return FileResponse(crop_path, media_type=media)


# --- Web UI ---

_static_dir = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_static_dir / "index.html")


def main():
    parser = argparse.ArgumentParser(description="Anchor Canvas Server")
    parser.add_argument("--state-file", "-s", default="./canvas.json", help="JSON file for persistence")
    parser.add_argument("--data-dir", "-d", default=None, help="Ingestion data directory (for document browsing)")
    parser.add_argument("--port", "-p", type=int, default=8002)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    global _canvas, _data_dir
    _canvas = Canvas(state_file=Path(args.state_file).resolve())
    _canvas.on_change(_broadcast)
    if args.data_dir:
        _data_dir = Path(args.data_dir).resolve()
        logger.info("Data directory: %s", _data_dir)

    logger.info("Canvas server at http://%s:%d (state: %s)", args.host, args.port, args.state_file)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info" if args.verbose else "warning")


if __name__ == "__main__":
    main()
