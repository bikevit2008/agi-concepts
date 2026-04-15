from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.config.settings import HysteresisParams


@dataclass
class HysteresisChannel:
    """Single hysteresis channel: models a persistent internal state.

    value accumulates when stimulated, decays when not.
    Only triggers effects when above threshold.
    Mimics how emotions/sensations persist and fade with inertia.
    """

    name: str
    value: float = 0.0
    decay_rate: float = 0.05
    accumulation_rate: float = 0.15
    threshold: float = 0.3

    @classmethod
    def from_params(cls, name: str, params: HysteresisParams) -> HysteresisChannel:
        return cls(
            name=name,
            decay_rate=params.decay_rate,
            accumulation_rate=params.accumulation_rate,
            threshold=params.threshold,
        )

    @property
    def is_active(self) -> bool:
        return self.value >= self.threshold

    def stimulate(self, intensity: float = 1.0) -> None:
        """Accumulate value from a stimulus.

        intensity is applied directly (e.g. 0.55 from Emotion agent adds 0.55).
        accumulation_rate acts as a minimum floor per stimulation.
        """
        self.value += max(self.accumulation_rate, intensity)
        self.value = min(1.0, self.value)

    def tick(self) -> None:
        """Decay value by one tick. Called every consciousness loop tick."""
        self.value -= self.decay_rate
        self.value = max(0.0, self.value)

    def reset(self) -> None:
        self.value = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "active": self.is_active,
            "threshold": self.threshold,
        }


@dataclass
class HysteresisEngine:
    """Manages all hysteresis channels.

    Channels: stress, euphoria, fatigue, pain.
    Each tick, all channels decay.
    External events stimulate specific channels.
    Active channels feed into RuntimeState modifications.
    """

    channels: Dict[str, HysteresisChannel] = field(default_factory=dict)

    @classmethod
    def from_settings(cls, settings: Any) -> HysteresisEngine:
        """Build engine from HysteresisSettings."""
        engine = cls()
        for channel_name in ("stress", "euphoria", "fatigue", "pain"):
            params = getattr(settings, channel_name, None)
            if params:
                engine.channels[channel_name] = HysteresisChannel.from_params(channel_name, params)
        return engine

    def tick(self) -> None:
        """Decay all channels by one tick."""
        for ch in self.channels.values():
            ch.tick()

    def stimulate(self, channel_name: str, intensity: float = 1.0) -> None:
        """Stimulate a specific channel."""
        ch = self.channels.get(channel_name)
        if ch:
            ch.stimulate(intensity)

    def get_active_channels(self) -> Dict[str, float]:
        """Return dict of channel_name -> value for all active channels."""
        return {name: ch.value for name, ch in self.channels.items() if ch.is_active}

    def compute_runtime_delta(self, flags: Any) -> Dict[str, float]:
        """Compute runtime state adjustments based on active hysteresis channels.

        Cross-channel influence — like real consciousness:
        Stress doesn't just narrow attention, it also drains energy and increases chaotic thinking.
        Pain doesn't just reduce bandwidth, it slows processing and drains energy.
        Euphoria expands perception and boosts energy.
        Fatigue dulls everything.

        Deltas accumulate additively across channels.
        """
        delta: Dict[str, float] = {}

        if not getattr(flags, "runtime_effects_enabled", True):
            return delta

        def _add(key: str, value: float) -> None:
            delta[key] = delta.get(key, 0) + value

        stress = self.channels.get("stress")
        if stress and stress.is_active and getattr(flags, "stress_narrows_context", True):
            v = stress.value
            _add("context_window", -int(2048 * v))
            _add("attention_focus", -0.3 * v)
            _add("temperature", 0.3 * v)       # stress = chaotic thinking
            _add("energy_level", -0.25 * v)     # stress drains energy

        euphoria = self.channels.get("euphoria")
        if euphoria and euphoria.is_active and getattr(flags, "emotion_affects_temperature", True):
            v = euphoria.value
            _add("temperature", 0.5 * v)        # creativity boost
            _add("context_window", int(1024 * v))  # expanded perception
            _add("energy_level", 0.3 * v)       # euphoria energizes
            _add("attention_focus", 0.2 * v)    # sharper focus

        fatigue = self.channels.get("fatigue")
        if fatigue and fatigue.is_active:
            v = fatigue.value
            _add("processing_latency", 2.0 * v)  # sluggish processing
            _add("energy_level", -0.5 * v)       # primary fatigue effect
            _add("temperature", -0.3 * v)        # dull, uncreative
            _add("attention_focus", -0.25 * v)   # can't concentrate

        pain = self.channels.get("pain")
        if pain and pain.is_active and getattr(flags, "pain_reduces_bandwidth", True):
            v = pain.value
            _add("bandwidth", -0.5 * v)
            _add("attention_focus", -0.2 * v)
            _add("energy_level", -0.3 * v)       # pain is exhausting
            _add("processing_latency", 1.0 * v)  # pain slows thinking

        return delta

    def to_dict(self) -> Dict[str, Any]:
        return {name: ch.to_dict() for name, ch in self.channels.items()}

    def reset_all(self) -> None:
        for ch in self.channels.values():
            ch.reset()
