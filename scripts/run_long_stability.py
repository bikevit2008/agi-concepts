#!/usr/bin/env python3
"""Long-run stability runner for deterministic no-LLM experiments."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
try:
    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
    )
except ImportError:
    pass

from src.experiments.harness import ScriptedTeam, run_loop  # noqa: E402
from src.experiments.metrics import detect_death_spiral, summarize_run  # noqa: E402


def run_stability(ticks: int, stress_per_tick: float) -> Dict[str, Any]:
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": f"echo:{s}"},
        stimuli_per_tick={"stress": stress_per_tick} if stress_per_tick else {},
    )
    result = run_loop(ticks=ticks, team=team)
    summary = summarize_run(result.channel_traces)
    spirals = {
        channel: detect_death_spiral(trace, window=min(50, max(1, ticks // 4)))
        for channel, trace in result.channel_traces.items()
    }
    final_runtime = result.runtime_trace[-1] if result.runtime_trace else {}
    return {
        "ticks": ticks,
        "stress_per_tick": stress_per_tick,
        "errors": result.errors,
        "channels": summary,
        "death_spirals": spirals,
        "final_runtime": final_runtime,
        "stable": not result.errors and all(value is None for value in spirals.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-run deterministic stability harness")
    parser.add_argument("--ticks", type=int, default=1000)
    parser.add_argument("--stress-per-tick", type=float, default=0.05)
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args()

    report = run_stability(args.ticks, args.stress_per_tick)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"Long stability run ({args.ticks} ticks)")
    print(f"stable={report['stable']} errors={len(report['errors'])}")
    for name, metrics in report["channels"].items():
        print(
            f"{name:<10} max={metrics['max']:.3f} "
            f"mean={metrics['mean']:.3f} "
            f"above={metrics['time_above_0.95']} "
            f"spirals={metrics['spiral_count']}"
        )


if __name__ == "__main__":
    main()
