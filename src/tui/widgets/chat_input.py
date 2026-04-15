from __future__ import annotations

from textual.events import Key
from textual.message import Message
from textual.widgets import Input


class ChatInput(Input):
    """Input widget for submitting stimuli to the consciousness system."""

    DEFAULT_CSS = """
    ChatInput {
        dock: bottom;
        margin: 0 1;
    }
    """

    class StimulusSubmitted(Message):
        """Emitted when user submits a stimulus."""

        def __init__(self, stimulus: str) -> None:
            self.stimulus = stimulus
            super().__init__()

    def _on_key(self, event: Key) -> None:
        if event.key == "space":
            event.stop()
            event.prevent_default()
            self.insert_text_at_cursor(" ")
            return
        super()._on_key(event)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(self.StimulusSubmitted(text))
            self.clear()
