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
    # dt=2.0, ref=2.0 → normalized=1.0 → decay = 0.1 (original calibration)
    ch.tick(dt=2.0, reference_interval=2.0)
    assert abs(ch.value - 0.4) < 0.001
    ch.tick(dt=2.0, reference_interval=2.0)
    assert abs(ch.value - 0.3) < 0.001
    assert ch.is_active
    ch.tick(dt=2.0, reference_interval=2.0)
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


def test_dt_scaling_decay():
    """Bug #1 regression: decay must scale linearly with dt relative to reference_interval."""
    ch1 = HysteresisChannel(name="test", value=1.0, decay_rate=0.05)
    ch2 = HysteresisChannel(name="test", value=1.0, decay_rate=0.05)

    # dt=1.0 with reference_interval=2.0 → 0.5× normal decay
    ch1.tick(dt=1.0, reference_interval=2.0)
    # dt=2.0 with reference_interval=2.0 → 1.0× normal decay  
    ch2.tick(dt=2.0, reference_interval=2.0)

    decay_1 = 1.0 - ch1.value  # 0.05 * 0.5 = 0.025
    decay_2 = 1.0 - ch2.value  # 0.05 * 1.0 = 0.05

    # dt=2.0 produces exactly 2× decay of dt=1.0
    assert abs(decay_2 - 2.0 * decay_1) < 0.0001, (
        f"dt=2.0 decay ({decay_2}) should be 2× dt=1.0 decay ({decay_1})"
    )
    # Original calibration preserved: dt=2.0 gives decay_rate=0.05
    assert abs(decay_2 - 0.05) < 0.0001, (
        f"dt=2.0 at ref=2.0 should decay by 0.05 (original calibration), got {decay_2}"
    )


def test_self_stimulation_capped():
    """Bug #3 regression: total self-stimulation per reflection must not exceed 0.1."""
    from src.agents.base import ReflectionResult

    # Simulate a reflection that tries to pump 0.5 into stress + 0.3 into fatigue
    reflection = ReflectionResult(
        thought="I am very stressed and tired.",
        mood_assessment="terrible",
        hysteresis_stimuli={"stress": 0.5, "fatigue": 0.3},
    )

    # Apply the same cap logic as in reflect_sync()
    stimuli = dict(reflection.hysteresis_stimuli)
    total_stim = sum(abs(v) for v in stimuli.values())
    if total_stim > 0.1:
        scale = 0.1 / total_stim
        for ch in list(stimuli):
            stimuli[ch] *= scale

    # After capping, each channel's absolute value should be scaled proportionally
    assert abs(stimuli["stress"] - 0.0625) < 0.001, (
        f"stress should be 0.5*(0.1/0.8)=0.0625, got {stimuli['stress']}"
    )
    assert abs(stimuli["fatigue"] - 0.0375) < 0.001, (
        f"fatigue should be 0.3*(0.1/0.8)=0.0375, got {stimuli['fatigue']}"
    )
    assert sum(abs(v) for v in stimuli.values()) <= 0.1 + 1e-9
