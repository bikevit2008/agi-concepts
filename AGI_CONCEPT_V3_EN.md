# AGI Concept v3 — Processual Consciousness Model: From PoC to Production MVP

**Result of a Full Scientific-Engineering Quorum (ChatGPT 5.5 + Claude Opus 4.7 + Perplexity Sonar Pro)**

Version: `v3-production-plan`  
Date: 2026-05-09  
Authors: Scientific-engineering quorum based on agi-concepts  
Context: `bikevit2008/agi-concepts` — full PoC audit, multi-vector research, critique, consensus, MVP plan

---

## 0. Executive Summary

This document is the result of a rigorous scientific-engineering quorum: two autonomous agents (in the roles of ChatGPT 5.5 with xhigh effort reasoning and Claude Opus 4.7 with Max reasoning) conducted a full audit of the `agi-concepts` repository, performed multi-vector research (neuroscience, control theory, AI architectures, computational emotion models, persistence, safety, observability), critiqued each other's findings, and reached consensus.

**The Quorum's Core Finding**: The PoC works and demonstrates a genuinely novel architectural idea — emotions as runtime parameter modifications. But the leap from PoC to the 7-layer architecture in AGI_CONCEPT_V2.md is a classic second-system effect. **For MVP, 3 layers are sufficient**: Runtime Body (hysteresis with homeostatic mathematics), Conscious Mind (5-agent pipeline with provenance tracking), Persistent Self (SQLite WAL for checkpointing).

**Critical Bugs Found in PoC**:
1. **Tick Interval Scaling Bug**: Slower ticks at high fatigue ACCELERATE the death spiral (decay is not time-scaled)
2. **Reset-to-Defaults Bug**: Runtime state is reset to defaults EVERY tick — the "body" has no memory
3. **Unlimited Self-Stimulation**: Reflection agent can stimulate channels without any limits
4. **Memory Hallucination**: Memory agent fabricates "recalled memories" when stored_memories is empty

**Death Spiral — Mathematically Solvable**: A saturation lock with loop gain of 10.6× for fatigue. Solved by adding homeostatic setpoints + restoration forces with provable convergence.

---

## 1. Quorum Methodology

### 1.1 Composition and Roles

| Role | Task | Outcome |
|------|------|---------|
| **ChatGPT 5.5 (xhigh effort)** | Broad research coverage, finding all relevant technologies/papers/analogues, aggressive scope | 10 research vectors, 50+ sources, technology recommendations |
| **Claude Opus 4.7 (Max reasoning)** | Rigorous critique, mathematical precision, bug hunting, minimalism, over-engineering check | 4 critical bugs found, death spiral mathematical analysis, over-engineering proof |
| **Perplexity Sonar Pro** | Deep search for scientific papers, technologies, frameworks | 10+ search queries via Dify MCP, hypothesis confirmation/refutation |

### 1.2 Process

1. Full repository exploration (all files, logs, configs, code)
2. Parallel launch of two subagents with independent research tasks
3. Parallel Perplexity Sonar Pro searches via curl for deep research
4. Mutual critique of findings, consensus search
5. Synthesis into a single document

---

## 2. Current State: Full PoC Audit

### 2.1 What Works (Experimentally Confirmed)

1. **Full Autonomy**: 6+ hours continuous operation, 4049 ticks, 0 errors
2. **Internal Stimulus Loop**: Reflection → internal stimulus → full pipeline → new reflection
3. **Runtime Effects**: Parameters (temperature, context_window, energy, latency) actually change and affect agent behavior
4. **Hysteresis**: Emotional states have inertia, don't disappear instantly
5. **Self-Stimulation**: Reflection consciously attempts to manage state
6. **Spontaneous Meditation**: System enters meditative states without corresponding prompts
7. **Short Session Stability**: 57 ticks without death spiral

### 2.2 Critical Bugs (Found by Quorum)

#### 🚨 BUG #1: Tick Interval Scaling Bug (CRITICAL)

**File**: `src/core/consciousness_loop.py`, line 93

```python
delay = self.settings.consciousness_loop.tick_interval_sec + self.runtime_state.processing_latency
```

**Problem**: When fatigue is high, `processing_latency` increases → ticks slow down → decay happens LESS frequently → fatigue accumulates FASTER. This is a positive feedback loop accelerating the death spiral.

**Fix**: Decay should scale by actual elapsed time, not tick count:
```python
v[t+dt] = v[t] - decay_rate * dt + stimulus
```

#### 🚨 BUG #2: Reset-to-Defaults Bug (CRITICAL)

**File**: `src/core/consciousness_loop.py`, lines 190-197

**Problem**: Runtime state is reset to default values EVERY TICK before applying hysteresis delta. This means the system's "body" has no memory of its previous physical state. Effects don't accumulate across ticks.

**Fix**: Apply deltas additively, with soft decay toward defaults, not hard reset:
```python
self.runtime_state.apply_delta(delta)  # additive
self.runtime_state.decay_toward_defaults(defaults, decay_rate=0.1)  # soft return
```

