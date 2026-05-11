from __future__ import annotations

import asyncio
import copy
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from src.config.flags import FeatureFlags
from src.config.settings import RuntimeDefaults, Settings
from src.contracts.governance import (
    GovernanceDecision,
    ICircuitBreaker,
    IGovernanceKernel,
    NullCircuitBreaker,
    NullGovernanceKernel,
    StimulationRequest,
)
from src.contracts.goals import (
    IGoalPursuitPolicy,
    IGoalStack,
    NullGoalPursuitPolicy,
    NullGoalStack,
)
from src.contracts.ml import (
    CollapseSignal,
    ICollapseForecaster,
    IRecoveryPolicy,
    IRuminationDetector,
    NullCollapseForecaster,
    NullRecoveryPolicy,
    NullRuminationDetector,
    RecoveryAction,
    RuminationSignal,
    WarningLevel,
)
from src.contracts.observability import (
    IObservabilityCollector,
    NullObservabilityCollector,
)
from src.contracts.persistence import (
    ICheckpoint,
    IEventStore,
    NullCheckpoint,
    NullEventStore,
    Snapshot,
)
from src.contracts.sleep import (
    IMemoryConsolidator,
    ISleepManager,
    NullMemoryConsolidator,
    NullSleepManager,
    SleepPhase,
    WakeState,
)
from src.core.event_bus import EventBus, EventType
from src.core.hysteresis import HysteresisEngine
from src.core.runtime_state import RuntimeState
from src.engine.homeostatic_hysteresis import HomeostaticHysteresisEngine
from src.team.consciousness_team import ConsciousnessTeam

logger = structlog.get_logger("consciousness.loop")


def gated_stimulate(
    hysteresis: HysteresisEngine | HomeostaticHysteresisEngine,
    governance: IGovernanceKernel,
    agent: str,
    channel: str,
    intensity: float,
    tick: int,
    reason: Optional[str] = None,
) -> GovernanceDecision:
    """Apply a stimulation request through the governance kernel.

    This is the only sanctioned path for any subsystem to mutate hysteresis
    state. The kernel decides allow/deny, and only on ALLOW does the
    stimulation actually hit the engine. Records the decision either way
    so per-tick aggregations are accurate.
    """
    request = StimulationRequest(
        agent=agent,
        channel=channel,
        intensity=intensity,
        tick=tick,
        reason=reason,
    )
    decision = governance.authorize(request)
    if decision == GovernanceDecision.ALLOW:
        hysteresis.stimulate(channel, intensity)
        governance.record(request)
    return decision


