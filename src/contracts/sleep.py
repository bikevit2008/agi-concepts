"""Sleep & memory consolidation contracts — circadian rhythm + sleep mode.

Two distinct responsibilities:
1. ISleepManager — Two-Process model (Process S = homeostatic sleep
   pressure; Process C = circadian alerting). Decides when to enter
   sleep mode based on accumulated fatigue + circadian phase.
2. IMemoryConsolidator — runs during sleep mode. NREM-like phase:
   replay & strengthen. REM-like phase: cross-link + abstraction.

The loop calls sleep_manager.update(...) every tick. When asleep, LLM
calls are heavily restricted (or disabled), and the consolidator is
invoked to process the memory store.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Protocol, runtime_checkable


class WakeState(str, Enum):
    AWAKE = "awake"
    DROWSY = "drowsy"  # transitioning into sleep
    SLEEPING = "sleeping"  # NREM/REM cycles
    WAKING = "waking"  # transitioning out of sleep


class SleepPhase(str, Enum):
    NONE = "none"  # awake, no sleep phase
    NREM = "nrem"  # consolidation, replay, downscaling
    REM = "rem"  # abstraction, novel associations


@dataclass
class SleepDecision:
    """Outcome of a sleep_manager.update() call for the current tick."""

    wake_state: WakeState
    phase: SleepPhase
    sleep_pressure: float  # 0..1; Process S
    circadian_phase: float  # 0..2π or 0..1 normalized; Process C
    suppress_llm_calls: bool  # if True, loop should skip agent runs this tick
    rationale: str = ""


@runtime_checkable
class ISleepManager(Protocol):
    """Decides when the system should sleep, and orchestrates phases."""

    def update(
        self,
        tick: int,
        dt_seconds: float,
        runtime_state: Dict[str, float],
        hysteresis_state: Dict[str, float],
    ) -> SleepDecision:
        """Advance sleep model by dt seconds; return decision for this tick."""
        ...

    def force_sleep(self) -> None:
        """Externally trigger immediate sleep entry (e.g. circuit breaker)."""
        ...

    def force_wake(self) -> None:
        """Externally trigger immediate wake (e.g. user stimulus)."""
        ...

    def to_dict(self) -> Dict[str, object]:
        """Snapshot of internal state."""
        ...


@runtime_checkable
class IMemoryConsolidator(Protocol):
    """Processes the memory store during sleep phases.

    NREM: replays memories with high emotional intensity, strengthens edges,
    downscales weak edges.

    REM: looks for cross-cluster links, generates novel associations,
    creates "abstractions" (compressed summaries of memory clusters).
    """

    def consolidate_nrem(self, memory_ids: List[str]) -> Dict[str, object]:
        """Run NREM-phase consolidation. Returns stats."""
        ...

    def consolidate_rem(self, memory_ids: List[str]) -> Dict[str, object]:
        """Run REM-phase consolidation. Returns stats."""
        ...

    def to_dict(self) -> Dict[str, object]:
        ...


# ---------------------------------------------------------------------------
# Null implementations
# ---------------------------------------------------------------------------


class NullSleepManager:
    """No-op sleep manager: always awake, no pressure, no suppression."""

    def update(
        self,
        tick: int,
        dt_seconds: float,
        runtime_state: Dict[str, float],
        hysteresis_state: Dict[str, float],
    ) -> SleepDecision:
        return SleepDecision(
            wake_state=WakeState.AWAKE,
            phase=SleepPhase.NONE,
            sleep_pressure=0.0,
            circadian_phase=0.0,
            suppress_llm_calls=False,
            rationale="null sleep manager",
        )

    def force_sleep(self) -> None:
        return None

    def force_wake(self) -> None:
        return None

    def to_dict(self) -> Dict[str, object]:
        return {"type": "null"}


class NullMemoryConsolidator:
    """No-op memory consolidator: does no work, returns empty stats."""

    def consolidate_nrem(self, memory_ids: List[str]) -> Dict[str, object]:
        return {"phase": "nrem", "consolidated": 0}

    def consolidate_rem(self, memory_ids: List[str]) -> Dict[str, object]:
        return {"phase": "rem", "consolidated": 0}

    def to_dict(self) -> Dict[str, object]:
        return {"type": "null"}
