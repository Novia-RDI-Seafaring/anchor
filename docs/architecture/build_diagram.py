# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools>=4.50", "playwright==1.59.0"]
# ///
"""Draw Anchor's architecture figure: intent loop (a) and software layers (b).

Run from the repository root:

    uv run docs/architecture/build_diagram.py            # SVG + PDF
    uv run docs/architecture/build_diagram.py --png out.png

Writes ``docs/assets/diagrams/anchor-architecture.svg`` (fonts embedded as a
subset, so it renders the same everywhere) and ``anchor-architecture.pdf``
(190 mm wide, a journal column-and-a-half figure).

The build checks itself. Text is measured with the font's own metrics while
laying out, then the SVG is opened in headless Chromium and every rendered
text box is checked against the box it belongs to and against every other
text. Any overflow or collision fails the build with the offending strings.

The figure is a logical view. The browser, the agent harness and the CLI are
separate processes; they meet in the project's files. See
``docs/architecture/diagram-brief.md`` for the inventory behind each box.
"""
from __future__ import annotations

import argparse
import io
import sys
from base64 import b64encode
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
FONTS = HERE / "fonts"
OUT_DIR = HERE.parent / "assets" / "diagrams"
STEM = "anchor-architecture"

TITLE = "Anchor: intent-driven collaboration and software layers"
DESC = (
    "Panel a: a person expresses an intent on the canvas in the browser; the browser resolves the marks to "
    "element ids; Anchor stores the intent; the user's agent harness pulls it, reads the canvas and sources, "
    "and replies with questions, suggestions or direct additions; Anchor stages or applies them; the person "
    "reviews in place. Panel b: inside one environment, the HTTP, MCP and CLI entry points share one project "
    "runtime. The pure core holds the intent and workspace services. Producer extensions (PDF, FMU, CAD, "
    "SysML) plug in beside it; the PDF extension resolves source references and may call an optional model "
    "API outside the environment, only if the environment allows egress. Infrastructure implements the "
    "storage and event ports over plain project files: intents, canvases and documents in bronze, silver and "
    "gold layers."
)

W, H = 900, 1058
WIDTH_MM = 190

# Colour carries one meaning across both panels.
INK, MUTED, LINE, RULE = "#20303B", "#4D5C66", "#6C7B85", "#CFD7DD"
BLUE, BLUE_BG = "#245C7A", "#EDF4F8"        # the person, in the browser
TEAL, TEAL_BG = "#28695F", "#EFF6F3"        # Anchor
AMBER, AMBER_BG = "#8C6220", "#FBF5E8"      # outside Anchor: agent harness, model API
GREY_BG, PANEL_BG = "#F2F4F6", "#F7F9FA"

BODY, SMALL, CAPS = 13.0, 12.0, 11.5
LINE_STEP = 19.0


# ---------------------------------------------------------------- fonts ----

class Face:
    """One font file: advance widths for layout, and a subset for embedding."""

    def __init__(self, path: Path, weight: int) -> None:
        self.path, self.weight = path, weight
        self.font = TTFont(path)
        self.upm = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.hmtx = self.font["hmtx"]
        self.used: set[str] = set()

    def width(self, text: str, size: float) -> float:
        self.used.update(text)
        units = 0
        for ch in text:
            glyph = self.cmap.get(ord(ch)) or ".notdef"
            units += self.hmtx[glyph][0]
        return units * size / self.upm

    def subset_b64(self) -> str:
        font = TTFont(self.path)
        options = Options()
        options.layout_features = ["kern", "liga", "calt"]
        sub = Subsetter(options)
        sub.populate(text="".join(sorted(self.used | set(" .,-0123456789"))))
        sub.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        return b64encode(buf.getvalue()).decode("ascii")


REGULAR = Face(FONTS / "WorkSans-Regular.ttf", 400)
BOLD = Face(FONTS / "WorkSans-Bold.ttf", 700)


def face(bold: bool) -> Face:
    return BOLD if bold else REGULAR


