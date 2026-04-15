import tempfile
from pathlib import Path

from src.config.flags import FeatureFlags


def test_default_flags():
    flags = FeatureFlags()
    assert flags.perception_enabled is True
    assert flags.emotion_enabled is True
    assert flags.hysteresis_enabled is True


def test_toggle():
    flags = FeatureFlags()
    new_val = flags.toggle("perception_enabled")
    assert new_val is False
    assert flags.perception_enabled is False
    new_val = flags.toggle("perception_enabled")
    assert new_val is True


def test_to_dict():
    flags = FeatureFlags()
    d = flags.to_dict()
    assert "perception_enabled" in d
    assert "emotion_affects_temperature" in d
    assert all(isinstance(v, bool) for v in d.values())


def test_from_yaml_and_save():
    flags = FeatureFlags(perception_enabled=False, stress_narrows_context=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "flags.yaml"
        flags.save_yaml(path)
        loaded = FeatureFlags.from_yaml(path)
        assert loaded.perception_enabled is False
        assert loaded.stress_narrows_context is False
        assert loaded.emotion_enabled is True


def test_from_yaml_missing_file():
    flags = FeatureFlags.from_yaml("/nonexistent/path/flags.yaml")
    assert flags.perception_enabled is True  # defaults


def test_from_yaml_ignores_unknown():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "flags.yaml"
        path.write_text("perception_enabled: false\nunknown_flag: true\n")
        flags = FeatureFlags.from_yaml(path)
        assert flags.perception_enabled is False
        assert not hasattr(flags, "unknown_flag")
