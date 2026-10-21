# comma-command

Run configured commands from any shell with the `NAME, ARGS` form.

After installation and PATH setup:

```console
$ comma add greet -- echo hello
added greet, → echo hello

$ greet, world
hello world
```

Each configured name is an executable shim on PATH that forwards the remaining
arguments to its command. Run `comma init --write` to add the shim directory to
PATH; no shell function or command-not-found hook is needed.

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

If the shim directory is not on `PATH` — a CI job, a container, a repo where nobody
ran `comma init` — `comma gus, hello world` reaches the same dispatch path. `comma`
takes `NAME,` rather than bare `NAME` so that a registered name can never collide
with the management subcommands (`ls`, `run`, `doctor`, ...).

Because the final step *replaces* the dispatcher instead of spawning a child,
the target inherits the terminal, stdin, signals and job control directly, and its
exit status reaches your shell unchanged. No wrapper process remains.

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
```

The nested `[commands.<name>]` table is canonical and supports per-command options
such as `env` and `cwd`. For a simple entry, this string shorthand is also accepted:

```toml
[commands]
pyi = "uv run ipython --"
```

The shorthand is input sugar; the nested table remains the documented schema.

Arguments are appended verbatim, so `--` at the end of `cmd` is the usual way to
keep flags from being swallowed by the target's own option parser.

Per-command settings live in the same table:

```toml
[commands.deploy]
cmd = ["kubectl", "apply", "-f", "k8s/"]
cwd = "~/src/infra"
env = { KUBECONFIG = "~/.kube/staging" }
env_unset = ["HTTP_PROXY"]
```

`env` is **merged into** the inherited environment, so `PATH` and `HOME` keep working,
and `env_unset` drops inherited variables first — a name may not appear in both.
`cwd` is `~`-expanded and applied before the target runs. The same options exist on
the command line: `comma add --env K=V --unset K --cwd DIR NAME -- CMD...`.

## Commands

| Command | What it does |
| --- | --- |
| `comma add [--env K=V] [--unset K] [--cwd DIR] NAME -- CMD...` | register a name and create its `NAME,` shim |
| `comma edit` | open the config in `$EDITOR`, re-validate it, reconcile the shims |
| `comma rm NAME` | unregister a name and remove its shim |
| `comma ls [--json]` | list registered names |
| `comma run NAME [--] [ARG...]` | run a name without going through the shim |
| `comma NAME, [ARG...]` | the shell spelling, without the shim on PATH (handy in CI) |
| `comma which NAME` | show the shim path and the command it runs |
| `comma init [--write] [--shell S]` | print or install PATH + completion setup |
| `comma doctor` | check config, PATH, shims and targets |
| `comma completion bash\|zsh\|fish` | print a completion script |

Names must be shell-safe words: letters, digits, `.`, `_`, `+`, `-`. The comma is
added for you, so `comma add gus, -- ...` is rejected rather than silently creating
`gus,,`.

## Design decisions

Recorded so they do not get relitigated every release:

- **No `command_not_found_handle` fallback.** The hook only fires when a PATH lookup
  fails, so it cannot resolve a name whose `NAME,` file already exists; it is also
  bash-only and fights the distro's own hook. `comma add` instead refuses to
  overwrite a foreign `NAME,` unless you pass `--force`, and CI/scripts use
  `comma NAME, ...`.
- **`[commands.<name>]` is canonical.** Per-command options (`env`, `cwd`, ...)
  live in that sub-table. The `name = "..."` shorthand stays as input sugar and
  is not documented twice.
- **No argument completion for target commands.** Command-position completion is
  free because the shims are real files on `PATH`, and `comma`'s own subcommands
  have completion. Completing a target's *arguments* would need a completion
  protocol per target — out of scope for the current release and better designed
  once there is a concrete need.

## Limits

- POSIX first. Windows would need a `.cmd` shim layer, which is not implemented yet.
- The `comma-command` crate on crates.io is a name reservation for a future native
  binary; the Python implementation is the one to install today.

## Development

```console
$ uv venv && uv pip install -e '.[dev]'
$ uv run pytest
$ uv run ruff check .
```

MIT licensed.
