from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from src.config.flags import FeatureFlags
from src.config.settings import (
    DbSettings,
    HysteresisParams,
    HysteresisSettings,
    LoggingSettings,
    LoopSettings,
    ModelSettings,
    RuntimeDefaults,
    Settings,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _build_hysteresis_params(data: Dict[str, Any]) -> HysteresisParams:
    return HysteresisParams(
        decay_rate=data.get("decay_rate", 0.05),
        accumulation_rate=data.get("accumulation_rate", 0.15),
        threshold=data.get("threshold", 0.3),
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
    runtime = RuntimeDefaults(**{k: v for k, v in rt_data.items()})

    hyst_data = data.get("hysteresis", {})
    hysteresis = HysteresisSettings(
        stress=_build_hysteresis_params(hyst_data.get("stress", {})),
        euphoria=_build_hysteresis_params(hyst_data.get("euphoria", {})),
        fatigue=_build_hysteresis_params(hyst_data.get("fatigue", {})),
        pain=_build_hysteresis_params(hyst_data.get("pain", {})),
    )

    loop_data = data.get("consciousness_loop", {})
    loop = LoopSettings(
        tick_interval_sec=loop_data.get("tick_interval_sec", 2.0),
        max_idle_ticks=loop_data.get("max_idle_ticks", 50),
    )

    log_data = data.get("logging", {})
    logging_settings = LoggingSettings(
        level=log_data.get("level", "INFO"),
        json_dir=log_data.get("json_dir", "logs"),
        console_enabled=log_data.get("console_enabled", True),
    )

    db_data = data.get("db", {})
    db = DbSettings(path=db_data.get("path", "data/consciousness.db"))

    return Settings(
        model=model,
        runtime_state=runtime,
        hysteresis=hysteresis,
        consciousness_loop=loop,
        logging=logging_settings,
        db=db,
    )


def load_flags(config_dir: Path | None = None) -> FeatureFlags:
    cfg_dir = config_dir or CONFIG_DIR
    return FeatureFlags.from_yaml(cfg_dir / "flags.yaml")
