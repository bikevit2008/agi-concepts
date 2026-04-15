from src.core.runtime_state import RuntimeState


def test_default_values():
    rs = RuntimeState()
    assert rs.temperature == 0.7
    assert rs.context_window == 4096
    assert rs.bandwidth == 1.0


def test_clamp_lower():
    rs = RuntimeState(temperature=-1.0, bandwidth=-0.5, energy_level=-1.0)
    rs.clamp()
    assert rs.temperature == 0.0
    assert rs.bandwidth == 0.0
    assert rs.energy_level == 0.0


def test_clamp_upper():
    rs = RuntimeState(temperature=5.0, bandwidth=2.0, energy_level=3.0)
    rs.clamp()
    assert rs.temperature == 2.0
    assert rs.bandwidth == 1.5  # euphoria can push above 1.0
    assert rs.energy_level == 1.5


def test_apply_delta():
    rs = RuntimeState(temperature=0.7, bandwidth=1.0)
    rs.apply_delta({"temperature": 0.3, "bandwidth": -0.5})
    assert abs(rs.temperature - 1.0) < 0.001
    assert abs(rs.bandwidth - 0.5) < 0.001


def test_apply_delta_clamps():
    rs = RuntimeState(bandwidth=0.1)
    rs.apply_delta({"bandwidth": -0.5})
    assert rs.bandwidth == 0.0


def test_diff():
    rs1 = RuntimeState(temperature=0.7, bandwidth=1.0)
    rs2 = RuntimeState(temperature=1.0, bandwidth=1.0)
    diff = rs2.diff(rs1)
    assert "temperature" in diff
    assert diff["temperature"]["old"] == 0.7
    assert diff["temperature"]["new"] == 1.0
    assert "bandwidth" not in diff


def test_from_dict():
    data = {"temperature": 0.5, "bandwidth": 0.8, "unknown_field": 42}
    rs = RuntimeState.from_dict(data)
    assert rs.temperature == 0.5
    assert rs.bandwidth == 0.8


def test_to_dict():
    rs = RuntimeState()
    d = rs.to_dict()
    assert "temperature" in d
    assert "bandwidth" in d
    assert len(d) == 6
