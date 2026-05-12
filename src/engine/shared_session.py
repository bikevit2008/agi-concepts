"""Persistent shared session blackboard.

This is an Agno-inspired session-state layer with stricter boundaries:
subsystems write named namespaces, agents receive compact projections, and the
whole state round-trips through checkpoints.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.contracts.session import SessionMutation


DEFAULT_NAMESPACES = (
    "runtime",
    "hysteresis",
    "goals",
    "learning",
    "memory",
    "agents",
    "tasks",
    "metadata",
)


@dataclass
class PersistentSharedSessionState:
    """Checkpointable blackboard with namespace-level mutation audit."""

    session_id: str = "default"
    max_recent_mutations: int = 40
    allowed_namespaces: List[str] = field(
        default_factory=lambda: list(DEFAULT_NAMESPACES)
    )

    _namespaces: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    _recent_mutations: List[SessionMutation] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.session_id = str(self.session_id or "default")
        self.max_recent_mutations = max(1, _int_or_default(self.max_recent_mutations, 40))
        self.allowed_namespaces = [
            str(namespace)
            for namespace in (self.allowed_namespaces or list(DEFAULT_NAMESPACES))
            if str(namespace)
        ]
        for namespace in self.allowed_namespaces:
            self._namespaces.setdefault(namespace, {})

    def update_namespace(
        self,
        namespace: str,
        values: Dict[str, Any],
        tick: int = 0,
        source: str = "system",
        replace: bool = False,
    ) -> Dict[str, Any]:
        namespace = str(namespace or "").strip()
        if not namespace:
            return {}
        if namespace not in self.allowed_namespaces:
            self.allowed_namespaces.append(namespace)
        clean_values = _as_json_dict(values)
        current = {} if replace else copy.deepcopy(self._namespaces.get(namespace, {}))
        self._namespaces[namespace] = _deep_merge(current, clean_values)
        self._record_mutation(
            namespace=namespace,
            values=clean_values,
            tick=tick,
            source=source,
        )
        return copy.deepcopy(self._namespaces[namespace])

    def context(
        self,
        agent: str = "system",
        include_namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        namespaces = include_namespaces or [
            "runtime",
            "hysteresis",
            "goals",
            "learning",
            "tasks",
            "agents",
        ]
        projection = {
            namespace: copy.deepcopy(self._namespaces.get(namespace, {}))
            for namespace in namespaces
            if namespace in self._namespaces
        }
        return {
            "type": "persistent",
            "session_id": self.session_id,
            "agent": str(agent or "system"),
            "namespaces": projection,
            "recent_mutations": [
                mutation.to_dict() for mutation in self._recent_mutations[-5:]
            ],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": "persistent",
            "session_id": self.session_id,
            "config": {
                "max_recent_mutations": self.max_recent_mutations,
                "allowed_namespaces": list(self.allowed_namespaces),
            },
            "namespaces": copy.deepcopy(self._namespaces),
            "recent_mutations": [
                mutation.to_dict() for mutation in self._recent_mutations
            ],
        }

    def restore(self, data: Any) -> None:
        if not isinstance(data, dict):
            return
        self.session_id = str(data.get("session_id") or self.session_id)
        config = data.get("config")
        if isinstance(config, dict):
            self.max_recent_mutations = max(
                1,
                _int_or_default(
                    config.get("max_recent_mutations"),
                    self.max_recent_mutations,
                ),
            )
            raw_namespaces = config.get("allowed_namespaces")
            if isinstance(raw_namespaces, list):
                self.allowed_namespaces = [
                    str(namespace) for namespace in raw_namespaces if str(namespace)
                ]
        namespaces = data.get("namespaces")
        self._namespaces = {}
        if isinstance(namespaces, dict):
            for namespace, value in namespaces.items():
                if isinstance(value, dict):
                    self._namespaces[str(namespace)] = _as_json_dict(value)
        for namespace in self.allowed_namespaces:
            self._namespaces.setdefault(namespace, {})
        raw_mutations = data.get("recent_mutations")
        self._recent_mutations = []
        if isinstance(raw_mutations, list):
            for item in raw_mutations[-self.max_recent_mutations :]:
                if isinstance(item, dict):
                    self._recent_mutations.append(SessionMutation.from_dict(item))

    def _record_mutation(
        self,
        namespace: str,
        values: Dict[str, Any],
        tick: int,
        source: str,
    ) -> None:
        self._recent_mutations.append(
            SessionMutation(
                tick=_int_or_default(tick, 0),
                namespace=namespace,
                source=str(source or "system"),
                keys=sorted(str(key) for key in values.keys()),
            )
        )
        self._recent_mutations = self._recent_mutations[-self.max_recent_mutations :]


def _deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(dict(base[key]), value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _as_json_dict(values: Any) -> Dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    return {str(key): _json_safe(value) for key, value in values.items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            return str(value)
    return str(value)


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["DEFAULT_NAMESPACES", "PersistentSharedSessionState"]
