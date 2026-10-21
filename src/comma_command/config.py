"""Reading and writing ``config.toml``.

Two ways to declare a command, both equivalent::

    [commands.gus]
    cmd = ["too", "talk", "gus", "--"]

    [commands]
    gus = "too talk gus --"

The list form is the canonical one: it survives arguments containing spaces
without quoting games.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 only
    import tomli as tomllib  # type: ignore[no-redef]

#: Names become ``<name>,`` file names, so keep them boring: no slashes, no
#: leading dash (looks like a flag), no trailing comma (ambiguous on dispatch).
_NAME_RE = re.compile(r"^[A-Za-z0-9_+][A-Za-z0-9._+-]*$")
_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(Exception):
    """Raised when the config file exists but cannot be understood."""


@dataclass(frozen=True)
class Command:
    """One registered name."""

    name: str
    argv: tuple[str, ...]

    def display(self) -> str:
        return " ".join(shlex.quote(part) for part in self.argv)


def validate_name(name: str) -> str:
    if not name:
        raise ConfigError("name cannot be empty")
    if name.endswith(","):
        raise ConfigError(f"invalid name {name!r}: the comma is added for you")
    if name.startswith("-"):
        raise ConfigError(f"invalid name {name!r}: must not start with '-'")
    if name in (".", ".."):
        raise ConfigError(f"invalid name {name!r}")
    if not _NAME_RE.match(name):
        raise ConfigError(
            f"invalid name {name!r}: use letters, digits, '.', '_', '+', '-'"
        )
    return name


def _coerce(name: str, value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        argv = shlex.split(value)
    elif isinstance(value, dict):
        key = "cmd" if "cmd" in value else "command" if "command" in value else None
        if key is None:
            raise ConfigError(f"[commands.{name}] needs a 'cmd' key")
        raw = value[key]
        if isinstance(raw, str):
            argv = shlex.split(raw)
        elif isinstance(raw, list) and all(isinstance(part, str) for part in raw):
            argv = list(raw)
        else:
            raise ConfigError(f"[commands.{name}].cmd must be a string or a list of strings")
    else:
        raise ConfigError(
            f"[commands.{name}] must be a string or a table with a 'cmd' key"
        )
    if not argv:
        raise ConfigError(f"command {name!r} is empty")
    return tuple(argv)


def load(path: Path) -> dict[str, Command]:
    """Parse ``path``. A missing file is an empty config, not an error."""
    if not path.exists():
        return {}
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc

    table = raw.get("commands", {})
    if not isinstance(table, dict):
        raise ConfigError(f"{path}: 'commands' must be a table")

    commands: dict[str, Command] = {}
    for name, value in table.items():
        validate_name(name)
        commands[name] = Command(name=name, argv=_coerce(name, value))
    return commands


def _toml_key(name: str) -> str:
    return name if _BARE_KEY_RE.match(name) else json.dumps(name)


def _toml_string(text: str) -> str:
    # JSON string escapes are a subset of TOML basic-string escapes.
    return json.dumps(text, ensure_ascii=False)


def save(path: Path, commands: dict[str, Command]) -> None:
    lines = [
        "# comma config — manage it with `comma add NAME -- COMMAND...`",
        "# docs: https://github.com/by3hak/comma-command",
        "",
    ]
    for name in sorted(commands):
        command = commands[name]
        rendered = ", ".join(_toml_string(part) for part in command.argv)
        lines.append(f"[commands.{_toml_key(name)}]")
        lines.append(f"cmd = [{rendered}]")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
