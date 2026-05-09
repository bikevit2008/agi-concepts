"""Smoke tests for CLI scripts in `scripts/`."""

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run(module_path: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / module_path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_ablation_text_mode():
    cp = _run("scripts/run_ablation.py", "--ticks", "20")
    assert cp.returncode == 0, cp.stderr
    # Human-readable output contains the table header
    assert "Ablation summary" in cp.stdout
    assert "baseline" in cp.stdout


def test_run_ablation_json_mode():
    cp = _run("scripts/run_ablation.py", "--ticks", "20", "--json")
    assert cp.returncode == 0, cp.stderr
    data = json.loads(cp.stdout)
    assert data["ticks"] == 20
    assert any(a["name"] == "baseline" for a in data["ablations"])


def test_run_falsifiable_text_mode():
    cp = _run("scripts/run_falsifiable.py", "--ticks", "30")
    assert cp.returncode == 0, cp.stderr
    assert "Falsifiable test results" in cp.stdout


def test_run_falsifiable_json_mode():
    cp = _run("scripts/run_falsifiable.py", "--ticks", "30", "--json")
    assert cp.returncode == 0, cp.stderr
    data = json.loads(cp.stdout)
    assert data["ticks"] == 30
    assert len(data["results"]) == 3


def test_main_cli_version():
    cp = subprocess.run(
        [sys.executable, "-m", "src.main", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert cp.returncode == 0
    assert "agi-consciousness" in cp.stdout
