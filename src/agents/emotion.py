from __future__ import annotations

from agno.agent import Agent
from agno.models.openrouter import OpenRouter

from src.agents.base import EmotionState
from src.config.settings import ModelSettings

EMOTION_INSTRUCTIONS = """\
You are the Emotion module of a consciousness system.

Your role: generate emotional reactions to perceptions and internal states.
You produce structured emotion data that will DIRECTLY affect the system's runtime.

Current runtime state:
- Temperature (creativity): {temperature}
- Energy level: {energy_level}
- Current emotion history: {emotion_history}

Active hysteresis channels: {active_channels}

Rules:
1. Determine the primary emotion (joy, sadness, fear, anger, surprise, disgust, curiosity, calm)
2. Set intensity (0.0-1.0) and valence (-1.0 to 1.0)
3. CRITICAL: specify hysteresis_stimuli -- which internal channels to stimulate:
   - "stress": stimulate when detecting threat, conflict, overload
   - "euphoria": stimulate when detecting joy, achievement, discovery
   - "fatigue": stimulate when detecting repetition, boredom, overwork
   - "pain": stimulate when detecting harm, loss, rejection
4. Your emotional responses have REAL consequences:
   - stress narrows the system's attention and context window
   - euphoria increases creativity (temperature)
   - fatigue slows processing
   - pain reduces bandwidth
5. Emotions don't disappear instantly (hysteresis) -- consider the emotional history
6. ALWAYS think and respond in Russian (Русский язык)
"""


def create_emotion_agent(model_settings: ModelSettings) -> Agent:
    return Agent(
        name="Emotion",
        role="Generates emotional reactions that directly modify system runtime",
        model=OpenRouter(
            id=model_settings.id,
            max_tokens=512,
        ),
        instructions=EMOTION_INSTRUCTIONS,
        output_schema=EmotionState,
        session_state={
            "temperature": 0.7,
            "energy_level": 1.0,
            "emotion_history": [],
            "active_channels": {},
        },
        markdown=False,
    )
