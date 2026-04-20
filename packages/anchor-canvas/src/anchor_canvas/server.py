"""Anchor Canvas Server — HTTP API + WebSocket for real-time canvas sync.

Start with:
    anchor-canvas --state-file ./canvas.json --port 8002
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
from fastapi.responses import HTMLResponse
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


# --- Minimal embedded UI (placeholder until we build the React app) ---

@app.get("/")
async def index():
    return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Anchor Canvas</title>
<style>
  body { font-family: system-ui; margin: 0; background: #1a1a2e; color: #eee; }
  #canvas { width: 100vw; height: 100vh; position: relative; overflow: hidden; }
  .node { position: absolute; padding: 8px 12px; border-radius: 6px; background: #16213e;
           border: 1px solid #0f3460; font-size: 13px; cursor: move; min-width: 60px; text-align: center; }
  .node.concept { border-color: #4a9eff; }
  .node.entity { border-color: #ff6b6b; border-radius: 50%; }
  .node.fact { border-color: #ffd93d; }
  .node.document { border-color: #6bcb77; }
  .node.image { border-color: #a66cff; }
  #status { position: fixed; top: 8px; right: 12px; font-size: 12px; opacity: 0.6; }
</style></head>
<body>
<div id="canvas"></div>
<div id="status">connecting...</div>
<script>
const canvas = document.getElementById('canvas');
const status = document.getElementById('status');
let nodes = {}, edges = {};

function render() {
  canvas.innerHTML = '';
  for (const n of Object.values(nodes)) {
    const el = document.createElement('div');
    el.className = 'node ' + (n.node_type || 'concept');
    el.style.left = n.x + 'px';
    el.style.top = n.y + 'px';
    if (n.width) el.style.width = n.width + 'px';
    el.textContent = n.label || n.node_type;
    el.title = JSON.stringify(n.data || {}, null, 2);
    canvas.appendChild(el);
  }
}

function connect() {
  const ws = new WebSocket('ws://' + location.host + '/ws');
  ws.onopen = () => { status.textContent = 'connected'; };
  ws.onclose = () => { status.textContent = 'disconnected'; setTimeout(connect, 2000); };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.event === 'state') {
      nodes = {}; edges = {};
      (msg.nodes || []).forEach(n => nodes[n.id] = n);
      (msg.edges || []).forEach(e => edges[e.id] = e);
    } else if (msg.event === 'node_added' || msg.event === 'node_updated') {
      nodes[msg.node.id] = msg.node;
    } else if (msg.event === 'node_removed') {
      delete nodes[msg.id];
    } else if (msg.event === 'cleared') {
      nodes = {}; edges = {};
    }
    status.textContent = 'v' + (msg.version || '?');
    render();
  };
}
connect();
</script>
</body></html>""")


def main():
    parser = argparse.ArgumentParser(description="Anchor Canvas Server")
    parser.add_argument("--state-file", "-s", default="./canvas.json", help="JSON file for persistence")
    parser.add_argument("--port", "-p", type=int, default=8002)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)

    global _canvas
    _canvas = Canvas(state_file=Path(args.state_file).resolve())
    _canvas.on_change(_broadcast)

    logger.info("Canvas server at http://%s:%d (state: %s)", args.host, args.port, args.state_file)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info" if args.verbose else "warning")


if __name__ == "__main__":
    main()
