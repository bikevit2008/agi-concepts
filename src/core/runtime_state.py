from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Dict


@dataclass
class RuntimeState:
    """Runtime parameters that affect agent behavior.

    These are the "hardware" layer of consciousness:
    emotions and sensations modify these values,
    which in turn change how agents think and respond.

    temperature     -- LLM generation creativity (0.0-2.0)
    context_window  -- effective context window size (tokens)
    processing_latency -- additional delay per tick (seconds)
    bandwidth       -- bus throughput capacity (0.0-1.0)
    attention_focus -- focus quality (0.0-1.0), low = fragmented
    energy_level    -- available compute energy (0.0-1.0)
    """

    temperature: float = 0.7
    context_window: int = 4096
    processing_latency: float = 0.0
    bandwidth: float = 1.0
    attention_focus: float = 1.0
    energy_level: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RuntimeState:
        valid = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in valid})

    def clamp(self) -> None:
        """Clamp all values to valid ranges."""
        self.temperature = max(0.0, min(2.0, self.temperature))
        self.context_window = max(256, min(128_000, self.context_window))
        self.processing_latency = max(0.0, min(30.0, self.processing_latency))
        self.bandwidth = max(0.0, min(1.5, self.bandwidth))
        self.attention_focus = max(0.0, min(1.5, self.attention_focus))
        self.energy_level = max(0.0, min(1.5, self.energy_level))

    def apply_delta(self, delta: Dict[str, float]) -> None:
        """Apply incremental changes to runtime state."""
        for key, value in delta.items():
            if hasattr(self, key):
                current = getattr(self, key)
                if isinstance(current, int):
                    setattr(self, key, current + int(value))
                else:
                    setattr(self, key, current + value)
        self.clamp()

    def diff(self, other: RuntimeState) -> Dict[str, Any]:
        """Return dict of fields that differ between self and other."""
        result: Dict[str, Any] = {}
        for fld in fields(self):
            v_self = getattr(self, fld.name)
            v_other = getattr(other, fld.name)
            if v_self != v_other:
                result[fld.name] = {"old": v_other, "new": v_self}
        return result
