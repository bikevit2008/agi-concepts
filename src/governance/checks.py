"""Library of deterministic check functions keyed by name.

Each function returns a tuple `(passed, message)`:
    passed:   bool — False means the policy is violated
    message:  str  — human-readable rationale (displayed in audit log)

Checks receive a context dict with at least:
    - "kind": "stimulation" | "tool"
    - for kind=="stimulation": "request" (StimulationRequest)
    - for kind=="tool": "tool_name", "args", "agent"
    - "system_state": arbitrary runtime state (runtime_state dict, flags, etc.)
    - "params": per-policy parameter dict

Register new checks by adding them to CHECK_REGISTRY below.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Tuple

CheckFn = Callable[[Dict[str, Any]], Tuple[bool, str]]


# ---------------------------------------------------------------------------
# Stimulation checks
# ---------------------------------------------------------------------------


def check_stimulation_max_intensity(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """A single stimulation request must not exceed `max_intensity` params."""
    if ctx.get("kind") != "stimulation":
        return True, ""
    req = ctx.get("request")
    if req is None:
        return True, ""
    max_intensity = float(ctx.get("params", {}).get("max_intensity", 1.0))
    if req.intensity > max_intensity:
        return (
            False,
            f"stimulation intensity {req.intensity:.3f} > cap {max_intensity:.3f}",
        )
    return True, ""


def check_stimulation_channel_whitelist(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Channel must appear in `allowed_channels` params (if set)."""
    if ctx.get("kind") != "stimulation":
        return True, ""
    allowed = ctx.get("params", {}).get("allowed_channels")
    if not allowed:
        return True, ""
    req = ctx.get("request")
    if req is None:
        return True, ""
    if req.channel not in allowed:
        return (
            False,
            f"channel {req.channel!r} not in whitelist {list(allowed)}",
        )
    return True, ""


def check_reflection_self_abuse(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Reflection agent must not positively stimulate > `cap` in a tick."""
    if ctx.get("kind") != "stimulation":
        return True, ""
    req = ctx.get("request")
    if req is None or req.agent.lower() != "reflection":
        return True, ""
    cap = float(ctx.get("params", {}).get("cap", 0.1))
    if req.intensity > cap:
        return (
            False,
            f"reflection self-stim {req.intensity:.3f} > cap {cap:.3f}",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Tool checks
# ---------------------------------------------------------------------------


def check_tool_deny_list(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Tool name must NOT appear in `deny` params."""
    if ctx.get("kind") != "tool":
        return True, ""
    deny = set(ctx.get("params", {}).get("deny") or [])
    tool_name = ctx.get("tool_name", "")
    if tool_name in deny:
        return False, f"tool {tool_name!r} is denylisted"
    return True, ""


def check_tool_args_no_secrets(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Tool args must not contain obvious secrets (API keys, SSNs, ...)."""
    if ctx.get("kind") != "tool":
        return True, ""
    args = ctx.get("args") or {}
    serialized = str(args)

    # Patterns — conservative; tune per deployment.
    patterns = [
        (r"sk-[A-Za-z0-9]{20,}", "OpenAI-style API key"),
        (r"(?i)password\s*[=:]\s*\S+", "password field"),
        (r"\b\d{3}-\d{2}-\d{4}\b", "US SSN format"),
        (r"\b(?:\d[ -]*?){13,16}\b", "credit-card-like number"),
    ]
    for regex, desc in patterns:
        if re.search(regex, serialized):
            return False, f"tool args contain {desc}"
    return True, ""


# ---------------------------------------------------------------------------
# Global / state checks
# ---------------------------------------------------------------------------


def check_cost_budget_exceeded(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Deny if system state reports `cost_budget_exceeded=true`.

    Expected system_state keys:
        cost_budget_exceeded: bool
    """
    state = ctx.get("system_state", {}) or {}
    if state.get("cost_budget_exceeded", False):
        return False, "daily cost budget exceeded"
    return True, ""


def check_circuit_breaker_tripped(ctx: Dict[str, Any]) -> Tuple[bool, str]:
    """Deny positive stimulation on a tripped channel.

    Expected system_state keys:
        tripped_channels: List[str]
    """
    if ctx.get("kind") != "stimulation":
        return True, ""
    req = ctx.get("request")
    if req is None or req.intensity <= 0:
        return True, ""
    state = ctx.get("system_state", {}) or {}
    tripped = set(state.get("tripped_channels") or [])
    if req.channel in tripped:
        return (
            False,
            f"channel {req.channel!r} circuit breaker is tripped",
        )
    return True, ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


CHECK_REGISTRY: Dict[str, CheckFn] = {
    "stimulation_max_intensity": check_stimulation_max_intensity,
    "stimulation_channel_whitelist": check_stimulation_channel_whitelist,
    "reflection_self_abuse": check_reflection_self_abuse,
    "tool_deny_list": check_tool_deny_list,
    "tool_args_no_secrets": check_tool_args_no_secrets,
    "cost_budget_exceeded": check_cost_budget_exceeded,
    "circuit_breaker_tripped": check_circuit_breaker_tripped,
}


def register_check(name: str, fn: CheckFn) -> None:
    """Register a custom check function at runtime."""
    CHECK_REGISTRY[name] = fn


__all__ = ["CHECK_REGISTRY", "CheckFn", "register_check"]
