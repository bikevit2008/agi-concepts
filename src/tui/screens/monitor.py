from __future__ import annotations

from typing import Any, Dict, List

from rich.table import Table
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Static


class MonitorScreen(ModalScreen[None]):
    """Modal screen showing detailed event history and state."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    MonitorScreen {
        align: center middle;
    }

    #monitor-container {
        width: 90%;
        max-height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #monitor-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(self, events: List[Dict[str, Any]], snapshot: Dict[str, Any]) -> None:
        super().__init__()
        self.events = events
        self.snapshot = snapshot

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="monitor-container"):
            yield Static("Consciousness Monitor", id="monitor-title")
            yield Static(self._render_snapshot())
            yield Static(self._render_events())
        yield Footer()

    def _render_snapshot(self) -> Table:
        table = Table(title="Current State Snapshot", expand=True)
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="white")

        for key, value in self.snapshot.items():
            if isinstance(value, dict):
                for k, v in value.items():
                    table.add_row(f"  {key}.{k}", str(v))
            else:
                table.add_row(key, str(value))

        return table

    def _render_events(self) -> Table:
        table = Table(title="Recent Events (last 20)", expand=True)
        table.add_column("Time", style="dim", ratio=2)
        table.add_column("Type", style="cyan", ratio=1)
        table.add_column("Source", style="yellow", ratio=1)
        table.add_column("Data", ratio=4)

        for event in self.events[-20:]:
            ts = event.get("timestamp", "")[-12:]
            etype = event.get("type", "")
            source = event.get("source", "")
            data = str(event.get("data", ""))[:80]
            table.add_row(ts, etype, source, data)

        return table
