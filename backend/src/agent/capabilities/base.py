"""Shared routing registry — consumed by RouterCapability, populated by each domain capability."""
from dataclasses import dataclass, field


@dataclass
class RoutingRegistry:
    """Tool-name sets that RouterCapability uses to classify and filter tools per model step."""

    list_only_tools: frozenset[str] = field(default_factory=frozenset)
    raw_search_tools: frozenset[str] = field(default_factory=frozenset)
    low_level_canvas_tools: frozenset[str] = field(default_factory=frozenset)
    high_level_technical_tools: frozenset[str] = field(default_factory=frozenset)

    @property
    def canvas_edit_tools(self) -> frozenset[str]:
        return self.low_level_canvas_tools | self.high_level_technical_tools
