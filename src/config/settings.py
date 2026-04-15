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


@dataclass
class HysteresisSettings:
    stress: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.05, 0.15, 0.3))
    euphoria: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.08, 0.12, 0.4))
    fatigue: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.02, 0.10, 0.5))
    pain: HysteresisParams = field(default_factory=lambda: HysteresisParams(0.10, 0.20, 0.2))


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
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    runtime_state: RuntimeDefaults = field(default_factory=RuntimeDefaults)
    hysteresis: HysteresisSettings = field(default_factory=HysteresisSettings)
    consciousness_loop: LoopSettings = field(default_factory=LoopSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    db: DbSettings = field(default_factory=DbSettings)
