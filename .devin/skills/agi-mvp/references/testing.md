# Testing reference

## Test layout

```
tests/
├── conftest.py             # docker_available + auto-skip @pytest.mark.docker
├── test_*.py               # unit + integration tests, ~300+ cases
└── test_e2e.py             # full-stack scenarios (real SQLite, real LanceDB)
```

## Patterns

### 1. Use `LoopHarness` for any loop-touching test

```python
from src.experiments.harness import LoopHarness, ScriptedTeam, run_loop

team = ScriptedTeam(stimulus_response=lambda s: {"response": "ok"})
result = run_loop(
    ticks=200,
    team=team,
    flags_overrides={"feedback_loops_enabled": False},
)
```

`LoopHarness` wires the loop with Null implementations of every
non-essential subsystem (persistence, memory, observability, sleep,
ML). Only governance + circuit_breaker + hysteresis are live.

**Critical:** `LoopHarness.run` defaults to `simulated_time=True`,
which rewinds `_last_tick_time` before each `_tick()` so `dt` equals
`tick_interval_sec` instead of ~0 (real wall-clock between Python
calls). Without it, decay never fires and traces stay constant. See
[gotchas.md](gotchas.md#loop-time).

### 2. ScriptedTeam injection knobs

```python
team = ScriptedTeam(
    stimulus_response=lambda s: {"response": f"echo:{s}"},
    reflection_response=lambda: None,            # or {"thought": "..."}
    thought_response=lambda: None,
    stimuli_on_stimulus={"stress": 0.5},          # one-shot per stimulus
    stimuli_per_tick={"fatigue": 0.05},           # every tick
)
```

These bypass governance. Use them to set up trajectory experiments
without instrumenting real Agno agents.

### 3. Falsifiable test pattern

A falsifiable test states a hypothesis, runs the harness with specific
overrides, and asserts a measurable property:

```python
def test_h1_homeostatic_recovers_from_moderate_stress():
    """Hypothesis: homeostatic engine recovers from stress=0.5 in <150 ticks."""
    team = ScriptedTeam(stimulus_response=lambda s: {"response": "injected"})
    team.stimuli_on_stimulus = {"stress": 0.5}
    result = run_loop(
        ticks=300,
        team=team,
        flags_overrides={
            "homeostatic_hysteresis_enabled": True,
            "feedback_loops_enabled": False,
        },
        stimulus_plan={1: "inject"},
    )
    trace = result.channel_trace("stress")
    peak = max(range(len(trace)), key=lambda i: trace[i])
    recovery = measure_recovery_time(trace, from_tick=peak, to_baseline=0.3)
    assert recovery is not None and recovery < 150
```

**Don't soften the assertion when it fails — investigate.** A failing
falsifiable test is a real finding, not a flaky test.

### 4. Ablation pattern

`tests/test_ablations.py` runs the same setup twice with one knob
flipped and asserts behavioural divergence:

```python
def test_ablation_homeostatic_vs_linear_produces_different_traces():
    r_h = run_loop(ticks=100, flags_overrides={"homeostatic_hysteresis_enabled": True})
    r_l = run_loop(ticks=100, flags_overrides={"homeostatic_hysteresis_enabled": False})
    assert abs(r_h.channel_trace("stress")[-1] - r_l.channel_trace("stress")[-1]) > 1e-3
```

The CLI script `scripts/run_ablation.py` runs all 9 ablation scenarios
in sequence and prints a summary table.

### 5. Constitutional test pattern

When adding a new constitutional check, write tests at three levels:

1. **Unit:** the check function itself with synthetic ctx dicts.
2. **Integration:** load the constitution YAML, build an
   `ConstitutionalAuditor`, audit a request with crafted args.
3. **Loop integration:** run a tick that would normally trigger the
   gated action, assert governance returns DENY_CONSTITUTION.

### 6. Docker-marked tests

Anything that needs a real container goes:

```python
import pytest

pytestmark = pytest.mark.docker

@pytest.fixture(scope="module")
def my_container():
    from testcontainers.core.container import DockerContainer
    container = DockerContainer("...").with_exposed_ports(...)
    container.start()
    try:
        yield container
    finally:
        container.stop()
```

Auto-skipped when Docker isn't running (see `conftest.py`).

## Metrics from `src/experiments/metrics.py`

- `time_above_saturation(trace, threshold=0.95)` → MTTDS proxy.
- `detect_death_spiral(trace, window=50, threshold=0.95)` → first
  tick of sustained saturation.
- `spiral_count(trace, threshold, min_length)` → distinct episodes.
- `measure_recovery_time(trace, from_tick, to_baseline=0.3)` →
  ticks until value drops below baseline.
- `summarize_run(channel_traces)` → per-channel max / mean /
  time_above_0.95 / spiral_count.

## CLI scripts

- `scripts/run_ablation.py --ticks 200 [--json]` — V3 §8.2
  ablation matrix.
- `scripts/run_falsifiable.py --ticks 300 [--json]` — V3 §8.3
  falsifiable hypothesis runner.
- `scripts/train_offline_recovery.py --events data/events.db
  --output data/recovery_bc.json` — train BC recovery policy from
  accumulated event log.

All three silence structlog at ERROR (only stderr) so their stdout is
clean, machine-parsable JSON.

## When tests fail

1. **Timing tests fail** → almost always `simulated_time=False` or
   forgot to call `loop._tick()` (use `_tick`, not `_tick_inner` —
   `_tick` increments `_tick_count`).
2. **Governance test fails because counters are off** → check
   floating-point tolerance. Use `_FP_TOLERANCE = 1e-9` (already in
   `src/governance/kernel.py`); 0.1 + 0.1 + 0.1 = 0.30000000000000004.
3. **Provenance test fails because similarity is negative** → set
   `min_provenance_similarity ≤ 0` to disable the check, OR ensure
   text/cluster have realistic embeddings. The HashingEmbedder gives
   negative cosine for unrelated text, which is correct behaviour.
4. **OTel tests run for 12+ seconds** → you're letting the SDK retry
   to a non-existent collector. Pass `disable_exporters=True` to
   `OtelObservabilityCollector` in tests.
5. **LanceDB raises "table already exists"** → another test (or test
   shard) created the table first. Race-tolerant `_open_or_create_table`
   catches this; if you see it, the catch is missing.
