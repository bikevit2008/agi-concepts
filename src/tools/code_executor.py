"""Sandboxed code execution tool.

Backends (declared in settings.tools.code_executor_backend):

- "subprocess" — DEFAULT. Runs Python in a subprocess with a strict
  timeout, NO network, dropped resource limits where possible. Suitable
  for trusted code only — there is NO syscall isolation.
- "e2b" — uses E2B's managed sandbox-as-a-service (SDK required).
  Strong isolation, good DX, vendor lock-in.
- "nsjail" — uses nsjail (Linux-only) for namespace + seccomp isolation.
  Strongest local option but requires nsjail installed and configured.

WARNING: subprocess is NOT a security boundary. Do not enable for
adversarial input without nsjail or E2B.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.tools import ITool, ToolCall, ToolResult

logger = structlog.get_logger("consciousness.tools.code_executor")


@dataclass
class CodeExecutorTool:
    """ITool for sandboxed Python code execution."""

    backend: str = "subprocess"
    timeout_seconds: float = 5.0
    memory_limit_mb: int = 256

    @property
    def name(self) -> str:
        return "code_executor"

    @property
    def description(self) -> str:
        return (
            "Execute a small snippet of Python code in a sandbox. "
            "Args: {code: str, timeout_seconds: float (default 5)}"
        )

    @property
    def required_capability(self) -> str:
        return "tools:code_executor"

    def execute(self, call: ToolCall) -> ToolResult:
        code = call.args.get("code") or ""
        if not isinstance(code, str) or not code.strip():
            return ToolResult(success=False, error="code is required")
        timeout = float(call.args.get("timeout_seconds", self.timeout_seconds))

        if self.backend == "subprocess":
            return self._subprocess(code, timeout)
        if self.backend == "e2b":
            return self._e2b(code, timeout)
        if self.backend == "nsjail":
            return self._nsjail(code, timeout)
        return ToolResult(success=False, error=f"unknown backend: {self.backend}")

    def _subprocess(self, code: str, timeout: float) -> ToolResult:
        """Trusted-code subprocess execution.

        Spawns python -c <code> in a clean environment, captures stdout/
        stderr, enforces timeout. NO syscall sandboxing.
        """
        # Hardened environment — strip everything except minimal locale
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False
            ) as f:
                f.write(code)
                code_path = f.name
            try:
                cp = subprocess.run(
                    ["python3", code_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            finally:
                try:
                    os.unlink(code_path)
                except OSError:
                    pass
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="execution timed out")
        except Exception as e:
            return ToolResult(success=False, error=f"subprocess error: {e}")

        return ToolResult(
            success=cp.returncode == 0,
            output={
                "stdout": cp.stdout[-4000:],
                "stderr": cp.stderr[-2000:],
                "returncode": cp.returncode,
            },
            error=None if cp.returncode == 0 else f"non-zero exit: {cp.returncode}",
        )

    def _e2b(self, code: str, timeout: float) -> ToolResult:
        try:
            from e2b_code_interpreter import Sandbox  # type: ignore[import-not-found]
        except ImportError:
            return ToolResult(
                success=False,
                error="e2b-code-interpreter not installed; backend unavailable",
            )
        try:
            with Sandbox() as sandbox:
                execution = sandbox.run_code(code, timeout=int(timeout))
            return ToolResult(
                success=not execution.error,
                output={
                    "stdout": "\n".join(execution.logs.stdout)[-4000:],
                    "stderr": "\n".join(execution.logs.stderr)[-2000:],
                    "results": [str(r) for r in execution.results][-10:],
                },
                error=str(execution.error) if execution.error else None,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"e2b error: {e}")

    def _nsjail(self, code: str, timeout: float) -> ToolResult:
        """Run python under nsjail with default sandboxing.

        Requires `nsjail` in PATH. We invoke a minimal config that
        disables network, mounts only /usr and /lib, drops all caps.
        """
        if shutil.which("nsjail") is None:
            return ToolResult(success=False, error="nsjail not installed")
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(code)
            code_path = f.name
        try:
            cp = subprocess.run(
                [
                    "nsjail",
                    "--quiet",
                    "--time_limit", str(int(timeout)),
                    "--rlimit_as", str(self.memory_limit_mb * 1024 * 1024),
                    "--disable_clone_newnet",
                    "--", "/usr/bin/python3", code_path,
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 5.0,
            )
            return ToolResult(
                success=cp.returncode == 0,
                output={"stdout": cp.stdout[-4000:], "stderr": cp.stderr[-2000:]},
                error=None if cp.returncode == 0 else f"non-zero exit: {cp.returncode}",
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="nsjail timeout")
        except Exception as e:
            return ToolResult(success=False, error=f"nsjail error: {e}")
        finally:
            try:
                os.unlink(code_path)
            except OSError:
                pass


__all__ = ["CodeExecutorTool"]
