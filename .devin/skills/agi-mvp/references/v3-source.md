# V3 audit traceability — which decision drove which stage

Cross-reference between `AGI_CONCEPT_V3_RU.md` (the original quorum
audit) and the implementation stages. When a future change touches an
existing subsystem, look up what V3 said about it before deciding to
deviate.

## Critical bugs (V3 §2.2) → Stage 1

| V3 bug | Where fixed | How |
|--------|-------------|-----|
| #1 Tick interval scaling bug | `consciousness_loop.py:_tick_inner` | `dt` from `time.monotonic()`, capped at 5×tick interval |
| #2 Reset-to-defaults bug    | `runtime_state.py:decay_toward_defaults` + `consciousness_loop.py` | additive `apply_delta`, soft decay rate 0.1 |
| #3 Unlimited self-stimulation | `consciousness_team.py:_gated_stimulate` | governance kernel + `reflection_self_stim_cap` |
| #4 Memory hallucination | `consciousness_team.py:process_stimulus_sync` + Stage 5 provenance | retrieval-first prompt + embedding similarity check |

## Death spiral math (V3 §2.3) → Stage 2

The V3 audit derived loop gain 10.6× for fatigue and concluded saturation
lock is mathematically guaranteed under the linear engine. Stage 2's
`HomeostaticHysteresisEngine` adds setpoint + restoration force; the
stability condition `2·decay·(1−setpoint) + restoration·(1−threshold) > max_stim`
is checked in the per-channel calibration. See
[sota.md](sota.md#hysteresis-engine-stage-2).

## Architectural decisions (V3 §10)

| V3 decision | Stage(s) | Implementation |
|-------------|----------|----------------|
| #1 Event-driven, not call-driven | 8 | `IEventBus` with AsyncIO + NATS impls |
| #2 Governance — code, not prompts | 3, 11 | `DeterministicGovernanceKernel` + YAML constitution |
| #3 Memory — retrieval-first | 5, 15 | LanceDB + `EmbeddingProvenanceTracker` + LLM REM |
| #4 Hysteresis — separate engine | 2 | `HomeostaticHysteresisEngine` (drop-in for `HysteresisEngine`) |
| #5 Sleep — mandatory | 9 | `CircadianSleepManager` (Two-Process Model) |

## Phases (V3 §7)

V3 proposed 4 phases; we ended up with 17 stages plus a
forward-looking skill. Mapping:

| V3 Phase | V3 description | Our stages |
|----------|----------------|------------|
| 1 | Fix Death Spiral + Persistence | 0 (infra), 1 (4 bugs), 2 (homeostatic engine), 3 (governance + breaker), 4 (SQLite WAL), 5 (memory + provenance), 6 (cost + fallback) |
| 2 | Sleep/Recovery + ML Regulators | 9 (sleep mode), 12 (rumination + collapse + recovery), 15 (LLM REM), 16 (offline-RL BC) |
| 3 | Governance Layer + Event Buses | 8 (NATS bus), 10 (tools registry), 11 (constitutional auditor), 17 (prompt injection + Grafana alerts) |
| 4 | Observability + Tools/World Interfaces | 7 (OTel + Rerun), 13 (E2E + ablation + falsifiable), 14 (production observability bundle), 18 (this skill) |

## Risk register (V3 §9)

| V3 risk | Status | How addressed |
|---------|--------|---------------|
| LanceDB API instability | Mitigated | `IMemoryStore` abstraction; `InMemoryMemoryStore` fallback; race-tolerant `_open_or_create_table` |
| NATS operational complexity | Mitigated | NATS opt-in via flag; AsyncioEventBus default; testcontainers-based integration tests |
| JAX install issues | Avoided | Pure NumPy + Pure-Python paths; no JAX dependency |
| LLM cost escalation | Mitigated | `InMemoryCostTracker` + daily budget cap + 80%-threshold alert; sleep-mode suppresses LLM calls |
| Governance too restrictive | Mitigated | Configurable YAML constitution; `min_provenance_similarity ≤ 0` disables provenance |
| Memory hallucination persists | Mitigated | Retrieval-first + double provenance check (centroid + max-member) + constitutional gate |
| Provider unavailable | Mitigated | Agno's `FallbackConfig` per agent; `build_fallback_models()` from settings |
| Prompt injection | Mitigated (Stage 17) | Spotlighting + datamarking + heuristic classifier (recursive Base64 decode) + constitutional policy |
| Over-engineering creep | Watched | Strict 3-layer contract: contracts → adapters → application; Null impl for every Protocol |

## Metrics (V3 §8.1) — current values vs V3 targets

| Metric | V3 target | Current status |
|--------|-----------|----------------|
| MTTDS | >24h | Falsifiable test H3 confirms no death spiral over 500 ticks under default config |
| Recovery time | <20 ticks from stress=0.8 | Falsifiable H1: <150 ticks from stress=0.5 (default `restoration_gain=0.3` is at edge of stability) |
| Memory provenance accuracy | >90% | `EmbeddingProvenanceTracker` enforces threshold 0.85; integration test verifies hallucinated recalls are filtered |
| Cross-session similarity | cosine >0.9 | Implemented via `restore_from_checkpoint` (Stage 4 integration test verifies round-trip) |
| Cost stability | ±20% | Per-tick token logging + per-agent breakdown in `InMemoryCostTracker.stats()` |
| Stimulus discrimination | cosine <0.7 | Tested implicitly via embedding diversity in tests |
| Narrative integrity | <5% contradictions | Cross-agent consistency: planning_input includes all upstream agent outputs; not currently measured |

## Open questions / deferred items

These were called out in V3 but not implemented in Stages 0-17:

- **Active inference / predictive setpoint** (V3 §3.1). Allostasis
  instead of homeostasis. Deferred.
- **Φ (IIT) measurement** (V3 §3.1). Computationally hard for
  non-trivial systems. We use the architectural ideas (differentiation
  + integration, exclusion axiom for clear agent boundaries) but
  don't compute Φ.
- **Skill library a la Voyager** (V3 §3.2) for emergent learned
  capabilities. We have a tool registry but no automatic skill
  discovery.
- **OCC / CPM for emotion classification** (V3 §3.3). We use a small
  set of emotions hand-coded into prompts; full appraisal models are
  deferred.
- **Visualization of internal state** (V3 §6, Rerun). Stage 7 wires
  `RerunLogger` but the dashboards beyond basic time series are
  deferred.

## When V3 is wrong

V3 is opinionated and was correct on every audit-finding we tested,
but it's an ambitious roadmap. **Keep deviating informed:** if you
choose a different design, document why in the commit message and
update this file.
