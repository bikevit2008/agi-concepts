from src.agents._fallback import build_fallback_config
from src.agents.emotion import create_emotion_agent
from src.agents.memory import create_memory_agent
from src.agents.perception import create_perception_agent
from src.agents.planning import create_planning_agent
from src.agents.reflection import create_reflection_agent
from src.agents.reflection_consolidator import create_reflection_consolidator_agent
from src.config.settings import ModelSettings


def test_build_fallback_config_uses_error_specific_routes():
    settings = ModelSettings(
        id="x-ai/grok-4.20",
        fallback_models=["anthropic/claude-sonnet-4-20250514", "openai/gpt-4o"],
    )
    config = build_fallback_config(settings)
    assert config is not None
    assert len(config.on_error) == 2
    assert len(config.on_rate_limit) == 2
    assert len(config.on_context_overflow) == 2


def test_agent_factories_set_fallback_config():
    settings = ModelSettings(
        id="x-ai/grok-4.20",
        fallback_models=["anthropic/claude-sonnet-4-20250514"],
    )
    factories = [
        create_perception_agent,
        create_emotion_agent,
        create_memory_agent,
        create_planning_agent,
        create_reflection_agent,
        create_reflection_consolidator_agent,
    ]
    for factory in factories:
        agent = factory(settings)
        assert agent.fallback_config is not None
        assert agent.fallback_config.on_error
        assert agent.fallback_config.on_rate_limit
        assert agent.fallback_config.on_context_overflow
