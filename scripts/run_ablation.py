#!/usr/bin/env python3
"""Ablation runner — turn each subsystem off one at a time, record metrics.

Usage:
    python scripts/run_ablation.py --ticks 1000
    python scripts/run_ablation.py --ticks 500 --json > ablation.json

Writes a JSON report with per-ablation summary metrics (max / mean /
time_above_0.95 / spiral_count per channel).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Silence structlog / stdlib loggers so only the CLI output goes to stdout.
logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
try:
    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
    )
except ImportError:
    pass

from src.experiments.harness import ScriptedTeam, run_loop  # noqa: E402
from src.experiments.metrics import summarize_run  # noqa: E402

ABLATIONS: List[Dict[str, Any]] = [
    {"name": "baseline", "flags": {}},
    {"name": "no_feedback_loops", "flags": {"feedback_loops_enabled": False}},
    {"name": "no_homeostatic", "flags": {"homeostatic_hysteresis_enabled": False}},
    {"name": "no_governance", "flags": {"governance_enabled": False}},
    {"name": "no_circuit_breaker", "flags": {"circuit_breaker_enabled": False}},
    {"name": "no_runtime_effects", "flags": {"runtime_effects_enabled": False}},
    {"name": "no_hysteresis", "flags": {"hysteresis_enabled": False}},
    {"name": "no_self_reflection", "flags": {"self_reflection_enabled": False}},
    {
        "name": "no_anything",
        "flags": {
            "feedback_loops_enabled": False,
            "governance_enabled": False,
            "circuit_breaker_enabled": False,
            "self_reflection_enabled": False,
            "autonomous_thoughts_enabled": False,
        },
    },
]


def run_one(name: str, flags: Dict[str, Any], ticks: int) -> Dict[str, Any]:
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": f"echo:{s}"},
        stimuli_per_tick={"stress": 0.1},
    )
    result = run_loop(ticks=ticks, team=team, flags_overrides=flags)
    summary = summarize_run(result.channel_traces)
    return {
        "name": name,
        "flags_overrides": flags,
        "errors": result.errors,
        "channels": summary,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Ablation harness")
    p.add_argument("--ticks", type=int, default=500)
    p.add_argument("--json", action="store_true", help="emit JSON report")
    args = p.parse_args()

    results = [run_one(a["name"], a["flags"], args.ticks) for a in ABLATIONS]

    if args.json:
        print(json.dumps({"ticks": args.ticks, "ablations": results}, indent=2))
        return

    # Human-readable
    print(f"Ablation summary ({args.ticks} ticks each):\n")
    header = f"{'name':<24} {'stress.max':>11} {'stress.above':>13} {'fatigue.max':>11}"
    print(header)
    print("-" * len(header))
    for r in results:
        stress = r["channels"].get("stress", {})
        fatigue = r["channels"].get("fatigue", {})
        print(
            f"{r['name']:<24} {stress.get('max', 0):>11.3f} "
            f"{stress.get('time_above_0.95', 0):>13d} "
            f"{fatigue.get('max', 0):>11.3f}"
        )


if __name__ == "__main__":
    main()
