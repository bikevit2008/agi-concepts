from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class FeatureFlags:
    """Feature flags for consciousness system components.

    Each flag can be toggled at runtime via TUI to run experiments
    on what truly contributes to emergent consciousness.
    """

    # Core agents
    perception_enabled: bool = True
    emotion_enabled: bool = True
    memory_enabled: bool = True
    planning_enabled: bool = True

    # Core mechanics
    hysteresis_enabled: bool = True
    runtime_effects_enabled: bool = True
    feedback_loops_enabled: bool = True

    # Inner monologue & autonomy
    self_reflection_enabled: bool = True
    autonomous_thoughts_enabled: bool = True
    internal_stimulus_enabled: bool = True

    # Experiment: emotion -> runtime mapping
    emotion_affects_temperature: bool = True
    stress_narrows_context: bool = True
    pain_reduces_bandwidth: bool = True

    @classmethod
    def from_yaml(cls, path: str | Path) -> FeatureFlags:
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            data: Dict[str, Any] = yaml.safe_load(f) or {}
        valid_fields = {fld.name for fld in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, bool]:
        return {fld.name: getattr(self, fld.name) for fld in fields(self)}

    def toggle(self, flag_name: str) -> bool:
        """Toggle a flag by name. Returns new value."""
        if not hasattr(self, flag_name):
            raise ValueError(f"Unknown flag: {flag_name}")
        new_val = not getattr(self, flag_name)
        setattr(self, flag_name, new_val)
        return new_val

    def save_yaml(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)
