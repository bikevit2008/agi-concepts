from scripts.run_long_stability import run_stability
from src.experiments.harness import ScriptedTeam, run_loop


def test_deterministic_harness_replays_same_trace():
    stimulus_plan = {1: "alpha", 5: "beta"}
    team1 = ScriptedTeam(stimuli_per_tick={"stress": 0.03})
    team2 = ScriptedTeam(stimuli_per_tick={"stress": 0.03})

    run1 = run_loop(ticks=20, team=team1, stimulus_plan=stimulus_plan)
    run2 = run_loop(ticks=20, team=team2, stimulus_plan=stimulus_plan)

    assert run1.errors == []
    assert run2.errors == []
    assert run1.runtime_trace == run2.runtime_trace
    assert run1.channel_traces == run2.channel_traces
    assert run1.stimuli_submitted == run2.stimuli_submitted


def test_long_stability_report_shape():
    report = run_stability(ticks=30, stress_per_tick=0.02)

    assert report["ticks"] == 30
    assert report["errors"] == []
    assert "stress" in report["channels"]
    assert "death_spirals" in report
    assert "final_runtime" in report
    assert isinstance(report["stable"], bool)
