"""Operator command parsing. Unknown text is rejected, never treated as motion."""

from __future__ import annotations

from patrol.ground.kernel.catalog import COMMANDS, ZONES
from patrol.ground.kernel.contracts import Command
from patrol.ground.kernel.faults import fault


def parse_command(text: str) -> Command:
    if not isinstance(text, str):
        raise fault("invalid_input", "command text must be a string")
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