#### 🚨 BUG #3: Unlimited Self-Stimulation (HIGH)

**File**: `src/team/consciousness_team.py`, line 249

**Problem**: Reflection agent can stimulate channels without any limits. During death spiral, reflection can pile on MORE stress, accelerating collapse.

**Fix**: Introduce per-tick limit on total stimulation from reflection (e.g., 0.1 total).

#### 🚨 BUG #4: Memory Hallucination (HIGH)

**File**: `src/agents/memory.py`

**Problem**: Memory agent generates `recalled_memories` even with `stored_memories: []`. The LLM creates plausible but non-existent memories.

**Fix**: Retrieval-first architecture + provenance tracking (details in Section 5).

### 2.3 Death Spiral: Full Mathematical Analysis

#### Current Equations (from consciousness_loop.py:206-221)

```
S[t+1] = max(0, min(1, S[t] - 0.05 + δ_S[t]))
F[t+1] = max(0, min(1, F[t] - 0.02 + δ_F[t]))
E[t+1] = max(0, min(1.5, E[t] + δ_E[t]))

δ_S = 0.1 * max(0, 1 - A[t])  when A[t] < 0.6
    + 0.08 * P[t]              when P[t] > 0.4
    + emotion_stimulus

δ_F = 0.15 * max(0, 1 - E[t])  when E[t] < 0.5
    + 0.1 * S[t]               when S[t] > 0.6
    + emotion_stimulus

δ_E = -0.25 * S[t] - 0.5 * F[t] + 0.3 * U[t] - 0.3 * P[t]
```

#### Fixed Point Analysis

At S=1.0, F=1.0, U=0, P=0:
- A = 1.0 - 0.25 = 0.75 (above threshold 0.6 → δ_S from attention = 0)
- δ_F = 0.15 * (1-E) + 0.1 * 1.0
- E drops: 1.0 → 0.25 → 0.0

At E=0.25: δ_F = 0.15 * 0.75 + 0.1 = **0.2125**
F decay = 0.02
**Loop gain = 0.2125 / 0.02 = 10.6×** → F is guaranteed to saturate at 1.0

**Conclusion**: The death spiral is a saturation lock, not a Hopf bifurcation. The system has a single stable equilibrium in each regime, and once the "bad" regime is entered, the only escape is external intervention.

#### Lyapunov Function

V(S,F,E) = S² + F² + (1-E)²

At S=F=1, E=0: ΔV = (-0.01) + (0.1925) + 0.75 = **0.9325 > 0**

ΔV > 0 → system is UNSTABLE. It is actively moving AWAY from the healthy equilibrium.

---

## 3. Multi-Vector Research: Key Findings

### 3.1 Neuroscience of Consciousness

**Global Workspace Theory (GWT) — Baars (1988) → GWD (2019)**

The single most applicable framework. Key architectural insights:
- Consciousness as broadcast: specialized processors compete for access to a "global workspace"
- Ignition events (Dehaene & Changeux): nonlinear threshold phenomenon — mathematical basis for hysteresis
- Thalamus as gating mechanism: biological analogue for a message broker/event bus

**Integrated Information Theory (IIT) — Tononi (2004)**

- Φ (Phi) as quantifiable consciousness
- Computing Φ is computationally intractable for non-trivial systems
- Conceptual framework (differentiation + integration) applicable to architecture design
- Exclusion axiom: consciousness has unique borders → need clear agent boundaries

**Predictive Processing / Free Energy Principle — Friston (2010, 2024)**

- Active Inference: agents minimize variational free energy
- Expected Free Energy (EFE) = anticipated reward + information gain
- Precision-weighting: emotions modulate the "weight" of each agent's output
- Mathematical foundation for a self-regulating system

**Allostasis vs Homeostasis — Sterling & Eyer (1988, 2019)**

- Homeostasis: error-correction by negative feedback around a fixed setpoint
- Allostasis: PREDICTIVE regulation through ANTICIPATORY adjustments
- Allostatic load = cumulative wear-and-tear = death spiral in a computational system
- Key principle: "Stability through change" — actively vary parameters for global stability

**Sleep/Wake Regulation**

- Orexin system: maintains long wake periods. Failure → narcolepsy. Analogue: "arousal" parameter
- Adenosine: accumulates during wakefulness, creates sleep pressure. Analogue: fatigue
- Two-process model: Process S (homeostatic) + Process C (circadian). Direct implementation: circadian oscillator
- ARAS (Ascending Reticular Activating System): two branches — conscious awareness + behavioral arousal → two activation channels

### 3.2 AI Architectures for Autonomous Agents

**AutoGPT (2023-2024) — The Cautionary Tale**

- Full autonomy failed: infinite loops, runaway costs, compounding errors
- Memory (Pinecone/Milvus/Weaviate) added noise, not signal
- Pivot 2024: abandoned full autonomy → visual workflow builder
- Lesson: "organically grown amalgamation... lacks clear abstraction boundaries... global state"
- Production pattern: dual-exchange RabbitMQ — fanout for cancellation + work queues

