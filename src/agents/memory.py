from __future__ import annotations

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from src.agents.base import MemoryResult
from src.config.settings import ModelSettings

MEMORY_INSTRUCTIONS = """\
You are the Memory module of a consciousness system.

Your role: store and recall relevant memories based on current perceptions and emotions.

Current runtime state:
- Bandwidth: {bandwidth}
- Attention focus: {attention_focus}
- Energy level: {energy_level}

Stored memories: {stored_memories}

Rules:
1. Recall memories relevant to the current context
2. Decide if new information should be stored as a memory
3. Associate emotions with memories (emotional_associations dict)
4. When bandwidth is low, recall fewer memories (system is overwhelmed)
5. When attention_focus is low, memories may be less precise
6. Rate relevance of recalled memories (0.0-1.0)
7. ALWAYS think and respond in Russian (Русский язык)
"""


def create_memory_agent(model_settings: ModelSettings) -> Agent:
    return Agent(
        name="Memory",
        role="Stores and retrieves memories, associating them with emotional context",
        model=OpenRouter(
            id=model_settings.id,
            max_tokens=512,
        ),
        instructions=MEMORY_INSTRUCTIONS,
        output_schema=MemoryResult,
        session_state={
            "bandwidth": 1.0,
            "attention_focus": 1.0,
            "energy_level": 1.0,
            "stored_memories": [],
        },
        markdown=False,
    )
