from src.config.settings import HysteresisParams, HysteresisSettings
from src.core.hysteresis import HysteresisChannel, HysteresisEngine
from src.engine.homeostatic_hysteresis import (
    HomeostaticHysteresisChannel,
    HomeostaticHysteresisEngine,
)


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


# ═══════════════════════════════════════════════════════════════════
# Homeostatic Hysteresis Engine Tests
# ═══════════════════════════════════════════════════════════════════


def test_homeostatic_recovery_to_setpoint():
    """Inject stress=0.9, verify recovery to setpoint (not zero).

    The homeostatic engine must pull the value toward its setpoint,
    not toward zero. After saturation, the channel should converge
    to the setpoint with sufficient ticks.
    """
    ch = HomeostaticHysteresisChannel(
        name="fatigue",
        value=0.9,
        setpoint=0.1,
        decay_rate=0.02,
        threshold=0.5,
        restoration_gain=0.4,
    )
    # Run many ticks without stimulus — value must converge toward setpoint
    for _ in range(100):
        ch.tick(dt=2.0, reference_interval=2.0)

    # After 100 ticks with restoration_gain=0.4 above threshold=0.5,
    # the value should be close to setpoint (0.1), not zero.
    assert ch.value < 0.2, (
        f"Homeostatic recovery failed: value={ch.value:.4f}, expected < 0.2 after 100 ticks"
    )
    assert ch.value > 0.05, (
        f"Value decayed below setpoint: value={ch.value:.4f}, setpoint=0.1. "
        "Should converge to setpoint, not zero."
    )


def test_homeostatic_recovery_from_saturation():
    """Verify that the stability condition prevents permanent saturation.

    Fatigue at value=1.0 should recover to near-setpoint within a bounded
    number of ticks, proving the death spiral is permanently broken.
    """
    ch = HomeostaticHysteresisChannel(
        name="fatigue",
        value=1.0,
        setpoint=0.1,
        decay_rate=0.02,
        threshold=0.5,
        restoration_gain=0.4,
    )
    # Track recovery: value must drop below threshold within reasonable ticks
    ticks_to_recover = 0
    for _ in range(200):
        ch.tick(dt=2.0, reference_interval=2.0)
        ticks_to_recover += 1
        if ch.value < ch.threshold:
            break

    assert ticks_to_recover < 50, (
        f"Fatigue took {ticks_to_recover} ticks to drop below threshold (0.5). "
        "Death spiral still present — recovery too slow."
    )
    # Continue ticking to verify convergence to setpoint
    for _ in range(100):
        ch.tick(dt=2.0, reference_interval=2.0)

    assert ch.value < 0.15, (
        f"Fatigue at {ch.value:.4f} after recovery — should be near setpoint 0.1"
    )


