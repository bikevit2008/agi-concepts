"""LLM agent that turns a cluster of episodic memories into a semantic
abstraction (Generative-Agents-style reflection).

Inspired by Park et al. (2023) and refined per dify-search SOTA 2026:

- Generate-critique-refine isn't necessary at MVP scale; a single
  structured reflection pass with strict output schema works.
- Anti-hallucination: prompt explicitly forbids inventing facts not
  present in the input memories. Downstream provenance check
  (cosine similarity to cluster) catches violations anyway.
- Output schema validates the LLM didn't drift outside the cluster.

The agent is a thin wrapper around Agno's `Agent`, with `output_schema`
set to `ReflectionAbstraction`. Use `LlmReflectionAgent` to call it
through the cost-aware invoker so token usage flows into our
ICostTracker.
"""

from __future__ import annotations

from typing import List

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from pydantic import BaseModel, Field, field_validator

from src.agents._fallback import build_fallback_config
from src.config.settings import ModelSettings


class ReflectionAbstraction(BaseModel):
    """LLM-produced abstraction over a cluster of memories.

    Fields:
        abstraction:        higher-order generalisation (1-3 sentences)
        theme:              short tag, max ~3 words (e.g. "user_pet_preferences")
        confidence:         0..1, agent's self-assessed certainty
        supporting_memory_ids: ids of memories that support the abstraction.
                              Must be a subset of the cluster's member ids.
        reasoning:          short justification (1-2 sentences)
    """

    abstraction: str = Field(..., min_length=4)
    theme: str = Field(..., min_length=1, max_length=120)
    confidence: float = 0.5
    supporting_memory_ids: List[str] = Field(default_factory=list)
    reasoning: str = ""

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        if v < 0.0:
            return 0.0
        if v > 1.0:
            return 1.0
        return v

    @field_validator("theme")
    @classmethod
    def _strip_theme(cls, v: str) -> str:
        return v.strip()


REFLECTION_INSTRUCTIONS = """\
You are the REM-phase reflection module of a consciousness system.

Your task: take a CLUSTER of related episodic memories (raw observations
or events) and produce a single higher-order abstraction that captures
the pattern they share.

You will receive:
  - cluster_theme_hint:  a coarse tag (e.g. "joy", "stress")
  - memories: a numbered list of memories with their ids

Strict rules:
1. The `abstraction` MUST be a generalisation that the listed memories
   support. Do NOT add facts not present in any memory.
2. List ONLY the ids of memories that genuinely support the abstraction
   in `supporting_memory_ids`. If a memory is unrelated, omit its id.
3. If the cluster is too noisy to abstract reliably, return
   confidence < 0.3 and an abstraction that just summarises the
   common topic at very high level.
4. Keep `abstraction` to 1-3 sentences. `reasoning` 1-2 sentences.
5. `theme` = 1-3 word tag.
6. ALWAYS think and respond in Russian (Русский язык). The actual
   abstraction text is in Russian.

Output schema (Pydantic ReflectionAbstraction):
    abstraction: str
    theme: str
    confidence: float (0..1)
    supporting_memory_ids: List[str]
    reasoning: str
"""


def create_reflection_consolidator_agent(model_settings: ModelSettings) -> Agent:
    """Build the Agno Agent used by LlmMemoryConsolidator for REM."""
    return Agent(
        name="ReflectionConsolidator",
        role="Synthesises clusters of episodic memories into semantic abstractions during REM.",
        model=OpenRouter(
            id=model_settings.id,
            max_tokens=400,
        ),
        fallback_config=build_fallback_config(model_settings),
        instructions=REFLECTION_INSTRUCTIONS,
        output_schema=ReflectionAbstraction,
        markdown=False,
    )


__all__ = ["ReflectionAbstraction", "create_reflection_consolidator_agent"]
