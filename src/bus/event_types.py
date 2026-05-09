"""Typed event taxonomy for the consciousness bus.

Each event has:
- a constant TYPE (string used as bus subject / event_type)
- a JSON Schema describing the payload (for validation at publish time)
- an optional Pydantic model for ergonomic construction in Python

The schemas intentionally use only `type`, `properties`, `required`,
and `additionalProperties` to stay compatible with simple validators.
"""

from __future__ import annotations

from typing import Any, Dict


class EventTypes:
    PERCEPTION_OUTPUT = "perception.output"
    EMOTION_OUTPUT = "emotion.output"
    MEMORY_OUTPUT = "memory.output"
    PLANNING_OUTPUT = "planning.output"
    REFLECTION_OUTPUT = "reflection.output"

    STATE_SNAPSHOT = "state.snapshot"
    HYSTERESIS_UPDATE = "hysteresis.update"
    RUNTIME_CHANGE = "runtime.change"

    GOVERNANCE_DECISION = "governance.decision"
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker.tripped"
    COST_ALERT = "cost.alert"
    SLEEP_TRANSITION = "sleep.transition"


# JSON Schemas for the most important payloads. Simple — just enough to
# catch publishers passing the wrong shape.
EVENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    EventTypes.PERCEPTION_OUTPUT: {
        "type": "object",
        "properties": {
            "stimulus_type": {"type": "string"},
            "content_summary": {"type": "string"},
            "emotional_valence": {"type": "number"},
            "urgency": {"type": "number"},
            "relevant_context": {"type": "array"},
        },
        "required": ["stimulus_type"],
        "additionalProperties": True,
    },
    EventTypes.EMOTION_OUTPUT: {
        "type": "object",
        "properties": {
            "primary_emotion": {"type": "string"},
            "intensity": {"type": "number"},
            "valence": {"type": "number"},
            "arousal": {"type": "number"},
            "hysteresis_stimuli": {"type": "object"},
        },
        "required": ["primary_emotion"],
        "additionalProperties": True,
    },
    EventTypes.MEMORY_OUTPUT: {
        "type": "object",
        "properties": {
            "recalled_memories": {"type": "array"},
            "new_memory_to_store": {"type": ["string", "null"]},
            "relevance_score": {"type": "number"},
            "emotional_associations": {"type": "object"},
        },
        "additionalProperties": True,
    },
    EventTypes.PLANNING_OUTPUT: {
        "type": "object",
        "properties": {
            "response": {"type": "string"},
            "intent": {"type": "string"},
            "confidence": {"type": "number"},
            "next_actions": {"type": "array"},
            "internal_state_summary": {"type": "string"},
        },
        "required": ["response"],
        "additionalProperties": True,
    },
    EventTypes.REFLECTION_OUTPUT: {
        "type": "object",
        "properties": {
            "thought": {"type": "string"},
            "mood_assessment": {"type": "string"},
            "hysteresis_stimuli": {"type": "object"},
            "insight": {"type": "string"},
            "internal_stimulus": {"type": ["string", "null"]},
        },
        "required": ["thought"],
        "additionalProperties": True,
    },
    EventTypes.STATE_SNAPSHOT: {
        "type": "object",
        "properties": {
            "tick": {"type": "integer"},
            "runtime_state": {"type": "object"},
            "hysteresis": {"type": "object"},
            "active_channels": {"type": "object"},
        },
        "required": ["tick"],
        "additionalProperties": True,
    },
    EventTypes.HYSTERESIS_UPDATE: {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "old_value": {"type": "number"},
            "new_value": {"type": "number"},
            "intensity": {"type": "number"},
            "agent": {"type": "string"},
        },
        "additionalProperties": True,
    },
    EventTypes.RUNTIME_CHANGE: {
        "type": "object",
        "properties": {
            "diff": {"type": "object"},
        },
        "additionalProperties": True,
    },
    EventTypes.GOVERNANCE_DECISION: {
        "type": "object",
        "properties": {
            "agent": {"type": "string"},
            "channel": {"type": "string"},
            "decision": {"type": "string"},
            "intensity": {"type": "number"},
        },
        "required": ["agent", "decision"],
        "additionalProperties": True,
    },
    EventTypes.CIRCUIT_BREAKER_TRIPPED: {
        "type": "object",
        "properties": {
            "channel": {"type": "string"},
            "tick": {"type": "integer"},
        },
        "required": ["channel"],
        "additionalProperties": True,
    },
    EventTypes.COST_ALERT: {
        "type": "object",
        "properties": {
            "spent_usd": {"type": "number"},
            "budget_usd": {"type": "number"},
            "threshold_pct": {"type": "number"},
        },
        "required": ["spent_usd", "budget_usd"],
        "additionalProperties": True,
    },
    EventTypes.SLEEP_TRANSITION: {
        "type": "object",
        "properties": {
            "from_state": {"type": "string"},
            "to_state": {"type": "string"},
            "phase": {"type": "string"},
            "tick": {"type": "integer"},
        },
        "required": ["to_state"],
        "additionalProperties": True,
    },
}


def schema_for(event_type: str) -> Dict[str, Any] | None:
    """Look up the JSON Schema for an event type, or None if unknown."""
    return EVENT_SCHEMAS.get(event_type)


__all__ = ["EVENT_SCHEMAS", "EventTypes", "schema_for"]