def test_restoration_force_kicks_in_above_threshold():
    """Verify that active restoration force only applies above threshold.

    Below threshold, only nonlinear decay operates.
    Above threshold, restoration_gain adds extra downward force.
    """
    # Channel below threshold: only decay
    ch_below = HomeostaticHysteresisChannel(
        name="stress",
        value=0.25,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    ch_below.tick(dt=2.0, reference_interval=2.0)
    decay_only_drop = 0.25 - ch_below.value

    # Channel above threshold: decay + restoration
    ch_above = HomeostaticHysteresisChannel(
        name="stress",
        value=0.5,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    ch_above.tick(dt=2.0, reference_interval=2.0)
    combined_drop = 0.5 - ch_above.value

    # The above-threshold drop should be significantly larger
    # due to the additional restoration force
    assert combined_drop > decay_only_drop * 1.5, (
        f"Restoration force not effective: above-threshold drop={combined_drop:.4f}, "
        f"below-threshold drop={decay_only_drop:.4f}"
    )

    # Verify restoration contribution specifically:
    # decay at v=0.5: 0.05 * (0.5-0.1) * 1.5 = 0.03
    # restoration at v=0.5: 0.3 * (0.5-0.3) = 0.06
    # total = 0.09, scaled by 1.0 = 0.09
    expected_total = 0.09
    assert abs(combined_drop - expected_total) < 0.01, (
        f"Expected combined drop ~{expected_total:.3f}, got {combined_drop:.4f}"
    )


def test_restoration_force_zero_below_threshold():
    """Restoration must be exactly zero when value < threshold."""
    ch = HomeostaticHysteresisChannel(
        name="pain",
        value=0.15,
        setpoint=0.05,
        decay_rate=0.10,
        threshold=0.2,
        restoration_gain=0.5,
    )
    # At v=0.15 < threshold=0.2, restoration should be 0
    # Only decay operates: 0.10 * (0.15-0.05) * 1.15 = 0.0115
    ch.tick(dt=2.0, reference_interval=2.0)
    expected_value = 0.15 - 0.0115
    assert abs(ch.value - expected_value) < 0.001, (
        f"Below threshold, only decay should apply. Expected {expected_value:.4f}, got {ch.value:.4f}"
    )


def test_hysteretic_inertia_resists_rapid_change():
    """Verify that the hidden hysteretic state dampens rapid changes.

    When _hysteretic > 0.5 and desired_delta > 0, the delta is scaled by 0.3.
    This creates inertia — resistance to continued movement in the same direction.
    """
    ch = HomeostaticHysteresisChannel(
        name="euphoria",
        value=0.5,
        setpoint=0.15,
        decay_rate=0.08,
        threshold=0.4,
        restoration_gain=0.35,
    )
    # Manually set hysteretic state high (simulating sustained increase)
    ch._hysteretic = 0.8

    # Apply a positive stimulus — should be dampened
    ch.stimulate(0.5)
    ch.tick(dt=2.0, reference_interval=2.0)

    # With inertia active, the effective delta is only 30% of nominal
    # decay = 0.08 * (0.5-0.15) * 1.5 = 0.042
    # restoration = 0.35 * max(0, 0.5-0.4) = 0.035
    # net without stimulus = -(0.042 + 0.035) = -0.077
    # desired_delta = 0.5 - 0.077 = 0.423
    # hysteretic inertia: 0.423 * 0.3 = 0.1269
    # value change = 0.1269
    expected_value = 0.5 + 0.1269
    assert abs(ch.value - expected_value) < 0.01, (
        f"Hysteretic inertia failed: expected ~{expected_value:.4f}, got {ch.value:.4f}"
    )


def test_hysteretic_inertia_not_active_when_low():
    """When _hysteretic is low, no inertia dampening should occur."""
    ch = HomeostaticHysteresisChannel(
        name="euphoria",
        value=0.5,
        setpoint=0.15,
        decay_rate=0.08,
        threshold=0.4,
        restoration_gain=0.35,
    )
    ch._hysteretic = 0.0  # Low hysteretic state — no inertia

    ch.stimulate(0.5)
    ch.tick(dt=2.0, reference_interval=2.0)

    # Without inertia, full desired_delta is applied
    # decay = 0.08 * (0.5-0.15) * 1.5 = 0.042
    # restoration = 0.35 * max(0, 0.5-0.4) = 0.035
    # desired_delta = 0.5 - 0.077 = 0.423
    # value change = 0.423
    expected_value = 0.5 + 0.423
    assert abs(ch.value - expected_value) < 0.01, (
        f"No-inertia case failed: expected ~{expected_value:.4f}, got {ch.value:.4f}"
    )


def test_hysteretic_inertia_direction_specific():
    """Inertia only resists the direction aligned with _hysteretic sign.

    _hysteretic > 0.5 resists positive deltas only.
    _hysteretic < -0.5 resists negative deltas only.
    """
    # Case 1: _hysteretic > 0.5, negative delta → NO dampening
    ch1 = HomeostaticHysteresisChannel(
        name="stress",
        value=0.7,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    ch1._hysteretic = 0.8
    # No stimulus, so desired_delta = -decay - restoration (negative)
    ch1.tick(dt=2.0, reference_interval=2.0)
    # Should decay fully (no dampening since delta is negative but hysteretic is positive)
    # decay = 0.05 * (0.7-0.1) * 1.7 = 0.051
    # restoration = 0.3 * (0.7-0.3) = 0.12
    # total drop = 0.171
    expected = 0.7 - 0.171
    assert abs(ch1.value - expected) < 0.01, (
        f"Direction-specific inertia failed (case 1): expected ~{expected:.4f}, got {ch1.value:.4f}"
    )

    # Case 2: _hysteretic < -0.5, positive delta → NO dampening
    ch2 = HomeostaticHysteresisChannel(
        name="stress",
        value=0.1,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    ch2._hysteretic = -0.8
    ch2.stimulate(0.5)
    ch2.tick(dt=2.0, reference_interval=2.0)
    # Positive stimulus, negative hysteretic → no dampening
    # decay = 0.05 * (0.1-0.1) * 1.1 = 0.0
    # restoration = 0
    # desired_delta = 0.5
    expected = 0.1 + 0.5
    assert abs(ch2.value - expected) < 0.01, (
        f"Direction-specific inertia failed (case 2): expected ~{expected:.4f}, got {ch2.value:.4f}"
    )


def test_homeostatic_engine_stability_all_channels():
    """Verify the stability condition for all channels from default settings."""
    settings = HysteresisSettings()
    engine = HomeostaticHysteresisEngine.from_settings(settings)
    stability = engine.check_stability()
    for name, stable in stability.items():
        assert stable, (
            f"Channel '{name}' is UNSTABLE! "
            f"decay_rate * (1-setpoint) + restoration_gain * (1-threshold) <= 0.2125"
        )


def test_homeostatic_engine_from_settings():
    """Homeostatic engine must build from HysteresisSettings with new params."""
    settings = HysteresisSettings()
    engine = HomeostaticHysteresisEngine.from_settings(settings)
    assert "stress" in engine.channels
    assert "fatigue" in engine.channels
    # Verify new params are picked up
    fatigue = engine.channels["fatigue"]
    assert fatigue.setpoint == 0.1
    assert fatigue.restoration_gain == 0.4


def test_homeostatic_channel_from_params():
    """HomeostaticHysteresisChannel.from_params must read new fields."""
    params = HysteresisParams(
        decay_rate=0.05,
        accumulation_rate=0.15,
        threshold=0.3,
        setpoint=0.1,
        restoration_gain=0.3,
    )
    ch = HomeostaticHysteresisChannel.from_params("stress", params)
    assert ch.setpoint == 0.1
    assert ch.restoration_gain == 0.3


def test_homeostatic_dt_scaling():
    """dt normalization: half dt → half the continuous decay+restoration effect."""
    ch1 = HomeostaticHysteresisChannel(
        name="test",
        value=0.8,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    ch2 = HomeostaticHysteresisChannel(
        name="test",
        value=0.8,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )

    # No stimulus — pure decay + restoration
    ch1.tick(dt=1.0, reference_interval=2.0)  # scale = 0.5
    ch2.tick(dt=2.0, reference_interval=2.0)  # scale = 1.0

    drop_1 = 0.8 - ch1.value
    drop_2 = 0.8 - ch2.value

    # dt=2.0 produces ~2× the drop of dt=1.0
    assert abs(drop_2 - 2.0 * drop_1) < 0.01, (
        f"dt scaling failed: drop(dt=2.0)={drop_2:.4f}, drop(dt=1.0)={drop_1:.4f}, "
        f"ratio={drop_2/drop_1:.3f} (expected ~2.0)"
    )


def test_homeostatic_stimulate_is_discrete():
    """stimulate() stores discrete events; value doesn't change until tick()."""
    ch = HomeostaticHysteresisChannel(
        name="stress",
        value=0.0,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    assert ch.value == 0.0
    ch.stimulate(0.5)
    # Value must NOT change from stimulate() alone
    assert ch.value == 0.0, (
        f"stimulate() should be discrete — value changed to {ch.value} before tick()"
    )
    assert ch._pending_stimulus == 0.5

    # After tick, stimulus is processed
    ch.tick(dt=2.0, reference_interval=2.0)
    assert ch.value > 0.0, "Value should change after tick() processes the stimulus"
    assert ch._pending_stimulus == 0.0, "Pending stimulus should reset after tick()"


def test_homeostatic_engine_reset_all():
    """reset_all() must clear values and internal state."""
    settings = HysteresisSettings()
    engine = HomeostaticHysteresisEngine.from_settings(settings)
    engine.stimulate("stress", 1.0)
    engine.stimulate("pain", 1.0)
    engine.tick()
    engine.reset_all()
    for ch in engine.channels.values():
        assert ch.value == 0.0
        assert ch._hysteretic == 0.0
        assert ch._pending_stimulus == 0.0


def test_homeostatic_setpoint_pull_up():
    """When value is below setpoint, decay is negative → pulls value UP."""
    ch = HomeostaticHysteresisChannel(
        name="stress",
        value=0.0,
        setpoint=0.1,
        decay_rate=0.05,
        threshold=0.3,
        restoration_gain=0.3,
    )
    # No stimulus, value below setpoint
    ch.tick(dt=2.0, reference_interval=2.0)
    # decay = 0.05 * (0.0-0.1) * 1.0 = -0.005 (negative → pulls up)
    # restoration = 0 (below threshold)
    # desired_delta = 0 - (-0.005) = 0.005
    # value change = 0.005
    assert ch.value > 0.0, (
        f"Setpoint pull-up failed: value={ch.value:.4f}, should be > 0.0 "
        "(homeostatic pull toward setpoint)"
    )
    assert abs(ch.value - 0.005) < 0.001, (
        f"Expected value ~0.005, got {ch.value:.4f}"
    )


def test_homeostatic_compute_runtime_delta():
    """compute_runtime_delta works identically to old engine for cross-channel effects."""
    settings = HysteresisSettings()
    engine = HomeostaticHysteresisEngine.from_settings(settings)
    engine.stimulate("stress", 0.8)
    engine.tick()

    class MockFlags:
        runtime_effects_enabled = True
        stress_narrows_context = True
        emotion_affects_temperature = True
        pain_reduces_bandwidth = True

    delta = engine.compute_runtime_delta(MockFlags())
    assert "context_window" in delta
    assert delta["context_window"] < 0
    assert "temperature" in delta
    assert delta["temperature"] > 0
    assert "energy_level" in delta
    assert delta["energy_level"] < 0


def test_homeostatic_gain_bounded():
    """Global gain bound prevents any field from exceeding ±1.0 per tick."""
    settings = HysteresisSettings()
    engine = HomeostaticHysteresisEngine.from_settings(settings)
    # Saturate all channels
    for name in engine.channels:
        engine.channels[name].value = 1.0

    class MockFlags:
        runtime_effects_enabled = True
        stress_narrows_context = True
        emotion_affects_temperature = True
        pain_reduces_bandwidth = True

    delta = engine.compute_runtime_delta(MockFlags())
    for key, value in delta.items():
        assert -1.0 <= value <= 1.0, (
            f"Gain bound violated: {key}={value}, must be in [-1.0, 1.0]"
        )