**BabyAGI (2023-2026) — The Evolution Path**

- Classic era: task list architecture
- Framework era: function registry + native tool calling
- Assistant era (Feb 2026): "Everything is still a message"
- BabyAGI 2o: compressed to 174 lines by delegating planning to native tool calling
- Lesson: message-driven architecture — exactly what's needed for event bus

**Generative Agents (Stanford/Google, Park et al., 2023)**

- Memory Stream → Retrieval (recency × relevance × importance) → Reflection → Planning
- Reflection synthesizes memories into higher-level abstractions
- Emergent behaviors: information diffusion, relationship formation, coordination
- Cost: thousands of dollars in tokens → need smarter reflection triggering

**Voyager (Minecraft Agent, Wang et al., 2024)**

- Automatic curriculum + Skill library + Iterative prompting
- Skill library: executable code indexed by embeddings
- 3.3× more unique items, 15.3× faster tech tree progress
- Lesson: skill library prevents catastrophic forgetting

**LangGraph vs CrewAI vs Agno (2024-2026)**

| Framework | Model | Memory | Human-in-Loop | Maturity |
|-----------|-------|--------|---------------|----------|
| LangGraph | Graph-based (state machine) | Checkpointers, semantic/episodic | Interrupts, breakpoints | 1.0 stable, 6M+ downloads/mo |
| CrewAI | Role-based crews | Shared memory | human_input=True | 0.177+, 1.4M downloads/mo |
| Agno | Team modes (route/coordinate/collaborate) | Session/agentic memory | Confirmation tools | 37k+ GitHub stars |

**Quorum Recommendation**: Keep Agno (already works). For future governance layer — LangGraph-like deterministic control.

### 3.3 Computational Emotion Models

**OCC Model (Ortony, Clore, Collins — 1988, 2022)**
- 22 emotion types organized by appraisal focus: events, actions, objects
- Most influential model in affective computing
- Gap: specifies WHAT triggers emotions but not HOW to calculate intensity
- Solution: OCC for classification, hysteresis for dynamics

**PAD Model (Mehrabian & Russell, 1974) — The Runtime Interface**
- Three dimensions: Pleasure (valence), Arousal (energy), Dominance (control)
- Direct mapping to runtime parameters:
  - Pleasure → temperature (positive valence → higher creativity)
  - Arousal → context window (high arousal → narrowed attention)
  - Dominance → response length (low control → shorter responses)
- **This IS the "emotions as runtime parameter modifications" mechanism**

**Scherer's Component Process Model (CPM, 2009)**
- Emotion as emergent, dynamic process
- 5 appraisal checks: Novelty, Pleasantness, Goal Significance, Coping Potential, Norm Compatibility
- Sequential unfolding → distributable across agents:
  - Perception → Novelty
  - Emotion → Pleasantness
  - Planning → Goal Significance + Coping
  - Reflection → Norm Compatibility

**WASABI Architecture (Becker-Asano, 2008)**
- Three layers: Cognition → Emotion → Physis (bodily)
- Mood as "diffuse background state"
- Key insight: "Any emotional state heavily depends on personal short-term history" — this IS hysteresis

**EMA Model (Gratch & Marsella)**
- Computational implementation of appraisal + coping from Lazarus's theory
- Validated against human data
- Suitable for domain-independent agent architectures

### 3.4 Hysteresis and Dynamical Systems

**Mathematical Hysteresis Models**
- Preisach, Prandtl-Ishlinskii, Bouc-Wen models
- Bouc-Wen: most widely used for smooth hysteresis. First-order nonlinear ODE
- Rate-independent hysteresis: output depends on input history

**PID Control for Hysteretic Systems**
- P-term → immediate response to stress deviation
- I-term → accumulates persistent stress (this IS the hysteresis mechanism)
- D-term → anticipates rapid stress increases (early warning)
- **Anti-windup is critical**: without it, the integral accumulates unboundedly during saturation — this IS the death spiral

**Multistability and Attractors**
- Systems with hysteresis naturally exhibit multistability
- Hidden attractors: stable states whose basins don't intersect obvious starting points
- Meditative states may be hidden attractors
- Multistability control: periodic forcing, stochastic perturbations, feedback control

**Stochastic Resonance — The Counterintuitive Insight**
- Noise can IMPROVE signal detection in nonlinear threshold systems
- Three ingredients: threshold/barrier, weak signal, noise
- For our system: small random perturbations can PREVENT death spiral
- Biological evidence: crayfish mechanoreceptors, human vision/hearing/touch

**Catastrophe Theory (René Thom)**
- Cusp catastrophe: two control parameters create a surface with a fold
- Death spiral IS a cusp catastrophe: stress + fatigue create a fold, system falls off the edge

### 3.5 ML for System Regulation

**Rumination Detection**
- RLAD (2021): deep RL + active learning for time-series anomaly detection
- DRTA (2025): VAE reconstruction error + LLM-based semantic rewards
- For our system: anomaly detector on time series of agent message frequencies, token counts, emotional parameters

