#!/usr/bin/env python3
"""Draw Anchor's own architecture on an Anchor canvas.

Eats our own dog food: uses only the public HTTP API to create a workspace
and populate it with the same nodes + edges that the architecture diagram
shows. Demonstrates that the canvas's primitives (concept, entity, area,
edges, pictograms, dashed styling) are expressive enough to draw the
architecture — meaning any agent or script that can hit the API can
materialise the same diagram.

Usage:
    python tools/draw_architecture.py [--base http://localhost:8003] [--slug anchor-architecture]

Requires the Anchor server to be running. Creates the workspace if it
doesn't exist; clears it first if it does.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# ---------- column layout ---------------------------------------------------

# x coordinates per column; nodes get stacked vertically inside each
COL_SOURCES = 60
COL_PRODUCERS = 320
COL_DURABLE = 580
COL_HEX = 880
COL_CONSUMERS = 1280

ROW_TOP = 60
ROW_GAP = 140

# ---------- nodes -----------------------------------------------------------

# Each node: (id, node_type, label, x, y, data, optional parent)
NODES = [
    # SOURCE FILES area
    ("area-sources", "area", "Source files", COL_SOURCES - 20, 20, {
        "width": 220, "height": 600, "tone": "sources",
        "subtitle": "what producers ingest",
    }, None),
    ("src-pdf", "concept", "PDF",
        COL_SOURCES, ROW_TOP + ROW_GAP * 0, {
            "subtitle": "datasheet, leaflet",
            "pictogram": "page",
        }, "area-sources"),
    ("src-fmu", "concept", "FMU",
        COL_SOURCES, ROW_TOP + ROW_GAP * 1, {
            "subtitle": "simulation model",
            "pictogram": "model",
        }, "area-sources"),
    ("src-cad", "concept", "CAD",
        COL_SOURCES, ROW_TOP + ROW_GAP * 2, {
            "subtitle": "STEP, future",
            "pictogram": "cube",
            "dashed": True,
        }, "area-sources"),

    # PRODUCERS area
    ("area-producers", "area", "Producers", COL_PRODUCERS - 20, 20, {
        "width": 220, "height": 600, "tone": "producers",
        "subtitle": "OIP-shaped",
    }, None),
    ("prd-pdfs", "concept", "anchor_pdfs",
        COL_PRODUCERS, ROW_TOP + ROW_GAP * 0, {
            "subtitle": "OIP producer",
            "pictogram": "funnel",
        }, "area-producers"),
    ("prd-fmus", "concept", "anchor_fmus",
        COL_PRODUCERS, ROW_TOP + ROW_GAP * 1, {
            "subtitle": "OIP producer",
            "pictogram": "funnel",
        }, "area-producers"),
    ("prd-cad", "concept", "anchor_cad",
        COL_PRODUCERS, ROW_TOP + ROW_GAP * 2, {
            "subtitle": "future producer",
            "pictogram": "funnel",
            "dashed": True,
        }, "area-producers"),

    # DURABLE area
    ("area-durable", "area", "Durable on disk", COL_DURABLE - 20, 20, {
        "width": 240, "height": 600, "tone": "durable",
        "subtitle": "filesystem substrate",
    }, None),
    ("dur-docs", "concept", "DOCUMENTS",
        COL_DURABLE, ROW_TOP + ROW_GAP * 0, {
            "subtitle": "data/<producer>/...",
            "pictogram": "stack",
        }, "area-durable"),
    ("dur-canvases", "concept", "CANVASES",
        COL_DURABLE, ROW_TOP + ROW_GAP * 2, {
            "subtitle": "data/canvases/<slug>/",
            "pictogram": "graph",
        }, "area-durable"),

    # ANCHOR hexagon (concentric layered shapes via three rings)
    ("area-anchor", "area", "Anchor", COL_HEX - 20, 20, {
        "width": 280, "height": 600, "tone": "core",
        "subtitle": "hexagonal layering",
    }, None),
    ("anc-adapters", "concept", "ADAPTERS",
        COL_HEX, ROW_TOP + ROW_GAP * 0, {
            "subtitle": "HTTP · MCP · CLI · SSE",
            "pictogram": "hexagon",
        }, "area-anchor"),
    ("anc-infra", "concept", "INFRA",
        COL_HEX, ROW_TOP + ROW_GAP * 1, {
            "subtitle": "FsStores · MemoryBus",
            "pictogram": "hexagon",
        }, "area-anchor"),
    ("anc-core", "concept", "CORE",
        COL_HEX, ROW_TOP + ROW_GAP * 2, {
            "subtitle": "WorkspaceService · DomainEvent",
            "pictogram": "hexagon",
        }, "area-anchor"),
    ("anc-bus", "concept", "Event bus",
        COL_HEX, ROW_TOP + ROW_GAP * 3, {
            "subtitle": "in-memory pub/sub",
            "pictogram": "wave",
        }, "area-anchor"),

    # CONSUMERS area
    ("area-consumers", "area", "Consumers", COL_CONSUMERS - 20, 20, {
        "width": 240, "height": 760, "tone": "consumers",
        "subtitle": "many siblings",
    }, None),
    ("con-monitor", "concept", "MONITOR",
        COL_CONSUMERS, ROW_TOP + ROW_GAP * 0, {
            "subtitle": "headless · today",
            "pictogram": "chart",
        }, "area-consumers"),
    ("con-ui", "concept", "UI",
        COL_CONSUMERS, ROW_TOP + ROW_GAP * 1, {
            "subtitle": "visual canvas · today",
            "pictogram": "panel",
        }, "area-consumers"),
    ("con-agents", "concept", "AGENTS",
        COL_CONSUMERS, ROW_TOP + ROW_GAP * 2, {
            "subtitle": "Claude, Cursor · today",
            "pictogram": "chat",
        }, "area-consumers"),
    ("con-voice", "concept", "VOICE",
        COL_CONSUMERS, ROW_TOP + ROW_GAP * 3, {
            "subtitle": "future",
            "pictogram": "mic",
            "dashed": True,
        }, "area-consumers"),
    ("con-xr", "concept", "XR / Omniverse",
        COL_CONSUMERS, ROW_TOP + ROW_GAP * 4, {
            "subtitle": "future",
            "pictogram": "headset",
            "dashed": True,
        }, "area-consumers"),
]

# ---------- edges -----------------------------------------------------------

# Each edge: (source, target, label, edge_type)
EDGES = [
    # source -> producer
    ("src-pdf", "prd-pdfs", "", "floating"),
    ("src-fmu", "prd-fmus", "", "floating"),
    ("src-cad", "prd-cad", "", "floating"),

    # producer -> documents (via OIP)
    ("prd-pdfs", "dur-docs", "OIP", "floating"),
    ("prd-fmus", "dur-docs", "OIP", "floating"),
    ("prd-cad", "dur-docs", "OIP", "floating"),

    # documents <-> core (event sourcing-ish; durable substrate feeds anchor)
    ("dur-docs", "anc-core", "", "floating"),
    ("dur-canvases", "anc-core", "events.jsonl", "floating"),
    ("anc-core", "dur-canvases", "snapshot.json", "floating"),

    # internal: core -> bus, bus -> adapters
    ("anc-core", "anc-bus", "publish", "floating"),
    ("anc-bus", "anc-adapters", "subscribe", "floating"),
    ("anc-adapters", "anc-infra", "", "floating"),
    ("anc-infra", "anc-core", "", "floating"),

    # adapters <-> consumers
    ("anc-adapters", "con-monitor", "SSE", "floating"),
    ("anc-adapters", "con-ui", "HTTP · SSE", "floating"),
    ("anc-adapters", "con-agents", "MCP", "floating"),
    ("anc-adapters", "con-voice", "MCP", "floating"),
    ("anc-adapters", "con-xr", "MCP", "floating"),
]


# ---------- HTTP helpers ----------------------------------------------------

def _request(method: str, url: str, body: dict | None = None) -> dict | None:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"content-type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req) as rsp:
            raw = rsp.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {url} → {e.code}\n{body_text}") from e


def get(base: str, path: str) -> dict | None:
    return _request("GET", f"{base}{path}")


def post(base: str, path: str, body: dict) -> dict | None:
    return _request("POST", f"{base}{path}", body)


def delete(base: str, path: str) -> dict | None:
    return _request("DELETE", f"{base}{path}")


# ---------- main ------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", default="http://localhost:8003",
                   help="anchor server base URL")
    p.add_argument("--slug", default="anchor-architecture",
                   help="workspace slug to draw into")
    args = p.parse_args()

    base = args.base.rstrip("/")
    slug = args.slug

    # Verify server is up
    try:
        get(base, "/api/workspaces")
    except Exception as e:  # noqa: BLE001
        print(f"server not reachable at {base}: {e}", file=sys.stderr)
        return 1

    # Create workspace if missing; clear if existing
    workspaces = get(base, "/api/workspaces") or []
    have = any(w.get("slug") == slug for w in workspaces)
    if have:
        print(f"clearing existing workspace '{slug}'")
        post(base, f"/api/workspaces/{slug}/clear", {})
    else:
        print(f"creating workspace '{slug}'")
        post(base, "/api/workspaces", {"slug": slug, "title": "Anchor architecture"})

    # Place areas first so children can parent to them
    print(f"placing {len(NODES)} nodes...")
    for nid, ntype, label, x, y, data, parent in NODES:
        body = {
            "id": nid,
            "node_type": ntype,
            "label": label,
            "x": float(x),
            "y": float(y),
            "data": data,
        }
        if parent:
            body["parent"] = parent
        if "width" in data:
            body["width"] = data["width"]
        if "height" in data:
            body["height"] = data["height"]
        post(base, f"/api/workspaces/{slug}/nodes", body)

    print(f"placing {len(EDGES)} edges...")
    for src, tgt, label, etype in EDGES:
        post(base, f"/api/workspaces/{slug}/edges", {
            "source": src,
            "target": tgt,
            "label": label,
            "edge_type": etype,
        })

    print(f"done. open {base.replace('/api', '')}/c/{slug}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
