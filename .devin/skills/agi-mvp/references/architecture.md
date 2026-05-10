# Architecture reference

## Layered design (top → bottom)

```
┌─────────────────────────────────────────────────────────────┐
│ Application:  ConsciousnessLoop / ConsciousnessTeam         │
│   - depends only on Protocols                               │
│   - injects all subsystems through the constructor          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ depends on
┌─────────────────────────────────────────────────────────────┐
│ Contracts (src/contracts/):                                 │
│   IGovernanceKernel, ICircuitBreaker, IConstitutionalAuditor│
│   IEventStore, ICheckpoint                                  │
│   IMemoryStore, IProvenanceTracker                          │
│   ICostTracker, IModelInvoker                               │
│   IObservabilityCollector, ISpan                            │
│   IEventBus                                                 │
│   ISleepManager, IMemoryConsolidator                        │
│   IRuminationDetector, ICollapseForecaster, IRecoveryPolicy │
│   IToolRegistry, ITool                                      │
│                                                             │
│ Each ships with a Null implementation in the same file.     │
└─────────────────────────────────────────────────────────────┘
                              ▲ implements
                              │
┌─────────────────────────────────────────────────────────────┐
│ Concrete adapters:                                          │
│   src/engine/             — hysteresis, breaker, circadian, │
│                             memory consolidator, clusterer  │
│   src/governance/         — deterministic kernel, auditor   │
│   src/persistence/        — SQLite WAL, LanceDB, embedder,  │
│                             cost tracker, agno invoker      │
│   src/observability/      — OpenTelemetry collector         │
│   src/visualization/      — Rerun logger                    │
│   src/bus/                — AsyncIO + NATS implementations  │
│   src/ml/                 — rumination, collapse, recovery  │
│                             (rule + BC), dataset builder    │
│   src/tools/              — registry, web_search, executor  │
└─────────────────────────────────────────────────────────────┘
```

## Wiring — `src/tui/app.py` is the composition root

`ConsciousnessApp.__init__` builds:

1. Settings + flags (loaded from YAML).
2. `RuntimeState` from settings.
3. Both hysteresis engines; flag picks active.
4. Governance stack: circuit breaker → constitutional auditor →
   deterministic kernel.
5. Persistence: SqliteEventStore + SqliteCheckpoint or Null.
6. Memory: embedder (ST or Hashing) → memory store (LanceDB or
   InMemory) → provenance tracker.
7. Cost tracker.
8. Observability: OtelObservabilityCollector + RerunLogger or Nulls.
9. Sleep: CircadianSleepManager + LlmMemoryConsolidator (Stage 15) or
   HebbianMemoryConsolidator (Stage 9 fallback) or Null.
10. ML: ShannonRuminationDetector + CsdCollapseForecaster +
    RuleBasedRecoveryPolicy (or OfflineRecoveryPolicy if a trained
    BC checkpoint exists at boot).
11. Team passes governance + memory_store + provenance_tracker +
    cost_tracker.
12. Loop receives all subsystems; `_tick_inner` orchestrates them.

## Hot-path contract (`_tick_inner`)

Order matters. Each tick:

1. Compute `dt` from wall-clock (capped, never negative).
2. `governance.begin_tick(N)` — opens per-tick budget.
3. Set `team.current_tick = N` (governance traceability).
4. `sleep_manager.update(...)` if enabled — may produce
   `SleepDecision` with `suppress_llm_calls=True`.
5. If `suppress_llm_calls` is true:
     - Re-queue any received stimulus for after wake.
     - Skip self-reflection / spontaneous thought.
6. Otherwise:
     - Process stimulus through team (synchronous Agno calls in
       `asyncio.to_thread`).
     - Notify response callbacks.
     - Do autonomous thinking on idle ticks (reflection / spontaneous
       thoughts).
7. Soft-decay `RuntimeState` toward defaults (rate=0.1).
8. Compute hysteresis runtime delta + apply.
9. Feedback loops (low energy → fatigue, low attention → stress,
   prolonged stress → fatigue, prolonged pain → stress) — each
   stimulation goes through `gated_stimulate()` for governance.
10. `circuit_breaker.observe(channel, value, tick)` for every channel.
11. **Stage 12** ML regulators: rumination + collapse on each channel
    + recovery policy proposal → `_apply_recovery()` mutates state.
12. Clamp runtime state.
13. Compute `state_diff` vs pre-tick.
14. `governance.end_tick(N)` aggregates stats.
15. Build snapshot dict including governance + breaker + ml payload +
    `recovery_action` (Stage 16 dataset reads this).
16. Emit `STATE_SNAPSHOT` event on the in-process bus.
17. Persist snapshot + stimulus + runtime_change to `IEventStore`.
18. Every N ticks, save full `Snapshot` to `ICheckpoint`; prune older.
19. **Stage 15** maybe-consolidate when sleep phase changes.
20. Emit `consciousness.ticks` + per-channel hysteresis metrics.

## Adding a new subsystem — checklist

- [ ] Define a new `Protocol` + `NullX` impl in `src/contracts/`.
- [ ] Re-export from `src/contracts/__init__.py`.
- [ ] Add concrete impl(s) in the appropriate module.
- [ ] Decide whether the loop needs a new field. If yes:
        - Add `IX = field(default_factory=NullX)` to `ConsciousnessLoop`.
        - Wire from `ConsciousnessApp.__init__` honoring a feature flag.
        - Use it in `_tick_inner` only when the flag is on.
- [ ] Add unit tests for the impl.
- [ ] Add an integration test using `LoopHarness` + `ScriptedTeam`.
- [ ] If the subsystem makes decisions that affect the trajectory, add
      it to `tests/test_ablations.py` (turn it OFF, verify the
      expected behavioural change).
- [ ] Append a row to `IMPLEMENTATION_PLAN.md`.
- [ ] Commit with a long-form message in the same style as Stage 0-17.
