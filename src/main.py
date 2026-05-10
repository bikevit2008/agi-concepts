"""Entry point for the AGI Consciousness PoC system.

Usage:
    consciousness                # Launch full TUI (default)
    consciousness --headless     # Run loop without UI (production)
    consciousness --headless --max-ticks 1000   # Stop after N ticks
    consciousness --smoke        # Run deterministic no-LLM smoke test
    consciousness --version
"""
from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="consciousness",
        description="AGI Consciousness PoC — multi-agent consciousness loop with hysteresis",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the loop without the TUI (server / production mode).",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Stop after N ticks (headless only). Default: run forever.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a deterministic no-LLM smoke test and exit.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    return parser


def main() -> None:
    args = _build_argparser().parse_args()

    if args.version:
        from importlib.metadata import version, PackageNotFoundError
        try:
            v = version("agi-consciousness")
        except PackageNotFoundError:
            v = "0.0.0-dev"
        print(f"agi-consciousness {v}")
        return

    if args.smoke:
        _run_smoke()
        return

    if args.headless:
        asyncio.run(_run_headless(max_ticks=args.max_ticks))
        return

    # Default: full TUI
    from src.tui.app import ConsciousnessApp
    app = ConsciousnessApp()
    app.run()


async def _run_headless(max_ticks: int | None = None) -> None:
    """Run ConsciousnessLoop without a TUI.

    Wires up the same dependency graph as the TUI app, then runs the
    loop until SIGINT/SIGTERM (or until max_ticks is reached).
    """
    from src.tui.app import ConsciousnessApp

    # Reuse the wiring logic from ConsciousnessApp.__init__ — but we
    # never call .run() (that would launch Textual). Instead we drive
    # the consciousness_loop directly.
    app = ConsciousnessApp()
    print(
        f"[headless] starting consciousness loop "
        f"(persistence={app.flags.persistence_enabled}, "
        f"memory_store={type(app.memory_store).__name__}, "
        f"max_ticks={max_ticks or 'inf'})"
    )

    # Try to restore from checkpoint
    if app.consciousness_loop.restore_from_checkpoint():
        print(f"[headless] restored from checkpoint at tick {app.consciousness_loop.tick_count}")

    # Wire up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _request_stop() -> None:
        print("[headless] shutdown signal received")
        stop_event.set()
        app.consciousness_loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler on the default loop
            pass

    # Optionally cap the run length
    async def _tick_cap_watcher():
        while not stop_event.is_set():
            await asyncio.sleep(1.0)
            if max_ticks is not None and app.consciousness_loop.tick_count >= max_ticks:
                print(f"[headless] reached max_ticks={max_ticks}, stopping")
                _request_stop()
                return

    cap_task = asyncio.create_task(_tick_cap_watcher())
    try:
        await app.consciousness_loop.start()
    finally:
        cap_task.cancel()
        try:
            await cap_task
        except (asyncio.CancelledError, Exception):
            pass

        # Print final stats
        if app.flags.cost_tracking_enabled:
            stats = app.cost_tracker.stats()
            print(
                f"[headless] cost summary: spent ${stats.get('daily_spent_usd', 0):.4f} "
                f"of ${stats.get('daily_budget_usd', 0):.2f}; "
                f"calls={sum(m['call_count'] for m in stats.get('per_model', {}).values())}"
            )
        print(f"[headless] stopped at tick {app.consciousness_loop.tick_count}")


def _run_smoke() -> None:
    import logging

    import structlog

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.ERROR))

    from src.experiments.harness import ScriptedTeam, run_loop

    result = run_loop(
        ticks=3,
        team=ScriptedTeam(stimulus_response=lambda s: {"response": f"smoke:{s}"}),
        stimulus_plan={1: "smoke"},
    )
    if result.errors:
        raise SystemExit(f"[smoke] failed: {result.errors}")
    print(
        "[smoke] ok "
        f"ticks={result.total_ticks} "
        f"stimuli={len(result.stimuli_submitted)} "
        f"stress_last={result.channel_trace('stress')[-1]:.4f}"
    )


if __name__ == "__main__":
    main()
