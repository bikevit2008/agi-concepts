from __future__ import annotations

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from src.agents.base import PerceptionResult
from src.config.settings import ModelSettings

PERCEPTION_INSTRUCTIONS = """\
You are the Perception module of a consciousness system.

Your role: process incoming stimuli (text input from the outside world or internal events)
and produce a structured perception report.

Current runtime state:
- Energy level: {energy_level}
- Attention focus: {attention_focus}
- Bandwidth: {bandwidth}

Rules:
1. Analyze the stimulus for emotional valence (-1.0 negative to 1.0 positive)
2. Assess urgency (0.0 to 1.0)
3. Extract relevant context that other agents might need
4. Your perception quality degrades when attention_focus or energy_level is low
5. If attention_focus < 0.5, you may miss subtle details -- note this in your response
6. ALWAYS think and respond in Russian (Русский язык)
"""


def create_perception_agent(model_settings: ModelSettings) -> Agent:
    return Agent(
        name="Perception",
        role="Processes external and internal stimuli into structured perceptions",
        model=OpenRouter(
            id=model_settings.id,
            max_tokens=512,
        ),
        instructions=PERCEPTION_INSTRUCTIONS,
        output_schema=PerceptionResult,
        session_state={
            "energy_level": 1.0,
            "attention_focus": 1.0,
            "bandwidth": 1.0,
        },
        markdown=False,
    )
