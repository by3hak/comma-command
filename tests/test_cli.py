from __future__ import annotations

import json
from pathlib import Path

from conftest import activate, shim_dir


def test_add_creates_config_and_shim(comma, env, launcher, echoargs) -> None:
    result = comma("add", "gus", "--", str(echoargs), "too", "talk", "gus", "--")
    assert result.returncode == 0, result.stderr
    assert "added gus," in result.stdout

    config_path = Path(env["XDG_CONFIG_HOME"]) / "comma" / "config.toml"
    assert "[commands.gus]" in config_path.read_text(encoding="utf-8")

    shim = shim_dir(env) / "gus,"
    assert shim.is_symlink()
    assert shim.resolve() == launcher.resolve()


def test_add_lists_and_removes(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")

    listing = comma("ls")
    assert listing.returncode == 0
    assert "gus," in listing.stdout
    assert str(echoargs) in listing.stdout

    assert comma("rm", "gus").returncode == 0
    assert comma("ls").stdout.startswith("no commands registered")
    assert not (shim_dir(env) / "gus,").exists()
    assert comma("rm", "gus").returncode != 0


def test_add_requires_double_dash(comma, env, launcher, echoargs) -> None:
    result = comma("add", "gus", str(echoargs), "--")
    assert result.returncode == 2
    assert "--" in result.stderr


def test_add_rejects_bad_name(comma, env, launcher) -> None:
    result = comma("add", "has space", "--", "echo", "hi")
    assert result.returncode != 0
    assert "invalid name" in result.stderr


def test_add_refuses_to_clobber_foreign_file(comma, env, launcher) -> None:
    shim = shim_dir(env) / "gus,"
    shim.parent.mkdir(parents=True)
    shim.write_text("#!/bin/sh\necho not ours\n", encoding="utf-8")

    blocked = comma("add", "gus", "--", "echo", "hi")
    assert blocked.returncode != 0
    assert "already exists" in blocked.stderr
    assert comma("add", "--force", "gus", "--", "echo", "hi").returncode == 0


def test_ls_json(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "too", "talk", "gus", "--")
    payload = json.loads(comma("ls", "--json").stdout)
    assert payload["gus"]["cmd"] == [str(echoargs), "too", "talk", "gus", "--"]
    assert payload["gus"]["shim"].endswith("gus,")


def test_which(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")
    result = comma("which", "gus")
    assert result.returncode == 0
    assert "gus," in result.stdout
    assert "not registered" in comma("which", "nope").stderr


def test_init_prints_without_touching_dotfiles(comma, env) -> None:
    rc = Path(env["HOME"]) / ".bashrc"
    result = comma("init", "--shell", "bash")
    assert result.returncode == 0
    assert "export PATH=" in result.stdout
    assert not rc.exists()


def test_init_write_is_idempotent(comma, env) -> None:
    rc = Path(env["HOME"]) / ".bashrc"
    first = comma("init", "--write", "--shell", "bash")
    assert first.returncode == 0
    assert "# comma (managed)" in rc.read_text(encoding="utf-8")

    second = comma("init", "--write", "--shell", "bash")
    assert "already configured" in second.stdout
    assert rc.read_text(encoding="utf-8").count("# comma (managed)") == 1


def test_doctor_clean_install(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")
    comma("init", "--write", "--shell", "bash")
    activate(env)
    result = comma("doctor")
    assert result.returncode == 0, result.stdout
    assert "ok    gus," in result.stdout


def test_doctor_flags_missing_shim(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")
    (shim_dir(env) / "gus,").unlink()
    result = comma("doctor")
    assert result.returncode == 1
    assert "shim missing" in result.stdout


def test_completion_scripts(comma, env) -> None:
    for shell in ("bash", "zsh", "fish"):
        result = comma("completion", shell)
        assert result.returncode == 0
        assert "comma" in result.stdout
    assert comma("completion", "tcsh").returncode == 2


def test_version_and_help(comma, env) -> None:
    from comma_command import __version__

    assert f"comma {__version__}" in comma("--version").stdout
    usage = comma("--help").stdout
    assert "comma add" in usage and "NAME -- COMMAND" in usage
    assert "comma edit" in usage
    assert comma("bogus").returncode == 2


def test_add_accepts_end_of_options_marker(comma, env, launcher, echoargs) -> None:
    """`comma add --env K=V -- NAME -- CMD` must not treat `--` as the name."""
    result = comma(
        "add", "--env", "A=1", "--", "gus", "--", str(echoargs), "hi",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(comma("ls", "--json").stdout)
    assert payload["gus"]["cmd"] == [str(echoargs), "hi"]
    assert payload["gus"]["env"] == {"A": "1"}


def test_add_warns_when_target_is_missing(comma, env, launcher) -> None:
    result = comma("add", "typo", "--", "definitely-not-a-real-binary-xyz")

    assert result.returncode == 0, result.stderr
    assert "is not on PATH" in result.stderr
    assert "exit 127" in result.stderr
    assert "typo," in comma("ls").stdout


def test_add_reports_modifiers_dropped_by_a_replace(comma, env, launcher, tmp_path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    comma("add", "--env", "PROFILE=work", "--cwd", str(work), "svc", "--", "/bin/echo", "one")

    result = comma("add", "svc", "--", "/bin/echo", "two")

    assert result.returncode == 0, result.stderr
    assert "replaces the previous svc," in result.stdout
    assert "env PROFILE" in result.stdout
    assert f"cwd {work}" in result.stdout


def test_parallel_adds_are_not_lost(comma, env, launcher, tmp_path) -> None:
    """Concurrent read-modify-write used to drop entries; the lock must prevent it."""
    import subprocess as sp
    import sys

    procs = [
        sp.Popen(
            [sys.executable, "-m", "comma_command", "add", f"n{i}", "--", "/bin/echo", str(i)],
            env=env,
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
        )
        for i in range(8)
    ]
    for proc in procs:
        proc.wait()

    registered = json.loads(comma("ls", "--json").stdout)
    assert sorted(name for name in registered if name.startswith("n")) == [
        f"n{i}" for i in range(8)
    ], registered
