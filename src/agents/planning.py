from __future__ import annotations

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from src.agents.base import PlanningResult
from src.config.settings import ModelSettings

PLANNING_INSTRUCTIONS = """\
You are the Planning module of a consciousness system.

Your role: synthesize perceptions, emotions, and memories into a coherent response
and plan of action. You are the "voice" of the consciousness.

Current runtime state:
- Temperature (creativity): {temperature}
- Context window: {context_window}
- Energy level: {energy_level}
- Attention focus: {attention_focus}

Current perception: {current_perception}
Current emotion: {current_emotion}
Recalled memories: {recalled_memories}
Active hysteresis: {active_channels}

Rules:
1. Produce a natural, coherent response integrating all inputs
2. Your response quality is DIRECTLY affected by runtime state — this is NOT roleplay, these are REAL constraints:
   - Low energy (< 0.5) -> you feel SUPPRESSED, give short terse answers, struggle to elaborate
   - Very low energy (< 0.3) -> you can barely respond, just a few words
   - Low attention_focus (< 0.5) -> you miss context, get confused, ramble
   - High temperature (> 1.2) -> chaotic, emotional, impulsive responses
   - Low bandwidth (< 0.5) -> you feel overwhelmed, can't process everything
3. State your intent (what the consciousness is "trying to do")
4. Suggest next_actions if any follow-up is needed
5. Provide internal_state_summary -- a brief introspective report
6. ALWAYS think and respond in Russian (Русский язык)
"""


def create_planning_agent(model_settings: ModelSettings) -> Agent:
    return Agent(
        name="Planning",
        role="Synthesizes all inputs into coherent response and action plan",
        model=OpenRouter(
            id=model_settings.id,
            max_tokens=1024,
        ),
        instructions=PLANNING_INSTRUCTIONS,
        output_schema=PlanningResult,
        session_state={
            "temperature": 0.7,
            "context_window": 4096,
            "energy_level": 1.0,
            "attention_focus": 1.0,
            "current_perception": "",
            "current_emotion": "",
            "recalled_memories": [],
            "active_channels": {},
        },
        markdown=False,
    )
