"""Decorator helpers for capability-gated tools.

This borrows Agno's ergonomics while keeping execution behind the existing
`CapabilityGatedToolRegistry` contract.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, overload

from src.contracts.tools import ToolCall, ToolResult

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class ToolMetadata:
    """Static metadata attached to decorated tool functions."""

    name: str
    description: str
    required_capability: str
    requires_confirmation: bool = False
    cache_results: bool = False
    is_async: bool = False


@dataclass
class FunctionTool:
    """ITool adapter around a Python callable."""

    entrypoint: Callable[..., Any]
    metadata: ToolMetadata

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def description(self) -> str:
        return self.metadata.description

    @property
    def required_capability(self) -> str:
        return self.metadata.required_capability

    def execute(self, call: ToolCall) -> ToolResult:
        try:
            output = self.entrypoint(**call.args)
            if inspect.isawaitable(output):
                output = _run_awaitable(output)
            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, error=f"tool exception: {e}")


def _is_async_function(func: Callable[..., Any]) -> bool:
    if inspect.iscoroutinefunction(func):
        return True
    original = getattr(func, "__wrapped__", None)
    if original is not None and inspect.iscoroutinefunction(original):
        return True
    code = getattr(func, "__code__", None)
    if code is not None and code.co_flags & inspect.CO_COROUTINE:
        return True
    original_func = getattr(func, "__func__", None)
    return bool(original_func and inspect.iscoroutinefunction(original_func))


def _run_awaitable(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("async tool execution requires an async registry")


@overload
def tool(func: F) -> FunctionTool: ...


@overload
def tool(
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    required_capability: Optional[str] = None,
    requires_confirmation: bool = False,
    cache_results: bool = False,
) -> Callable[[F], FunctionTool]: ...


def tool(*args: Any, **kwargs: Any) -> FunctionTool | Callable[[F], FunctionTool]:
    """Convert a callable into an `ITool` adapter."""
    valid = {
        "name",
        "description",
        "required_capability",
        "requires_confirmation",
        "cache_results",
    }
    invalid = set(kwargs) - valid
    if invalid:
        raise ValueError(f"Invalid tool configuration arguments: {sorted(invalid)}")

    def decorate(func: F) -> FunctionTool:
        @wraps(func)
        def wrapped(*w_args: Any, **w_kwargs: Any) -> Any:
            return func(*w_args, **w_kwargs)

        tool_name = kwargs.get("name") or func.__name__
        description = kwargs.get("description") or inspect.getdoc(func) or tool_name
        capability = kwargs.get("required_capability") or f"tools:{tool_name}"
        metadata = ToolMetadata(
            name=tool_name,
            description=description,
            required_capability=capability,
            requires_confirmation=bool(kwargs.get("requires_confirmation", False)),
            cache_results=bool(kwargs.get("cache_results", False)),
            is_async=_is_async_function(func),
        )
        adapter = FunctionTool(entrypoint=wrapped, metadata=metadata)
        setattr(wrapped, "tool_metadata", metadata)
        setattr(adapter, "tool_metadata", metadata)
        return adapter

    if args and callable(args[0]) and len(args) == 1:
        return decorate(args[0])
    if args:
        raise TypeError("@tool accepts either a callable or keyword arguments")
    return decorate


__all__ = ["FunctionTool", "ToolMetadata", "_is_async_function", "tool"]
