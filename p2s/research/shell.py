"""Cross-platform shell dispatch for research lifecycle commands.

The retained experiments were driven from Git Bash on Windows and use Bash
syntax (inline environment assignments, ``2>/dev/null``, ``|| true``).  Python's
``shell=True`` chooses ``cmd.exe`` on Windows, so the framework explicitly
prefers Bash when it is available.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def find_bash() -> str | None:
    candidate = shutil.which("bash")
    if candidate:
        return candidate
    if os.name == "nt":
        for value in (
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Git\bin\bash.exe"),
        ):
            if os.path.exists(value):
                return value
    return None


def run_shell(
    command: str,
    *,
    cwd: str | os.PathLike[str] | None = None,
    check: bool = True,
    text: bool = True,
    stdout: Any = None,
    stderr: Any = None,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    bash = find_bash()
    if bash:
        return subprocess.run(
            [bash, "-lc", command],
            check=check,
            cwd=str(Path(cwd)) if cwd else None,
            text=text,
            stdout=stdout,
            stderr=stderr,
            capture_output=capture_output,
            env=env,
        )
    return subprocess.run(
        command,
        shell=True,
        check=check,
        cwd=str(Path(cwd)) if cwd else None,
        text=text,
        stdout=stdout,
        stderr=stderr,
        capture_output=capture_output,
        env=env,
    )


__all__ = ["find_bash", "run_shell"]
