from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, RichLog, Static

from src.tui.widgets.chat_input import ChatInput
from src.tui.widgets.state_panel import HysteresisPanel, RuntimeStatePanel


class MainScreen(Screen):
    """Main consciousness TUI screen: chat + state monitoring."""

    BINDINGS = [
        ("f1", "toggle_flags", "Flags"),
        ("f2", "toggle_monitor", "Monitor"),
        ("escape", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    #tick-status {
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        border: solid $surface;
        width: 100%;
    }

    #chat-area {
        height: 1fr;
        min-height: 10;
        border: solid $primary;
        width: 100%;
    }

    #bottom-panels {
        height: auto;
        max-height: 12;
        width: 100%;
    }

    #runtime-panel {
        width: 1fr;
    }

    #hysteresis-panel {
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("Consciousness System | Tick: 0 | Idle: 0", id="tick-status")
        chat = RichLog(id="chat-area", wrap=True, highlight=True, markup=True)
        chat.can_focus = False
        yield chat
        yield ChatInput(placeholder="Enter stimulus... (press Enter to submit)")
        with Horizontal(id="bottom-panels"):
            yield RuntimeStatePanel(id="runtime-panel")
            yield HysteresisPanel(id="hysteresis-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(ChatInput).focus()

    def update_tick_status(self, tick: int, idle: int, queue_size: int) -> None:
        status = self.query_one("#tick-status", Static)
        status.update(f"Tick: {tick} | Idle: {idle} | Queue: {queue_size}")

    def update_runtime_state(self, state_data: dict) -> None:
        panel = self.query_one("#runtime-panel", RuntimeStatePanel)
        panel.state_data = state_data

    def update_hysteresis(self, channels_data: dict) -> None:
        panel = self.query_one("#hysteresis-panel", HysteresisPanel)
        panel.channels_data = channels_data

    def add_chat_message(self, role: str, message: str) -> None:
        chat = self.query_one("#chat-area", RichLog)
        if role == "user":
            chat.write(f"[bold cyan]> {message}[/]")
        elif role == "system":
            chat.write(f"[bold green]{message}[/]")
        elif role == "reflection":
            chat.write(f"[bold magenta]~ {message}[/]")
        elif role == "thought":
            chat.write(f"[dim yellow]... {message}[/]")
        elif role == "error":
            chat.write(f"[bold red]{message}[/]")
        else:
            chat.write(message)

    def action_toggle_flags(self) -> None:
        self.app.action_toggle_flags()

    def action_toggle_monitor(self) -> None:
        self.app.action_toggle_monitor()

    def action_quit(self) -> None:
        self.app.exit()
