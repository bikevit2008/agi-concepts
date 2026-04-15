from __future__ import annotations

import asyncio
from typing import Any, Dict

from textual.app import App

from src.config.flags import FeatureFlags
from src.config.loader import load_flags, load_settings
from src.config.settings import Settings
from src.core.consciousness_loop import ConsciousnessLoop
from src.core.event_bus import EventBus, EventType
from src.core.hysteresis import HysteresisEngine
from src.core.runtime_state import RuntimeState
from src.logging.setup import get_logger, setup_logging
from src.team.consciousness_team import ConsciousnessTeam
from src.tui.screens.flags import FlagsScreen
from src.tui.screens.main import MainScreen
from src.tui.screens.monitor import MonitorScreen
from src.tui.widgets.chat_input import ChatInput

logger = get_logger("consciousness.tui")


class ConsciousnessApp(App):
    """Textual TUI application for the consciousness system."""

    TITLE = "AGI Consciousness PoC"
    SUB_TITLE = "Processual Consciousness Model"

    CSS = """
    Screen {
        background: $surface;
    }
    """

    SCREENS = {"main": MainScreen}

    def __init__(self) -> None:
        super().__init__()
        self.settings: Settings = load_settings()
        self.flags: FeatureFlags = load_flags()
        self.event_bus = EventBus()
        self.runtime_state = RuntimeState.from_dict(
            {
                "temperature": self.settings.runtime_state.temperature,
                "context_window": self.settings.runtime_state.context_window,
                "processing_latency": self.settings.runtime_state.processing_latency,
                "bandwidth": self.settings.runtime_state.bandwidth,
                "attention_focus": self.settings.runtime_state.attention_focus,
                "energy_level": self.settings.runtime_state.energy_level,
            }
        )
        self.hysteresis = HysteresisEngine.from_settings(self.settings.hysteresis)
        self.team = ConsciousnessTeam(
            model_settings=self.settings.model,
            runtime_state=self.runtime_state,
            hysteresis=self.hysteresis,
            flags=self.flags,
            event_bus=self.event_bus,
        )
        self.consciousness_loop = ConsciousnessLoop(
            settings=self.settings,
            flags=self.flags,
            runtime_state=self.runtime_state,
            hysteresis=self.hysteresis,
            event_bus=self.event_bus,
            team=self.team,
        )
        self._loop_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None

    async def on_mount(self) -> None:
        # Setup logging
        setup_logging(
            level=self.settings.logging.level,
            json_dir=self.settings.logging.json_dir,
            console_enabled=False,  # TUI handles console output
        )

        # Register response callback
        self.consciousness_loop.on_response(self._on_consciousness_response)
        self.consciousness_loop.on_reflection(self._on_reflection)

        # Subscribe to state snapshots for TUI updates
        self.event_bus.subscribe(EventType.STATE_SNAPSHOT, self._on_state_snapshot)

        # Push main screen
        await self.push_screen(MainScreen())

        # Start consciousness loop
        self._loop_task = asyncio.create_task(self.consciousness_loop.start())

        # Start monitor update loop
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def _on_reflection(self, data: Dict[str, Any]) -> None:
        """Handle inner monologue reflection or spontaneous thought."""
        try:
            screen = self.screen
            if not isinstance(screen, MainScreen):
                return

            # Spontaneous thought (from Planning agent)
            if data.get("_type") == "spontaneous_thought":
                response = data.get("response", "")
                if response:
                    screen.add_chat_message("thought", response)
                return

            # Reflection (from Reflection agent)
            thought = data.get("thought", "")
            mood = data.get("mood_assessment", "")
            insight = data.get("insight", "")
            internal = data.get("internal_stimulus", "")
            parts = [thought]
            if mood:
                parts.append(f"[{mood}]")
            if insight:
                parts.append(f"-- {insight}")
            if internal:
                parts.append(f">> {internal}")
            screen.add_chat_message("reflection", " ".join(parts))
        except Exception as e:
            logger.error("tui_reflection_error", error=str(e))

    async def _on_consciousness_response(self, result: Dict[str, Any]) -> None:
        """Handle response from consciousness pipeline."""
        try:
            screen = self.screen
            if isinstance(screen, MainScreen):
                response = result.get("response", "")
                self.call_from_thread(screen.add_chat_message, "system", response) if False else screen.add_chat_message("system", response)

                # Log agent pipeline details
                for agent_name in ("perception", "emotion", "memory", "planning"):
                    if agent_name in result:
                        data = result[agent_name]
                        if isinstance(data, dict):
                            summary = f"[dim][{agent_name}] {_summarize_agent_result(agent_name, data)}[/]"
                        else:
                            summary = f"[dim][{agent_name}] {str(data)[:100]}[/]"
                        screen.add_chat_message("info", summary)
        except Exception as e:
            logger.error("tui_response_error", error=str(e))

    async def _on_state_snapshot(self, event: Any) -> None:
        """Update TUI panels from state snapshot."""
        try:
            screen = self.screen
            if isinstance(screen, MainScreen):
                data = event.data
                screen.update_tick_status(
                    tick=data.get("tick", 0),
                    idle=data.get("idle_ticks", 0),
                    queue_size=0,
                )
                rt = data.get("runtime_state", {})
                if rt:
                    screen.update_runtime_state(rt)
                hyst = data.get("hysteresis", {})
                if hyst:
                    screen.update_hysteresis(hyst)
        except Exception:
            pass

    async def _monitor_loop(self) -> None:
        """Periodic TUI refresh for responsiveness."""
        while True:
            try:
                await asyncio.sleep(1.0)
                screen = self.screen
                if isinstance(screen, MainScreen):
                    snapshot = self.consciousness_loop.get_state_snapshot()
                    screen.update_tick_status(
                        tick=snapshot.get("tick", 0),
                        idle=snapshot.get("idle_ticks", 0),
                        queue_size=snapshot.get("queue_size", 0),
                    )
                    screen.update_runtime_state(snapshot.get("runtime_state", {}))
                    screen.update_hysteresis(snapshot.get("hysteresis", {}))
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def on_chat_input_stimulus_submitted(self, message: ChatInput.StimulusSubmitted) -> None:
        """Handle stimulus submission from chat input."""
        screen = self.screen
        if isinstance(screen, MainScreen):
            screen.add_chat_message("user", message.stimulus)
        await self.consciousness_loop.submit_stimulus(message.stimulus)

    def action_toggle_flags(self) -> None:
        self.push_screen(FlagsScreen(self.flags))

    def action_toggle_monitor(self) -> None:
        events = self.event_bus.get_history(limit=30)
        snapshot = self.consciousness_loop.get_state_snapshot()
        self.push_screen(MonitorScreen(events, snapshot))

    async def on_unmount(self) -> None:
        self.consciousness_loop.stop()
        if self._loop_task:
            self._loop_task.cancel()
        if self._monitor_task:
            self._monitor_task.cancel()


def _summarize_agent_result(agent_name: str, data: dict) -> str:
    """Create a brief summary of agent result for chat display."""
    if agent_name == "perception":
        return f"type={data.get('stimulus_type', '?')}, valence={data.get('emotional_valence', '?')}, urgency={data.get('urgency', '?')}"
    elif agent_name == "emotion":
        return f"{data.get('primary_emotion', '?')} (intensity={data.get('intensity', '?')}, valence={data.get('valence', '?')})"
    elif agent_name == "memory":
        recalled = data.get("recalled_memories", [])
        return f"recalled={len(recalled)}, new={'yes' if data.get('new_memory_to_store') else 'no'}"
    elif agent_name == "planning":
        return f"intent={data.get('intent', '?')}, confidence={data.get('confidence', '?')}"
    return str(data)[:80]
