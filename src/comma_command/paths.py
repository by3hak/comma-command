"""XDG-ish locations used by comma-command.

Everything is resolved at call time so tests can point ``HOME``,
``XDG_CONFIG_HOME`` and ``XDG_DATA_HOME`` at throwaway directories.
"""

from __future__ import annotations

import os
from pathlib import Path


def home() -> Path:
    raw = os.environ.get("HOME")
    return Path(raw) if raw else Path.home()


def _xdg(var: str, fallback: Path) -> Path:
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else fallback


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", home() / ".config") / "comma"


def config_path() -> Path:
    return config_dir() / "config.toml"


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", home() / ".local" / "share") / "comma"


def shim_dir() -> Path:
    """Directory holding the executable ``name,`` shims."""
    return data_dir() / "bin"
