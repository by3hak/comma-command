"""Turning ``name, args...`` into the configured command.

Dispatch ends in :func:`os.execvpe`: the process is replaced, so the child
inherits the terminal, the foreground process group, stdin, and its exit
status reaches the shell untouched. No wrapper process, no signal proxying.
"""

from __future__ import annotations

import os
import sys

from . import config as config_mod
from . import paths


def invoked_name(prog: str) -> str | None:
    """Return the registered name if ``prog`` is a ``name,`` shim."""
    base = os.path.basename(prog)
    if len(base) > 1 and base.endswith(","):
        return base[:-1]
    return None


def dispatch(name: str, args: list[str]) -> int:
    """Replace this process with the command registered under ``name``."""
    try:
        commands = config_mod.load(paths.config_path())
    except config_mod.ConfigError as exc:
        print(f"comma: {exc}", file=sys.stderr)
        return 1

    command = commands.get(name)
    if command is None:
        print(f"comma: no command named {name!r}.", file=sys.stderr)
        known = ", ".join(sorted(commands)) or "(none yet)"
        print(f"  registered: {known}", file=sys.stderr)
        print(f"  add one:    comma add {name} -- your-command --", file=sys.stderr)
        return 127

    argv = [*command.argv, *args]
    try:
        os.execvpe(argv[0], argv, os.environ)
    except FileNotFoundError:
        print(f"comma: command not found: {argv[0]!r} (registered as {name!r})", file=sys.stderr)
        return 127
    except PermissionError:
        print(f"comma: permission denied: {argv[0]!r} (registered as {name!r})", file=sys.stderr)
        return 126
    return 126  # pragma: no cover - execvpe either replaces us or raises
