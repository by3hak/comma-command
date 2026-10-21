"""Reading and writing ``config.toml``.

The canonical schema is a table per command::

    [commands.gus]
    cmd = ["too", "talk", "gus", "--"]
    cwd = "~/work"
    env = { TOO_PROFILE = "work" }
    env_unset = ["HTTP_PROXY"]

``cwd``, ``env`` and ``env_unset`` are optional. ``env`` is merged into the
inherited environment; ``env_unset`` removes inherited variables first, so a key
may not appear in both. The shorthand ``[commands] gus = "too talk gus --"`` is
accepted as input sugar.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 only
    import tomli as tomllib  # type: ignore[no-redef]

#: Names become ``<name>,`` file names, so keep them boring: no slashes, no
#: leading dash (looks like a flag), no trailing comma (ambiguous on dispatch).
_NAME_RE = re.compile(r"^[A-Za-z0-9_+][A-Za-z0-9._+-]*$")
_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_KNOWN_KEYS = frozenset({"cmd", "command", "cwd", "env", "env_unset"})


class ConfigError(Exception):
    """Raised when the config file exists but cannot be understood."""


@dataclass(frozen=True)
class Command:
    """One registered name."""

    name: str
    argv: tuple[str, ...]
    cwd: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    env_unset: tuple[str, ...] = ()

    def display(self) -> str:
        return " ".join(shlex.quote(part) for part in self.argv)

    def modifiers(self) -> list[str]:
        """Human-readable list of the non-default settings, for `comma ls`."""
        out = []
        if self.cwd:
            out.append(f"cwd={self.cwd}")
        if self.env:
            out.append("env=" + ",".join(sorted(self.env)))
        if self.env_unset:
            out.append("unset=" + ",".join(self.env_unset))
        return out


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


def _coerce_env(name: str, raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ConfigError(f"[commands.{name}].env must be a table of KEY = \"VALUE\"")
    env: dict[str, str] = {}
    for key, value in raw.items():
        if not key or "=" in key:
            raise ConfigError(f"[commands.{name}].env: invalid variable name {key!r}")
        if not isinstance(value, str):
            raise ConfigError(
                f"[commands.{name}].env.{key} must be a string "
                f"(got {type(value).__name__})"
            )
        env[key] = value
    return env


def _coerce_env_unset(name: str, raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise ConfigError(f"[commands.{name}].env_unset must be a list of variable names")
    for item in raw:
        if not item or "=" in item:
            raise ConfigError(f"[commands.{name}].env_unset: invalid variable name {item!r}")
    return tuple(raw)


def _coerce(name: str, value: object) -> Command:
    if isinstance(value, str):
        argv = shlex.split(value)
        cwd = None
        env: dict[str, str] = {}
        env_unset: tuple[str, ...] = ()
    elif isinstance(value, dict):
        unknown = set(value) - _KNOWN_KEYS
        if unknown:
            raise ConfigError(
                f"[commands.{name}]: unknown key(s) {', '.join(sorted(unknown))} "
                f"(known: {', '.join(sorted(_KNOWN_KEYS))})"
            )
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

        cwd = value.get("cwd")
        if cwd is not None and (not isinstance(cwd, str) or not cwd):
            raise ConfigError(f"[commands.{name}].cwd must be a non-empty string")

        env = _coerce_env(name, value["env"]) if "env" in value else {}
        env_unset = (
            _coerce_env_unset(name, value["env_unset"]) if "env_unset" in value else ()
        )
    else:
        raise ConfigError(
            f"[commands.{name}] must be a string or a table with a 'cmd' key"
        )

    if not argv:
        raise ConfigError(f"command {name!r} is empty")

    overlap = sorted(set(env) & set(env_unset))
    if overlap:
        raise ConfigError(
            f"[commands.{name}]: {', '.join(overlap)} in both env and env_unset — "
            "pick one, the order would be ambiguous"
        )

    return Command(name=name, argv=tuple(argv), cwd=cwd, env=env, env_unset=env_unset)


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
        commands[name] = _coerce(name, value)
    return commands


def _toml_key(name: str) -> str:
    return name if _BARE_KEY_RE.match(name) else _toml_string(name)


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
        if command.cwd:
            lines.append(f"cwd = {_toml_string(command.cwd)}")
        if command.env:
            pairs = ", ".join(
                f"{_toml_string(key)} = {_toml_string(value)}"
                for key, value in sorted(command.env.items())
            )
            lines.append(f"env = {{ {pairs} }}")
        if command.env_unset:
            keys = ", ".join(_toml_string(key) for key in command.env_unset)
            lines.append(f"env_unset = [{keys}]")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
