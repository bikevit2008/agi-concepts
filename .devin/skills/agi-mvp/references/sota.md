# SOTA reference (as of May 2026)

Per-subsystem references. Use this when deciding whether to upgrade an
implementation; cross-check that the prior art still represents the
state of the art.

## Hysteresis engine (Stage 2)

- **Bouc–Wen** family of hysteretic models — basis for the
  `HomeostaticHysteresisEngine`. Setpoint + nonlinear decay
  `decay_rate · (value − setpoint) · (1 + value)` + active restoration
  above threshold guarantee escape from saturation.
- Stability condition (V3 Section 2.3):
  `2·decay_rate·(1−setpoint) + restoration_gain·(1−threshold) > max_stim`.
  Default `stress.restoration_gain=0.3` is right at the edge — a
  one-shot 0.9 injection takes >100 ticks to recover. To make it
  robust, raise to 0.5+.
- **Fluxgate** + **Allostasis vs Homeostasis** (Sterling & Eyer):
  inspiration for predictive setpoint adjustment (deferred — Phase 2).

## Governance (Stages 3, 11)

- **Constitutional AI** + **Generate-critique-refine** (Anthropic 2022).
- **OPA / Cedar** for declarative policies. We chose YAML-loaded policies
  + pure-Python check functions (no Rego dependency).
- **OWASP LLM01:2025** — prompt injection #1 risk for agentic systems.
- **dify-search 2026 brief on Constitutional AI**: critical/high → DENY,
  medium → WARN, low → ALLOW. We follow this exactly.

## Persistence (Stage 4)

- **SQLite WAL mode** (`PRAGMA journal_mode=WAL`): ~3.6k writes/s,
  70k reads/s on commodity hardware. With `synchronous=NORMAL` durability
  is acceptable; with `synchronous=FULL` it's bullet-proof but slower.
- **Litestream** (deferred): continuous backup of SQLite to S3.
- **Apache Arrow** ↔ **DuckDB** (deferred): if event log grows past
  ~10M rows, migrate to columnar.

## Memory + provenance (Stages 5, 15)

- **Generative Agents** (Park et al. 2023): episodic→semantic via
  reflection synthesis with importance + relevance + recency scores.
- **MemGPT** (Packer et al. 2023; now Letta): tiered main/recall/archival.
- **HippoRAG** (Gutierrez et al. 2024, OSU): hippocampus-inspired RAG
  with graph reasoning. We don't yet build cross-cluster graphs.
- **A-MEM** (Xu et al., NeurIPS 2024): agentic memory critique →
  guidance loop.
- **Mem0** (mem0ai/mem0): production memory layer with priority +
  dynamic forgetting; LOCOMO benchmark winner. Our
  `LlmMemoryConsolidator` is the closest analogue.
- **HDBSCAN** (Campello et al. 2013) — best for sub-1000 doc semantic
  clusters per dify-search 2026. We use precomputed cosine distance
  matrix to avoid version-sensitive `metric='cosine'` arguments.
- **BAAI/bge-small-en-v1.5** as the default embedder: 384-d, ~30MB,
  good multilingual tolerance.
- **HashingEmbedder** (custom): deterministic SHA-1+MD5-sign hashing
  bigrams + L2-normalize. Used as fallback / for tests. Discrimination
  between near-duplicates is around 0.7-0.95 cosine similarity.

## Cost + fallback (Stage 6)

- **Agno's `FallbackConfig`** (Agno >= 2.5): `on_error`, `on_rate_limit`,
  `on_context_overflow`. We use it through agent factories with
  `build_fallback_models()`.
- **OpenRouter** prompt caching: 25-40% savings on system prompts —
  we don't enable explicitly yet, but the call sites are ready.
- **Daily budget cap + alert threshold** (Generative Agents pattern):
  `InMemoryCostTracker.alert_threshold_pct` triggers a one-time
  warning at 80% of budget.

## Observability (Stage 7)

