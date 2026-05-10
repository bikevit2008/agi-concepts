import tomllib
from pathlib import Path


def test_optional_dependency_groups_match_mvp_install_paths():
    data = tomllib.loads(Path("pyproject.toml").read_text())
    extras = data["project"]["optional-dependencies"]

    for name in [
        "core",
        "persistence",
        "memory-local",
        "memory-full",
        "memory",
        "bus",
        "observability",
        "ml",
        "tools",
        "dev",
        "mvp-local",
        "mvp-full",
        "all",
    ]:
        assert name in extras

    assert extras["persistence"] == []
    assert extras["memory-local"] == []
    assert any(dep.startswith("lancedb") for dep in extras["memory-full"])
    assert "agi-consciousness[persistence,memory-local]" in extras["mvp-local"]


def test_smoke_cli_runs_without_llm(capsys):
    from src.main import _run_smoke

    _run_smoke()
    out = capsys.readouterr().out
    assert "[smoke] ok" in out
    assert "ticks=3" in out
