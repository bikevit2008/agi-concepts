---
name: agi-mvp
description: Guidance for evolving the agi-concepts AGI MVP — architectural principles, SOTA techniques used, testing patterns, and known pitfalls accumulated across Stages 0-17. Invoke when extending the consciousness loop, adding subsystems, or running new ablation/falsifiable experiments. The skill captures hard-won knowledge so a future Devin (or human) doesn't repeat the same investigations.
---

# AGI MVP Skill

## Purpose

This skill contains the institutional knowledge of the `agi-concepts`
project after 17 stages of incremental hardening: architectural
principles, the SOTA references that informed each subsystem, the
testing patterns that work, and the gotchas that bit us along the way.

Use it whenever you're about to:

- Add a new subsystem to the consciousness loop (always start with a
  Protocol contract + Null implementation; see
  [references/architecture.md](references/architecture.md)).
- Replace an existing implementation with a more SOTA one (consult
  [references/sota.md](references/sota.md) for what's already been tried).
- Write tests that exercise the loop's hot path (read
  [references/testing.md](references/testing.md) — `simulated_time` is
  load-bearing).
- Investigate why an experiment behaves unexpectedly (cross-check
  [references/gotchas.md](references/gotchas.md) before assuming a bug).

## Hard rules

1. **Contracts before implementation.** Every new subsystem MUST start
   in `src/contracts/` as a `typing.Protocol` + a `NullX` no-op
   implementation. Concrete classes live in their own module
   (`src/{persistence,governance,engine,...}/`). The loop only depends
   on the contract.

2. **Fail-soft, never fail-hard.** Any persistence/network/LLM error
   inside `_tick_inner` must be caught and logged, never raised. The
   consciousness loop is the heartbeat; it must not stop because Tempo
   is down or LanceDB is locked.

3. **Governance gate everything that mutates hysteresis.** Don't call
   `hysteresis.stimulate()` directly from agents — go through
   `gated_stimulate()` (loop) or `_gated_stimulate()` (team) so the
   `IGovernanceKernel` can enforce per-tick / per-agent / reflection
   caps + the `IConstitutionalAuditor`.

4. **Negative stimulation is always allowed.** Self-soothing
   (negative intensity) bypasses governance caps. Don't gate it — that
   would prevent recovery during a saturation episode.

5. **Use `simulated_time=True` in test harnesses.** Real wall-clock is
   too fast in tests; without simulated time `dt ≈ 0` and decay never
   fires. Already enabled by default in `LoopHarness.run`.

6. **Anti-hallucination for any LLM-produced memory.** REM
   abstractions go through `IProvenanceTracker` *and*
   `IConstitutionalAuditor`. New LLM-side outputs that get persisted
   must follow the same pattern — see
   `src/engine/llm_memory_consolidator.py`.

## Map of the territory

```
src/contracts/          all Protocols + Null impls
src/engine/             hysteresis, circuit breaker, sleep, memory consolidation, clusterer
src/governance/         deterministic kernel, constitution YAML, prompt injection
src/persistence/        SQLite event store, checkpoint, LanceDB memory, embedder, cost
src/observability/      OpenTelemetry collector
src/visualization/      Rerun.io
src/bus/                AsyncIO + NATS implementations of IEventBus
src/ml/                 rumination, collapse forecaster, recovery (rule + offline BC)
src/tools/              capability-gated tool registry, web_search, code_executor
src/experiments/        harness, metrics
src/agents/             Agno agents (perception, emotion, memory, planning, reflection,
                        reflection_consolidator)

config/                 YAML config files (default, flags, constitution)
scripts/                ablation, falsifiable, BC training CLIs
deploy/observability/   docker-compose stack: OTel + Tempo + Prometheus + Grafana

tests/                  337 tests as of Stage 17, including:
                        - unit tests per module
                        - tests/test_falsifiable.py — V3 hypotheses
                        - tests/test_ablations.py    — V3 ablation matrix
                        - tests/test_e2e.py           — full-stack scenarios
                        - tests/test_nats_bus_integration.py — testcontainers
```

## Decision tree for new work

```
new feature?
├── changes the loop's hot path?
│   ├── yes → must be Protocol + Null + concrete + tests + simulated_time harness test
│   └── no  → can be a CLI script in scripts/ or a deploy/-side artefact
├── pulls in a new heavy dependency?
│   ├── core (always-on) → only if essential (hdbscan, numpy)
│   └── optional (opt-in) → put in pyproject.toml [extra]
├── exposes a new policy?
│   └── add a check function in src/governance/checks.py, register a
│       constitutional policy in config/constitution.yaml, integration
│       test asserting DENY/WARN as appropriate
└── adds a tool?
    └── implement ITool, declare required_capability, add unit test;
        register in CapabilityGatedToolRegistry; consider injection
        risk and add corresponding constitutional policy.
```

## When to bump up SOTA

- ML regulators currently use rule-based recovery + Behavior Cloning.
  CQL/IQL upgrade is justified once we have ≥10k logged transitions
  and explicit reward labels (not synthesised). See
  [references/sota.md](references/sota.md#offline-rl).
- Prompt injection classifier is heuristic. Plug Meta Prompt Guard 2
  (≈86M params) when the deployment can afford the latency budget.

## References

- [references/architecture.md](references/architecture.md): contract layer,
  dependency graph, integration points.
- [references/sota.md](references/sota.md): paper / repo references for
  every subsystem.
- [references/testing.md](references/testing.md): harness patterns,
  ablation methodology, falsifiable templates.
- [references/gotchas.md](references/gotchas.md): bugs and tricky
  details we already paid for.
- [references/v3-source.md](references/v3-source.md): traceability —
  which V3 audit decision drove which stage.