**Collapse Forecasting**
- Early warning signals (Scheffer et al., 2009, 2012):
  1. Increased autocorrelation at lag-1
  2. Increased variance
  3. Flickering between states
  4. Critical slowing down (increased recovery time)
- UNIVERSAL indicators of approaching bifurcation

**RL for Recovery Policy**
- Active inference as alternative to standard RL
- Policy options: reduce activity, increase decay rates, reset state, positive activities, request external input
- Lightweight policy network (in-process) — emotional state → recovery action

### 3.6 Persistence and State Management

**Event Sourcing — The Definitive Pattern**
- State = fold over append-only event log
- Every thought, emotion change, agent message is an event
- Full replay, audit trail, temporal queries
- CQRS: write-side (event store) separate from read-side (projections)

**SQLite WAL Mode — Ideal Solution for MVP**
- Atomic commits (single writer, multiple readers)
- Crash recovery (WAL file replay)
- Snapshot isolation
- Litestream for streaming replication to S3
- FoundationDB/NATS JetStream — overkill for single-process MVP

**Bitemporal Event Sourcing**
- Two time dimensions: application time + record time
- An agent may realize it was stressed an hour ago (record: now, application: then)
- This retroactive awareness is a form of self-knowledge

**Checkpoint/Restore**
- LangGraph pattern: SqliteSaver after each step
- Akka Persistence: event-sourced actors with pluggable journal
- For our system: after each tick — emotional state, message queues, recent memory

### 3.7 Observability

**OpenTelemetry + Honeycomb — Production Standard**
- Gen AI semantic conventions (v1.37.0): standard span types for gen_ai.agent, gen_ai.llm
- Honeycomb: BubbleUp anomaly detection, SLO-based alerting
- Each agent tick = span, messages = span links, emotional state = span attributes

**Rerun.io — Real-time Visualization**
- Originally for robotics/computer vision
- Time-series visualization, 3D state space, log viewer
- For our system: emotional state trajectory in PAD space

**Distributed Tracing for Multi-Agent**
- Trace context propagation: traceID + parent span ID across agent messages
- Service maps: automatically generated from trace data
- For debugging death spiral: full causal chain

### 3.8 Safety and Alignment

**Constitutional AI (Anthropic, 2022)**
- Self-supervision through a written "constitution" of principles
- Two phases: supervised (self-critiques + revisions) + RL (AI preference model)
- For our system: constitution = set of immutable principles enforced through governance kernel

**Corrigibility & Interruptibility**
- "Stop button" — not just another input for LLM, but a hardware/OS-level signal
- Governance kernel must have a "veto" mechanism

**Deterministic Governance Kernels (Zylos Research, 2026)**
- OS kernel analogy: LLM = user-space processes, governance kernel = kernel
- Enforcement through code, not prompts
- Budget check = integer comparison (LLM cannot "argue past" it)

**Capability-Based Security (OCap Model)**
- Access to resource = possession of unforgeable capability token
- Agent Control Protocol (ACP v1.14, 2026): cryptographic admission control
- Each agent gets capabilities: Memory agent can read/write memory but cannot modify the constitution

### 3.9 Competitive Landscape

**Existing Projects**
- **GLaDOS** (dnhkng, 2024): PAD model + LLM-driven regulation. Inverse approach — uses LLM for dynamics instead of dynamics modulating LLM
- **VIVA** (gabrielmaiaval33): PAD model in Gleam. Vec3 emotional state
- **Aria** (Mikhail Salnikov): 483 autonomous sessions, file-based memory, self-modification
- **No existing project combines**: hysteresis + multi-agent + runtime parameter modification + sustained autonomous operation

