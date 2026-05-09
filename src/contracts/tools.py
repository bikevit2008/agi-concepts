"""Tools / world interfaces contracts — capability-gated tool execution.

Two distinct responsibilities:
1. ITool — uniform interface for any external action (web search,
   code execution, file access, ...). Each tool declares the capability
   token it requires.
2. IToolRegistry — stores tools by name, resolves them at call time,
   enforces capability checks before invocation, audits every call.

Capability model:
- Each tool declares its required capability (e.g. "tools:web_search").
- The governance kernel issues capability tokens (per-agent, time-bounded).
- The registry verifies the agent's token before dispatching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """A request to execute a tool."""

    tool_name: str
    args: Dict[str, Any] = field(default_factory=dict)
    agent: str = "unknown"
    capability_token: Optional[str] = None
    tick: int = 0


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    audit_id: Optional[str] = None  # link to audit log entry


@runtime_checkable
class ITool(Protocol):
    """Single executable action.

    Tools are expected to be deterministic with respect to (args), or at
    least to declare side-effects in their description. The registry MUST
    log every invocation with input/output/error for auditability.
    """

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def required_capability(self) -> str: ...

    def execute(self, call: ToolCall) -> ToolResult: ...


@runtime_checkable
class IToolRegistry(Protocol):
    """Registry + dispatcher + capability gate."""

    def register(self, tool: ITool) -> None: ...

    def list_tools(self) -> List[Dict[str, str]]:
        """Return [{name, description, required_capability}, ...]."""
        ...

    def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        capability_token: Optional[str] = None,
        tick: int = 0,
    ) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Null implementation
# ---------------------------------------------------------------------------


class NullToolRegistry:
    """No-op registry: rejects every execute(), lists nothing."""

    def register(self, tool: ITool) -> None:
        return None

    def list_tools(self) -> List[Dict[str, str]]:
        return []

    def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        capability_token: Optional[str] = None,
        tick: int = 0,
    ) -> ToolResult:
        return ToolResult(
            success=False,
            error=f"NullToolRegistry: tool {tool_name!r} not available",
        )
