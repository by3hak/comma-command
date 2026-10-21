"""End-to-end: a real `name,` shim on PATH must reach the configured command."""

from __future__ import annotations

import subprocess
from pathlib import Path

from conftest import activate, run_shim, shim_dir


def test_gus_comma_maps_to_configured_argv(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "too", "talk", "gus", "--")
    activate(env)

    result = run_shim(env, "gus,", "hello", "world")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["too", "talk", "gus", "--", "hello", "world"]


def test_arguments_with_spaces_survive(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "too", "talk", "gus", "--")
    activate(env)

    result = run_shim(env, "gus,", "hello world", "--flag", "")

    assert result.stdout.splitlines() == ["too", "talk", "gus", "--", "hello world", "--flag", ""]


def test_exit_code_is_passed_through(comma, env, launcher) -> None:
    comma("add", "boom", "--", "/bin/sh", "-c", "exit 5")
    activate(env)

    assert run_shim(env, "boom,").returncode == 5


def test_stdin_is_inherited(comma, env, launcher) -> None:
    comma("add", "upper", "--", "/bin/sh", "-c", "tr a-z A-Z")
    activate(env)

    proc = subprocess.run(
        ["upper,"], env=env, input="hi\nthere\n", capture_output=True, text=True
    )

    assert proc.stdout == "HI\nTHERE\n"


def test_unknown_name_exits_127(comma, env, launcher) -> None:
    shim = shim_dir(env) / "ghost,"
    shim.parent.mkdir(parents=True)
    shim.symlink_to(launcher)
    activate(env)

    result = run_shim(env, "ghost,", "hi")

    assert result.returncode == 127
    assert "no command named 'ghost'" in result.stderr
    assert "comma add ghost" in result.stderr


def test_missing_target_exits_127(comma, env, launcher) -> None:
    comma("add", "gone", "--", "/nope/definitely-not-here")
    activate(env)

    result = run_shim(env, "gone,")

    assert result.returncode == 127
    assert "command not found" in result.stderr


def test_comma_run_without_shim(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")

    result = comma("run", "gus", "--", "hello")

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["--", "hello"]


def test_broken_config_is_reported(comma, env, launcher, echoargs) -> None:
    comma("add", "gus", "--", str(echoargs), "--")
    activate(env)

    config = Path(env["XDG_CONFIG_HOME"]) / "comma" / "config.toml"
    config.write_text("[commands.gus\n", encoding="utf-8")

    result = run_shim(env, "gus,")

    assert result.returncode == 1
    assert "invalid TOML" in result.stderr
