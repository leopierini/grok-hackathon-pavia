"""Post-dispatch presence session.

YOLO already sent the dog. This session only reacts to still-there / gone / unsure.
Every dog or drone action is an intent for the bridge. Nothing here opens a socket.
Halt wins: one ``halt``, then silence.
"""

from __future__ import annotations

from dataclasses import dataclass

from patrol.grok.presence import STANDOFF_M, WARNING_ID, WARNING_TEXT


@dataclass(frozen=True)
class Intent:
    """One action the bridge will turn into a proposal and a command shape."""

    action: str
    target: str
    warning_id: str | None = None
    text: str | None = None
    standoff_m: float | None = None


def _warning() -> Intent:
    return Intent("play_warning", "dog", warning_id=WARNING_ID, text=WARNING_TEXT)


def _follow() -> Intent:
    return Intent("follow", "dog", standoff_m=STANDOFF_M)


class PresenceSession:
    def __init__(self) -> None:
        self.halted = False
        self.warned = False
        self.closed = False
        self.trace: list[str] = []

    def halt(self) -> list[Intent]:
        """Operator halt. One explicit dog halt, then no further intents."""
        if self.halted:
            self.trace.append("halt:already")
            return []
        self.halted = True
        self.trace.append("halt")
        return [Intent("halt", "dog")]

    def on_presence(self, state: str, stage: str) -> list[Intent]:
        """Return the intents for one presence read. Unsure and timeout move nothing."""
        if self.halted:
            self.trace.append(f"dropped:{state}:halted")
            return []
        if self.closed:
            self.trace.append(f"dropped:{state}:closed")
            return []
        if state in {"uncertain", "timeout"}:
            self.trace.append(f"hold:{state}")
            return []
        if state == "not_visible":
            self.closed = True
            self.trace.append("gone")
            return [
                Intent("stop", "dog"),
                Intent("land_on_dog", "drone"),
                Intent("return_home", "dog"),
            ]
        if state != "person_visible":
            raise ValueError(f"unknown presence state: {state}")
        if stage != "dog_approach":
            # Drone still-there is a vision.decision hold, not a dog command.
            self.trace.append(f"visible:{stage}:no-command")
            return []
        if not self.warned:
            self.warned = True
            self.trace.append("warn")
            return [_warning()]
        self.trace.append("follow-warn")
        return [_follow(), _warning()]
