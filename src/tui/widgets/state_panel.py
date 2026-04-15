from __future__ import annotations

from typing import Any, Dict

from rich.table import Table
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class RuntimeStatePanel(Static):
    """Displays current runtime state as a live-updating panel."""

    state_data: reactive[Dict[str, Any]] = reactive({})

    def render(self) -> Table:
        table = Table(title="Runtime State", expand=True, show_header=True)
        table.add_column("Parameter", style="cyan", ratio=2)
        table.add_column("Value", style="white", ratio=1)
        table.add_column("Bar", ratio=3)

        data = self.state_data
        if not data:
            table.add_row("No data", "-", "")
            return table

        params = [
            ("temperature", 0.0, 2.0, "yellow"),
            ("context_window", 256, 128000, "blue"),
            ("max_tokens", 64, 2048, "bright_blue"),
            ("processing_latency", 0.0, 5.0, "red"),
            ("bandwidth", 0.0, 1.5, "green"),
            ("attention_focus", 0.0, 1.5, "magenta"),
            ("energy_level", 0.0, 1.5, "cyan"),
        ]

        for name, min_v, max_v, color in params:
            val = data.get(name, 0)
            if isinstance(val, float):
                val_str = f"{val:.3f}"
            else:
                val_str = str(val)

            # Normalize for bar
            if max_v > min_v:
                norm = (float(val) - min_v) / (max_v - min_v)
            else:
                norm = 0.0
            norm = max(0.0, min(1.0, norm))
            bar_len = int(norm * 20)
            bar = Text(f"{'#' * bar_len}{'.' * (20 - bar_len)}", style=color)

            table.add_row(name, val_str, bar)

        return table


class HysteresisPanel(Static):
    """Displays hysteresis channel states."""

    channels_data: reactive[Dict[str, Any]] = reactive({})

    def render(self) -> Table:
        table = Table(title="Hysteresis Channels", expand=True, show_header=True)
        table.add_column("Channel", style="cyan", ratio=2)
        table.add_column("Value", style="white", ratio=1)
        table.add_column("Active", ratio=1)
        table.add_column("Bar", ratio=3)

        data = self.channels_data
        if not data:
            table.add_row("No channels", "-", "-", "")
            return table

        colors = {"stress": "red", "euphoria": "green", "fatigue": "yellow", "pain": "magenta"}

        for name, ch_data in data.items():
            if isinstance(ch_data, dict):
                val = ch_data.get("value", 0.0)
                active = ch_data.get("active", False)
                color = colors.get(name, "white")

                bar_len = int(float(val) * 20)
                bar = Text(f"{'#' * bar_len}{'.' * (20 - bar_len)}", style=color)
                active_text = Text("ON", style="bold green") if active else Text("off", style="dim")

                table.add_row(name, f"{val:.3f}", active_text, bar)

        return table
