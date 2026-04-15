from __future__ import annotations

from textual.widgets import RichLog


class LogPanel(RichLog):
    """Scrollable log panel that displays consciousness system events."""

    DEFAULT_CSS = """
    LogPanel {
        height: 100%;
        border: solid $accent;
    }
    """

    def add_log_entry(self, message: str, style: str = "") -> None:
        """Add a styled log entry."""
        self.write(message)
