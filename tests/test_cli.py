from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

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


def test_add_reclaims_a_shim_from_an_earlier_install(comma, env, launcher, echoargs) -> None:
    """`comma doctor` calls a leftover shim missing and says to re-run `comma add`.

    A shim from a previous install (pipx instead of `uv tool`, a venv since
    deleted) still points at a `comma` launcher, so that advice has to work
    instead of failing with "was not created by comma".
    """
    shim = shim_dir(env) / "gus,"
    shim.parent.mkdir(parents=True)
    shim.symlink_to("/opt/old-comma/bin/comma")

    result = comma("add", "gus", "--", str(echoargs), "hi")

    assert result.returncode == 0, result.stderr
    assert shim.resolve() == launcher.resolve()


def test_add_still_refuses_a_foreign_symlink(comma, env, launcher, echoargs, tmp_path) -> None:
    other = tmp_path / "another-tool"
    other.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    other.chmod(0o755)
    shim = shim_dir(env) / "gus,"
    shim.parent.mkdir(parents=True)
    shim.symlink_to(other)

    result = comma("add", "gus", "--", str(echoargs), "hi")

    assert result.returncode != 0
    assert "already exists" in result.stderr


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


def test_add_accepts_options_after_the_name(comma, env, launcher, echoargs, tmp_path) -> None:
    """`comma add NAME --env K=V --cwd DIR -- CMD` is the spelling people try first.

    The name reads better next to its options than before them, and the `--`
    already separates the command, so the position must not matter.
    """
    work = tmp_path / "work"
    work.mkdir()

    result = comma(
        "add", "gus", "--env", "A=1", "--cwd", str(work), "--", str(echoargs), "hi",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(comma("ls", "--json").stdout)
    assert payload["gus"]["cmd"] == [str(echoargs), "hi"]
    assert payload["gus"]["env"] == {"A": "1"}
    assert payload["gus"]["cwd"] == str(work)
    assert (shim_dir(env) / "gus,").is_symlink()


def _fake_comma(directory: Path) -> Path:
    """A `comma` on PATH that answers `completion` without starting Python."""
    script = directory / "comma"
    script.write_text(
        "#!/bin/sh\n"
        'case "$2" in\n'
        "  bash) printf '%s\\n' 'complete -F _fake_comma comma' '_fake_comma() { :; }' ;;\n"
        "  zsh)  printf '%s\\n' '_fake_comma() { :; }' 'compdef _fake_comma comma' ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_init_setup_avoids_process_substitution(comma, env) -> None:
    """The setup must not need `source <(...)`.

    macOS ships bash 3.2, which reads the process substitution without waiting
    for the writer: the sourced text is never executed, so the documented setup
    registers no completion at all, and the writer dies with BrokenPipeError.
    """
    for shell in ("bash", "zsh"):
        snippet = comma("init", "--shell", shell).stdout
        assert "<(" not in snippet


def test_bash_setup_registers_completion(comma, env, tmp_path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    _fake_comma(tmp_path)
    rc = tmp_path / "rc.bash"
    rc.write_text(comma("init", "--shell", "bash").stdout, encoding="utf-8")

    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", f"source {rc}; complete -p comma"],
        env={**env, "PATH": f"{tmp_path}:{env['PATH']}"},
        capture_output=True,
        text=True,
    )

    assert "_fake_comma" in result.stdout, result.stderr
    assert result.stderr == ""


def test_zsh_setup_registers_completion_without_compinit(comma, env, tmp_path) -> None:
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("zsh is not installed")
    _fake_comma(tmp_path)
    rc = tmp_path / "zshrc"
    rc.write_text(comma("init", "--shell", "zsh").stdout, encoding="utf-8")

    result = subprocess.run(
        [zsh, "-f", "-c", f"source {rc}; whence -w _fake_comma"],
        env={**env, "PATH": f"{tmp_path}:{env['PATH']}"},
        capture_output=True,
        text=True,
    )

    assert "function" in result.stdout, result.stderr
    assert result.stderr == ""


needs_permissions = pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0,
    reason="file permissions do not apply to root",
)


@needs_permissions
def test_unreadable_config_is_reported_not_raised(comma, env) -> None:
    """Restored dotfiles can come back owned by another user."""
    comma("add", "gus", "--", "/bin/echo", "hi")
    config = Path(env["XDG_CONFIG_HOME"]) / "comma" / "config.toml"
    config.chmod(0)
    try:
        result = comma("ls")
    finally:
        config.chmod(0o644)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "cannot read" in result.stderr
    assert str(config) in result.stderr


@needs_permissions
def test_unwritable_config_directory_is_reported(comma, env) -> None:
    comma("add", "gus", "--", "/bin/echo", "hi")
    directory = Path(env["XDG_CONFIG_HOME"]) / "comma"
    directory.chmod(0o555)
    try:
        result = comma("add", "bob", "--", "/bin/echo", "hi")
    finally:
        directory.chmod(0o755)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "cannot write" in result.stderr


@needs_permissions
def test_unwritable_shim_directory_is_reported(comma, env) -> None:
    comma("add", "gus", "--", "/bin/echo", "hi")
    shims = shim_dir(env)
    shims.chmod(0o555)
    try:
        result = comma("add", "bob", "--", "/bin/echo", "hi")
    finally:
        shims.chmod(0o755)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("comma: ")
