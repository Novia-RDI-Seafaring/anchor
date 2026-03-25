# pyright: reportUnknownVariableType=false
"""FMU capability — FMU simulation tools and instructions."""
from dataclasses import dataclass
from textwrap import dedent
from typing import Any

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import FunctionToolset

from ..deps import AgentDeps
from ..tools import fmu as fmu_tools

# ── Tool names (used by RouterCapability) ────────────────────────────────────

HIGH_LEVEL_TOOLS: frozenset[str] = frozenset({
    "inspect_fmu_tool",
    "simulate_fmu_tool",
    "analyze_simulation_tool",
})

# ── Toolset ───────────────────────────────────────────────────────────────────

_toolset: FunctionToolset[AgentDeps] = FunctionToolset()
_toolset.tool(fmu_tools.inspect_fmu_tool)
_toolset.tool(fmu_tools.simulate_fmu_tool)
_toolset.tool(fmu_tools.analyze_simulation_tool)

# ── Instructions ──────────────────────────────────────────────────────────────

_INSTRUCTIONS = dedent("""
FMU tools:
  ALWAYS call check_canvas() first when user asks to simulate or work with FMUs.
  FMU nodes on canvas (node_type="fmu") have fmu_filename, fmu_model_name, and fmu_variables.
  Use the fmu_filename from the canvas node — do NOT ask the user to specify it if it's visible.

  inspect_fmu_tool(filename)
      Parse an uploaded FMU, create an fmu canvas node showing inputs/outputs/params.
      Only call this if no fmu node with that filename is already on canvas.
      If the fmu node already exists, use its node_id and filename directly for simulate_fmu_tool.

  simulate_fmu_tool(filename, fmu_node_id, param_overrides, stop_time)
      Run FMU simulation, create a plot node connected to the fmu node.
      fmu_node_id: use the id of the existing fmu canvas node (from check_canvas()).
      param_overrides: {param_name: value}. stop_time in seconds (default 10).

  analyze_simulation_tool(job_id, question)
      Render the simulation result as a plot image and analyze it with a vision model.
      Returns a text description of dynamics, trends, peaks, oscillations, steady-state.
      Use when the user asks about a simulation result, wants explanation, or comparison.
      job_id: the plot_job_id from a plot canvas node (find via check_canvas()).
      question: optional focused question, e.g. "why does it oscillate?" or "when does it stabilize?"
""").strip()


# ── Capability class ──────────────────────────────────────────────────────────

@dataclass
class FmuCapability(AbstractCapability[Any]):
    """FMU simulation tools and instructions."""

    def get_toolset(self) -> FunctionToolset[AgentDeps]:
        return _toolset

    def get_instructions(self) -> str:
        return _INSTRUCTIONS
