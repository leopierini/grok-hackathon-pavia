"""Grammar table for operator text."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.ground.extensions.g07.parser import parse_operator_text
from patrol.ground.kernel.contracts import Command
from patrol.ground.kernel.faults import GroundFault

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "fixtures" / "ground" / "g07"

GRAMMAR = (
    ("status", "status", ()),
    ("  arm  ", "arm", ()),
    ("start", "start", ()),
    ("arrived entrance", "arrived", ("entrance",)),
    ("arrived room_2", "arrived", ("room_2",)),
    ("arrived display", "arrived", ("display",)),
    ("flight-ready", "flight-ready", ()),
    ("halt", "halt", ()),
    ("reset", "reset", ()),
    ("quit", "quit", ()),
)

INVALID = (
    ("", "command is empty"),
    ("   ", "command is empty"),
    ("arrived", "arrived requires one known zone"),
    ("arrived lobby", "arrived requires one known zone"),
    ("arrived room_2 extra", "arrived requires one known zone"),
    ("status extra", "command does not take arguments"),
    ("flight-ready now", "command does not take arguments"),
    ("launch", "unknown command"),
    ("STATUS", "unknown command"),
    ("status;rm", "command contains unsupported characters"),
    ("status\x00", "command contains control characters"),
    ("\x1b[31mstatus", "command contains control characters"),
    ("status\t", "command contains control characters"),
    ("a" * 257, "command exceeds 256 characters"),
)


@pytest.mark.parametrize(("text", "name", "args"), GRAMMAR)
def test_grammar_accepts_exact_commands(text: str, name: str, args: tuple[str, ...]) -> None:
    command = parse_operator_text(text)
    assert command == Command(name, args, text)


@pytest.mark.parametrize(("text", "detail"), INVALID)
def test_invalid_input_is_rejected(text: str, detail: str) -> None:
    with pytest.raises(GroundFault) as caught:
        parse_operator_text(text)
    assert caught.value.error.code == "invalid_input"
    assert caught.value.error.detail == detail


def test_non_string_text_is_rejected() -> None:
    with pytest.raises(GroundFault) as caught:
        parse_operator_text(None)  # type: ignore[arg-type]
    assert caught.value.error.detail == "command text must be a string"


def test_fixture_lines_match_the_grammar() -> None:
    accepted = (FIXTURES / "commands.txt").read_text(encoding="utf-8").splitlines()
    for line in accepted:
        parsed = parse_operator_text(line)
        assert parsed.name
    rejected = (FIXTURES / "invalid_commands.txt").read_text(encoding="utf-8").splitlines()
    assert rejected
    for line in rejected:
        with pytest.raises(GroundFault):
            parse_operator_text(line)


def test_parser_source_has_no_unix_tty_api() -> None:
    root = ROOT / "patrol" / "ground" / "extensions" / "g07"
    banned = ("termios", "tty", "add_reader", "add_signal_handler")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text
