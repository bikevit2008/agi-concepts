"""Experiment harness — headless loop runs for falsifiable / ablation tests.

This package contains deterministic test fixtures: a scripted agent
team (no LLM calls), a minimal loop wirer, and helpers for measuring
metrics specified in AGI_CONCEPT_V3_RU.md section 8 (MTTDS,
recovery time, stimulus discrimination, ...).
"""

from src.experiments.harness import (
    HarnessResult,
    LoopHarness,
    ScriptedTeam,
    run_loop,
)
from src.experiments.metrics import (
    detect_death_spiral,
    measure_recovery_time,
    spiral_count,
    time_above_saturation,
)

__all__ = [
    "HarnessResult",
    "LoopHarness",
    "ScriptedTeam",
    "detect_death_spiral",
    "measure_recovery_time",
    "run_loop",
    "spiral_count",
    "time_above_saturation",
]