@dataclass
class ConsciousnessLoop:
    """The main event loop of the consciousness system.

    Analogous to:
    - Event loop in JavaScript
    - Infinite loop in microcontrollers
    - The "stream of consciousness" in humans

    Each tick:
    1. Process pending stimuli from the queue
    2. Run the agent pipeline (Perception -> Emotion -> Memory -> Planning)
    3. Apply hysteresis decay to all channels
    4. Compute runtime state delta from active hysteresis channels
    5. Update runtime state
    6. Emit state snapshot event
    7. Log everything

    The loop runs continuously, even without stimuli (idle ticks),
    simulating the never-stopping nature of consciousness.
    """

    settings: Settings
    flags: FeatureFlags
    runtime_state: RuntimeState
    hysteresis: HysteresisEngine | HomeostaticHysteresisEngine
    event_bus: EventBus
    team: ConsciousnessTeam

    # Stage 3 — governance & circuit breaker (Null implementations by default)
    governance: IGovernanceKernel = field(default_factory=NullGovernanceKernel)
    circuit_breaker: ICircuitBreaker = field(default_factory=NullCircuitBreaker)

    # Stage 4 — persistence (Null implementations by default)
    event_store: IEventStore = field(default_factory=NullEventStore)
    checkpoint: ICheckpoint = field(default_factory=NullCheckpoint)

    # Stage 7 — observability collector (OTel by default in TUI; Null otherwise)
    observability: IObservabilityCollector = field(default_factory=NullObservabilityCollector)

    # Stage 9 — sleep manager + memory consolidator (Null when disabled)
    sleep_manager: ISleepManager = field(default_factory=NullSleepManager)
    memory_consolidator: IMemoryConsolidator = field(default_factory=NullMemoryConsolidator)

    # Stage 12 — ML regulators (off by default; Null placeholders)
    rumination_detector: IRuminationDetector = field(default_factory=NullRuminationDetector)
    collapse_forecaster: ICollapseForecaster = field(default_factory=NullCollapseForecaster)
    recovery_policy: IRecoveryPolicy = field(default_factory=NullRecoveryPolicy)

    # Stage 29 — persistent intentions / goal stack
    goal_stack: IGoalStack = field(default_factory=NullGoalStack)
    goal_pursuit_policy: IGoalPursuitPolicy = field(default_factory=NullGoalPursuitPolicy)

    # Internal
    _tick_count: int = 0
    _idle_ticks: int = 0
    _running: bool = False
    _stimulus_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    _response_callbacks: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = field(default_factory=list)
    _reflection_callbacks: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = field(default_factory=list)
    _runtime_defaults: Optional[RuntimeDefaults] = None
    _reflection_interval: int = 5
    _last_tick_time: Optional[float] = None  # wall-clock time of last tick start (monotonic seconds)
    _checkpoint_every_ticks: int = 50

    def __post_init__(self) -> None:
        self._runtime_defaults = copy.deepcopy(self.settings.runtime_state)
        # Sync checkpoint frequency from settings
        self._checkpoint_every_ticks = self.settings.persistence.checkpoint_every_ticks

    def restore_from_checkpoint(self) -> bool:
        """Try to restore state from the latest checkpoint.

        Returns True if a checkpoint was loaded and applied; False if no
        checkpoint exists or an error occurred. The loop continues from
        the restored tick number.

        Persistence subsystem failures must NOT prevent the loop from
        starting fresh — we always degrade gracefully.
        """
        if not self.flags.persistence_enabled:
            return False
        try:
            snapshot = self.checkpoint.load_latest()
        except Exception as e:
            logger.error("checkpoint_restore_failed", error=str(e))
            return False
        if snapshot is None:
            return False

        try:
            # Restore runtime state
            if snapshot.runtime_state:
                rs = RuntimeState.from_dict(snapshot.runtime_state)
                self.runtime_state.temperature = rs.temperature
                self.runtime_state.context_window = rs.context_window
                self.runtime_state.processing_latency = rs.processing_latency
                self.runtime_state.bandwidth = rs.bandwidth
                self.runtime_state.attention_focus = rs.attention_focus
                self.runtime_state.energy_level = rs.energy_level
                self.runtime_state.clamp()

            # Restore hysteresis channel values.
            # `hysteresis.to_dict()` returns {channel_name: {value, ...}} directly,
            # without an outer "channels" wrapper.
            if snapshot.hysteresis and isinstance(snapshot.hysteresis, dict):
                for name, ch_data in snapshot.hysteresis.items():
                    if not isinstance(ch_data, dict):
                        continue
                    ch = self.hysteresis.channels.get(name)
                    if ch is None:
                        continue
                    try:
                        ch.value = float(ch_data.get("value", ch.value))
                    except (TypeError, ValueError):
                        pass

            # Restore team-side state
            if snapshot.memories:
                if hasattr(type(self.team), "restore_memories"):
                    self.team.restore_memories(list(snapshot.memories))
                else:
                    self.team.memories = list(snapshot.memories)
            if snapshot.emotion_history:
                self.team.emotion_history = list(snapshot.emotion_history)
            if snapshot.state_journal:
                self.team.state_journal = list(snapshot.state_journal)
            goal_source = None
            goal_payload = None
            extra = snapshot.extra or {}
            if "goal_stack" in extra:
                goal_source = "goal_stack"
                goal_payload = extra.get("goal_stack")
            elif "goals" in extra:
                goal_source = "goals"
                goal_payload = extra.get("goals")
            if goal_payload:
                self.goal_stack.restore(goal_payload)
                logger.info("goal_stack_restored", source=goal_source)
            goal_pursuit_payload = extra.get("goal_pursuit")
            if goal_pursuit_payload:
                policy_type = self.goal_pursuit_policy.to_dict().get("type")
                self.goal_pursuit_policy.restore(goal_pursuit_payload)
                if policy_type == "null":
                    logger.warning("goal_pursuit_restore_skipped_null_policy")
                else:
                    logger.info("goal_pursuit_restored")

            self._tick_count = snapshot.tick
            logger.info(
                "checkpoint_restored",
                tick=snapshot.tick,
                memories=len(snapshot.memories or []),
                emotion_history=len(snapshot.emotion_history or []),
            )
            return True
        except Exception as e:
            logger.error("checkpoint_apply_failed", error=str(e))
            return False

    def _apply_recovery(self, decision) -> None:
        """Act on a RecoveryDecision. Best-effort, non-blocking."""
        if decision is None or decision.action == RecoveryAction.NONE:
            return
        if decision.action == RecoveryAction.ALERT_ONLY:
            logger.info("recovery_alert", rationale=decision.rationale)
            return
        if decision.action == RecoveryAction.FORCE_SLEEP:
            logger.info("recovery_force_sleep", rationale=decision.rationale)
            try:
                self.sleep_manager.force_sleep()
            except Exception as e:
                logger.warning("recovery_force_sleep_failed", error=str(e))
            return
        if decision.action == RecoveryAction.INJECT_CALM:
            target = decision.target or "stress"
            intensity = max(0.01, float(decision.intensity or 0.15))
            logger.info(
                "recovery_inject_calm",
                target=target,
                intensity=intensity,
                rationale=decision.rationale,
            )
            try:
                # Negative stimulation = self-soothing, always allowed by governance
                self.hysteresis.stimulate(target, -intensity)
            except Exception as e:
                logger.warning("recovery_inject_calm_failed", error=str(e))
            return
        if decision.action == RecoveryAction.RESET_CHANNEL:
            target = decision.target
            if target and target in self.hysteresis.channels:
                logger.info("recovery_reset_channel", target=target)
                try:
                    self.hysteresis.channels[target].reset()
                except Exception as e:
                    logger.warning("recovery_reset_channel_failed", error=str(e))
            return
        if decision.action == RecoveryAction.LOWER_TEMPERATURE:
            logger.info("recovery_lower_temperature")
            self.runtime_state.temperature = max(
                0.1, self.runtime_state.temperature - 0.2
            )
            return

    async def _maybe_enqueue_goal_pursuit(self) -> bool:
        """Turn a stale active goal into a bounded internal stimulus."""
        if not (
            self.flags.goal_stack_enabled
            and self.flags.goal_pursuit_enabled
            and self.flags.internal_stimulus_enabled
        ):
            return False
        try:
            goal = self.goal_stack.top_active()
            decision = self.goal_pursuit_policy.maybe_pursue(
                tick=self._tick_count,
                idle_ticks=self._idle_ticks,
                goal=goal,
                runtime_state=self.runtime_state.to_dict(),
                hysteresis_state={
                    n: c.value for n, c in self.hysteresis.channels.items()
                },
            )
            if decision is None:
                return False
            await self._stimulus_queue.put(decision.stimulus)
            self.goal_pursuit_policy.record(decision)
            logger.info(
                "goal_pursuit_enqueued",
                goal_id=decision.goal_id,
                reason=decision.reason,
                stimulus=decision.stimulus[:120],
            )
            return True
        except Exception as e:
            logger.warning("goal_pursuit_failed", error=str(e))
            return False

    def _maybe_consolidate(self, decision) -> None:
        """Run memory consolidation when entering NREM/REM phases.

        We don't run on every tick — only when the phase actually changes
        (debounced via _last_consolidated_phase).
        """
        if not self.flags.memory_consolidation_enabled:
            return
        if decision is None or decision.phase == SleepPhase.NONE:
            return

        last = getattr(self, "_last_consolidated_phase", None)
        if last == decision.phase:
            return
        self._last_consolidated_phase = decision.phase

        try:
            if decision.phase == SleepPhase.NREM:
                stats = self.memory_consolidator.consolidate_nrem(memory_ids=[])
            else:
                stats = self.memory_consolidator.consolidate_rem(memory_ids=[])
            logger.info("memory_consolidation_done", phase=decision.phase.value, stats=stats)
        except Exception as e:
            logger.error("memory_consolidation_failed", error=str(e))

    def _build_snapshot(self) -> Snapshot:
        """Capture a full Snapshot of current state for checkpointing."""
        import time as _time
        return Snapshot(
            tick=self._tick_count,
            timestamp_ms=int(_time.time() * 1000),
            runtime_state=self.runtime_state.to_dict(),
            hysteresis=self.hysteresis.to_dict(),
            memories=(
                self.team.snapshot_memories()
                if hasattr(type(self.team), "snapshot_memories")
                else list(self.team.memories)
            ),
            emotion_history=list(self.team.emotion_history)[-50:],
            state_journal=list(self.team.state_journal)[-30:],
            extra={
                "governance": self.governance.to_dict(),
                "circuit_breaker": self.circuit_breaker.to_dict(),
                "goal_stack": self.goal_stack.to_dict(),
                "goal_pursuit": self.goal_pursuit_policy.to_dict(),
            },
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tick_count(self) -> int:
        return self._tick_count

    def on_response(self, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        """Register a callback for when the system produces a response."""
        self._response_callbacks.append(callback)

    def on_reflection(self, callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        """Register a callback for when the system produces a reflection."""
        self._reflection_callbacks.append(callback)

    async def submit_stimulus(self, stimulus: str) -> None:
        """Submit a stimulus to be processed on the next tick."""
        await self._stimulus_queue.put(stimulus)
        self._idle_ticks = 0
        logger.info("stimulus_submitted", stimulus=stimulus[:100], queue_size=self._stimulus_queue.qsize())

    async def start(self) -> None:
        """Start the consciousness loop."""
        self._running = True
        logger.info("loop_started", tick_interval=self.settings.consciousness_loop.tick_interval_sec)

        try:
            while self._running:
                await self._tick()
                # Add processing latency from runtime state
                delay = self.settings.consciousness_loop.tick_interval_sec + self.runtime_state.processing_latency
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info("loop_cancelled")
        finally:
            self._running = False
            # Stage 4 — graceful shutdown: final checkpoint + close stores
            if self.flags.persistence_enabled:
                try:
                    self.checkpoint.save(self._build_snapshot())
                    logger.info("graceful_checkpoint_saved", tick=self._tick_count)
                except Exception as e:
                    logger.error("graceful_checkpoint_failed", error=str(e))
                try:
                    self.event_store.close()
                    self.checkpoint.close()
                except Exception as e:
                    logger.warning("persistence_close_warning", error=str(e))
            logger.info("loop_stopped", total_ticks=self._tick_count)

    def stop(self) -> None:
        """Signal the loop to stop."""
        self._running = False

    async def _tick(self) -> None:
        """Execute one tick of the consciousness loop."""
        self._tick_count += 1

        with self.observability.start_span(
            "consciousness.tick",
            attributes={
                "consciousness.tick": self._tick_count,
                "consciousness.idle_ticks": self._idle_ticks,
            },
        ) as span:
            try:
                await self._tick_inner()
                span.set_status(ok=True)
            except Exception as e:
                logger.error("tick_error", tick=self._tick_count, error=str(e))
                span.record_exception(e)
                span.set_status(ok=False, description=str(e))

    async def _tick_inner(self) -> None:
        """Inner tick logic, separated so _tick can catch all errors."""
        # Compute dt from actual wall-clock time (Bug #1 fix)
        now = time.monotonic()
        simulated_dt = getattr(self, "_simulated_dt", None)
        if simulated_dt is not None:
            dt = float(simulated_dt)
        elif self._last_tick_time is None:
            dt = self.settings.consciousness_loop.tick_interval_sec
        else:
            dt = now - self._last_tick_time
        # Cap dt to prevent timing spikes from causing excessive decay;
        # guard against negative dt (clock edge case)
        dt = max(0.0, min(dt, 5.0 * self.settings.consciousness_loop.tick_interval_sec))
        self._last_tick_time = now

        # Stage 3 — begin governance window for this tick
        if self.flags.governance_enabled:
            self.governance.begin_tick(self._tick_count)

        # Make tick number visible to the team for governance traceability
        self.team.current_tick = self._tick_count

        # Stage 29 — refresh persistent goal lifecycle before agents act.
        if self.flags.goal_stack_enabled:
            try:
                changed_goals = self.goal_stack.refresh(
                    tick=self._tick_count,
                    runtime_state=self.runtime_state.to_dict(),
                    hysteresis_state={
                        n: c.value for n, c in self.hysteresis.channels.items()
                    },
                )
                if changed_goals:
                    logger.info(
                        "goal_stack_refreshed",
                        tick=self._tick_count,
                        changed=[
                            {
                                "id": goal.id,
                                "status": goal.status.value,
                                "failure_count": goal.failure_count,
                            }
                            for goal in changed_goals
                        ],
                    )
            except Exception as e:
                logger.warning("goal_stack_refresh_failed", error=str(e))

        # Stage 9 — advance sleep model and decide whether to suppress LLM
        sleep_decision = None
        if self.flags.sleep_mode_enabled:
            sleep_decision = self.sleep_manager.update(
                tick=self._tick_count,
                dt_seconds=dt,
                runtime_state=self.runtime_state.to_dict(),
                hysteresis_state={
                    n: c.value for n, c in self.hysteresis.channels.items()
                },
            )
            self._maybe_consolidate(sleep_decision)

        suppress_llm = bool(sleep_decision and sleep_decision.suppress_llm_calls)

        # Check for stimulus. During sleep suppression, leave the queue intact
        # so pending external/internal stimuli wait for wake without churn.
        stimulus: Optional[str] = None
        if suppress_llm:
            if self._stimulus_queue.qsize() > 0:
                logger.info(
                    "tick_stimulus_deferred_during_sleep",
                    tick=self._tick_count,
                    queue_size=self._stimulus_queue.qsize(),
                )
            else:
                self._idle_ticks += 1
        else:
            try:
                stimulus = self._stimulus_queue.get_nowait()
            except asyncio.QueueEmpty:
                self._idle_ticks += 1

        # Save pre-tick state for diff
        pre_state = copy.deepcopy(self.runtime_state)

        # Process stimulus if present
        result: Optional[Dict[str, Any]] = None
        if stimulus:
            self._idle_ticks = 0
            logger.info(
                "tick_processing", tick=self._tick_count, stimulus=stimulus[:100]
            )
            # Run blocking agent calls in a thread to not block the Textual event loop
            result = await asyncio.to_thread(self.team.process_stimulus_sync, stimulus)
            # Notify response callbacks
            for cb in self._response_callbacks:
                try:
                    await cb(result)
                except Exception as e:
                    logger.error("response_callback_error", error=str(e))

        # === AUTONOMOUS THINKING (no external stimulus) ===
        # Skip entirely while asleep — no internal monologue, no spontaneous
        # thoughts. The system needs rest.
        if not stimulus and self._idle_ticks > 0 and not suppress_llm:
            goal_pursuit_enqueued = await self._maybe_enqueue_goal_pursuit()
            # Keep idle_ticks until the queued goal stimulus is consumed on the
            # next tick; that preserves pursuit debounce semantics.

            # Self-reflection (every 5 idle ticks)
            if (
                not goal_pursuit_enqueued
                and self._idle_ticks % self._reflection_interval == 0
                and getattr(self.flags, "self_reflection_enabled", True)
            ):
                logger.info("self_reflection_triggered", idle_ticks=self._idle_ticks)
                reflection = await asyncio.to_thread(self.team.reflect_sync)
                if reflection:
                    for cb in self._reflection_callbacks:
                        try:
                            await cb(reflection)
                        except Exception as e:
                            logger.error("reflection_callback_error", error=str(e))

                    # Internal stimulus: reflection wants to think deeper about something
                    internal_stim = reflection.get("internal_stimulus")
                    if (
                        internal_stim
                        and getattr(self.flags, "internal_stimulus_enabled", True)
                    ):
                        logger.info("internal_stimulus_generated", stimulus=internal_stim[:100])
                        await self._stimulus_queue.put(f"[internal] {internal_stim}")

            # Spontaneous thoughts (every 3 idle ticks, but not on reflection ticks)
            elif (
                not goal_pursuit_enqueued
                and self._idle_ticks % 3 == 0
                and getattr(self.flags, "autonomous_thoughts_enabled", True)
            ):
                logger.info("spontaneous_thought_triggered", idle_ticks=self._idle_ticks)
                thought = await asyncio.to_thread(self.team.spontaneous_thought_sync)
                if thought:
                    for cb in self._reflection_callbacks:
                        try:
                            await cb(thought)
                        except Exception as e:
                            logger.error("thought_callback_error", error=str(e))

        # Record state journal (every tick)
        self.team.record_state_snapshot()

        # Hysteresis decay (every tick, even idle)
        if self.flags.hysteresis_enabled:
            self.hysteresis.tick(dt, reference_interval=self.settings.consciousness_loop.tick_interval_sec)

        # Compute runtime delta from hysteresis
        if self.flags.runtime_effects_enabled:
            # Soft decay toward defaults — preserves accumulated effects across ticks
            defaults = self._runtime_defaults
            if defaults:
                self.runtime_state.decay_toward_defaults(defaults, rate=0.1)

            delta = self.hysteresis.compute_runtime_delta(self.flags)
            if delta:
                self.runtime_state.apply_delta(delta)
                logger.info("runtime_delta_applied", delta=delta)

        # Feedback loops: if enabled, let runtime state AND channels influence each other
        if self.flags.feedback_loops_enabled:
            # Low energy → fatigue builds
            if self.runtime_state.energy_level < 0.5:
                gated_stimulate(
                    self.hysteresis,
                    self.governance,
                    agent="FeedbackLoop",
                    channel="fatigue",
                    intensity=0.15 * (1.0 - self.runtime_state.energy_level),
                    tick=self._tick_count,
                    reason="low_energy",
                )
            # Fragmented attention → stress builds
            if self.runtime_state.attention_focus < 0.6:
                gated_stimulate(
                    self.hysteresis,
                    self.governance,
                    agent="FeedbackLoop",
                    channel="stress",
                    intensity=0.1 * (1.0 - self.runtime_state.attention_focus),
                    tick=self._tick_count,
                    reason="fragmented_attention",
                )

            # Cross-channel cascades (like real consciousness):
            # Prolonged stress → burnout (fatigue)
            stress_ch = self.hysteresis.channels.get("stress")
            if stress_ch and stress_ch.value > 0.6:
                gated_stimulate(
                    self.hysteresis,
                    self.governance,
                    agent="FeedbackLoop",
                    channel="fatigue",
                    intensity=0.1 * stress_ch.value,
                    tick=self._tick_count,
                    reason="prolonged_stress",
                )
            # Prolonged pain → amplifies stress
            pain_ch = self.hysteresis.channels.get("pain")
            if pain_ch and pain_ch.value > 0.4:
                gated_stimulate(
                    self.hysteresis,
                    self.governance,
                    agent="FeedbackLoop",
                    channel="stress",
                    intensity=0.08 * pain_ch.value,
                    tick=self._tick_count,
                    reason="prolonged_pain",
                )

        # Stage 3 — circuit breaker observation (after all stim + decay this tick)
        if self.flags.circuit_breaker_enabled:
            for ch_name, ch in self.hysteresis.channels.items():
                self.circuit_breaker.observe(ch_name, ch.value, self._tick_count)

        # Stage 12 — ML regulators observation + recovery proposal
        ml_payload: Dict[str, Any] = {}
        if self.flags.ml_regulators_enabled:
            rumination_sig: Optional[RuminationSignal] = None
            collapse_sigs: List[CollapseSignal] = []

            # Rumination: feed the most recent emotion (or "idle" as default)
            try:
                last_emo = (
                    self.team.emotion_history[-1].get("primary_emotion", "idle")
                    if self.team.emotion_history
                    else "idle"
                )
                rumination_sig = self.rumination_detector.observe(last_emo, self._tick_count)
            except Exception as e:
                logger.warning("rumination_observe_failed", error=str(e))

            # Collapse forecaster: per-channel
            try:
                for ch_name, ch in self.hysteresis.channels.items():
                    collapse_sigs.append(
                        self.collapse_forecaster.observe(
                            ch_name, ch.value, self._tick_count
                        )
                    )
            except Exception as e:
                logger.warning("collapse_observe_failed", error=str(e))

            # Recovery proposal — loop applies it opportunistically
            try:
                decision = self.recovery_policy.propose(
                    rumination=rumination_sig,
                    collapse=collapse_sigs,
                    runtime_state=self.runtime_state.to_dict(),
                )
                self._apply_recovery(decision)
            except Exception as e:
                logger.warning("recovery_propose_failed", error=str(e))
                decision = None

            ml_payload = {
                "rumination": (
                    {
                        "level": rumination_sig.level.value,
                        "entropy": rumination_sig.entropy,
                    }
                    if rumination_sig
                    else None
                ),
                "collapse_worst": (
                    {
                        "level": max(
                            collapse_sigs, key=lambda s: s.level.value
                        ).level.value,
                    }
                    if collapse_sigs
                    else None
                ),
                "recovery_action": (decision.action.value if decision else None),
            }

        self.runtime_state.clamp()

        # Compute and log diff
        state_diff = self.runtime_state.diff(pre_state)

        # Stage 3 — close governance tick window, get aggregated stats
        governance_stats: Dict[str, Any] = {}
        if self.flags.governance_enabled:
            governance_stats = self.governance.end_tick(self._tick_count)

        # Emit state snapshot
        snapshot = {
            "tick": self._tick_count,
            "idle_ticks": self._idle_ticks,
            "runtime_state": self.runtime_state.to_dict(),
            "hysteresis": self.hysteresis.to_dict(),
            "active_channels": self.hysteresis.get_active_channels(),
            "state_diff": state_diff,
            "had_stimulus": stimulus is not None,
            "governance": governance_stats,
            "circuit_breaker_tripped": self.circuit_breaker.tripped_channels(),
            "goal_stack": (
                self.goal_stack.to_dict()
                if self.flags.goal_stack_enabled
                else {"type": "disabled", "goals": []}
            ),
            "goal_pursuit": (
                self.goal_pursuit_policy.to_dict()
                if self.flags.goal_pursuit_enabled
                else {"type": "disabled"}
            ),
            # Stage 12/16 — ML regulators payload + recovery_action shortcut
            # (used by ml.dataset.build_dataset_from_event_store)
            "ml": ml_payload,
            "recovery_action": ml_payload.get("recovery_action"),
        }

        await self.event_bus.emit(EventType.STATE_SNAPSHOT, snapshot, source="loop")

        if state_diff:
            await self.event_bus.emit(EventType.RUNTIME_CHANGE, {"diff": state_diff}, source="loop")

        # Stage 4 — persist event log + periodic checkpoint
        if self.flags.persistence_enabled:
            # Always log per-tick snapshot
            self.event_store.append(
                tick=self._tick_count,
                event_type="snapshot",
                payload=snapshot,
                source="loop",
            )
            if stimulus:
                self.event_store.append(
                    tick=self._tick_count,
                    event_type="stimulus",
                    payload={"stimulus": stimulus, "result": (result or {}).get("response", "")[:500]},
                    source="loop",
                )
            if state_diff:
                self.event_store.append(
                    tick=self._tick_count,
                    event_type="runtime_change",
                    payload={"diff": state_diff},
                    source="loop",
                )
            # Full checkpoint every N ticks
            if self._checkpoint_every_ticks > 0 and self._tick_count % self._checkpoint_every_ticks == 0:
                try:
                    self.checkpoint.save(self._build_snapshot())
                    keep = self.settings.persistence.keep_last_n_snapshots
                    if keep > 0 and self._tick_count > keep * self._checkpoint_every_ticks:
                        prune_before = self._tick_count - (keep - 1) * self._checkpoint_every_ticks
                        self.checkpoint.prune(prune_before)
                except Exception as e:
                    logger.error("checkpoint_save_failed", error=str(e), tick=self._tick_count)

        # Log tick
        log_data = {
            "tick": self._tick_count,
            "idle": self._idle_ticks,
            "active_channels": self.hysteresis.get_active_channels(),
        }
        if state_diff:
            log_data["state_diff"] = state_diff
        if result:
            log_data["response"] = result.get("response", "")[:200]
        if governance_stats.get("decisions"):
            log_data["governance_decisions"] = governance_stats["decisions"]
        if self.circuit_breaker.is_tripped():
            log_data["circuit_breaker_tripped"] = self.circuit_breaker.tripped_channels()

        logger.info("tick_complete", **log_data)

        # Stage 7 — emit metrics for the dashboard
        try:
            self.observability.record_metric("consciousness.ticks", 1.0)
            for ch_name, ch in self.hysteresis.channels.items():
                self.observability.record_metric(
                    "consciousness.hysteresis.value",
                    float(ch.value),
                    attributes={"channel": ch_name},
                )
        except Exception:
            pass

    def _compute_max_tokens(self) -> int:
        """Compute current max_tokens from vitality (energy + bandwidth)."""
        vitality = (self.runtime_state.energy_level + self.runtime_state.bandwidth) / 2.0
        return max(64, min(2048, int(1024 * vitality)))

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current full state snapshot."""
        rt = self.runtime_state.to_dict()
        rt["max_tokens"] = self._compute_max_tokens()
        return {
            "tick": self._tick_count,
            "running": self._running,
            "idle_ticks": self._idle_ticks,
            "queue_size": self._stimulus_queue.qsize(),
            "runtime_state": rt,
            "hysteresis": self.hysteresis.to_dict(),
            "active_channels": self.hysteresis.get_active_channels(),
            "flags": self.flags.to_dict(),
            "governance": self.governance.to_dict(),
            "circuit_breaker": self.circuit_breaker.to_dict(),
            "goal_stack": self.goal_stack.to_dict(),
            "goal_pursuit": self.goal_pursuit_policy.to_dict(),
        }
