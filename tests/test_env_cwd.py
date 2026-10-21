"""Per-command ``cwd`` / ``env`` / ``env_unset`` and ``comma edit``."""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import activate, run_shim, shim_dir


def write_config(env: dict[str, str], body: str) -> Path:
    path = Path(env["XDG_CONFIG_HOME"]) / "comma" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def make_shim(env: dict[str, str], launcher: Path, name: str) -> Path:
    shim = shim_dir(env) / f"{name},"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.symlink_to(launcher)
    return shim


def test_add_records_env_and_cwd(comma, env, launcher, tmp_path) -> None:
    work = tmp_path / "work"
    work.mkdir()

    result = comma(
        "add", "--env", "PROFILE=work", "--env", "X=1", "--cwd", str(work),
        "gus", "--", "/bin/echo", "hi",
    )

    assert result.returncode == 0, result.stderr
    text = (Path(env["XDG_CONFIG_HOME"]) / "comma" / "config.toml").read_text()
    assert "cwd = " in text
    assert "env = { " in text

    payload = json.loads(comma("ls", "--json").stdout)
    assert payload["gus"]["env"] == {"PROFILE": "work", "X": "1"}
    assert payload["gus"]["cwd"] == str(work)


def test_ls_text_shows_modifiers(comma, env, launcher, tmp_path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    comma("add", "--env", "A=1", "--cwd", str(work), "gus", "--", "/bin/echo", "hi")

    listing = comma("ls").stdout

    assert "cwd=" in listing
    assert "env=A" in listing


def test_env_overlays_inherited_environment(comma, env, launcher) -> None:
    comma(
        "add", "--env", "A=from-config", "envtest", "--",
        "/bin/sh", "-c", 'printf "%s\\n" "$A" "$B"',
    )
    activate(env)
    env["B"] = "inherited"

    result = run_shim(env, "envtest,")

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["from-config", "inherited"]


def test_env_unset_removes_inherited_variable(comma, env, launcher) -> None:
    write_config(
        env,
        '[commands.check]\n'
        'cmd = ["/bin/sh", "-c", \'printf "%s\\n" "${TOKEN:-absent}"\']\n'
        'env_unset = ["TOKEN"]\n',
    )
    make_shim(env, launcher, "check")
    activate(env)
    env["TOKEN"] = "inherited-value"

    result = run_shim(env, "check,")

    assert result.stdout.splitlines() == ["absent"]


def test_cwd_is_applied(comma, env, launcher, tmp_path) -> None:
    work = tmp_path / "proj"
    work.mkdir()
    comma("add", "--cwd", str(work), "here", "--", "/bin/sh", "-c", "pwd")
    activate(env)

    result = run_shim(env, "here,")

    assert os.path.realpath(result.stdout.strip()) == os.path.realpath(work)


def test_missing_cwd_fails_cleanly(comma, env, launcher) -> None:
    comma("add", "--cwd", "/nope/nowhere", "gone", "--", "/bin/echo", "hi")
    activate(env)

    result = run_shim(env, "gone,")

    assert result.returncode == 1
    assert "cannot change to cwd" in result.stderr


def test_env_and_env_unset_overlap_is_rejected(comma, env, launcher) -> None:
    write_config(
        env,
        '[commands.bad]\ncmd = ["/bin/echo", "hi"]\nenv = { A = "1" }\nenv_unset = ["A"]\n',
    )

    result = comma("ls")

    assert result.returncode == 1
    assert "both env and env_unset" in result.stderr


def test_unknown_key_is_rejected(comma, env, launcher) -> None:
    write_config(env, '[commands.typo]\ncmd = ["/bin/echo", "hi"]\nevn = { A = "1" }\n')

    result = comma("ls")

    assert result.returncode == 1
    assert "unknown key" in result.stderr


def _editor(tmp_path: Path, body: str) -> str:
    script = tmp_path / "fake-editor.py"
    script.write_text("#!/usr/bin/env python3\nimport sys\n" + body, encoding="utf-8")
    script.chmod(0o755)
    return str(script)


def test_edit_reconciles_shims(comma, env, launcher, tmp_path) -> None:
    editor = _editor(
        tmp_path,
        "open(sys.argv[1], 'a').write('\\n[commands.ed]\\ncmd = [\"/bin/echo\", \"edited\"]\\n')\n",
    )

    result = comma("edit", env_overrides={"EDITOR": editor})

    assert result.returncode == 0, result.stderr
    assert (shim_dir(env) / "ed,").is_symlink()
    activate(env)
    assert run_shim(env, "ed,").stdout.strip() == "edited"


def test_edit_removes_orphan_shims(comma, env, launcher, tmp_path) -> None:
    make_shim(env, launcher, "orphan")
    editor = _editor(tmp_path, "pass\n")

    result = comma("edit", env_overrides={"EDITOR": editor})

    assert result.returncode == 0, result.stderr
    assert not (shim_dir(env) / "orphan,").exists()


def test_edit_reports_broken_config(comma, env, launcher, tmp_path) -> None:
    editor = _editor(tmp_path, "open(sys.argv[1], 'a').write('\\n[commands.broken\\n')\n")

    result = comma("edit", env_overrides={"EDITOR": editor})

    assert result.returncode == 1
    assert "invalid TOML" in result.stderr


def test_add_unset_flag(comma, env, launcher) -> None:
    comma("add", "--unset", "TOKEN", "clean", "--", "/bin/echo", "hi")

    payload = json.loads(comma("ls", "--json").stdout)

    assert payload["clean"]["env_unset"] == ["TOKEN"]
