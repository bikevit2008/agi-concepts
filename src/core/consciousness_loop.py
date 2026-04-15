from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional

import structlog

from src.config.flags import FeatureFlags
from src.config.settings import RuntimeDefaults, Settings
from src.core.event_bus import EventBus, EventType
from src.core.hysteresis import HysteresisEngine
from src.core.runtime_state import RuntimeState
from src.team.consciousness_team import ConsciousnessTeam

logger = structlog.get_logger("consciousness.loop")


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
    hysteresis: HysteresisEngine
    event_bus: EventBus
    team: ConsciousnessTeam

    # Internal
    _tick_count: int = 0
    _idle_ticks: int = 0
    _running: bool = False
    _stimulus_queue: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    _response_callbacks: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = field(default_factory=list)
    _reflection_callbacks: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = field(default_factory=list)
    _runtime_defaults: Optional[RuntimeDefaults] = None
    _reflection_interval: int = 5

    def __post_init__(self) -> None:
        self._runtime_defaults = copy.deepcopy(self.settings.runtime_state)

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
            logger.info("loop_stopped", total_ticks=self._tick_count)

    def stop(self) -> None:
        """Signal the loop to stop."""
        self._running = False

    async def _tick(self) -> None:
        """Execute one tick of the consciousness loop."""
        self._tick_count += 1

        try:
            await self._tick_inner()
        except Exception as e:
            logger.error("tick_error", tick=self._tick_count, error=str(e))

    async def _tick_inner(self) -> None:
        """Inner tick logic, separated so _tick can catch all errors."""
        # Check for stimulus
        stimulus: Optional[str] = None
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
            logger.info("tick_processing", tick=self._tick_count, stimulus=stimulus[:100])
            # Run blocking agent calls in a thread to not block the Textual event loop
            result = await asyncio.to_thread(self.team.process_stimulus_sync, stimulus)
            # Notify response callbacks
            for cb in self._response_callbacks:
                try:
                    await cb(result)
                except Exception as e:
                    logger.error("response_callback_error", error=str(e))

        # === AUTONOMOUS THINKING (no external stimulus) ===
        if not stimulus and self._idle_ticks > 0:

            # Self-reflection (every 5 idle ticks)
            if (
                self._idle_ticks % self._reflection_interval == 0
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
                self._idle_ticks % 3 == 0
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
            self.hysteresis.tick()

        # Compute runtime delta from hysteresis
        if self.flags.runtime_effects_enabled:
            # Reset to defaults first, then apply hysteresis effects
            defaults = self._runtime_defaults
            if defaults:
                self.runtime_state.temperature = defaults.temperature
                self.runtime_state.context_window = defaults.context_window
                self.runtime_state.processing_latency = defaults.processing_latency
                self.runtime_state.bandwidth = defaults.bandwidth
                self.runtime_state.attention_focus = defaults.attention_focus
                self.runtime_state.energy_level = defaults.energy_level

            delta = self.hysteresis.compute_runtime_delta(self.flags)
            if delta:
                self.runtime_state.apply_delta(delta)
                logger.info("runtime_delta_applied", delta=delta)

        # Feedback loops: if enabled, let runtime state AND channels influence each other
        if self.flags.feedback_loops_enabled:
            # Low energy → fatigue builds
            if self.runtime_state.energy_level < 0.5:
                self.hysteresis.stimulate("fatigue", 0.15 * (1.0 - self.runtime_state.energy_level))
            # Fragmented attention → stress builds
            if self.runtime_state.attention_focus < 0.6:
                self.hysteresis.stimulate("stress", 0.1 * (1.0 - self.runtime_state.attention_focus))

            # Cross-channel cascades (like real consciousness):
            # Prolonged stress → burnout (fatigue)
            stress_ch = self.hysteresis.channels.get("stress")
            if stress_ch and stress_ch.value > 0.6:
                self.hysteresis.stimulate("fatigue", 0.1 * stress_ch.value)
            # Prolonged pain → amplifies stress
            pain_ch = self.hysteresis.channels.get("pain")
            if pain_ch and pain_ch.value > 0.4:
                self.hysteresis.stimulate("stress", 0.08 * pain_ch.value)

        self.runtime_state.clamp()

        # Compute and log diff
        state_diff = self.runtime_state.diff(pre_state)

        # Emit state snapshot
        snapshot = {
            "tick": self._tick_count,
            "idle_ticks": self._idle_ticks,
            "runtime_state": self.runtime_state.to_dict(),
            "hysteresis": self.hysteresis.to_dict(),
            "active_channels": self.hysteresis.get_active_channels(),
            "state_diff": state_diff,
            "had_stimulus": stimulus is not None,
        }

        await self.event_bus.emit(EventType.STATE_SNAPSHOT, snapshot, source="loop")

        if state_diff:
            await self.event_bus.emit(EventType.RUNTIME_CHANGE, {"diff": state_diff}, source="loop")

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

        logger.info("tick_complete", **log_data)

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
        }
