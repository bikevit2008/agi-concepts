from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModelSettings:
    provider: str = "openrouter"
    id: str = "x-ai/grok-4.20"
    fallback_models: List[str] = field(
        default_factory=lambda: ["anthropic/claude-sonnet-4-20250514", "openai/gpt-4o"]
    )


@dataclass
class RuntimeDefaults:
    temperature: float = 0.7
    context_window: int = 32768
    processing_latency: float = 0.0
    bandwidth: float = 1.0
    attention_focus: float = 1.0
    energy_level: float = 1.0


@dataclass
class HysteresisParams:
    decay_rate: float = 0.05
    accumulation_rate: float = 0.15
    threshold: float = 0.3
    setpoint: float = 0.1
    restoration_gain: float = 0.4


@dataclass
class HysteresisSettings:
    stress: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.05, 0.15, 0.3, 0.1, 0.3))
    euphoria: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.08, 0.12, 0.4, 0.15, 0.35))
    fatigue: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.02, 0.10, 0.5, 0.1, 0.4))
    pain: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.10, 0.20, 0.2, 0.05, 0.5))


@dataclass
class LoopSettings:
    tick_interval_sec: float = 2.0
    max_idle_ticks: int = 50


@dataclass
class LoggingSettings:
    level: str = "INFO"
    json_dir: str = "logs"
    console_enabled: bool = True


@dataclass
class DbSettings:
    path: str = "data/consciousness.db"


@dataclass
class GovernanceSettings:
    """Stage 3 — deterministic stimulation policy.

    Stage 11 — constitutional auditor (path + toggle).
    """

    per_tick_stimulus_cap: float = 0.3
    per_agent_stimulus_cap: float = 0.2
    reflection_self_stim_cap: float = 0.1
    enforce_circuit_breaker: bool = True
    constitution_path: str = "config/constitution.yaml"


@dataclass
class CircuitBreakerSettings:
    """Stage 3 — saturation lock detection."""

    saturation_threshold: float = 0.95
    trip_after_ticks: int = 50
    reset_below: float = 0.7


@dataclass
class PersistenceSettings:
    """Stage 4 — SQLite WAL event log + checkpoint."""

    enabled: bool = True
    event_store_path: str = "data/events.db"
    checkpoint_path: str = "data/checkpoints.db"
    checkpoint_every_ticks: int = 50  # full snapshot frequency
    wal_checkpoint_every_seconds: float = 300.0  # PRAGMA wal_checkpoint(RESTART)
    keep_last_n_snapshots: int = 20  # prune older snapshots


@dataclass
class MemorySettings:
    """Stage 5 — vector memory store + provenance tracking."""

    enabled: bool = True
    backend: str = "lancedb"  # "lancedb" | "in_memory"
    lancedb_uri: str = "data/memories.lance"
    table_name: str = "memories"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_provider: str = "sentence-transformers"  # "sentence-transformers" | "openai"
    real_threshold: float = 0.85  # cosine sim ≥ this => REAL
    uncertain_threshold: float = 0.65  # cosine sim ≥ this and < real => UNCERTAIN
    max_results: int = 5


@dataclass
class CostSettings:
    """Stage 6 — token + USD tracking, daily cap."""

    enabled: bool = True
    daily_budget_usd: float = 5.0
    alert_threshold_pct: float = 0.8
    log_every_record: bool = False


@dataclass
class ObservabilitySettings:
    """Stage 7 — OpenTelemetry + Rerun.io."""

    enabled: bool = False  # off by default — opt-in
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "agi-consciousness"
    rerun_enabled: bool = False
    rerun_application_id: str = "consciousness"
    rerun_spawn: bool = True


@dataclass
class BusSettings:
    """Stage 8 — NATS JetStream."""

    enabled: bool = False  # off by default — uses asyncio bus
    nats_url: str = "nats://localhost:4222"
    stream_name: str = "consciousness"
    durable_consumer: str = "consciousness-loop"
    schema_validation: bool = True


