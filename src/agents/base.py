from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class EmotionState(BaseModel):
    """Structured output for Emotion agent."""

    primary_emotion: str
    intensity: float  # 0.0-1.0
    valence: float  # -1.0 (negative) to 1.0 (positive)
    arousal: float  # 0.0 (calm) to 1.0 (excited)
    hysteresis_stimuli: Dict[str, float] = {}  # channel_name -> intensity
    reasoning: str = ""


class PerceptionResult(BaseModel):
    """Structured output for Perception agent."""

    stimulus_type: str  # "verbal", "internal", "environmental"
    content_summary: str
    emotional_valence: float  # -1.0 to 1.0
    urgency: float  # 0.0 to 1.0
    relevant_context: List[str] = []


class MemoryResult(BaseModel):
    """Structured output for Memory agent."""

    recalled_memories: List[str] = []
    new_memory_to_store: Optional[str] = None
    relevance_score: float = 0.0
    emotional_associations: Dict[str, float] = {}


class PlanningResult(BaseModel):
    """Structured output for Planning agent."""

    response: str
    intent: str
    confidence: float = 0.5
    next_actions: List[str] = []
    internal_state_summary: str = ""


class ReflectionResult(BaseModel):
    """Structured output for Reflection (inner monologue) agent."""

    thought: str
    mood_assessment: str  # brief self-assessment of current emotional state
    hysteresis_stimuli: Dict[str, float] = {}  # can self-stimulate channels
    insight: str = ""  # any realization or pattern noticed
    internal_stimulus: Optional[str] = None  # self-generated stimulus for full pipeline processing
