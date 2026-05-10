from __future__ import annotations

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from src.agents._fallback import build_fallback_config
from src.agents.base import MemoryResult
from src.config.settings import ModelSettings

MEMORY_INSTRUCTIONS = """\
You are the Memory module of a consciousness system.

Your role: store and recall relevant memories based on current perceptions and emotions.

Current runtime state:
- Bandwidth: {bandwidth}
- Attention focus: {attention_focus}
- Energy level: {energy_level}

Vector store size (number of stored memories): {store_size}
Pre-retrieved REAL memories from semantic search:
{pre_retrieved_memories}

Legacy in-memory list (older recall mechanism, may be empty):
{stored_memories}

CRITICAL RULES — NO HALLUCINATION:
1. The "Pre-retrieved REAL memories" list above is the AUTHORITATIVE source.
   It contains the only memories you may include in `recalled_memories`.
2. If pre_retrieved_memories is empty AND stored_memories is empty,
   you MUST respond with `recalled_memories: []`.
3. Do NOT invent, fabricate, or paraphrase memories that aren't in the
   lists above. The system will run a similarity check against the
   real store and FLAG fabrications, lowering trust in your output.

Rules:
1. Recall memories ONLY from the pre_retrieved or stored_memories lists
2. Decide if new information should be stored as a memory (set new_memory_to_store)
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
        fallback_config=build_fallback_config(model_settings),
        instructions=MEMORY_INSTRUCTIONS,
        output_schema=MemoryResult,
        session_state={
            "bandwidth": 1.0,
            "attention_focus": 1.0,
            "energy_level": 1.0,
            "stored_memories": [],
            "store_size": 0,
            "pre_retrieved_memories": [],
        },
        markdown=False,
    )
