from src.config.settings import HysteresisParams, HysteresisSettings
from src.core.hysteresis import HysteresisChannel, HysteresisEngine


def test_channel_stimulate():
    ch = HysteresisChannel(name="stress", accumulation_rate=0.15, threshold=0.3)
    assert not ch.is_active
    # intensity 0.55 applied directly (> accumulation_rate 0.15)
    ch.stimulate(0.55)
    assert abs(ch.value - 0.55) < 0.001
    assert ch.is_active  # 0.55 > threshold 0.30


def test_channel_decay():
    ch = HysteresisChannel(name="stress", value=0.5, decay_rate=0.1, threshold=0.3)
    assert ch.is_active
    ch.tick()
    assert abs(ch.value - 0.4) < 0.001
    ch.tick()
    assert abs(ch.value - 0.3) < 0.001
    assert ch.is_active
    ch.tick()
    assert not ch.is_active


def test_channel_clamp():
    ch = HysteresisChannel(name="test", accumulation_rate=0.6)
    ch.stimulate(0.8)
    ch.stimulate(0.8)
    assert ch.value == 1.0  # clamped to max


def test_engine_from_settings():
    settings = HysteresisSettings()
    engine = HysteresisEngine.from_settings(settings)
    assert "stress" in engine.channels
    assert "euphoria" in engine.channels
    assert "fatigue" in engine.channels
    assert "pain" in engine.channels


def test_engine_tick_decays_all():
    settings = HysteresisSettings()
    engine = HysteresisEngine.from_settings(settings)
    engine.stimulate("stress", 1.0)
    engine.stimulate("euphoria", 1.0)
    val_stress = engine.channels["stress"].value
    val_euphoria = engine.channels["euphoria"].value
    engine.tick()
    assert engine.channels["stress"].value < val_stress
    assert engine.channels["euphoria"].value < val_euphoria


def test_engine_active_channels():
    settings = HysteresisSettings()
    engine = HysteresisEngine.from_settings(settings)
    assert len(engine.get_active_channels()) == 0
    # Stimulate stress above threshold (0.3)
    for _ in range(3):
        engine.stimulate("stress", 1.0)
    active = engine.get_active_channels()
    assert "stress" in active


def test_compute_runtime_delta():
    settings = HysteresisSettings()
    engine = HysteresisEngine.from_settings(settings)
    # Stimulate stress above threshold
    engine.stimulate("stress", 0.8)

    class MockFlags:
        runtime_effects_enabled = True
        stress_narrows_context = True
        emotion_affects_temperature = True
        pain_reduces_bandwidth = True

    delta = engine.compute_runtime_delta(MockFlags())
    assert "context_window" in delta
    assert delta["context_window"] < 0
    # Cross-channel: stress also affects temperature and energy
    assert "temperature" in delta
    assert delta["temperature"] > 0  # stress = chaotic thinking
    assert "energy_level" in delta
    assert delta["energy_level"] < 0  # stress drains energy


def test_reset_all():
    settings = HysteresisSettings()
    engine = HysteresisEngine.from_settings(settings)
    engine.stimulate("stress", 1.0)
    engine.stimulate("pain", 1.0)
    engine.reset_all()
    for ch in engine.channels.values():
        assert ch.value == 0.0
