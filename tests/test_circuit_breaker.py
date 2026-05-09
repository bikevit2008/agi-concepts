"""Tests for SaturationCircuitBreaker (Stage 3).

Cover:
- Channel doesn't trip below threshold.
- Channel trips after sustained saturation.
- Once tripped, value drop below reset_below clears the trip.
- Reset() clears state for one or all channels.
- Multiple channels tracked independently.
- to_dict() exposes diagnostic state.
"""

from src.engine.circuit_breaker import SaturationCircuitBreaker


def test_no_trip_below_threshold():
    cb = SaturationCircuitBreaker(saturation_threshold=0.95, trip_after_ticks=5)
    for tick in range(100):
        # Value 0.9 < threshold 0.95 — must NEVER trip
        assert cb.observe("stress", 0.9, tick) is False
    assert not cb.is_tripped()
    assert cb.tripped_channels() == []


def test_trips_after_sustained_saturation():
    cb = SaturationCircuitBreaker(saturation_threshold=0.95, trip_after_ticks=5)
    # 4 saturated ticks — not tripped yet
    for tick in range(4):
        assert cb.observe("stress", 0.99, tick) is False
    assert not cb.is_tripped("stress")

    # 5th saturated tick — should trip on this call
    assert cb.observe("stress", 0.99, 4) is True
    assert cb.is_tripped("stress")
    assert "stress" in cb.tripped_channels()


def test_clears_on_value_drop():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=2, reset_below=0.5)
    # Trip the breaker
    cb.observe("fatigue", 0.95, 0)
    cb.observe("fatigue", 0.95, 1)
    assert cb.is_tripped("fatigue")

    # Stays tripped while value is still elevated
    cb.observe("fatigue", 0.7, 2)
    assert cb.is_tripped("fatigue")

    # Drops below reset_below — clears the trip
    cb.observe("fatigue", 0.4, 3)
    assert not cb.is_tripped("fatigue")


def test_reset_specific_channel():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=1)
    cb.observe("stress", 0.99, 0)
    assert cb.is_tripped("stress")
    cb.reset("stress")
    assert not cb.is_tripped("stress")


def test_reset_all_channels():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=1)
    cb.observe("stress", 0.99, 0)
    cb.observe("fatigue", 0.99, 0)
    assert cb.is_tripped()
    cb.reset()
    assert not cb.is_tripped()
    assert cb.tripped_channels() == []


def test_independent_channels():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=2)
    # Stress trips, fatigue doesn't
    cb.observe("stress", 0.99, 0)
    cb.observe("stress", 0.99, 1)
    cb.observe("fatigue", 0.5, 0)
    cb.observe("fatigue", 0.5, 1)
    assert cb.is_tripped("stress")
    assert not cb.is_tripped("fatigue")


def test_consecutive_counter_resets_on_drop():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=3)
    cb.observe("stress", 0.99, 0)
    cb.observe("stress", 0.99, 1)
    # Drop below threshold — counter resets
    cb.observe("stress", 0.5, 2)
    cb.observe("stress", 0.99, 3)
    cb.observe("stress", 0.99, 4)
    # Only 2 consecutive saturated ticks since reset, should NOT have tripped
    assert not cb.is_tripped("stress")


def test_to_dict_exposes_state():
    cb = SaturationCircuitBreaker(saturation_threshold=0.9, trip_after_ticks=2)
    cb.observe("stress", 0.99, 0)
    cb.observe("stress", 0.99, 1)
    state = cb.to_dict()
    assert state["type"] == "saturation"
    assert state["channels"]["stress"]["is_tripped"] is True
    assert state["channels"]["stress"]["total_trips"] == 1


def test_satisfies_contract():
    """Statically verify SaturationCircuitBreaker satisfies ICircuitBreaker."""
    from src.contracts.governance import ICircuitBreaker
    cb: ICircuitBreaker = SaturationCircuitBreaker()
    assert isinstance(cb, ICircuitBreaker)
