# Gotchas — bugs and tricky details we already paid for

A list of non-obvious failure modes encountered between Stages 0-17.
Read this before debugging "weird" behaviour or before making
"obvious" simplifications.

## Loop time

### `dt` is computed from `time.monotonic()`, not from tick count

This is correct behaviour in production (real wall-clock keeps decay
proportional to elapsed seconds), but it breaks tests that drive the
loop in a tight Python loop — `dt ≈ 0` between calls, decay never
fires, traces stay flat.

**Fix in tests:** always use `LoopHarness.run(simulated_time=True)`
(default). It rewinds `loop._last_tick_time` by `tick_interval_sec`
before each `_tick()` so `dt = tick_interval_sec`.

We learned this the hard way in Stage 13 — the first run of
`test_h1_homeostatic_engine_recovers_from_injected_stress` looked like
homeostasis was broken; it was the test harness.

### `_tick` vs `_tick_inner`

`_tick` increments `self._tick_count` and wraps `_tick_inner` in a
try/except + observability span. **Always call `_tick()` from tests**
unless you specifically want to bypass the counter (almost never).

## Hysteresis math

### `restoration_gain=0.3` is the edge of stability

V3 stability condition for `stress`:
```
2·decay_rate·(1−setpoint) + restoration_gain·(1−threshold) > max_stim
2·0.05·0.9   + 0.3·0.7      = 0.09 + 0.21 = 0.30
```
A one-shot 0.9 stim creates `_pending_stimulus = 0.30` rate; we sit
right at the edge. Recovery takes >100 ticks. **Either**:
- Bump `stress.restoration_gain` to 0.5+ in `default.yaml`.
- Cap one-shot stims to 0.5 in production (do this via the
  `STIMULATION_MAX_INTENSITY` constitutional policy).

### `_hysteretic` state slows recovery

When the channel has been at high value for a while, `_hysteretic > 0.5`,
which scales further `desired_delta` by 0.3 (resistance to direction
change). This is *intended* — that's the hysteresis. But it makes the
math feel slower than the surface formula suggests. See
`HomeostaticHysteresisChannel.tick`.

## Governance kernel

### Floating-point boundary on caps

`0.1 + 0.1 + 0.1 = 0.30000000000000004` in IEEE-754. The kernel uses
`_FP_TOLERANCE = 1e-9` so a sum that's exactly at-cap-up-to-fuzz
still passes. Don't lower the tolerance.

### Negative intensity is unconditionally allowed

Any policy / cap / circuit-breaker check is bypassed when
`request.intensity ≤ 0`. This is by design (self-soothing during
recovery must not be gated). If you add a new constraint, exempt
negative intensity explicitly.

### `state_provider` is called on every authorize

Keep it cheap (~µs). Don't call slow store reads from the lambda.
Right now it returns `cost_budget_exceeded` + `tripped_channels` from
already-computed objects.

## Persistence

### LanceDB table re-create races

Two tests using the same `tmp_path` and `table_name` can race:
`list_tables()` doesn't include a brand-new table immediately, so
`create_table(mode='create')` raises `ValueError`. We catch it and
fall back to `open_table` — see `LanceDbMemoryStore._open_or_create_table`.

### LanceDB `to_pandas()` requires pandas

We don't depend on pandas. Use `_to_records()` (PyArrow `to_pylist()`)
instead.

### SQLite WAL files are NOT in `*.db`

`.db-wal` and `.db-shm` are also written. They're in `.gitignore`
already. If you symlink the data directory, copy all three.

### Snapshot restore — hysteresis dict shape

`hysteresis.to_dict()` returns `{channel_name: {value, ...}}` directly,
without a top-level `"channels"` wrapper. Stage 4 originally looked
for `snapshot.hysteresis["channels"]` and silently failed to restore;
the fix is in `restore_from_checkpoint`.

## Memory store

### HashingEmbedder needs unigram overlap

It hashes unigrams + bigrams. Two sentences with one shared word
get cosine ~0.33. Three sentences sharing "user enjoys" land around
0.37, well below typical similarity thresholds (0.7). For tests that
need clusters to form, use **strongly-overlapping** texts like
`"alpha alpha repeated text aaa"` / `"alpha alpha repeated text bbb"`.

In production, `SentenceTransformerEmbedder` solves this — its
embeddings are semantic.

### Cosine similarity can be negative

`HashingEmbedder` produces signed vectors (the sign comes from MD5).
Cosine similarity ranges over `[-1, 1]`. If `min_provenance_similarity`
is positive, expect a positive cosine (good). To disable the check
use `min_provenance_similarity ≤ 0` — we explicitly skip the check
in that range.

## Observability

### OTel SDK retries against unreachable collectors

By default the OTLP gRPC exporter retries every second when the
collector at `localhost:4317` is down. Tests run for 12+ seconds.
Pass `disable_exporters=True` to `OtelObservabilityCollector` in
tests; in production the collector is up.

### `force_flush(timeout_millis=...)` not `force_flush(timeout=...)`

OTel SDK uses millis, not seconds. `flush(timeout_seconds=5.0)` does
the conversion internally.

## Sleep manager

### `force_sleep()` requires two ticks

Calling `sleep_manager.force_sleep()` puts the manager into DROWSY,
not SLEEPING — the latter happens after `seconds_in_state > 5.0`,
which means at least one extra tick with `dt > 5s`. With
`simulated_time=True` and `tick_interval_sec=2.0`, you need 3 ticks
total to see SLEEPING. This is *correct* (drowsiness precedes sleep)
but surprising in tests.

## ML regulators

### `OfflineRecoveryPolicy` falls back when uncertain

If the trained BC's top-class probability is below
`confidence_threshold` (default 0.6), we delegate to
`RuleBasedRecoveryPolicy`. The decision's `rationale` will say
`"bc_unsure(p=0.42); fallback: ..."` — read that field to confirm
which path was taken.

### CSD warms up — first 10-20 ticks return OK regardless

`CsdCollapseForecaster` returns `WarningLevel.OK` until
`min_observations` (default 10) samples are collected. Don't assert
on the level for very short traces.

## Tools

### Subprocess code executor is NOT a security boundary

`CodeExecutorTool(backend="subprocess")` runs `python3 -c <code>` in
a stripped environment with a timeout. There's no syscall isolation.
If untrusted code is a possibility, use the `nsjail` or `e2b`
backends. The default is `subprocess` for ease — change for
adversarial deployments.

### Audit log writes are best-effort

If `audit_log_path` is unwritable we log a warning and continue. The
in-memory record is always correct. Don't rely on the JSONL file as
your only source of truth — the structured log is.

## Tests

### `test_run_ablation_json_mode` once printed Python logs into stdout

The fix was in `scripts/run_ablation.py`:
```python
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
)
```
Apply the same to any new CLI script that emits structured output.

### `pytest.mark.docker` warning before registration

If you add `pytest.mark.docker` somewhere new, register it in
`pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = ["docker: integration tests requiring Docker"]
```
otherwise pytest emits an ugly warning per file.

## CLI

### `consciousness` entrypoint requires editable install

`pip install -e .` is required for the `consciousness` script to be
on PATH. From a fresh checkout, `python -m src.main` works without
install.
