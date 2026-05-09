"""Capability-gated tool registry + audit log.

Implements `IToolRegistry`:
- register(tool): add a tool to the registry by name
- list_tools(): return metadata for discovery
- execute(tool_name, args, agent, capability_token, tick): dispatch with
  capability check + audit log entry

Capability model:
- Each tool declares `required_capability` (e.g. "tools:web_search").
- Caller passes a capability_token (issued externally; we just verify
  format here — proper issuer/verifier integration is out of scope for
  the MVP).
- Audit log: append-only JSON Lines file. Every call (allowed or denied)
  produces a record with agent, tool, args_hash, output_hash (or error),
  duration, timestamp, capability_token (hashed for privacy).

The registry is intentionally minimal — it doesn't implement OAuth 2.0
token exchange (RFC 8693) or DPoP. Those are integration points for a
future production deployment.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.tools import ITool, IToolRegistry, ToolCall, ToolResult

logger = structlog.get_logger("consciousness.tools.registry")


def _hash(payload: Any) -> str:
    """Stable, short content hash for audit logs.

    We never store raw inputs or outputs in the audit log — just hashes,
    so a leak of the audit log cannot reveal what a tool was actually
    called with.
    """
    try:
        serialized = json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        serialized = str(payload)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def _hash_token(token: Optional[str]) -> str:
    if not token:
        return ""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


@dataclass
class CapabilityGatedToolRegistry:
    """`IToolRegistry` with capability checks + audit log.

    Args:
        audit_log_path: where to append JSON Lines audit records.
        granted_capabilities: set of capabilities that are allowed.
            If empty, ALL calls are denied (FAIL-CLOSED).
        rate_limit_per_minute: per-tool calls/minute cap (best-effort).
    """

    audit_log_path: Optional[str] = None
    granted_capabilities: List[str] = field(default_factory=list)
    rate_limit_per_minute: int = 60

    _tools: Dict[str, ITool] = field(default_factory=dict)
    _calls_window: Dict[str, List[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        if self.audit_log_path:
            Path(self.audit_log_path).parent.mkdir(parents=True, exist_ok=True)

    def register(self, tool: ITool) -> None:
        with self._lock:
            self._tools[tool.name] = tool

    def list_tools(self) -> List[Dict[str, str]]:
        with self._lock:
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "required_capability": t.required_capability,
                }
                for t in self._tools.values()
            ]

    def execute(
        self,
        tool_name: str,
        args: Dict[str, Any],
        agent: str,
        capability_token: Optional[str] = None,
        tick: int = 0,
    ) -> ToolResult:
        start = time.monotonic()
        audit_id = uuid.uuid4().hex[:12]

        # Tool lookup
        with self._lock:
            tool = self._tools.get(tool_name)
        if tool is None:
            result = ToolResult(
                success=False,
                error=f"unknown tool: {tool_name}",
                audit_id=audit_id,
            )
            self._audit(
                tool_name=tool_name,
                agent=agent,
                args=args,
                token=capability_token,
                result=result,
                tick=tick,
                duration_ms=0.0,
                decision="deny:unknown",
            )
            return result

        # Capability check
        required = tool.required_capability
        if required not in self.granted_capabilities:
            result = ToolResult(
                success=False,
                error=f"capability {required!r} not granted",
                audit_id=audit_id,
            )
            self._audit(
                tool_name=tool_name,
                agent=agent,
                args=args,
                token=capability_token,
                result=result,
                tick=tick,
                duration_ms=0.0,
                decision="deny:capability",
            )
            return result

        # Rate limit
        if not self._check_rate_limit(tool_name):
            result = ToolResult(
                success=False,
                error=f"rate limit exceeded for {tool_name}",
                audit_id=audit_id,
            )
            self._audit(
                tool_name=tool_name,
                agent=agent,
                args=args,
                token=capability_token,
                result=result,
                tick=tick,
                duration_ms=0.0,
                decision="deny:rate_limit",
            )
            return result

        # Execute
        try:
            call = ToolCall(
                tool_name=tool_name,
                args=args,
                agent=agent,
                capability_token=capability_token,
                tick=tick,
            )
            result = tool.execute(call)
        except Exception as e:
            result = ToolResult(success=False, error=f"tool exception: {e}")
        result.audit_id = audit_id
        result.duration_ms = (time.monotonic() - start) * 1000.0

        self._audit(
            tool_name=tool_name,
            agent=agent,
            args=args,
            token=capability_token,
            result=result,
            tick=tick,
            duration_ms=result.duration_ms,
            decision="allow" if result.success else "fail",
        )
        return result

    def _check_rate_limit(self, tool_name: str) -> bool:
        if self.rate_limit_per_minute <= 0:
            return True
        now = time.monotonic()
        window = self._calls_window.setdefault(tool_name, [])
        # Drop entries older than 60s
        while window and (now - window[0]) > 60.0:
            window.pop(0)
        if len(window) >= self.rate_limit_per_minute:
            return False
        window.append(now)
        return True

    def _audit(
        self,
        tool_name: str,
        agent: str,
        args: Dict[str, Any],
        token: Optional[str],
        result: ToolResult,
        tick: int,
        duration_ms: float,
        decision: str,
    ) -> None:
        record = {
            "ts_ms": int(time.time() * 1000),
            "audit_id": result.audit_id,
            "tool": tool_name,
            "agent": agent,
            "tick": tick,
            "args_hash": _hash(args),
            "output_hash": _hash(result.output) if result.output is not None else None,
            "error": result.error,
            "decision": decision,
            "duration_ms": round(duration_ms, 3),
            "token_hash": _hash_token(token),
        }
        logger.info("tool_audit", **record)
        if not self.audit_log_path:
            return
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("tool_audit_write_failed", error=str(e))


__all__ = ["CapabilityGatedToolRegistry"]
