from __future__ import annotations

from dataclasses import fields

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Footer, Header, Static

from src.config.flags import FeatureFlags


class FlagsScreen(ModalScreen[None]):
    """Modal screen for toggling feature flags in real-time."""

    BINDINGS = [
        ("escape", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    FlagsScreen {
        align: center middle;
    }

    #flags-container {
        width: 70;
        max-height: 80%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #flags-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(self, feature_flags: FeatureFlags) -> None:
        super().__init__()
        self.feature_flags = feature_flags

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="flags-container"):
            yield Static("Feature Flags (toggle to experiment)", id="flags-title")
            for fld in fields(self.feature_flags):
                value = getattr(self.feature_flags, fld.name)
                label = fld.name.replace("_", " ").title()
                yield Checkbox(label, value=value, id=f"flag-{fld.name}")
        yield Footer()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        flag_name = event.checkbox.id
        if flag_name and flag_name.startswith("flag-"):
            attr_name = flag_name[5:]  # strip "flag-" prefix
            if hasattr(self.feature_flags, attr_name):
                setattr(self.feature_flags, attr_name, event.value)
