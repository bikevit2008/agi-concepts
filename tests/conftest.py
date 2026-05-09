"""Shared pytest fixtures.

Auto-skip integration tests that need Docker if Docker isn't running.
"""

from __future__ import annotations

import os
import shutil
import socket

import pytest


def _docker_available() -> bool:
    """Best-effort detection: docker binary present + daemon socket reachable."""
    if shutil.which("docker") is None:
        return False
    socket_path = "/var/run/docker.sock"
    if os.path.exists(socket_path):
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect(socket_path)
            sock.close()
            return True
        except OSError:
            return False
    # Docker Desktop on macOS uses a different socket path; fall back to
    # connecting to the default localhost daemon port (rare).
    try:
        with socket.create_connection(("127.0.0.1", 2375), timeout=0.5):
            return True
    except OSError:
        # Last resort — `docker info` returns 0 quickly when daemon is up.
        try:
            import subprocess

            cp = subprocess.run(
                ["docker", "info"], capture_output=True, timeout=5
            )
            return cp.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_available()


def pytest_collection_modifyitems(config, items):
    """Auto-skip @pytest.mark.docker tests when Docker isn't available."""
    if _docker_available():
        return
    skip_marker = pytest.mark.skip(reason="Docker daemon not available")
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip_marker)
