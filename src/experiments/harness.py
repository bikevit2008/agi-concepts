"""Headless loop harness for deterministic experiments.

Gives tests & ablation scripts a way to run the full ConsciousnessLoop
machinery WITHOUT any LLM calls. The team is replaced by a deterministic
`ScriptedTeam` whose outputs are fixed (or driven by a small DSL).

Example:
    from src.experiments.harness import ScriptedTeam, LoopHarness

    team = ScriptedTeam(
        default_emotion="calm",
        stimulus_response=lambda s: {"response": f"echo:{s}"},
    )
    h = LoopHarness(team=team, flags_overrides={"homeostatic_hysteresis_enabled": True})
    result = await h.run(ticks=200)
    print(result.channel_trace("stress")[-10:])
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from src.config.flags import FeatureFlags
from src.config.loader import load_flags, load_settings
from src.config.settings import Settings
from src.bus.asyncio_bus import AsyncioEventBus
from src.contracts.governance import (
    IConstitutionalAuditor,
    NullCircuitBreaker,
    NullConstitutionalAuditor,
    NullGovernanceKernel,
)
from src.contracts.goals import NullGoalStack
from src.contracts.learning import ILearningStore
from src.contracts.memory import NullMemoryStore, NullProvenanceTracker
from src.contracts.ml import (
    NullCollapseForecaster,
    NullRecoveryPolicy,
    NullRuminationDetector,
)
from src.contracts.observability import NullObservabilityCollector
from src.contracts.persistence import NullCheckpoint, NullEventStore
from src.contracts.sleep import NullMemoryConsolidator, NullSleepManager
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.hysteresis import HysteresisEngine
from src.core.runtime_state import RuntimeState
from src.engine.circuit_breaker import SaturationCircuitBreaker
from src.engine.goal_pursuit import DeterministicGoalPursuitPolicy
from src.engine.goal_stack import PersistentGoalStack
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.engine.learning_store import PersistentLearningStore
from src.governance.kernel import DeterministicGovernanceKernel, GovernancePolicy


@dataclass
class ScriptedTeam:
    """A deterministic stand-in for `ConsciousnessTeam` — no LLM calls.

    Use callbacks to shape responses:
        stimulus_response(stim) -> dict for each process_stimulus_sync
        reflection_response()   -> optional dict
        thought_response()      -> optional dict

    Hysteresis stimulations (stimuli_on_stimulus) are applied directly via
    the hysteresis engine — they bypass the governance kernel so experiments
    can inject conditions without policy interference.
    """

    runtime_state: Optional[RuntimeState] = None
    hysteresis: Optional[Any] = None

    stimulus_response: Callable[[str], Dict[str, Any]] = field(
        default_factory=lambda: (lambda s: {"response": f"ok:{s}"})
    )
    reflection_response: Callable[[], Optional[Dict[str, Any]]] = field(
        default_factory=lambda: lambda: None
    )
    thought_response: Callable[[], Optional[Dict[str, Any]]] = field(
        default_factory=lambda: lambda: None
    )

    # Per-call stimulations on hysteresis (applied after process_stimulus_sync)
    stimuli_on_stimulus: Dict[str, float] = field(default_factory=dict)
    stimuli_per_tick: Dict[str, float] = field(default_factory=dict)

    memories: List[str] = field(default_factory=list)
    emotion_history: List[Dict[str, Any]] = field(default_factory=list)
    state_journal: List[Dict[str, Any]] = field(default_factory=list)
    processed_results: List[Dict[str, Any]] = field(default_factory=list)
    reflection_results: List[Dict[str, Any]] = field(default_factory=list)
    thought_results: List[Dict[str, Any]] = field(default_factory=list)
    current_tick: int = 0

    # Internal counters
    _process_calls: int = 0
    _reflect_calls: int = 0
    _thought_calls: int = 0

    def process_stimulus_sync(self, stimulus: str) -> Dict[str, Any]:
        self._process_calls += 1
        for channel, intensity in self.stimuli_on_stimulus.items():
            if self.hysteresis is not None:
                self.hysteresis.stimulate(channel, intensity)
        result = self.stimulus_response(stimulus)
        self.processed_results.append(result)
        return result

    def reflect_sync(self) -> Optional[Dict[str, Any]]:
        self._reflect_calls += 1
        result = self.reflection_response()
        if result:
            self.reflection_results.append(result)
        return result

    def spontaneous_thought_sync(self) -> Optional[Dict[str, Any]]:
        self._thought_calls += 1
        result = self.thought_response()
        if result:
            self.thought_results.append(result)
        return result

    def record_state_snapshot(self) -> None:
        if self.runtime_state is None or self.hysteresis is None:
            return
        self.state_journal.append(
            {
                "runtime": self.runtime_state.to_dict(),
                "channels": {
                    n: round(c.value, 4) for n, c in self.hysteresis.channels.items()
                },
            }
        )
        if len(self.state_journal) > 500:
            self.state_journal = self.state_journal[-500:]
        # Apply per-tick stimulations for experiments
        for channel, intensity in self.stimuli_per_tick.items():
            self.hysteresis.stimulate(channel, intensity)


@dataclass
class HarnessResult:
    """Aggregated snapshot of loop behavior during a harness run."""

    settings: Settings
    flags: FeatureFlags
    total_ticks: int
    runtime_trace: List[Dict[str, float]]  # runtime_state each tick
    channel_traces: Dict[str, List[float]]  # per-channel value trace
    stimuli_submitted: List[str]
    errors: List[str]
    responses: List[Dict[str, Any]] = field(default_factory=list)
    reflections: List[Dict[str, Any]] = field(default_factory=list)
    thoughts: List[Dict[str, Any]] = field(default_factory=list)
    goal_stack: Dict[str, Any] = field(default_factory=dict)
    goal_pursuit: Dict[str, Any] = field(default_factory=dict)
    learning: Dict[str, Any] = field(default_factory=dict)

    def channel_trace(self, channel: str) -> List[float]:
        return self.channel_traces.get(channel, [])


@dataclass
class LoopHarness:
    """Wires a ConsciousnessLoop with a ScriptedTeam + Null subsystems.

    Only governance + circuit_breaker + hysteresis are live by default.
    Other subsystems (persistence, memory, observability, sleep, ML) are
    Null — enable them explicitly through flags_overrides if needed.
    """

    team: Optional[ScriptedTeam] = None
    settings_overrides: Dict[str, Any] = field(default_factory=dict)
    flags_overrides: Dict[str, Any] = field(default_factory=dict)

    def build(self) -> ConsciousnessLoop:
        settings = copy.deepcopy(load_settings())
        for k, v in self.settings_overrides.items():
            if "." in k:
                section, attr = k.split(".", 1)
                obj = getattr(settings, section, None)
                if obj is not None and hasattr(obj, attr):
                    setattr(obj, attr, v)
            else:
                setattr(settings, k, v)

        flags = load_flags()
        for k, v in self.flags_overrides.items():
            setattr(flags, k, v)

        runtime_state = RuntimeState(
            temperature=settings.runtime_state.temperature,
            context_window=settings.runtime_state.context_window,
            processing_latency=settings.runtime_state.processing_latency,
            bandwidth=settings.runtime_state.bandwidth,
            attention_focus=settings.runtime_state.attention_focus,
            energy_level=settings.runtime_state.energy_level,
        )

        # Use homeostatic engine when the flag is on (matches production default)
        if flags.homeostatic_hysteresis_enabled:
            hysteresis = HomeostaticHysteresisEngine.from_settings(settings.hysteresis)
        else:
            hysteresis = HysteresisEngine.from_settings(settings.hysteresis)

        team = self.team or ScriptedTeam()
        team.runtime_state = runtime_state
        team.hysteresis = hysteresis

        # Minimal governance stack (kernel + breaker); auditor is Null
        circuit_breaker = (
            SaturationCircuitBreaker(
                saturation_threshold=settings.circuit_breaker.saturation_threshold,
                trip_after_ticks=settings.circuit_breaker.trip_after_ticks,
                reset_below=settings.circuit_breaker.reset_below,
            )
            if flags.circuit_breaker_enabled
            else NullCircuitBreaker()
        )
        governance = (
            DeterministicGovernanceKernel(
                policy=GovernancePolicy(
                    per_tick_stimulus_cap=settings.governance.per_tick_stimulus_cap,
                    per_agent_stimulus_cap=settings.governance.per_agent_stimulus_cap,
                    reflection_self_stim_cap=settings.governance.reflection_self_stim_cap,
                    enforce_circuit_breaker=settings.governance.enforce_circuit_breaker,
                ),
                circuit_breaker=circuit_breaker,
            )
            if flags.governance_enabled
            else NullGovernanceKernel()
        )

        goal_stack = (
            PersistentGoalStack(
                max_active_goals=settings.goal_stack.max_active_goals,
                stale_after_ticks=settings.goal_stack.stale_after_ticks,
                block_after_failures=settings.goal_stack.block_after_failures,
                abandon_after_failures=settings.goal_stack.abandon_after_failures,
                pressure_stress_threshold=settings.goal_stack.pressure_stress_threshold,
                pressure_blocks_below_priority=(
                    settings.goal_stack.pressure_blocks_below_priority
                ),
            )
            if flags.goal_stack_enabled
            else NullGoalStack()
        )
        goal_pursuit_policy = DeterministicGoalPursuitPolicy(
            min_idle_ticks=settings.goal_stack.pursuit_min_idle_ticks,
            min_ticks_between_attempts=(
                settings.goal_stack.pursuit_min_ticks_between_attempts
            ),
            progress_stale_after_ticks=(
                settings.goal_stack.pursuit_progress_stale_after_ticks
            ),
            max_attempts_per_goal=(
                settings.goal_stack.pursuit_max_attempts_per_goal
            ),
            pause_stress_threshold=(
                settings.goal_stack.pursuit_pause_stress_threshold
            ),
            pause_low_priority_below=(
                settings.goal_stack.pursuit_pause_low_priority_below
            ),
        )
        learning_store: ILearningStore = PersistentLearningStore(
            session_id=settings.learning.session_id,
            max_recent_events=settings.learning.max_recent_events,
            max_insights=settings.learning.max_insights,
            min_insight_length=settings.learning.min_insight_length,
        )

        return ConsciousnessLoop(
            settings=settings,
            flags=flags,
            runtime_state=runtime_state,
            hysteresis=hysteresis,
            event_bus=AsyncioEventBus(schema_validation=settings.bus.schema_validation),
            team=team,
            governance=governance,
            circuit_breaker=circuit_breaker,
            event_store=NullEventStore(),
            checkpoint=NullCheckpoint(),
            observability=NullObservabilityCollector(),
            sleep_manager=NullSleepManager(),
            memory_consolidator=NullMemoryConsolidator(),
            rumination_detector=NullRuminationDetector(),
            collapse_forecaster=NullCollapseForecaster(),
            recovery_policy=NullRecoveryPolicy(),
            goal_stack=goal_stack,
            goal_pursuit_policy=goal_pursuit_policy,
            learning_store=learning_store,
        )

    async def run(
        self,
        ticks: int,
        stimulus_plan: Optional[Dict[int, str]] = None,
        simulated_time: bool = True,
    ) -> HarnessResult:
        """Run the loop for `ticks` ticks, returning a HarnessResult.

        Args:
            ticks: how many ticks to drive.
            stimulus_plan: optional {tick: stimulus_text} — stimuli queued
                before that tick runs.
            simulated_time: when True (default), we force the loop to
                compute `dt == tick_interval_sec`. This keeps
                experiments independent of real CPU speed.
        """
        loop = self.build()
        tick_dt = loop.settings.consciousness_loop.tick_interval_sec
        if simulated_time:
            loop._simulated_dt = tick_dt
        runtime_trace: List[Dict[str, float]] = []
        channel_traces: Dict[str, List[float]] = {
            n: [] for n in loop.hysteresis.channels
        }
        stimuli_submitted: List[str] = []
        errors: List[str] = []
        plan = dict(stimulus_plan or {})

        for tick_idx in range(1, ticks + 1):
            if tick_idx in plan:
                s = plan[tick_idx]
                stimuli_submitted.append(s)
                await loop.submit_stimulus(s)
            if simulated_time and loop._last_tick_time is not None:
                # Pretend the previous tick happened exactly tick_dt ago.
                import time as _time

                loop._last_tick_time = _time.monotonic() - tick_dt
            try:
                await loop._tick()
            except Exception as e:
                errors.append(f"tick {tick_idx}: {e}")

            runtime_trace.append(loop.runtime_state.to_dict())
            for n, ch in loop.hysteresis.channels.items():
                channel_traces[n].append(ch.value)

        return HarnessResult(
            settings=loop.settings,
            flags=loop.flags,
            total_ticks=ticks,
            runtime_trace=runtime_trace,
            channel_traces=channel_traces,
            stimuli_submitted=stimuli_submitted,
            errors=errors,
            responses=list(getattr(loop.team, "processed_results", [])),
            reflections=list(getattr(loop.team, "reflection_results", [])),
            thoughts=list(getattr(loop.team, "thought_results", [])),
            goal_stack=loop.goal_stack.to_dict(),
            goal_pursuit=loop.goal_pursuit_policy.to_dict(),
            learning=loop.learning_store.to_dict(),
        )


def run_loop(
    ticks: int,
    team: Optional[ScriptedTeam] = None,
    flags_overrides: Optional[Dict[str, Any]] = None,
    settings_overrides: Optional[Dict[str, Any]] = None,
    stimulus_plan: Optional[Dict[int, str]] = None,
) -> HarnessResult:
    """Sync convenience wrapper around `LoopHarness.run`."""
    h = LoopHarness(
        team=team,
        flags_overrides=flags_overrides or {},
        settings_overrides=settings_overrides or {},
    )
    return asyncio.run(h.run(ticks=ticks, stimulus_plan=stimulus_plan))


__all__ = ["HarnessResult", "LoopHarness", "ScriptedTeam", "run_loop"]
