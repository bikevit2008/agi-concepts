"""Tests for the tools subsystem (Stage 10).

Cover:
- Tool registry: register, list_tools, execute (allow / deny / unknown).
- Capability gating: missing capability → DENY.
- Rate limiting: enforce per-minute caps.
- Audit log: written for every call (allow OR deny).
- WebSearchTool stub backend.
- CodeExecutorTool subprocess backend (trusted code).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from src.contracts.tools import (
    ITool,
    IToolRegistry,
    NullToolRegistry,
    ToolCall,
    ToolResult,
)
from src.tools.code_executor import CodeExecutorTool
from src.tools.registry import CapabilityGatedToolRegistry
from src.tools.web_search import WebSearchTool


# --- Registry --------------------------------------------------------------


class _StubTool:
    """Minimal ITool for registry tests."""

    def __init__(self, name: str = "stub", capability: str = "tools:stub") -> None:
        self._name = name
        self._capability = capability

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Stub tool for tests"

    @property
    def required_capability(self) -> str:
        return self._capability

    def execute(self, call: ToolCall) -> ToolResult:
        return ToolResult(success=True, output={"echo": call.args})


def test_registry_register_and_list():
    reg = CapabilityGatedToolRegistry(granted_capabilities=["tools:stub"])
    reg.register(_StubTool())
    listing = reg.list_tools()
    assert len(listing) == 1
    assert listing[0]["name"] == "stub"
    assert listing[0]["required_capability"] == "tools:stub"


def test_registry_executes_when_capability_granted():
    reg = CapabilityGatedToolRegistry(granted_capabilities=["tools:stub"])
    reg.register(_StubTool())
    result = reg.execute(
        "stub", args={"foo": "bar"}, agent="Test", capability_token="t1"
    )
    assert result.success is True
    assert result.output == {"echo": {"foo": "bar"}}
    assert result.audit_id is not None


def test_registry_denies_without_capability():
    reg = CapabilityGatedToolRegistry(granted_capabilities=[])  # no caps granted
    reg.register(_StubTool())
    result = reg.execute("stub", args={}, agent="Test")
    assert result.success is False
    assert "not granted" in (result.error or "")


def test_registry_denies_unknown_tool():
    reg = CapabilityGatedToolRegistry(granted_capabilities=["tools:stub"])
    result = reg.execute("nonexistent", args={}, agent="Test")
    assert result.success is False
    assert "unknown tool" in (result.error or "")


def test_registry_rate_limit():
    reg = CapabilityGatedToolRegistry(
        granted_capabilities=["tools:stub"],
        rate_limit_per_minute=2,
    )
    reg.register(_StubTool())
    r1 = reg.execute("stub", args={}, agent="A")
    r2 = reg.execute("stub", args={}, agent="A")
    r3 = reg.execute("stub", args={}, agent="A")
    assert r1.success and r2.success
    assert r3.success is False
    assert "rate limit" in (r3.error or "")


def test_registry_audit_log_written(tmp_path: Path):
    audit_path = tmp_path / "audit.jsonl"
    reg = CapabilityGatedToolRegistry(
        granted_capabilities=["tools:stub"],
        audit_log_path=str(audit_path),
    )
    reg.register(_StubTool())
    reg.execute("stub", args={"k": "v"}, agent="X", capability_token="tok123")
    reg.execute("nonexistent", args={}, agent="X")  # deny:unknown

    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rec_ok = json.loads(lines[0])
    assert rec_ok["tool"] == "stub"
    assert rec_ok["agent"] == "X"
    assert rec_ok["decision"] == "allow"
    # Args / output / token must be HASHED, not raw —
    # check that the unique args VALUE "v" doesn't appear anywhere in the
    # serialized record (only its hash should).
    serialized = json.dumps(rec_ok)
    assert '"v"' not in serialized  # raw arg value absent
    assert "tok123" not in serialized  # raw token absent
    assert rec_ok["token_hash"] != "tok123"
    assert len(rec_ok["token_hash"]) == 16
    assert "args_hash" in rec_ok
    assert len(rec_ok["args_hash"]) == 16

    rec_deny = json.loads(lines[1])
    assert rec_deny["decision"] == "deny:unknown"


def test_registry_handles_tool_exception():
    class _Bomb(_StubTool):
        def execute(self, call: ToolCall) -> ToolResult:  # type: ignore[override]
            raise RuntimeError("boom")

    reg = CapabilityGatedToolRegistry(granted_capabilities=["tools:stub"])
    reg.register(_Bomb())
    result = reg.execute("stub", args={}, agent="X")
    assert result.success is False
    assert "tool exception" in (result.error or "")


def test_null_registry_rejects_everything():
    reg: IToolRegistry = NullToolRegistry()
    result = reg.execute("anything", args={}, agent="X")
    assert result.success is False
    assert reg.list_tools() == []


def test_registry_satisfies_contract():
    reg: IToolRegistry = CapabilityGatedToolRegistry(granted_capabilities=[])
    assert isinstance(reg, IToolRegistry)


# --- WebSearchTool ---------------------------------------------------------


def test_web_search_stub_backend():
    tool = WebSearchTool(backend="stub")
    call = ToolCall(tool_name="web_search", args={"query": "AI", "max_results": 3}, agent="X")
    result = tool.execute(call)
    assert result.success is True
    assert isinstance(result.output, list)
    assert len(result.output) == 3
    assert "AI" in result.output[0]["title"]


def test_web_search_empty_query():
    tool = WebSearchTool(backend="stub")
    result = tool.execute(ToolCall(tool_name="web_search", args={}, agent="X"))
    assert result.success is False


def test_web_search_callable_backend():
    def fake_search(query: str, max_results: int):
        return [{"title": query, "url": "https://x", "snippet": "snip"}]

    tool = WebSearchTool(backend="callable", custom_search=fake_search)
    result = tool.execute(
        ToolCall(tool_name="web_search", args={"query": "test", "max_results": 1}, agent="X")
    )
    assert result.success is True
    assert result.output[0]["title"] == "test"


def test_web_search_required_capability():
    tool = WebSearchTool()
    assert tool.required_capability == "tools:web_search"


# --- CodeExecutorTool ------------------------------------------------------


def test_code_executor_subprocess_runs_simple_code():
    tool = CodeExecutorTool(backend="subprocess", timeout_seconds=5.0)
    call = ToolCall(
        tool_name="code_executor",
        args={"code": "print('hello world')"},
        agent="X",
    )
    result = tool.execute(call)
    assert result.success is True
    assert "hello world" in result.output["stdout"]


def test_code_executor_subprocess_captures_error():
    tool = CodeExecutorTool(backend="subprocess", timeout_seconds=5.0)
    call = ToolCall(
        tool_name="code_executor",
        args={"code": "raise RuntimeError('bad')"},
        agent="X",
    )
    result = tool.execute(call)
    assert result.success is False
    assert "RuntimeError" in result.output["stderr"] or "bad" in result.output["stderr"]


def test_code_executor_subprocess_timeout():
    tool = CodeExecutorTool(backend="subprocess", timeout_seconds=0.5)
    call = ToolCall(
        tool_name="code_executor",
        args={"code": "import time; time.sleep(10)"},
        agent="X",
    )
    result = tool.execute(call)
    assert result.success is False
    assert "time" in (result.error or "").lower()


def test_code_executor_empty_code():
    tool = CodeExecutorTool(backend="subprocess")
    call = ToolCall(tool_name="code_executor", args={}, agent="X")
    result = tool.execute(call)
    assert result.success is False


def test_code_executor_required_capability():
    tool = CodeExecutorTool()
    assert tool.required_capability == "tools:code_executor"