- **OpenTelemetry GenAI semantic conventions** (in development as of
  2025-2026). Span attributes: `gen_ai.system`, `gen_ai.request.model`,
  `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`.
  `gen_ai.system="openrouter"` is the default in `OtelObservabilityCollector`.
- **Tempo** (Grafana) for traces; **Prometheus** for metrics; **Grafana**
  for dashboards. Bundle in `deploy/observability/`.
- **Rerun.io** for real-time visualization of internal state during
  development.

## Bus (Stage 8)

- **NATS JetStream** (nats-py >= 2.11): durable, replayable, fast.
  Per dify-search SOTA: best for typed event buses with JSON Schema
  validation in 2026. Beats Redis Streams (no native multi-tenancy)
  and Kafka (heavier ops).

## Sleep mode (Stage 9)

- **Two-Process Model of sleep regulation** (Borbély 1982):
  Process S (homeostatic sleep pressure) + Process C (circadian
  alerting signal). Implemented exactly as described in
  `src/engine/circadian.py`.
- **NREM/REM cycling** at ~90-minute mammalian periodicity.
- **Hebbian memory consolidation** (Diekelmann & Born 2010): co-active
  memories strengthen during NREM. Our pair-shared-emotion logic in
  `HebbianMemoryConsolidator` mirrors this at MVP fidelity.
- **REM-phase abstraction generation** via LLM reflection (Stage 15) —
  the Generative-Agents pattern fits this perfectly.

## ML regulators (Stage 12)

- **Critical Slowing Down** (Scheffer 2009): rising lag-1 autocorrelation
  + variance + trend slope flag approaching tipping points. Implemented
  exactly in `CsdCollapseForecaster`.
- **Shannon entropy on categorical state** for rumination detection
  (we use it on the primary_emotion stream).
- **Conservative Q-Learning (CQL)** + **Implicit Q-Learning (IQL)**
  are the SOTA offline-RL choices for small (≤10k transitions)
  discrete-action datasets per dify-search 2026. We use Behavior
  Cloning as a baseline; upgrade once the dataset grows.

## Tools (Stage 10) + injection defense (Stage 17)

- **OAuth 2.0 Token Exchange (RFC 8693)** + **DPoP** (RFC 9449) for
  capability tokens. We have placeholder support; full token issuer +
  verifier are out of MVP scope.
- **nsjail** vs **E2B** vs **subprocess** for sandboxed code execution.
  Our `CodeExecutorTool` supports all three; default is subprocess
  (trusted code only — no security boundary).
- **Hines 2024 spotlighting** + **Chen 2024 StruQ** for prompt
  injection. Our `spotlight()` and `datamark()` implement the data-only
  delimiter pattern.
- **Meta Prompt Guard 2** (86M / 22M params) — best ML classifier in
  the space (81% APR at 3% utility loss). Currently we use a
  heuristic deterministic classifier with recursive Base64 decoding;
  Prompt Guard 2 is the next upgrade.

## Offline RL (Stage 16)

- **d3rlpy** library for production CQL/IQL. Currently we have only
  Behavior Cloning via numpy. Upgrade once we have ≥10k transitions
  with explicit rewards.
- **OfflineRL-Kit** as a pure-PyTorch alternative.

## What's next (post-Stage 17)

In rough priority order:

1. **Sender-bound capability tokens** (DPoP) for tools.
2. **Meta Prompt Guard 2** wrapper for `InjectionClassifier` (replace
   the heuristic classifier as primary; keep heuristic as cheap pre-filter).
3. **Cross-cluster graph abstraction** (HippoRAG-style) on top of
   REM clusters.
4. **CQL/IQL** offline-RL replacement for BC once dataset is large.
5. **Active inference** (Friston): predictive setpoint adjustment for
   the homeostatic engine. Allostasis instead of homeostasis.
6. **Distributed deployments**: NatsEventBus instead of AsyncioEventBus,
   PostgreSQL for shared event store, multiple consciousness instances
   sharing memory.
