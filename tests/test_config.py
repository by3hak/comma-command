from __future__ import annotations

from pathlib import Path

import pytest

from comma_command import config as config_mod


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_is_empty_config(tmp_path: Path) -> None:
    assert config_mod.load(tmp_path / "nope" / "config.toml") == {}


def test_list_form(tmp_path: Path) -> None:
    path = write(
        tmp_path / "config.toml",
        '[commands.gus]\ncmd = ["too", "talk", "gus", "--"]\n',
    )
    commands = config_mod.load(path)
    assert commands["gus"].argv == ("too", "talk", "gus", "--")


def test_shorthand_string_form(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", '[commands.gus]\ncmd = "too talk gus --"\n')
    assert config_mod.load(path)["gus"].argv == ("too", "talk", "gus", "--")


def test_flat_table_form(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", '[commands]\ngus = "too talk gus --"\n')
    assert config_mod.load(path)["gus"].argv == ("too", "talk", "gus", "--")


def test_other_key_names(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", '[commands.gus]\ncommand = "echo hi"\n')
    assert config_mod.load(path)["gus"].argv == ("echo", "hi")


def test_roundtrip_keeps_awkward_arguments(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = {
        "gus": config_mod.Command("gus", ("too", "talk", "gus", "--")),
        # a name that needs a quoted TOML key, plus argument quoting traps
        "my.tool": config_mod.Command("my.tool", ("echo", "a b", 'q"uote', "中文")),
    }
    config_mod.save(path, original)
    assert '[commands."my.tool"]' in path.read_text(encoding="utf-8")
    assert config_mod.load(path) == original


def test_invalid_toml_raises(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", "[commands.gus\ncmd = 1\n")
    with pytest.raises(config_mod.ConfigError, match="invalid TOML"):
        config_mod.load(path)


def test_empty_command_raises(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", '[commands.gus]\ncmd = []\n')
    with pytest.raises(config_mod.ConfigError, match="empty"):
        config_mod.load(path)


def test_missing_cmd_key_raises(tmp_path: Path) -> None:
    path = write(tmp_path / "config.toml", '[commands.gus]\nenv = {}\n')
    with pytest.raises(config_mod.ConfigError, match="needs a 'cmd' key"):
        config_mod.load(path)


@pytest.mark.parametrize("name", ["", "-x", "a,b", "a/b", ".", "..", "has space"])
def test_invalid_names(name: str) -> None:
    with pytest.raises(config_mod.ConfigError):
        config_mod.validate_name(name)


@pytest.mark.parametrize("name", ["gus", "a", "my.tool", "x_y", "C++", "tool2"])
def test_valid_names(name: str) -> None:
    assert config_mod.validate_name(name) == name


def test_display_quotes_spaces() -> None:
    command = config_mod.Command("x", ("echo", "a b"))
    assert command.display() == "echo 'a b'"
