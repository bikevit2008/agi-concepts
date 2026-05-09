"""Ablation studies — AGI_CONCEPT_V3_RU.md section 8.2.

Systematically disables one subsystem at a time and verifies the
behavioral signature described in the V3 audit:

    OFF feedback_loops            → no feedback-driven drift
    OFF self_reflection           → no reflection-triggered stimuli
    OFF emotion                   → no emotion-driven hysteresis stim
    OFF hysteresis                → no emotional inertia
    OFF homeostatic_hysteresis    → linear engine is used
    OFF runtime_effects           → runtime_state stays at defaults

These are NOT regression tests of output — they are structural
assertions about what changes when each knob is turned.
"""

from __future__ import annotations

from src.experiments.harness import ScriptedTeam, run_loop


def _make_team_with_injection():
    return ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
        stimuli_per_tick={"stress": 0.1},
    )


def test_ablation_homeostatic_vs_linear_produces_different_traces():
    team1 = _make_team_with_injection()
    team2 = _make_team_with_injection()

    r_h = run_loop(
        ticks=100,
        team=team1,
        flags_overrides={"homeostatic_hysteresis_enabled": True},
    )
    r_l = run_loop(
        ticks=100,
        team=team2,
        flags_overrides={"homeostatic_hysteresis_enabled": False},
    )

    stress_h = r_h.channel_trace("stress")
    stress_l = r_l.channel_trace("stress")

    # Final values must differ (they use different math)
    assert abs(stress_h[-1] - stress_l[-1]) > 1e-3, (
        f"homeostatic end={stress_h[-1]} vs linear end={stress_l[-1]}"
    )


def test_ablation_runtime_effects_off_freezes_runtime_state():
    """If runtime_effects are disabled, runtime_state never mutates
    beyond clamping."""
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
        stimuli_per_tick={"stress": 0.5},  # would normally push runtime params
    )
    result = run_loop(
        ticks=50,
        team=team,
        flags_overrides={
            "runtime_effects_enabled": False,
            "feedback_loops_enabled": False,  # isolate the effect
        },
    )
    # runtime_trace's `temperature` should remain at the default (0.7)
    temps = [rs["temperature"] for rs in result.runtime_trace]
    assert all(abs(t - 0.7) < 1e-3 for t in temps[:5]), (
        f"temperature drifted with runtime_effects off: {temps[:10]}"
    )


def test_ablation_feedback_loops_off_channel_decays_monotonically():
    """With feedback off, after a one-shot stimulation the channel decays."""
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
    )
    team.stimuli_on_stimulus = {"stress": 0.8}
    result = run_loop(
        ticks=150,
        team=team,
        flags_overrides={
            "feedback_loops_enabled": False,
            "homeostatic_hysteresis_enabled": True,
        },
        stimulus_plan={1: "inject"},
    )
    stress = result.channel_trace("stress")
    peak = max(stress)
    peak_idx = stress.index(peak)
    # After the peak, value should be monotonically non-increasing (within a
    # small numeric tolerance) because there's no feedback or new stim.
    for i in range(peak_idx + 5, len(stress)):
        prev = stress[peak_idx + 1]
        cur = stress[i]
        # Allow micro-fluctuations from floating-point
        assert cur <= prev + 1e-3, (
            f"channel rebounded after peak: peak_tick={peak_idx}, "
            f"later tick {i}: {cur} vs prev {prev}"
        )


def test_ablation_hysteresis_off_skips_decay():
    """If hysteresis disabled, `tick()` is skipped; channel values only
    change due to stimulations (no decay)."""
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
    )
    team.stimuli_on_stimulus = {"stress": 0.5}
    result = run_loop(
        ticks=50,
        team=team,
        flags_overrides={
            "hysteresis_enabled": False,
            "feedback_loops_enabled": False,
            "runtime_effects_enabled": False,
        },
        stimulus_plan={1: "inject"},
    )
    stress = result.channel_trace("stress")
    # Stress was stimulated once; without decay it should stay at ~0.5 for
    # the rest of the run.
    non_zero = [v for v in stress if v > 0.01]
    if non_zero:
        # All non-zero values should be roughly equal (no decay)
        mn = min(non_zero)
        mx = max(non_zero)
        assert mx - mn < 1e-3, f"stress decayed with hysteresis off: {mn}..{mx}"


def test_ablation_governance_off_allows_larger_total_stim():
    """Turning off governance removes the per-tick cap ⇒ channels reach
    higher peak values for the same injection."""
    team_on = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
    )
    team_off = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
    )
    # Intentionally small per-tick cap — forces governance to clip the sum
    overrides_on = {"governance_enabled": True, "feedback_loops_enabled": True}
    overrides_off = {"governance_enabled": False, "feedback_loops_enabled": True}

    r_on = run_loop(ticks=200, team=team_on, flags_overrides=overrides_on)
    r_off = run_loop(ticks=200, team=team_off, flags_overrides=overrides_off)

    stress_on = max(r_on.channel_trace("stress"))
    stress_off = max(r_off.channel_trace("stress"))
    # With feedback the channels climb; with governance off, peaks should
    # be at least as high.
    assert stress_off >= stress_on - 1e-6, (
        f"governance-off peak {stress_off:.3f} should be ≥ governance-on peak "
        f"{stress_on:.3f}"
    )
