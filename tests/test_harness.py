"""Tests for the experiment harness (Stage 13 — infrastructure)."""


from src.experiments.harness import ScriptedTeam, run_loop
from src.experiments.metrics import (
    detect_death_spiral,
    measure_recovery_time,
    spiral_count,
    summarize_run,
    time_above_saturation,
)


def test_scripted_team_returns_fixed_response():
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": f"echo:{s}"}
    )
    result = team.process_stimulus_sync("hi")
    assert result == {"response": "echo:hi"}


def test_harness_runs_n_ticks_without_errors():
    result = run_loop(ticks=50)
    assert result.total_ticks == 50
    assert len(result.runtime_trace) == 50
    assert result.errors == []


def test_harness_channel_traces_populated():
    result = run_loop(ticks=30)
    for ch in ("stress", "euphoria", "fatigue", "pain"):
        assert len(result.channel_trace(ch)) == 30


def test_harness_flags_overrides_apply():
    result = run_loop(ticks=5, flags_overrides={"feedback_loops_enabled": False})
    assert result.flags.feedback_loops_enabled is False


def test_harness_stimulus_plan_submits_stimuli():
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": f"r:{s}"},
    )
    result = run_loop(
        ticks=10,
        team=team,
        stimulus_plan={3: "hello", 7: "bye"},
    )
    assert result.stimuli_submitted == ["hello", "bye"]


def test_harness_applies_scripted_stimulations():
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": "ok"},
        stimuli_per_tick={"stress": 0.3},
    )
    result = run_loop(ticks=30, team=team)
    # Stress should rise above 0 with per-tick injection
    stress = result.channel_trace("stress")
    assert max(stress) > 0.1


# --- Metrics ---------------------------------------------------------------


def test_time_above_saturation():
    trace = [0.1, 0.5, 0.96, 0.97, 0.2]
    assert time_above_saturation(trace, 0.95) == 2


def test_detect_death_spiral_found():
    trace = [0.1] * 40 + [0.99] * 60
    t = detect_death_spiral(trace, window=50, threshold=0.95)
    assert t is not None
    assert t >= 90  # window of 50 saturated samples ends at or after index 90


def test_detect_death_spiral_not_found():
    trace = [0.1, 0.5, 0.3, 0.2] * 25  # never saturated
    assert detect_death_spiral(trace) is None


def test_spiral_count_counts_distinct_episodes():
    trace = [0.99] * 15 + [0.1] * 10 + [0.99] * 20 + [0.1] * 5
    # Two distinct saturations
    assert spiral_count(trace, threshold=0.95, min_length=10) == 2


def test_measure_recovery_time_reaches_baseline():
    trace = [1.0, 0.9, 0.7, 0.5, 0.29, 0.2]
    # From tick 0, baseline 0.3: first index where value < 0.3 is 4
    assert measure_recovery_time(trace, from_tick=0, to_baseline=0.3) == 4


def test_measure_recovery_time_no_recovery():
    trace = [1.0] * 20
    assert measure_recovery_time(trace, from_tick=0, to_baseline=0.3) is None


def test_summarize_run_shape():
    channels = {"stress": [0.1, 0.5, 0.96, 0.97, 0.2], "pain": [0.0, 0.0, 0.0]}
    summary = summarize_run(channels)
    assert "max" in summary["stress"]
    assert summary["stress"]["time_above_0.95"] == 2
    assert summary["pain"]["max"] == 0.0
