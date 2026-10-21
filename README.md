# comma-command

Run any command you have installed from any shell, as if it were a shell builtin:

```console
$ gus, hello world
# → too talk gus -- hello world
```

Register an entry once. From then on, `NAME, any words` is the whole interface — no
aliases to source, no shell hook, no TUI.

## Install

```console
$ uv tool install comma-command    # or: pipx install comma-command
$ comma init --write               # puts the shim directory on PATH
$ exec $SHELL                      # or open a new terminal
```

## Quickstart

```console
$ comma add gus -- too talk gus --
added gus, → too talk gus --

$ comma add pyi -- uv run ipython --
added pyi, → uv run ipython --

$ gus, hello world          # runs: too talk gus -- hello world
$ pyi, --pdb script.py      # runs: uv run ipython -- --pdb script.py
$ comma ls
gus,  too talk gus --
pyi,  uv run ipython --
```

`comma add` does two things: writes the entry to `~/.config/comma/config.toml` and
creates an executable named exactly `gus,` in `~/.local/share/comma/bin`.

## How it works

The shim is a multicall dispatcher — the same trick `busybox` and `git` use for
subcommands, applied to names:

1. `gus,` is a symlink to the `comma` executable.
2. `comma` looks at `argv[0]`, sees a trailing comma, strips it, and finds `gus` in
   the config.
3. It calls `os.execvpe("too", ["too", "talk", "gus", "--", "hello", "world"])`.

Because the final step *replaces* the process instead of spawning a child, the
target command inherits the terminal, stdin, signals and job control directly, and
its exit status reaches your shell unchanged. `comma,` adds no wrapping layer.

Why not the alternatives:

- **Shell aliases/functions.** `gus,` is not a portable function name in bash or
  fish, and functions only exist in interactive shells you have sourced.
- **`command_not_found_handle` hooks.** Bash-only, collides with distro handlers
  (Nix, Debian's package suggestion hook), and silently does nothing in
  non-interactive shells, `sh -c`, cron, or most editors' task runners.
- **Shims on `PATH`.** Work everywhere a real executable works, including
  `xargs`, `find -exec`, CI scripts, Makefiles and shell completion.

## Configuration

`~/.config/comma/config.toml` — managed by `comma`, but hand-editable:

```toml
[commands.gus]
cmd = ["too", "talk", "gus", "--"]

# shorthand is fine too
[commands.pyi]
cmd = "uv run ipython --"
```

Arguments are appended verbatim, so `--` at the end of `cmd` is the usual way to
keep flags from being swallowed by the target's own option parser.

## Commands

| Command | What it does |
| --- | --- |
| `comma add NAME -- CMD...` | register a name and create its `NAME,` shim |
| `comma rm NAME` | unregister a name and remove its shim |
| `comma ls [--json]` | list registered names |
| `comma run NAME [--] [ARG...]` | run a name without going through the shim |
| `comma which NAME` | show the shim path and the command it runs |
| `comma init [--write] [--shell S]` | print or install PATH + completion setup |
| `comma doctor` | check config, PATH, shims and targets |
| `comma completion bash\|zsh\|fish` | print a completion script |

Names must be shell-safe words: letters, digits, `.`, `_`, `+`, `-`. The comma is
added for you, so `comma add gus, -- ...` is rejected rather than silently creating
`gus,,`.

## Limits

- POSIX first. Windows needs a `.cmd` shim layer, which is not in 0.1.
- No per-command `env`/`cwd` yet; use `cmd = ["sh", "-c", "..."]` as an escape hatch.
- The `comma-command` crate on crates.io is a name reservation for a future native
  binary; the Python implementation is the one to install today.

## Development

```console
$ uv venv && uv pip install -e '.[dev]'
$ uv run pytest
$ uv run ruff check .
```

MIT licensed.
