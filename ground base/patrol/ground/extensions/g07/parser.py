"""Operator command grammar. Invalid text is rejected and never executed."""

from __future__ import annotations

import re

from patrol.ground.kernel.catalog import COMMANDS, ZONES
from patrol.ground.kernel.contracts import Command
from patrol.ground.kernel.faults import fault

MAX_COMMAND_CHARS = 256
_PRINTABLE = re.compile(r"^[A-Za-z0-9 _-]*$")


def parse_operator_text(text: str) -> Command:
    if not isinstance(text, str):
        raise fault("invalid_input", "command text must be a string")
    if len(text) > MAX_COMMAND_CHARS:
        raise fault("invalid_input", "command exceeds 256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise fault("invalid_input", "command contains control characters")
    if _PRINTABLE.fullmatch(text) is None:
        raise fault("invalid_input", "command contains unsupported characters")
    parts = text.strip().split()
    if not parts:
        raise fault("invalid_input", "command is empty")
    name = parts[0]
    if name not in COMMANDS:
        raise fault("invalid_input", "unknown command")
    args = tuple(parts[1:])
    if name == "arrived":
        if len(args) != 1 or args[0] not in ZONES:
            raise fault("invalid_input", "arrived requires one known zone")
    elif args:
        raise fault("invalid_input", "command does not take arguments")
    return Command(name=name, args=args, raw=text)
