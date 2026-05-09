#!/usr/bin/env python3
"""Falsifiable harness — injects canonical stress patterns and reports
whether each hypothesis (from AGI_CONCEPT_V3_RU section 8.3) is
falsified or supported.

Usage:
    python scripts/run_falsifiable.py
    python scripts/run_falsifiable.py --ticks 1000 --json
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

logging.basicConfig(level=logging.ERROR, stream=sys.stderr)
try:
    import structlog

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR),
    )
except ImportError:
    pass

from src.experiments.harness import ScriptedTeam, run_loop  # noqa: E402
from src.experiments.metrics import (  # noqa: E402
    detect_death_spiral,
    measure_recovery_time,
    time_above_saturation,
)


def h1_recovery_from_moderate_stress(ticks: int) -> Dict[str, Any]:
    team = ScriptedTeam(
        stimulus_response=lambda s: {"response": "injected"},
    )
    team.stimuli_on_stimulus = {"stress": 0.5}
    r = run_loop(
        ticks=ticks,
        team=team,
        flags_overrides={"homeostatic_hysteresis_enabled": True, "feedback_loops_enabled": False},
        stimulus_plan={1: "inject"},
    )
    trace = r.channel_trace("stress")
    peak = max(range(len(trace)), key=lambda i: trace[i])
    rec = measure_recovery_time(trace, from_tick=peak, to_baseline=0.3)
    return {
        "name": "H1 homeostatic recovers from moderate (0.5) injection",
        "peak_tick": peak,
        "recovery_ticks": rec,
        "supported": rec is not None and rec < 150,
    }


def h3_no_death_spiral_under_governance(ticks: int) -> Dict[str, Any]:
    team = ScriptedTeam(stimulus_response=lambda s: {"response": "ok"})
    r = run_loop(
        ticks=ticks,
        team=team,
        flags_overrides={
            "homeostatic_hysteresis_enabled": True,
            "feedback_loops_enabled": True,
            "governance_enabled": True,
            "circuit_breaker_enabled": True,
        },
    )
    spirals = {
        ch: detect_death_spiral(r.channel_trace(ch), window=50, threshold=0.95)
        for ch in ("stress", "euphoria", "fatigue", "pain")
    }
    any_spiral = any(v is not None for v in spirals.values())
    return {
        "name": "H3 governance+homeostatic → no death spiral",
        "spirals": spirals,
        "supported": not any_spiral,
    }


def h5_governance_caps_stim(ticks: int) -> Dict[str, Any]:
    """Exercise the governance kernel directly with synthetic stimuli."""
    from src.contracts.governance import GovernanceDecision, StimulationRequest
    from src.engine.circuit_breaker import SaturationCircuitBreaker
    from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy

    kernel = DeterministicGovernanceKernel(
        policy=GovernancePolicy(per_tick_stimulus_cap=0.3),
        circuit_breaker=SaturationCircuitBreaker(),
    )
    allowed = 0
    kernel.begin_tick(0)
    for i in range(200):
        req = StimulationRequest(
            agent=f"Agent{i % 3}", channel="stress", intensity=0.05, tick=0
        )
        if kernel.authorize(req) == GovernanceDecision.ALLOW:
            kernel.record(req)
            allowed += 1
    stats = kernel.end_tick(0)
    return {
        "name": "H5 governance caps cumulative stimulation per tick",
        "allowed": allowed,
        "total_positive": stats["total_positive"],
        "supported": stats["total_positive"] <= 0.3 + 1e-9 and allowed < 200,
    }


HYPOTHESES = [h1_recovery_from_moderate_stress, h3_no_death_spiral_under_governance, h5_governance_caps_stim]


def main() -> None:
    p = argparse.ArgumentParser(description="Falsifiable harness")
    p.add_argument("--ticks", type=int, default=500)
    p.add_argument("--json", action="store_true", help="emit JSON report")
    args = p.parse_args()

    results: List[Dict[str, Any]] = []
    for h in HYPOTHESES:
        try:
            results.append(h(args.ticks))
        except Exception as e:
            results.append({"name": h.__name__, "error": str(e), "supported": False})

    if args.json:
        print(json.dumps({"ticks": args.ticks, "results": results}, indent=2))
        return

    print(f"Falsifiable test results ({args.ticks} ticks each):\n")
    for r in results:
        status = "SUPPORT" if r.get("supported") else "FALSIFIED"
        print(f"  [{status}] {r['name']}")
        for k, v in r.items():
            if k not in ("name", "supported"):
                print(f"      {k} = {v}")


if __name__ == "__main__":
    main()
