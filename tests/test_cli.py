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
    assert "comma 0.1.0" in comma("--version").stdout
    usage = comma("--help").stdout
    assert "comma add NAME" in usage
    assert comma("bogus").returncode == 2
