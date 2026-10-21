"""The ``comma`` command line.

``comma`` is both the manager (``add``/``rm``/``ls``/``init``/...) and the
dispatcher: when it is invoked through a ``name,`` shim, ``argv[0]`` tells it
which registered command to run.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from . import __version__, paths
from . import config as config_mod
from .dispatch import dispatch, invoked_name

USAGE = """\
comma — run any configured command as `name, args`

usage:
  comma add NAME -- COMMAND [ARG...]   register NAME (creates the `NAME,` shim)
  comma rm NAME                        unregister NAME
  comma ls [--json]                    list registered commands
  comma run NAME [--] [ARG...]         run NAME without going through the shim
  comma NAME, [ARG...]                 same as `NAME,`, for shells without the shim on PATH
  comma which NAME                     show the shim and what NAME runs
  comma init [--write] [--shell S]     print or install shell setup (PATH + completion)
  comma doctor                         check the installation
  comma completion SHELL               print completion for bash, zsh or fish
  comma --version | --help

example:
  comma add gus -- too talk gus --
  gus, hello world                     # runs: too talk gus -- hello world
"""

_SHELLS = ("bash", "zsh", "fish", "sh")


class CliError(Exception):
    """A user-facing mistake; printed without a traceback."""


# --------------------------------------------------------------------------- helpers


def _on_path(directory: Path) -> bool:
    try:
        target = directory.resolve()
    except OSError:  # pragma: no cover - unreadable dir
        target = directory
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        try:
            if Path(entry).expanduser().resolve() == target:
                return True
        except OSError:  # pragma: no cover
            continue
    return False


def _launcher() -> Path:
    """Absolute path of the ``comma`` executable the shims should point at."""
    override = os.environ.get("COMMA_SHIM_TARGET")
    if override:
        return Path(override).expanduser().absolute()
    found = shutil.which("comma")
    if found:
        return Path(found).absolute()
    beside_python = Path(sys.executable).parent / "comma"
    if beside_python.exists():
        return beside_python.absolute()
    raise CliError(
        "cannot find the `comma` executable to link the shim to; "
        "set COMMA_SHIM_TARGET to its path"
    )


def _is_our_shim(shim: Path) -> bool:
    if not shim.is_symlink():
        return False
    try:
        return shim.resolve() == _launcher().resolve()
    except (OSError, CliError):
        return False


def _install_shim(name: str) -> Path:
    target = _launcher()
    shim = paths.shim_dir() / f"{name},"
    paths.shim_dir().mkdir(parents=True, exist_ok=True)
    if shim.is_symlink() or shim.exists():
        shim.unlink()
    shim.symlink_to(target)
    return shim


def _detect_shell() -> str:
    base = os.path.basename(os.environ.get("SHELL", ""))
    return base if base in _SHELLS else "bash"


def _rc_path(shell: str) -> Path:
    if shell == "fish":
        return paths.home() / ".config" / "fish" / "config.fish"
    if shell == "zsh":
        return paths.home() / ".zshrc"
    return paths.home() / ".bashrc"


def _init_snippet(shell: str) -> str:
    shim = paths.shim_dir()
    if shell == "fish":
        return (
            "# comma (managed)\n"
            f"set -gx PATH {shim} $PATH\n"
            "comma completion fish | source\n"
        )
    completion = "" if shell == "sh" else f'source <(comma completion {shell})\n'
    return f'# comma (managed)\nexport PATH="{shim}:$PATH"\n{completion}'


# --------------------------------------------------------------------------- commands


def _add(args: list[str]) -> int:
    force = False
    while args and args[0].startswith("-") and args[0] != "--":
        flag = args.pop(0)
        if flag in ("-f", "--force"):
            force = True
        elif flag in ("-h", "--help"):
            print("usage: comma add [--force] NAME -- COMMAND [ARG...]")
            return 0
        else:
            raise CliError(f"add: unknown option {flag}")

    if len(args) < 3:
        raise CliError("add: expected `comma add NAME -- COMMAND [ARG...]`")

    name, tail = args[0], args[1:]
    if tail[0] != "--":
        raise CliError(
            "add: put `--` between the name and the command, "
            "e.g. `comma add gus -- too talk gus --`"
        )
    cmd_argv = tail[1:]
    if not cmd_argv:
        raise CliError("add: missing command after `--`")

    config_mod.validate_name(name)

    shim = paths.shim_dir() / f"{name},"
    if (shim.exists() or shim.is_symlink()) and not force and not _is_our_shim(shim):
        raise CliError(
            f"add: {shim} already exists and was not created by comma "
            "(rerun with --force to replace it)"
        )

    commands = config_mod.load(paths.config_path())
    commands[name] = config_mod.Command(name=name, argv=tuple(cmd_argv))
    config_mod.save(paths.config_path(), commands)
    _install_shim(name)

    print(f"added {name}, → {commands[name].display()}")
    if not _on_path(paths.shim_dir()):
        print(f"note: {paths.shim_dir()} is not on PATH — run `comma init --write`")
    return 0


def _rm(args: list[str]) -> int:
    if not args:
        raise CliError("rm: expected `comma rm NAME`")
    name = args[0]
    commands = config_mod.load(paths.config_path())
    if name not in commands:
        raise CliError(f"rm: no command named {name!r}")

    removed = commands.pop(name)
    config_mod.save(paths.config_path(), commands)

    shim = paths.shim_dir() / f"{name},"
    if shim.is_symlink() or shim.exists():
        shim.unlink()

    print(f"removed {name}, (was {removed.display()})")
    return 0


def _ls(args: list[str]) -> int:
    commands = config_mod.load(paths.config_path())

    if "--json" in args:
        payload = {
            name: {"cmd": list(cmd.argv), "shim": str(paths.shim_dir() / f"{name},")}
            for name, cmd in sorted(commands.items())
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if not commands:
        print("no commands registered yet — try: comma add gus -- too talk gus --")
        return 0

    width = max(len(name) for name in commands) + 1
    for name in sorted(commands):
        print(f"{name + ',':<{width}}  {commands[name].display()}")
    return 0


def _names(args: list[str]) -> int:
    """Hidden helper for shell completion."""
    for name in sorted(config_mod.load(paths.config_path())):
        print(name)
    return 0


def _run(args: list[str]) -> int:
    if not args:
        raise CliError("run: expected `comma run NAME [--] [ARG...]`")
    name, rest = args[0], args[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    return dispatch(name, rest)


def _which(args: list[str]) -> int:
    if not args:
        raise CliError("which: expected `comma which NAME`")
    name = args[0]
    commands = config_mod.load(paths.config_path())
    command = commands.get(name)
    shim = paths.shim_dir() / f"{name},"

    if command is None and not shim.exists():
        print(f"{name}: not registered", file=sys.stderr)
        return 1

    print(f"name:  {name},")
    print(f"shim:  {shim}" + ("" if shim.exists() else "  (missing)"))
    print(
        "path:  "
        + ("on PATH" if _on_path(paths.shim_dir()) else "NOT on PATH — run `comma init --write`")
    )
    if command is not None:
        print(f"runs:  {command.display()}")
    return 0


def _init(args: list[str]) -> int:
    shell = _detect_shell()
    write = False
    index = 0
    while index < len(args):
        option = args[index]
        if option == "--write":
            write = True
            index += 1
        elif option == "--shell":
            index += 1
            if index >= len(args):
                raise CliError("init: --shell needs a value")
            shell = args[index]
            index += 1
        elif option in ("-h", "--help"):
            print("usage: comma init [--write] [--shell bash|zsh|fish]")
            return 0
        else:
            raise CliError(f"init: unknown option {option}")

    if shell not in _SHELLS:
        raise CliError(f"init: unsupported shell {shell!r} (bash, zsh, fish)")

    snippet = _init_snippet(shell)
    if not write:
        print(snippet, end="")
        return 0

    rc = _rc_path(shell)
    rc.parent.mkdir(parents=True, exist_ok=True)
    existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
    if "# comma (managed)" in existing:
        print(f"already configured in {rc}")
        return 0

    with rc.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(snippet)
    print(f"updated {rc} — open a new shell (or `source {rc}`)")
    return 0


def _doctor(args: list[str]) -> int:
    config = paths.config_path()
    shims = paths.shim_dir()
    print(f"comma {__version__} (comma-command)")
    print(f"config: {config}")
    print(f"shims:  {shims}")

    try:
        commands = config_mod.load(config)
    except config_mod.ConfigError as exc:
        print(f"FAIL  config: {exc}")
        return 1

    count = len(commands)
    print(f"ok    config parsed ({count} command{'s' if count != 1 else ''})")

    problems = 0
    if _on_path(shims):
        print("ok    shim directory is on PATH")
    else:
        print("warn  shim directory is not on PATH — run `comma init --write`")

    shell = _detect_shell()
    rc = _rc_path(shell)
    configured = rc.exists() and "# comma (managed)" in rc.read_text(
        encoding="utf-8", errors="replace"
    )
    if configured:
        print(f"ok    shell setup present in {rc}")
    else:
        print(f"warn  no shell setup in {rc} — run `comma init --write`")

    for name in sorted(commands):
        command = commands[name]
        shim = shims / f"{name},"
        issues = []
        if not shim.exists():
            issues.append("shim missing — re-run `comma add`")
        elif not os.access(shim, os.X_OK):
            issues.append("shim is not executable")
        if shutil.which(command.argv[0]) is None:
            issues.append(f"target {command.argv[0]!r} is not on PATH")
        if issues:
            print(f"FAIL  {name},: " + "; ".join(issues))
            problems += 1
        else:
            print(f"ok    {name}, → {command.display()}")

    return 1 if problems else 0


_BASH_COMPLETION = """\
# bash completion for comma
_comma_complete() {
    local cur prev
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=( $(compgen -W "add rm ls run which init doctor completion help" -- "$cur") )
        return
    fi
    case "$prev" in
        rm|run|which) COMPREPLY=( $(compgen -W "$(comma _names)" -- "$cur") ) ;;
        completion)   COMPREPLY=( $(compgen -W "bash zsh fish" -- "$cur") ) ;;
    esac
}
complete -F _comma_complete comma
# `name,` shims need no completion: they are real files on PATH, so the shell
# completes them like any other executable.
"""

_ZSH_COMPLETION = """\
#compdef comma
_comma() {
    local -a subcommands names
    subcommands=(add rm ls run which init doctor completion help)
    if (( CURRENT == 2 )); then
        _describe 'command' subcommands
        return
    fi
    case "${words[2]}" in
        rm|run|which) names=(${(f)"$(comma _names)"}); _describe 'name' names ;;
        completion)   _values 'shell' bash zsh fish ;;
    esac
}
compdef _comma comma
"""

_FISH_COMPLETION = """\
complete -c comma -f
complete -c comma -n '__fish_use_subcommand' -a 'add rm ls run which init doctor completion help'
complete -c comma -n '__fish_seen_subcommand_from rm run which' -a '(comma _names)'
complete -c comma -n '__fish_seen_subcommand_from completion' -a 'bash zsh fish'
"""


def _completion(args: list[str]) -> int:
    shell = args[0] if args else _detect_shell()
    scripts = {
        "bash": _BASH_COMPLETION,
        "zsh": _ZSH_COMPLETION,
        "fish": _FISH_COMPLETION,
    }
    script = scripts.get(shell)
    if script is None:
        raise CliError(f"completion: unsupported shell {shell!r} (bash, zsh, fish)")
    print(script, end="")
    return 0


_HANDLERS = {
    "add": _add,
    "rm": _rm,
    "ls": _ls,
    "list": _ls,
    "run": _run,
    "which": _which,
    "init": _init,
    "doctor": _doctor,
    "completion": _completion,
    "_names": _names,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    prog = argv[0] if argv else "comma"
    args = argv[1:]

    # Reached through a `name,` shim: we are the dispatcher, not the manager.
    name = invoked_name(prog)
    if name is not None:
        return dispatch(name, args)

    # `comma NAME, args...` — the same spelling as the shell form, for machines
    # where the shim directory is not on PATH. Not `comma NAME args`: that would
    # collide with the management subcommands (an alias called `ls` or `run`).
    if args and len(args[0]) > 1 and args[0].endswith(","):
        return dispatch(args[0][:-1], args[1:])

    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE)
        return 0
    if args[0] in ("-V", "--version", "version"):
        print(f"comma {__version__} (comma-command)")
        return 0

    handler = _HANDLERS.get(args[0])
    if handler is None:
        print(f"comma: unknown command {args[0]!r}\n", file=sys.stderr)
        sys.stderr.write(USAGE)
        return 2

    try:
        return handler(args[1:])
    except CliError as exc:
        print(f"comma: {exc}", file=sys.stderr)
        return 2
    except config_mod.ConfigError as exc:
        print(f"comma: {exc}", file=sys.stderr)
        return 1
