# pyright: reportUnknownVariableType=false
"""Engineering knowledge capability — pump-curve reference tools and instructions."""
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

from pydantic_ai import BinaryContent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from ...deps import AgentDeps

HIGH_LEVEL_TOOLS: frozenset[str] = frozenset({
    "get_pump_curve_reference",
    "get_sample_pump_curve",
})

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "engineering" / "pump_curves"

_PUMP_CURVE_TOPICS: dict[str, dict[str, str]] = {
    "title_box": {
        "image": "pump_curve_titlebox.png",
        "title": "Pump Curve Title Box",
        "text": (
            "The title box identifies which pump and speed the curve applies to: manufacturer, "
            "pump model and size, rated speed, and impeller range. Check this first so you do "
            "not read the wrong curve."
        ),
    },
    "x_axis": {
        "image": "pump_curve_xaxis.png",
        "title": "Pump Curve X-Axis",
        "text": (
            "The x-axis is flow rate, often in GPM, m3/h, or L/s. As required head rises, the "
            "operating point moves left and delivered flow drops."
        ),
    },
    "y_axis": {
        "image": "pump_curve_yaxis.png",
        "title": "Pump Curve Y-Axis",
        "text": (
            "The y-axis is head, usually in feet or meters. Head is the pressure-equivalent lift "
            "the pump can produce and is preferred because it is independent of fluid density."
        ),
    },
    "impeller": {
        "image": "pump_curve_impeller.png",
        "title": "Impeller Trim Curves",
        "text": (
            "The family of descending H-Q curves corresponds to impeller diameters. Larger "
            "impellers sit higher and deliver more head and flow. Each curve typically follows "
            "a shutoff-head-minus-k-times-flow-squared shape."
        ),
    },
    "horsepower": {
        "image": "pump_curve_horsepower.png",
        "title": "Horsepower Lines",
        "text": (
            "Diagonal horsepower lines indicate power requirement at each operating point. Power "
            "usually rises with flow, so points far to the right can drive motor sizing and energy use."
        ),
    },
    "npshr": {
        "image": "pump_curve_npsh.png",
        "title": "NPSHr Curves",
        "text": (
            "NPSHr is Net Positive Suction Head Required. It rises with flow and sets the minimum "
            "suction condition needed to avoid cavitation. The system must provide NPSHa greater than NPSHr."
        ),
    },
    "minimum_flow": {
        "image": "pump_curve_minflow.png",
        "title": "Minimum Flow Line",
        "text": (
            "The minimum continuous stable flow line marks the unsafe low-flow region. Operating "
            "left of it risks recirculation, overheating, vibration, and premature damage."
        ),
    },
}

_OVERVIEW = dedent("""
Pump curve reading guide:
  - Title box: identifies model, size, speed, and impeller range
  - X-axis: flow rate
  - Y-axis: head
  - H-Q curves: one per impeller size, descending left to right
  - BEP: best efficiency region, usually where the pump should operate
  - Horsepower lines: motor load at each operating point
  - NPSHr: suction requirement curve
  - Minimum flow line: left-side unsafe operating boundary

Available topic names for get_pump_curve_reference(topic):
  title_box, x_axis, y_axis, impeller, horsepower, npshr, minimum_flow
""").strip()

_SAMPLE_CURVE_INTRO = (
    "Example matplotlib code for a centrifugal pump performance curve, including "
    "manufacturer and experimental H-Q curves with efficiency and power overlays."
)

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()


def _load_image(filename: str) -> BinaryContent | None:
    path = _KNOWLEDGE_DIR / filename
    if not path.exists():
        return None
    return BinaryContent(data=path.read_bytes(), media_type="image/png")


@_toolset.tool_plain
def get_pump_curve_reference(topic: str = "overview") -> list[str | BinaryContent]:
    """Return reference knowledge for reading centrifugal pump curves.

    topic:
      overview, title_box, x_axis, y_axis, impeller, horsepower, npshr, minimum_flow

    Use this before or during PDF pump-curve analysis when you need help interpreting
    chart structure, labels, or operating concepts.
    """
    normalized = topic.strip().lower().replace(" ", "_")
    if normalized in {"overview", "summary", "guide"}:
        return [_OVERVIEW]

    entry = _PUMP_CURVE_TOPICS.get(normalized)
    if not entry:
        available = ", ".join(sorted(_PUMP_CURVE_TOPICS))
        return [f"Unknown pump-curve topic '{topic}'. Available topics: overview, {available}."]

    result: list[str | BinaryContent] = [f"{entry['title']}\n\n{entry['text']}"]
    image = _load_image(entry["image"])
    if image is not None:
        result.append(f"[Annotated reference image: {entry['title']}]")
        result.append(image)
    return result


@_toolset.tool_plain
def get_sample_pump_curve() -> list[str | BinaryContent]:
    """Return example pump-curve plotting code and its rendered output image.

    Use this when you want a concrete reference for what a pump performance chart
    looks like or how one can be represented programmatically.
    """
    result: list[str | BinaryContent] = []

    code_path = _KNOWLEDGE_DIR / "sample_code.py"
    if code_path.exists():
        code = code_path.read_text(encoding="utf-8")
        result.append(f"{_SAMPLE_CURVE_INTRO}\n\n```python\n{code}\n```")

    image = _load_image("sample_output.png")
    if image is not None:
        result.append("[Rendered sample pump curve]")
        result.append(image)

    if not result:
        result.append("Pump curve reference assets are not available.")

    return result


_INSTRUCTIONS = dedent("""
Engineering knowledge tools:
  get_pump_curve_reference(topic)
      Use when the user asks about pump curves, performance charts, head-flow plots,
      NPSHr, BEP, horsepower overlays, impeller trims, or minimum-flow limits.
      This gives you reference engineering knowledge plus annotated example images.

  get_sample_pump_curve()
      Use when you want a concrete sample chart and plotting pattern for a centrifugal pump curve.

Usage rule:
  When analyzing a pump curve from a PDF or canvas image:
  1. If the chart semantics are unclear, call get_pump_curve_reference() first.
  2. Then use read_document_page() or analyze_pdf_page() on the actual datasheet page.
  3. Ground the final answer in the real document, not only in generic pump knowledge.
""").strip()


@dataclass
class EngineeringKnowledgeCapability(AbstractCapability[Any]):
    """Engineering reference knowledge tools."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
