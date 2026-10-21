from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A hermetic environment: throwaway HOME, XDG dirs, src on PYTHONPATH."""
    home = tmp_path / "home"
    home.mkdir()
    pythonpath = str(SRC)
    if os.environ.get("PYTHONPATH"):
        pythonpath += os.pathsep + os.environ["PYTHONPATH"]
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "PYTHONPATH": pythonpath,
        "SHELL": "/bin/bash",
    }


@pytest.fixture
def comma(env: dict[str, str]):
    """Call the CLI in a subprocess; returns a CompletedProcess."""

    def run(*args: str, env_overrides: dict[str, str] | None = None):
        merged = {**env, **(env_overrides or {})}
        return subprocess.run(
            [sys.executable, "-m", "comma_command", *args],
            env=merged,
            capture_output=True,
            text=True,
        )

    return run


@pytest.fixture
def launcher(env: dict[str, str], tmp_path: Path) -> Path:
    """A stand-in for the installed ``comma`` executable.

    ``COMMA_SHIM_TARGET`` points the shims here. The launcher forwards the
    shim path as ``argv[0]`` so dispatch behaves exactly like a real install.
    """
    driver = tmp_path / "driver.py"
    driver.write_text(
        "import sys\n"
        "from comma_command.cli import main\n"
        "sys.argv = sys.argv[1:]\n"
        "raise SystemExit(main(sys.argv))\n",
        encoding="utf-8",
    )
    path = tmp_path / "bin" / "comma"
    path.parent.mkdir()
    path.write_text(
        f'#!/bin/sh\nexec "{sys.executable}" "{driver}" "$0" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)
    env["COMMA_SHIM_TARGET"] = str(path)
    return path


@pytest.fixture
def echoargs(tmp_path: Path) -> Path:
    """A command that prints its arguments one per line."""
    script = tmp_path / "echoargs"
    script.write_text('#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n', encoding="utf-8")
    script.chmod(0o755)
    return script


def shim_dir(env: dict[str, str]) -> Path:
    return Path(env["XDG_DATA_HOME"]) / "comma" / "bin"


def activate(env: dict[str, str]) -> dict[str, str]:
    """Put the shim directory on PATH, the way `comma init` would."""
    env["PATH"] = str(shim_dir(env)) + os.pathsep + env["PATH"]
    return env


def run_shim(env: dict[str, str], shim: str, *args: str):
    """Execute a ``name,`` shim the way a shell would."""
    return subprocess.run([shim, *args], env=env, capture_output=True, text=True)
