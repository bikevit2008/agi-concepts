"""Rerun.io real-time visualization integration.

Streams to a Rerun viewer:
- Time-series of runtime parameters (temperature, energy, attention, ...)
- Time-series of hysteresis channel values (stress, euphoria, ...)
- Scalar PAD-space coordinates (Pleasure / Arousal / Dominance projection)
- Text logs (chat-like, last N agent responses)
- Cost over time

Lazy-imports rerun-sdk so the rest of the codebase works on machines
without it.

Spawn modes:
- spawn=True: launches a viewer subprocess on first connect.
- spawn=False: assumes a viewer is already listening (e.g. `rerun --serve`).

API note: We intentionally don't expose Rerun's full API; we provide a
small set of `log_*` methods sized to the consciousness loop's needs.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger("consciousness.visualization.rerun")


class RerunLogger:
    """Thin wrapper around `rerun_sdk` for streaming consciousness state."""

    def __init__(
        self,
        application_id: str = "consciousness",
        spawn: bool = True,
    ) -> None:
        try:
            import rerun as rr
        except ImportError as e:
            raise ImportError(
                "rerun-sdk is not installed. Install with `pip install rerun-sdk` "
                "or set rerun_enabled=false in flags."
            ) from e

        self._rr = rr
        self._application_id = application_id
        try:
            rr.init(application_id, spawn=spawn)
        except Exception as e:
            logger.warning("rerun_init_warning", error=str(e))

    def log_runtime_state(self, tick: int, runtime_state: Dict[str, Any]) -> None:
        """Log scalar values for each runtime parameter."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            for k, v in runtime_state.items():
                if isinstance(v, (int, float)):
                    rr.log(f"runtime/{k}", rr.Scalar(float(v)))
        except Exception as e:
            logger.debug("rerun_log_runtime_warning", error=str(e))

    def log_hysteresis(self, tick: int, channels: Dict[str, Any]) -> None:
        """Log scalar values for each hysteresis channel."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            for name, ch in channels.items():
                if isinstance(ch, dict) and "value" in ch:
                    rr.log(f"hysteresis/{name}", rr.Scalar(float(ch["value"])))
        except Exception as e:
            logger.debug("rerun_log_hysteresis_warning", error=str(e))

    def log_pad_projection(
        self,
        tick: int,
        pleasure: float,
        arousal: float,
        dominance: float,
    ) -> None:
        """Log a 3D point in PAD (Pleasure-Arousal-Dominance) emotion space."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            rr.log("pad/point", rr.Points3D([[pleasure, arousal, dominance]]))
            rr.log("pad/p", rr.Scalar(float(pleasure)))
            rr.log("pad/a", rr.Scalar(float(arousal)))
            rr.log("pad/d", rr.Scalar(float(dominance)))
        except Exception as e:
            logger.debug("rerun_log_pad_warning", error=str(e))

    def log_response(self, tick: int, source: str, content: str) -> None:
        """Log a text message in the response stream."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            rr.log(f"chat/{source}", rr.TextLog(content[:500]))
        except Exception as e:
            logger.debug("rerun_log_response_warning", error=str(e))

    def log_cost(self, tick: int, cost_usd: float, daily_budget_usd: float) -> None:
        """Log running cost vs. budget."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            rr.log("cost/spent_usd", rr.Scalar(cost_usd))
            rr.log("cost/budget_usd", rr.Scalar(daily_budget_usd))
            if daily_budget_usd > 0:
                rr.log("cost/utilization_pct", rr.Scalar(100.0 * cost_usd / daily_budget_usd))
        except Exception as e:
            logger.debug("rerun_log_cost_warning", error=str(e))

    def log_circuit_breaker(self, tick: int, tripped_channels: list) -> None:
        """Emit a marker when the circuit breaker trips."""
        rr = self._rr
        try:
            rr.set_time_seconds("tick", tick)
            rr.log("circuit_breaker/tripped_count", rr.Scalar(float(len(tripped_channels))))
            if tripped_channels:
                rr.log(
                    "circuit_breaker/tripped",
                    rr.TextLog(f"TRIPPED: {', '.join(tripped_channels)}"),
                )
        except Exception as e:
            logger.debug("rerun_log_cb_warning", error=str(e))

    def shutdown(self) -> None:
        try:
            self._rr.disconnect()
        except Exception:
            pass


class NullRerunLogger:
    """No-op rerun logger. Drop-in when rerun is disabled."""

    def log_runtime_state(self, tick: int, runtime_state: Dict[str, Any]) -> None:
        return None

    def log_hysteresis(self, tick: int, channels: Dict[str, Any]) -> None:
        return None

    def log_pad_projection(
        self,
        tick: int,
        pleasure: float,
        arousal: float,
        dominance: float,
    ) -> None:
        return None

    def log_response(self, tick: int, source: str, content: str) -> None:
        return None

    def log_cost(self, tick: int, cost_usd: float, daily_budget_usd: float) -> None:
        return None

    def log_circuit_breaker(self, tick: int, tripped_channels: list) -> None:
        return None

    def shutdown(self) -> None:
        return None


__all__ = ["RerunLogger", "NullRerunLogger"]