@dataclass
class SleepSettings:
    """Stage 9 — circadian rhythm + sleep mode.

    Stage 15 — LLM REM-consolidation knobs.
    """

    enabled: bool = False  # off by default — opt-in
    awake_seconds: float = 4 * 3600.0  # 4 hours awake
    sleep_seconds: float = 1 * 3600.0  # 1 hour sleep
    pressure_to_sleep_threshold: float = 0.7
    pressure_to_wake_threshold: float = 0.2
    nrem_fraction: float = 0.7  # of sleep time spent in NREM
    suppress_llm_during_sleep: bool = True
    # LLM consolidation
    rem_min_cluster_size: int = 3
    rem_max_clusters_per_cycle: int = 5
    rem_min_provenance_similarity: float = 0.4
    rem_dedup_theme_ttl_seconds: float = 300.0
    rem_clusterer_backend: str = "hdbscan"  # "hdbscan" | "density_fallback"


@dataclass
class MLRegulatorsSettings:
    """Stage 12 — rumination detector + collapse forecaster + recovery policy."""

    enabled: bool = False
    # Rumination
    rumination_window: int = 30
    rumination_warn_threshold: float = 0.8  # bits
    rumination_crit_threshold: float = 0.3
    # Collapse
    collapse_window: int = 50
    collapse_trend_history: int = 20
    collapse_ar1_warn_threshold: float = 0.6
    collapse_variance_warn_threshold: float = 0.1
    collapse_slope_warn_threshold: float = 0.01
    # Recovery policy
    calm_intensity: float = 0.15
    alert_on_info: bool = True


@dataclass
class GoalStackSettings:
    """Stage 29 — persistent intentions / goal stack."""

    max_active_goals: int = 5
    stale_after_ticks: int = 50
    block_after_failures: int = 3
    abandon_after_failures: int = 6
    pressure_stress_threshold: float = 0.9
    pressure_blocks_below_priority: float = 0.4
    # Stage 30 — active goal pursuit
    pursuit_min_idle_ticks: int = 2
    pursuit_min_ticks_between_attempts: int = 6
    pursuit_progress_stale_after_ticks: int = 8
    pursuit_max_attempts_per_goal: int = 20
    pursuit_pause_stress_threshold: float = 0.92
    pursuit_pause_low_priority_below: float = 0.5


@dataclass
class ToolsSettings:
    """Stage 10 — capability-gated tool registry."""

    enabled: bool = False  # off by default — opt-in
    audit_log_path: str = "data/tool_audit.jsonl"
    web_search_enabled: bool = False
    code_executor_enabled: bool = False
    code_executor_backend: str = "subprocess"  # "subprocess" | "e2b" | "nsjail"


@dataclass
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    runtime_state: RuntimeDefaults = field(default_factory=RuntimeDefaults)
    hysteresis: HysteresisSettings = field(default_factory=HysteresisSettings)
    consciousness_loop: LoopSettings = field(default_factory=LoopSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    db: DbSettings = field(default_factory=DbSettings)
    governance: GovernanceSettings = field(default_factory=GovernanceSettings)
    circuit_breaker: CircuitBreakerSettings = field(default_factory=CircuitBreakerSettings)
    persistence: PersistenceSettings = field(default_factory=PersistenceSettings)
    memory: MemorySettings = field(default_factory=MemorySettings)
    cost: CostSettings = field(default_factory=CostSettings)
    observability: ObservabilitySettings = field(default_factory=ObservabilitySettings)
    bus: BusSettings = field(default_factory=BusSettings)
    sleep: SleepSettings = field(default_factory=SleepSettings)
    tools: ToolsSettings = field(default_factory=ToolsSettings)
    ml_regulators: MLRegulatorsSettings = field(default_factory=MLRegulatorsSettings)
    goal_stack: GoalStackSettings = field(default_factory=GoalStackSettings)