def wrap(text: str, size: float, width: float, bold: bool = False) -> list[str]:
    """Greedy word wrap with real advance widths."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if face(bold).width(trial, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# --------------------------------------------------------------- canvas ----

@dataclass
class Box:
    id: str
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


@dataclass
class Figure:
    parts: list[str] = field(default_factory=list)
    boxes: dict[str, Box] = field(default_factory=dict)
    markers: set[str] = field(default_factory=set)

    # -- primitives ---------------------------------------------------------

    def rect(self, box_id: str | None, x, y, w, h, fill="#FFFFFF", stroke=LINE, width=1.0,
             dash: str | None = None, radius=3.0) -> Box:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        tag = f' data-box="{box_id}"' if box_id else ""
        self.parts.append(
            f'<rect{tag} x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{extra}/>'
        )
        box = Box(box_id or "", x, y, w, h)
        if box_id:
            assert box_id not in self.boxes, f"duplicate box id {box_id}"
            self.boxes[box_id] = box
        return box

    def text(self, x, y, value: str, size=BODY, bold=False, color=INK, align="left",
             within: str | None = None) -> float:
        """Draw one line at baseline ``y``; ``within`` names the box it must stay in."""
        width = face(bold).width(value, size)
        start = {"left": x, "center": x - width / 2, "right": x - width}[align]
        assert start >= 0 and start + width <= W, f"text leaves the figure: {value!r}"
        if within:
            box = self.boxes[within]
            assert box.x <= start and start + width <= box.right, (
                f"text wider than its box {within!r}: {value!r} ({width:.0f} px in {box.w:.0f})"
            )
        anchor = {"left": "start", "center": "middle", "right": "end"}[align]
        tag = f' data-in="{within}"' if within else ""
        self.parts.append(
            f'<text{tag} x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{700 if bold else 400}" '
            f'text-anchor="{anchor}" fill="{color}">{escape(value)}</text>'
        )
        return width

    def path(self, points, color=LINE, width=1.2, arrow=False, dash: str | None = None) -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        if arrow:
            marker = "m" + color.lstrip("#")
            self.markers.add(color)
            extra += f' marker-end="url(#{marker})"'
        pts = " ".join(f"{px},{py}" for px, py in points)
        self.parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" '
            f'stroke-linejoin="round"{extra}/>'
        )

    # -- composites ---------------------------------------------------------

    def card(self, box_id, x, y, w, h, title, lines, fill, stroke, number=None,
             size=BODY) -> Box:
        """A titled card. ``lines`` are wrapped to the card; the card must hold them."""
        box = self.rect(box_id, x, y, w, h, fill=fill, stroke=stroke, width=1.2)
        offset = 14
        if number is not None:
            self.parts.append(
                f'<circle cx="{x + 24}" cy="{y + 24}" r="11" fill="{stroke}"/>'
            )
            self.text(x + 24, y + 29, str(number), 12.5, True, "#FFFFFF", "center", within=box_id)
            offset = 43
        self.text(x + offset, y + 29, title, 14.5, True, stroke, within=box_id)
        row = 0
        for line in lines:
            for piece in wrap(line, size, w - 28):
                self.text(x + 14, y + 53 + row * LINE_STEP, piece, size, within=box_id)
                row += 1
        used = 53 + (row - 1) * LINE_STEP + 8 if row else 36
        assert used <= h, f"card {box_id!r} needs {used:.0f} px, has {h}"
        return box

    def label(self, x, y, value, color=MUTED, within=None) -> None:
        self.text(x, y, value.upper(), CAPS, True, color, within=within)

    # -- output -------------------------------------------------------------

    def svg(self) -> str:
        fonts = "".join(
            f'@font-face{{font-family:"Work Sans";font-weight:{f.weight};'
            f'src:url(data:font/ttf;base64,{f.subset_b64()}) format("truetype");}}'
            for f in (REGULAR, BOLD)
        )
        markers = "".join(
            f'<marker id="m{c.lstrip("#")}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
            f'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            for c in sorted(self.markers)
        )
        height_mm = WIDTH_MM * H / W
        return "\n".join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH_MM}mm" height="{height_mm:.2f}mm" '
            f'viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{escape(TITLE)}</title>',
            f'<desc id="desc">{escape(DESC)}</desc>',
            f"<defs><style>{fonts}text{{font-family:\"Work Sans\",Arial,sans-serif}}</style>{markers}</defs>",
            f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
            *self.parts,
            "</svg>",
        ])


# --------------------------------------------------------------- panels ----

def panel_a(f: Figure) -> None:
    """The intent loop: express, resolve, store, act, apply or stage, review."""
    f.text(20, 28, "a", 16, True)
    f.text(43, 28, "Intent-driven collaboration", 18, True)
    f.label(20, 60, "Browser: draw and resolve", BLUE)
    f.label(460, 60, "Anchor: durable handoff", TEAL)
    f.label(680, 60, "User's agent harness", AMBER)

    f.card("a1", 20, 73, 190, 140, "Express intent", [], BLUE_BG, BLUE, 1)
    f.text(34, 125, "Select, draw, point, label", BODY, within="a1")
    # A gesture on a table: a stroke between rows and a callout.
    f.rect(None, 38, 140, 71, 55, stroke="#84949E", width=0.8, radius=0)
    for gy in (154, 168, 182):
        f.path([(38, gy), (109, gy)], "#B6C2CA", 0.7)
    f.path([(68, 140), (68, 195)], "#B6C2CA", 0.7)
    f.path([(30, 169), (62, 167), (88, 169), (116, 168)], AMBER, 2)
    f.text(122, 160, "split here", 11.5, color=AMBER, within="a1")

    f.card("a2", 240, 73, 190, 140, "Resolve marks", [
        "Element and row ids",
        "Sketch nodes and edges",
        "Positions and edit marks",
        "Typed text + structure",
    ], BLUE_BG, BLUE, 2)
    f.card("a3", 460, 73, 190, 140, "Store intent", [
        "Durable project request",
        "Targets + canvas version",
        "Thread of asks, replies",
        "Signal: intent pending",
    ], TEAL_BG, TEAL, 3)
    f.card("a4", 680, 73, 190, 140, "Interpret + act", [
        "Pull it via MCP or CLI",
        "Read canvas and sources",
        "Ask, suggest or add",
        "Post progress, result",
    ], AMBER_BG, AMBER, 4)
    for x in (210, 430, 650):
        f.path([(x, 147), (x + 29, 147)], LINE, 1.35, arrow=True)

    f.card("a5", 460, 263, 190, 114, "Apply or stage", [
        "Additions land proposed",
        "Suggestions are staged",
        "Checked against version",
    ], TEAL_BG, TEAL, 5)
    f.card("a6", 240, 263, 190, 114, "Review in place", [
        "Approve: applied at once",
        "Decline, revert, revise",
        "Accept or reject a set",
    ], BLUE_BG, BLUE, 6)
    f.path([(775, 213), (775, 320), (651, 320)], AMBER, 1.4, arrow=True)
    f.text(683, 294, "operations", BODY, color=AMBER)
    f.text(683, 311, "and replies", BODY, color=AMBER)
    f.path([(460, 320), (431, 320)], TEAL, 1.4, arrow=True)
    f.path([(240, 320), (115, 320), (115, 214)], BLUE, 1.4, arrow=True)
    f.text(29, 345, "revise / clarify", BODY, color=BLUE)

    note = ("Canvas changes reach every open view over SSE, including writes from other processes. "
            "Intents send only a pending signal; the browser then pulls the thread from the project store.")
    for i, line in enumerate(wrap(note, 12.0, 860)):
        f.text(20, 397 + i * 17, line, 12.0, color=MUTED)
    f.path([(20, 436), (880, 436)], RULE, 0.8)


def panel_b(f: Figure) -> None:
    """Software layers inside one environment, with the model API outside it."""
    f.text(20, 466, "b", 16, True)
    f.text(43, 466, "Software responsibilities", 18, True)

    # Outside the trust boundary, top right: the optional model endpoint.
    f.card("api", 672, 448, 208, 56, "Model API (optional)", [], AMBER_BG, AMBER)
    f.text(686, 494, "OpenAI-compatible endpoint", SMALL, color=MUTED, within="api")

    env = f.rect("env", 20, 520, 860, 524, fill="#FFFFFF", stroke=INK, width=1.0, dash="6,4", radius=6)
    f.label(32, 540, "Environment", INK, within="env")
    f.text(130, 540, "trust boundary: provider, endpoint and local-only mode hold for every project",
           SMALL, color=MUTED, within="env")

    # Entry points.
    cells = [("HTTP + SSE", "the browser", BLUE), ("MCP (stdio)", "an agent harness", AMBER),
             ("CLI", "scripts and agents", INK)]
    strip = f.rect("entry", 32, 552, 592, 52, fill=GREY_BG, stroke=LINE)
    cell_w = strip.w / 3
    for i, (name, who, color) in enumerate(cells):
        cx = strip.x + cell_w * i + cell_w / 2
        if i:
            f.path([(strip.x + cell_w * i, strip.y), (strip.x + cell_w * i, strip.bottom)], "#A7B3BB", 0.8)
        f.text(cx, strip.y + 23, name, 14, True, INK, "center", within="entry")
        f.text(cx, strip.y + 41, f"used by {who}", SMALL, color=color, align="center", within="entry")

    run = f.rect("runtime", 32, 620, 592, 34, fill=TEAL_BG, stroke=TEAL)
    w = f.text(46, 642, "ProjectRuntime", BODY, True, TEAL, within="runtime")
    f.text(46 + w + 10, 642, "one composition root per project; every entry point shares its services",
           SMALL, color=INK, within="runtime")
    for i in range(3):
        cx = strip.x + cell_w * i + cell_w / 2
        f.path([(cx, strip.bottom), (cx, run.y - 1)], LINE, 1.1, arrow=True)

    # Pure core.
    core = f.rect("core", 32, 680, 592, 150, fill=PANEL_BG, stroke=TEAL, width=0.9, dash="5,3")
    f.label(44, 698, "Pure core", TEAL, within="core")
    f.text(124, 698, "no files, no network, no vendor SDKs", SMALL, color=MUTED, within="core")
    f.path([(328, run.bottom), (328, core.y - 1)], LINE, 1.1, arrow=True)
    f.card("intent", 44, 710, 264, 108, "Intent service", [
        "Enqueue, thread, resolve",
        "Questions and suggestions",
        "Apply, decline, revert",
    ], TEAL_BG, TEAL)
    f.card("workspace", 344, 710, 268, 108, "Workspace service", [
        "Nodes, edges, spec rows",
        "Validate, persist, publish",
        "Attributed, versioned changes",
    ], TEAL_BG, TEAL)
    f.path([(308, 764), (343, 764)], TEAL, 1.3, arrow=True)
    f.text(326, 756, "ops", SMALL, color=TEAL, align="center")

    # Producer extensions, plugged in beside the core.
    ext = f.rect("ext", 664, 552, 204, 278, fill=PANEL_BG, stroke=TEAL, width=0.9, dash="5,3")
    f.label(676, 570, "Extensions", TEAL, within="ext")
    f.card("pdf", 676, 580, 180, 150, "PDF", [
        "Bronze, silver, gold",
        "Search regions, cells",
        "Resolve source refs",
        "Keyed or harness ingest",
    ], TEAL_BG, TEAL, size=SMALL)
    for i, name in enumerate(("FMU", "CAD", "SysML")):
        bx = 676 + i * 62
        f.rect(f"chip{i}", bx, 742, 56, 28, fill=TEAL_BG, stroke=TEAL, width=1.0)
        f.text(bx + 28, 761, name, SMALL, True, TEAL, "center", within=f"chip{i}")
    for i, line in enumerate(wrap("Each ships an OIP manifest; the core never imports one.", SMALL, 180)):
        f.text(676, 790 + i * 16, line, SMALL, color=MUTED, within="ext")
    f.path([(run.right, 637), (ext.x - 1, 637)], LINE, 1.1, arrow=True)
    f.text(644, 630, "starts", SMALL, color=MUTED, align="center")
    # Source resolution: a spec row's ref is filled in from gold regions.
    f.path([(ext.x, 800), (613, 800)], TEAL, 1.3, arrow=True)
    f.text(644, 792, "refs", SMALL, color=TEAL, align="center")

    # The only way out: PDF model calls, if the environment allows egress.
    f.path([(800, 580), (800, 505)], AMBER, 1.3, arrow=True, dash="4,3")
    f.text(792, 534, "only if egress", SMALL, color=AMBER, align="right")
    f.text(792, 548, "is allowed", SMALL, color=AMBER, align="right")

    # Infrastructure.
    infra = f.rect("infra", 32, 858, 836, 54, fill=GREY_BG, stroke=LINE)
    f.label(46, 878, "Infrastructure: implements the ports", MUTED, within="infra")
    f.text(46, 899, "File stores  ·  In-process event bus  ·  Event-log tailer for other processes  ·  "
           "Presence and activity log", BODY, within="infra")
    f.path([(328, core.bottom), (328, infra.y - 1)], LINE, 1.1, arrow=True)
    f.path([(766, ext.bottom), (766, infra.y - 1)], LINE, 1.1, arrow=True)

    # Files.
    files = f.rect("files", 32, 938, 836, 94, fill=PANEL_BG, stroke=LINE)
    f.path([(450, infra.bottom), (450, files.y - 1)], LINE, 1.1, arrow=True)
    f.text(462, 930, "read / write", SMALL, color=MUTED)
    f.label(46, 957, "Project files", MUTED, within="files")
    f.text(160, 957, "plain files in .anchor_data, shared by anchor serve, anchor-mcp and the CLI",
           SMALL, color=MUTED, within="files")
    columns = [
        ("Intents", "Requests + thread items", "Outlive any one agent session"),
        ("Canvases", "Event log + state snapshot", "Source refs on nodes and rows"),
        ("Documents", "Bronze / Silver / Gold", "PDFs, layout, source regions"),
    ]
    col_w = files.w / 3
    for i, (head, line1, line2) in enumerate(columns):
        x = files.x + 14 + i * col_w
        if i:
            f.path([(files.x + i * col_w, 966), (files.x + i * col_w, 1024)], "#B8C3CA", 0.8)
        f.text(x, 982, head, 14, True, within="files")
        f.text(x, 1002, line1, BODY, within="files")
        f.text(x, 1021, line2, SMALL, color=MUTED, within="files")
    assert env.bottom >= files.bottom + 8


# --------------------------------------------------------------- checks ----

def static_checks(f: Figure) -> list[str]:
    """Sibling boxes must not overlap unless one contains the other."""
    problems = []
    items = [b for b in f.boxes.values() if b.id]

    def contains(a: Box, b: Box) -> bool:
        return a.x <= b.x and a.y <= b.y and b.right <= a.right and b.bottom <= a.bottom

    for i, a in enumerate(items):
        for b in items[i + 1:]:
            overlap = min(a.right, b.right) > max(a.x, b.x) and min(a.bottom, b.bottom) > max(a.y, b.y)
            if overlap and not (contains(a, b) or contains(b, a)):
                problems.append(f"boxes overlap: {a.id} and {b.id}")
    return problems


RENDER_CHECK = """
() => {
  const svg = document.querySelector('svg');
  const vb = svg.viewBox.baseVal;
  const boxes = {};
  for (const r of svg.querySelectorAll('rect[data-box]')) boxes[r.dataset.box] = r.getBBox();
  const texts = [...svg.querySelectorAll('text')].map(t => ({t: t.textContent, b: t.getBBox(), in: t.dataset.in}));
  const bad = [];
  const pad = 1;
  for (const {t, b, in: owner} of texts) {
    if (b.x < vb.x || b.y < vb.y || b.x + b.width > vb.width || b.y + b.height > vb.height) bad.push('outside figure: ' + t);
    const o = owner && boxes[owner];
    if (o && (b.x < o.x - pad || b.y < o.y - pad || b.x + b.width > o.x + o.width + pad || b.y + b.height > o.y + o.height + pad))
      bad.push('outside ' + owner + ': ' + t);
  }
  // A label may sit inside a box or clear of it, never across its border.
  for (const {t, b} of texts) for (const [id, o] of Object.entries(boxes)) {
    const ox = Math.min(b.x + b.width, o.x + o.width) - Math.max(b.x, o.x);
    const oy = Math.min(b.y + b.height, o.y + o.height) - Math.max(b.y, o.y);
    const inside = b.x >= o.x - pad && b.y >= o.y - pad && b.x + b.width <= o.x + o.width + pad && b.y + b.height <= o.y + o.height + pad;
    if (ox > 1 && oy > 1 && !inside) bad.push('text crosses the border of ' + id + ': ' + t);
  }
  for (let i = 0; i < texts.length; i++) for (let j = i + 1; j < texts.length; j++) {
    const a = texts[i].b, c = texts[j].b;
    const ox = Math.min(a.x + a.width, c.x + c.width) - Math.max(a.x, c.x);
    const oy = Math.min(a.y + a.height, c.y + c.height) - Math.max(a.y, c.y);
    if (ox > 1 && oy > 2) bad.push('text collides: ' + JSON.stringify(texts[i].t) + ' / ' + JSON.stringify(texts[j].t));
  }
  return bad;
}
"""


def render(svg_path: Path, pdf_path: Path, png_path: Path | None) -> list[str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2)
        page.goto(svg_path.as_uri())
        page.evaluate("document.fonts.ready.then(() => true)")
        problems = page.evaluate(RENDER_CHECK)
        if png_path:
            page.locator("svg").first.screenshot(path=str(png_path))
        # Print from an HTML page: page.pdf cannot print a bare SVG document.
        page = browser.new_page()
        page.set_content(f"<html><body style='margin:0'>{svg_path.read_text(encoding='utf-8')}</body></html>")
        page.evaluate("document.fonts.ready.then(() => true)")
        page.pdf(path=str(pdf_path), width=f"{WIDTH_MM}mm", height=f"{WIDTH_MM * H / W + 0.5:.2f}mm",
                 print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        browser.close()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--png", type=Path, help="also write a PNG preview here")
    args = parser.parse_args()

    fig = Figure()
    panel_a(fig)
    panel_b(fig)
    problems = static_checks(fig)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    svg_path = args.out_dir / f"{STEM}.svg"
    pdf_path = args.out_dir / f"{STEM}.pdf"
    svg_path.write_text(fig.svg(), encoding="utf-8")
    problems += render(svg_path, pdf_path, args.png)

    for line in problems:
        print(f"layout: {line}", file=sys.stderr)
    print(svg_path)
    print(pdf_path)
    if args.png:
        print(args.png)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