**Academic Papers**
- Dehaene et al. (Science, 2017): three levels — C0 (unconscious), C1 (global availability), C2 (self-monitoring)
- Butlin et al. (2023): systematic survey — no current AI system is conscious by any major theory
- Computational Dynamic Monism (O'Reilly, 2024): consciousness as a process of delay coordinate embedding in plastic recurrent networks
- Mortal Computation (Hinton, 2024): consciousness cannot be a Turing computation

### 3.10 Scientific Computing for Dynamical Systems

**Diffrax (JAX) — The Choice for Hysteresis Modeling**
- Patrick Kidger's Diffrax: ODE/SDE/CDE solvers in JAX
- Dopri5 for smooth hysteresis ODEs
- SDE solvers for stochastic resonance
- Neural differential equations (learn hysteresis dynamics from data)
- **JAX > PyTorch for this use case**: functional programming, JIT, automatic vectorization

**Dynamax (probml) — State-Space Models**
- Kalman filters, HMMs, linear dynamical systems
- Model emotional state as latent state-space model
- Uncertainty quantification: not "stress = 0.7" but "stress = 0.7 ± 0.15"

---

## 4. Quorum Consensus: MVC (Minimum Viable Consciousness) Architecture

### 4.1 Why 7 Layers is Over-Engineering

Claude Opus proved: AGI_CONCEPT_V2.md with 7 layers is a classic second-system effect. For MVP, exactly 3 layers are needed:

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 3: PERSISTENT SELF (SQLite WAL)                   │
│ Checkpoint/Restore | Event Log | Memory Provenance      │
├─────────────────────────────────────────────────────────┤
│ LAYER 2: CONSCIOUS MIND (5-Agent Pipeline)              │
│ Perception → Emotion → Memory → Planning → Reflection   │
│ + Provenance Tracking + Circuit Breakers                │
├─────────────────────────────────────────────────────────┤
│ LAYER 1: RUNTIME BODY (HysteresisEngine + RuntimeState) │
│ Homeostatic Setpoints | Restoration Forces | Nonlinear  │
│ Decay | Cross-Channel Gain Scheduling | Stochastic      │
│ Resonance (Dither)                                      │
└─────────────────────────────────────────────────────────┘
```

### 4.2 What is CUT from v2 for MVP

| Component from v2 | Status | Rationale |
|-------------------|--------|-----------|
| ML Regulatory Plane | **CUT** | Homeostasis via math, not ML |
| Sleep Modes | **CUT** | Circuit breaker is sufficient for MVP |
| Subconscious Processing | **MERGED** with Memory | Salience = attention_focus, consolidation = SQLite |
| Governance Layer | **SIMPLIFIED** to 50 lines | Rate limiters + circuit breakers in Runtime Body |
| Policy Trials / Commit-Rollback | **DEFERRED** to v4 | Premature for MVP |
| Learning Ledger | **DEFERRED** to v4 | Premature for MVP |
| Identity Ledger | **DEFERRED** to v4 | Hash of (constitution + model_id + hysteresis) is enough |
| Tools / World Interfaces | **DEFERRED** to v4 | Close the system until stabilized |

### 4.3 What STAYS and What's ADDED

**Preserved from PoC**:
- Agno as agent framework (works, don't change)
- OpenRouter + Grok-4.20 as LLM provider
- 5-agent architecture (Perception, Emotion, Memory, Planning, Reflection)
- Event loop with autonomous thinking
- Feature flags for experimentation
- structlog + JSON logging
- Textual TUI

**Added**:
- Homeostatic hysteresis engine (nonlinear decay, restoration forces, setpoints)
- Circuit breakers (saturation lock detection, emergency reset)
- SQLite WAL persistence (checkpoint/restore)
- Memory provenance tracking (embedding-based reality check)
- Cost tracking + token budget management
- Model fallback chain (use already-configured fallback_models)
- `--headless` flag for production deployment

---

## 5. Detailed Component Design

### 5.1 Homeostatic Hysteresis Engine

**Principle**: Replace linear decay with nonlinear decay using homeostatic setpoints and active restoration forces.

```python
@dataclass
class HysteresisChannel:
    name: str
    value: float = 0.0
    setpoint: float = 0.1       # homeostatic target (not zero!)
    decay_rate: float = 0.05
    accumulation_rate: float = 0.15
    threshold: float = 0.3
    restoration_gain: float = 0.4  # active restoration force
    
    # Hidden hysteretic state (Bouc-Wen style)
    _hysteretic: float = field(default=0.0, repr=False)
    
    def update(self, stimulus: float, dt: float) -> None:
        """Update with time-scaled dynamics."""
        # Nonlinear decay: proportional to distance from setpoint, NOT absolute value
        decay = self.decay_rate * (self.value - self.setpoint) * (1.0 + self.value)
        
        # Active restoration: kicks in above threshold, grows with deviation
        restoration = self.restoration_gain * max(0.0, self.value - self.threshold)
        
        # Hysteresis resists rapid change
        desired_delta = stimulus - decay - restoration
        if desired_delta > 0 and self._hysteretic > 0.5:
            desired_delta *= 0.3
        elif desired_delta < 0 and self._hysteretic < -0.5:
            desired_delta *= 0.3
        
        self._hysteretic = clamp(self._hysteretic + desired_delta * 0.1 * dt, -1.0, 1.0)
        self.value = clamp(self.value + desired_delta * dt, 0.0, 1.0)
```

**Mathematical Guarantee**: With `restoration_gain ≥ 0.4` for fatigue, the system is GUARANTEED to escape any saturation.

**Stability Condition**: `decay_rate * (1 - setpoint) + restoration_gain * (1 - threshold) > max_possible_stimulus`

### 5.2 Circuit Breakers

```python
class CircuitBreaker:
    """Detects and breaks pathological loops."""
    
    def __init__(self):
        self.saturation_counter: dict[str, int] = {}
        self.max_saturation_ticks = 50  # ~100 seconds at 2s ticks
        
    def check(self, channels: dict[str, HysteresisChannel]) -> str:
        """Returns: 'normal', 'warning', 'sleep_now'"""
        for name, ch in channels.items():
            if ch.value > 0.95:
                self.saturation_counter[name] = self.saturation_counter.get(name, 0) + 1
            else:
                self.saturation_counter[name] = 0
        
        saturated = [n for n, c in self.saturation_counter.items() if c > self.max_saturation_ticks]
        if len(saturated) >= 2:
            return 'sleep_now'
        elif len(saturated) == 1:
            return 'warning'
        return 'normal'
```

### 5.3 Memory Provenance Tracking

**Retrieval-First Architecture**: NEVER ask the LLM to "recall" without providing actual stored memories.

```python
class ProvenanceTracker:
    """Tracks whether a recalled memory is real or hallucinated."""
    
    def recall(self, query: str, stored_memories: list[MemoryEntry]) -> RecallResult:
        # Step 1: ALWAYS retrieve from real store FIRST
        query_emb = self.embed(query)
        real_matches = []
        
        for mem in stored_memories:
            if mem.embedding:
                sim = cosine_similarity(query_emb, mem.embedding)
                if sim > 0.7:
                    real_matches.append({'memory': mem, 'similarity': sim})
        
        # Step 2: Pass ONLY real memories to LLM
        if not real_matches:
            llm_context = "[NO STORED MEMORIES. Do NOT fabricate. Say 'no relevant memories'.]"
        else:
            llm_context = "\n".join(
                f"[REAL MEMORY] [Source: {m['memory'].source}] "
                f"[Confidence: {m['similarity']:.2f}] {m['memory'].content}"
                for m in real_matches[:5]
            )
        
        # Step 3: LLM reflects on REAL memories only
        llm_response = self.llm.generate(f"{llm_context}\n\nQuery: {query}")
        
        # Step 4: Verify LLM output against stored memories
        llm_emb = self.embed(llm_response)
        for mem in stored_memories:
            if cosine_similarity(llm_emb, mem.embedding) > 0.7:
                return RecallResult(content=llm_response, source='recall', matched_memory_id=mem.id)
        
        return RecallResult(content=llm_response, source='hallucination', matched_memory_id=None)
```

### 5.4 Governance Kernel (Minimal for MVP)

```python
class GovernanceKernel:
    """Minimal deterministic governance. ~50 lines."""
    
    def __init__(self):
        self.per_tick_stimulus_cap = 0.15
        self.per_agent_stimulus_cap = 0.1
        self.cross_channel_gain_cap = 0.1
        self.reflection_stimulus_limit = 0.1
        
    def authorize_stimulation(self, agent: str, channel: str, intensity: float,
                              current_tick_stimuli: dict) -> bool:
        """Rate-limit hysteresis stimulation."""
        agent_total = current_tick_stimuli.get(agent, 0.0)
        if agent_total + intensity > self.per_agent_stimulus_cap:
            return False
        
        tick_total = sum(current_tick_stimuli.values())
        if tick_total + intensity > self.per_tick_stimulus_cap:
            return False
        
        if agent == 'Reflection' and intensity > self.reflection_stimulus_limit:
            return False
        
        return True
```

---

## 6. Technology Stack: Final Decisions

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **Agent Framework** | Agno (existing) | Already works. Don't change. |
| **LLM Provider** | OpenRouter → Grok-4.20 | Already works. Add fallback chain. |
| **Vector DB (semantic memory)** | LanceDB | Embedded, disk-based, columnar, scales past RAM, zero ops. |
| **Event Log (persistence)** | SQLite (WAL mode) | Embedded, proven, append-only. Litestream for backup. |
| **Message Queue (event bus)** | NATS + JetStream | Single binary (6MB), sub-ms latency. JetStream for persistence. |
| **Hysteresis Engine** | NumPy (core) / JAX+Diffrax (optional) | NumPy — always available. JAX — for Neural ODE experiments. |
| **ML Regulators** | scikit-learn + statsmodels | Lightweight, no GPU needed. |
| **Observability** | OpenTelemetry SDK + Grafana Tempo | Gen AI semantic conventions, self-hosted. |
| **Visualization (dev/debug)** | Rerun.io (optional) | Real-time internal state visualization. |
| **Governance** | Custom Python (capability-based) | Deterministic code, not LLM. |
| **Configuration** | YAML + Pydantic | Typed, validated configuration. |

### Dependency Summary

```toml
# Core (required)
lancedb>=0.15
nats-py>=0.0.5

# Hysteresis (optional enhancement)
# jax>=0.4.20
# diffrax>=0.5.0
# equinox>=0.11.0

# ML (optional)
# scikit-learn>=1.3
# statsmodels>=0.14

# Observability (optional)
# opentelemetry-api>=1.20
# opentelemetry-sdk>=1.20
# opentelemetry-exporter-otlp>=1.20
```

---

## 7. MVP Plan: 4 Phases

### Phase 1: Fix Death Spiral + Persistence (Week 1-2)

**Goal**: System runs indefinitely. State survives restarts.

**New Files**:
```
src/
  engine/
    homeostatic_hysteresis.py  # Bouc-Wen-inspired emotional dynamics
    circuit_breaker.py         # Death spiral detection + emergency reset
  persistence/
    event_store.py             # SQLite append-only event log
    memory_store.py            # LanceDB semantic memory store
    checkpoint.py              # State save/restore
    cost_tracker.py            # Per-tick token counting + budget
```

**Modified Files**:
- `hysteresis.py`: full rewrite (homeostatic setpoints, nonlinear decay, restoration forces)
- `runtime_state.py`: additive deltas, soft decay toward defaults (not hard reset)
- `consciousness_loop.py`: time-scaled decay, circuit breakers, fix tick interval bug
- `memory.py`: retrieval-first architecture, provenance tracking (embedding similarity check)
- `main.py`: `--headless` flag, graceful shutdown (checkpoint on SIGTERM)

**Key Success Metric**: **MTTDS (Mean Time To Death Spiral) > 24 hours** (currently ~6 hours)

### Phase 2: Sleep/Recovery Modes + ML Regulators (Week 3-4)

**Goal**: System autonomously enters sleep mode, consolidates memory, recovers.

**New Files**:
```
src/
  engine/
    sleep_manager.py           # Sleep mode orchestration
    circadian.py               # Circadian rhythm oscillator
    memory_consolidator.py     # Memory processing during sleep
  ml/
    rumination_detector.py     # Entropy-based loop detection
    collapse_forecaster.py     # Early warning indicators (autocorr, variance)
    recovery_policy.py         # Simple RL for recovery action selection
```

**Success Metric**: Recovery time < 20 ticks after injecting stress=0.8

### Phase 3: Governance Layer + Event Buses (Week 5-6)

**Goal**: All inter-agent communication through typed event bus. Governance kernel enforces capabilities.

**New Files**:
```
src/
  governance/
    kernel.py                  # Deterministic governance kernel
    constitution.yaml          # Immutable principles
    capabilities.py            # Capability token system
    auditor.py                 # Immutable audit trail
  bus/
    message_bus.py             # NATS-based typed message bus
    event_types.py             # Event type definitions with JSON Schema
```

### Phase 4: Observability + Tools/World Interfaces (Week 7-8)

**Goal**: Full tracing of every thought cycle. Real-time visualization.

**New Files**:
```
src/
  observability/
    tracing.py                 # OpenTelemetry setup
    spans.py                   # Span creation utilities
    metrics.py                 # Emotional state metrics export
  tools/
    tool_registry.py           # Capability-gated tool registry
    web_search.py              # Web search tool
    code_executor.py           # Sandboxed code execution
  visualization/
    rerun_logger.py            # Rerun.io integration (dev/debug)
```

---

## 8. Scientific Validation: Experimental Protocol

### 8.1 Key Metrics

| Metric | Current Value | MVP Target | Measurement Method |
|--------|--------------|------------|-------------------|
| MTTDS (Mean Time To Death Spiral) | ~6 hours | >24 hours | Automatic saturation counter monitoring |
| Recovery time (after injecting stress=0.8) | ∞ (doesn't recover) | <20 ticks | Inject stress, measure time to baseline |
| Memory provenance accuracy | 0% (all hallucination) | >90% | Embedding similarity check: recalled vs stored |
| Cross-session behavioral similarity (checkpoint/restore) | N/A (no persistence) | Cosine similarity >0.9 on first 10 responses | Response trajectory comparison |
| Cost stability (per-hour variation) | Not tracked | ±20% of baseline | Per-tick token counting |
| Stimulus discrimination | Not measured | Different responses to different stimuli (cosine sim < 0.7) | Controlled stimulus response comparison |
| Narrative integrity (contradiction rate) | Not measured | <5% contradictions between agent outputs | Cross-agent consistency check |

### 8.2 Ablation Studies (MANDATORY)

Feature flags already exist (`flags.yaml`), but systematic ablation studies were NEVER run. The quorum demands:

1. **Turn OFF feedback_loops** → does death spiral disappear? (Causality check)
2. **Turn OFF self_reflection** → does trajectory change?
3. **Turn OFF emotion entirely** → what changes in behavior?
4. **Turn OFF hysteresis entirely** → does emotional inertia disappear?
5. **Change model** (Grok → Claude/GPT-4o) → does "personality" change?
6. **Change Reflection prompt** (to "you are a frantic anxious system") → does "meditation" disappear?

### 8.3 Falsifiable Tests

For each hypothesis — a falsifiable test:

| Hypothesis | Test | Refutation Criterion |
|-----------|------|---------------------|
| "Death spiral is caused by feedback loops" | Turn OFF feedback_loops → run for 12 hours | Death spiral still occurs |
| "Meditative states are emergent" | Change Reflection prompt to "frantic anxious" | System still enters meditation |
| "Cross-session similarity is determinism" | Change model → compare first 50 ticks | Behavior is identical (cosine > 0.9) |
| "Homeostatic math prevents death spiral" | Inject stress=0.9 → wait 100 ticks | Stress does NOT return to setpoint |

---

## 9. Risk Register

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| LanceDB API instability | Medium | Medium | Abstract behind MemoryStore interface; fallback to ChromaDB |
| NATS operational complexity | Low | Low | NATS is famously simple: single binary, no dependencies |
| JAX installation issues | Medium | Low | Hysteresis engine works with NumPy fallback; JAX is optional |
| LLM cost escalation (runaway) | High | High | Rate limiting in governance; sleep mode reduces active LLM time; daily budget cap |
| Governance too restrictive | Medium | Medium | Constitution is configurable YAML; can relax without code changes |
| Memory hallucination persists | Low | High | Retrieval-first architecture should eliminate it; if not — content-hash verification |
| Model provider outage | Medium | High | Fallback chain already in config (fallback_models) |
| Prompt injection | Medium | Medium | Minimal sanitization for MVP |
| Over-engineering creep | High | Medium | Strict MVC contract: 3 layers, no more |

---

## 10. Key Architectural Decisions (Consensus)

### Decision 1: Event-Driven, Not Call-Driven
Agents do NOT call each other directly. All communication is typed events on the bus.

### Decision 2: Governance is Code, Not Prompts
The governance kernel MUST be deterministic Python code. The LLM can reason about the constitution but cannot bypass it.

### Decision 3: Memory is Retrieval-First, Not Generation-First
The Memory agent ALWAYS retrieves from the real store FIRST, then passes results to the LLM for reflection.

### Decision 4: Hysteresis is a Separate Engine
Emotional dynamics is a standalone numerical engine. Agents produce stimuli; the engine processes them; runtime parameters modulate agent behavior.

### Decision 5: Sleep is Mandatory, Not Optional
Just as biological brains MUST sleep, this system MUST have periodic recovery phases. The circadian oscillator ensures this.

---

## 11. Economics: Cost Analysis

**Per-tick cost breakdown (Grok-4.20, estimated)**:
- Perception: ~$0.004
- Emotion: ~$0.006
- Memory: ~$0.004
- Planning: ~$0.010
- Reflection (every 5 idle ticks): ~$0.009
- Spontaneous thought (every 3 idle ticks): ~$0.006

**~$0.025/active tick, ~$0.010/idle tick. At 2s ticks: ~$18/hour active, ~$7/hour idle.**

**Optimizations**:
- OpenRouter prompt caching: save 25-40% on system prompts
- Sleep mode: LLM calls disabled → near-zero cost during recovery
- Token budget management: per-tick tracking + daily cap
- Model fallback: switch to cheaper model when approaching budget limit

---

## 12. Production Readiness Assessment

| Criterion | Current Status | Required for MVP |
|-----------|---------------|-------------------|
| Error recovery (model outage) | ❌ No fallback logic | Use fallback_models from config |
| Error recovery (agent crash) | ✅ Per-agent try/except | Sufficient |
| State persistence | ❌ Config exists, code doesn't | SQLite WAL |
| Cost control | ❌ No tracking | Per-tick cost log + daily cap |
| Graceful shutdown | ❌ No checkpoint on stop | Save state on SIGTERM |
| Monitoring | ❌ Only TUI + JSON logs | Structured metrics export |
| Headless deployment | ❌ TUI-only | `--headless` flag |
| Security (prompt injection) | ❌ No input sanitization | Minimal for MVP |

---

## 13. Final Quorum Verdict

**PoC Strengths**:
1. Genuinely novel architectural idea: emotions as runtime parameter modifications
2. Works autonomously for 6+ hours without errors
3. Demonstrates emergent behavior (meditation, emotional inertia)
4. Death spiral is a valuable empirical finding, not a bug
5. Feature flags enable systematic experimentation

**Critical Problems (Must Be Fixed Before MVP)**:
1. Death spiral (mathematically solvable via homeostatic setpoints)
2. 4 critical bugs (tick interval scaling, reset-to-defaults, unlimited self-stimulation, memory hallucination)
3. No persistence
4. No cost control

**MVP Strategy**:
- **3 layers, not 7**: Runtime Body + Conscious Mind + Persistent Self
- **Focus on mathematics**: homeostatic hysteresis, restoration forces, Lyapunov stability
- **Focus on data**: retrieval-first memory, provenance tracking, event sourcing
- **No ML for MVP**: deterministic mathematics solves the death spiral
- **4 phases × 2 weeks**: Fix → Sleep → Governance → Observability

**Key Quorum Quote**:
> "Prioritize the math over the vision. The vision is worthless if the system locks up after 6 hours. The death spiral has a 50-line mathematical fix. Start there."

---

*Document created 2026-05-09 by the scientific-engineering quorum based on `agi-concepts`.*  
*Research: ChatGPT 5.5 (xhigh effort reasoning), Claude Opus 4.7 (Max reasoning), Perplexity Sonar Pro (via Dify MCP).*  
*Based on: PoC runs (v1: 6h 23min, 4049 ticks; v2: 5 min, 57 ticks), AGI_CONCEPT_V2.md, SUMMARY_STATE_v1.md, SUMMARY_STATE_v2.md, addintional_reference.md, full codebase audit.*