from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Type, TypeVar

import yaml

from src.config.flags import FeatureFlags
from src.config.settings import (
    BusSettings,
    CircuitBreakerSettings,
    CostSettings,
    DbSettings,
    GovernanceSettings,
    GoalStackSettings,
    HysteresisParams,
    HysteresisSettings,
    LoggingSettings,
    LoopSettings,
    LearningSettings,
    MemorySettings,
    MLRegulatorsSettings,
    ModelSettings,
    ObservabilitySettings,
    PersistenceSettings,
    RuntimeDefaults,
    Settings,
    SharedSessionSettings,
    SleepSettings,
    TaskLedgerSettings,
    ToolsSettings,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


T = TypeVar("T")


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _build_dataclass(cls: Type[T], data: Dict[str, Any]) -> T:
    """Build a dataclass instance, only passing fields it knows about.

    Unknown YAML keys are silently dropped so old configs keep working
    when new fields are added.
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls!r} is not a dataclass")
    valid = {fld.name for fld in fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid}
    return cls(**filtered)  # type: ignore[arg-type]


def _build_hysteresis_params(data: Dict[str, Any]) -> HysteresisParams:
    return HysteresisParams(
        decay_rate=data.get("decay_rate", 0.05),
        accumulation_rate=data.get("accumulation_rate", 0.15),
        threshold=data.get("threshold", 0.3),
        setpoint=data.get("setpoint", 0.1),
        restoration_gain=data.get("restoration_gain", 0.4),
    )


def load_settings(config_dir: Path | None = None) -> Settings:
    cfg_dir = config_dir or CONFIG_DIR
    data = _load_yaml(cfg_dir / "default.yaml")

    model_data = data.get("model", {})
    model = ModelSettings(
        provider=model_data.get("provider", "openrouter"),
        id=model_data.get("id", "anthropic/claude-sonnet-4-20250514"),
        fallback_models=model_data.get("fallback_models", []),
    )

    rt_data = data.get("runtime_state", {})
    runtime = _build_dataclass(RuntimeDefaults, rt_data)

    hyst_data = data.get("hysteresis", {})
    hysteresis = HysteresisSettings(
        stress=_build_hysteresis_params(hyst_data.get("stress", {})),
        euphoria=_build_hysteresis_params(hyst_data.get("euphoria", {})),
        fatigue=_build_hysteresis_params(hyst_data.get("fatigue", {})),
        pain=_build_hysteresis_params(hyst_data.get("pain", {})),
    )

    loop = _build_dataclass(LoopSettings, data.get("consciousness_loop", {}))
    logging_settings = _build_dataclass(LoggingSettings, data.get("logging", {}))
    db = _build_dataclass(DbSettings, data.get("db", {}))

    governance = _build_dataclass(GovernanceSettings, data.get("governance", {}))
    circuit_breaker = _build_dataclass(CircuitBreakerSettings, data.get("circuit_breaker", {}))
    persistence = _build_dataclass(PersistenceSettings, data.get("persistence", {}))
    memory = _build_dataclass(MemorySettings, data.get("memory", {}))
    cost = _build_dataclass(CostSettings, data.get("cost", {}))
    observability = _build_dataclass(ObservabilitySettings, data.get("observability", {}))
    bus = _build_dataclass(BusSettings, data.get("bus", {}))
    sleep = _build_dataclass(SleepSettings, data.get("sleep", {}))
    tools = _build_dataclass(ToolsSettings, data.get("tools", {}))
    ml_regulators = _build_dataclass(
        MLRegulatorsSettings, data.get("ml_regulators", {})
    )
    goal_stack = _build_dataclass(GoalStackSettings, data.get("goal_stack", {}))
    learning = _build_dataclass(LearningSettings, data.get("learning", {}))
    shared_session = _build_dataclass(
        SharedSessionSettings,
        data.get("shared_session", {}),
    )
    task_ledger = _build_dataclass(TaskLedgerSettings, data.get("task_ledger", {}))

    return Settings(
        model=model,
        runtime_state=runtime,
        hysteresis=hysteresis,
        consciousness_loop=loop,
        logging=logging_settings,
        db=db,
        governance=governance,
        circuit_breaker=circuit_breaker,
        persistence=persistence,
        memory=memory,
        cost=cost,
        observability=observability,
        bus=bus,
        sleep=sleep,
        tools=tools,
        ml_regulators=ml_regulators,
        goal_stack=goal_stack,
        learning=learning,
        shared_session=shared_session,
        task_ledger=task_ledger,
    )


def load_flags(config_dir: Path | None = None) -> FeatureFlags:
    cfg_dir = config_dir or CONFIG_DIR
    return FeatureFlags.from_yaml(cfg_dir / "flags.yaml")
