"""wsl — WSL2 read-only bridge for mining agents inside Ubuntu.

The main harness runs in WSL2 (per the plan) and later in Docker. This
module resolves WSL2 paths + runs the miner inside Ubuntu for agents
whose session stores live in the Linux side (~/.claude, ~/.codex, etc.).

Always read-only: uses wsl.exe to invoke python3 with a small miner
command line; never writes inside the guest except the /mnt/c host-
visible gold output.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def wsl_available() -> bool:
    return shutil.which("wsl") is not None


def run_in_wsl(script: str, timeout: int = 120) -> str:
    if not wsl_available():
        raise RuntimeError("wsl.exe not found — install WSL2 or run adapters locally")
    proc = subprocess.run(
        ["wsl", "-d", "Ubuntu", "--", "bash", "-lc", script],
        capture_output=True, text=True, timeout=timeout)
    return proc.stdout + (proc.stderr or "")


def mine_wsl_agents(agents: tuple[str, ...] = ("claude", "codex")) -> str:
    """Best-effort: enumerate Linux-side agent session stores (sizes only)."""
    checks = {
        "claude": "~/.claude/projects 2>/dev/null",
        "codex": "~/.codex/sessions 2>/dev/null",
        "pi": "~/.pi/agent/sessions 2>/dev/null",
    }
    lines = []
    for name, path in checks.items():
        if name not in agents:
            continue
        out = run_in_wsl(
            f'test -d {path.split(" 2>/dev/null")[0]} && '
            f'echo "{name}: $(find {path.split(" 2>/dev/null")[0]} -name "*.jsonl" | wc -l) files" '
            f'|| echo "{name}: absent"')
        lines.append(out.strip())
    return "\n".join(lines)


if __name__ == "__main__":
    print(mine_wsl_agents())
    print("wsl_available:", wsl_available())