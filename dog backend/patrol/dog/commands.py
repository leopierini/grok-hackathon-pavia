"""Dispatch a v2 dog.command onto the methods the dog already has.

Fake and real adapters both expose ``execute`` and ``play_warning``. Motion
words are recorded on the fake dog. The real dog speaks a warning and halts;
it does not invent a walk from a command envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from patrol.contract import AdapterError

_MOTION = frozenset({"approach", "follow", "return_home", "stand", "move_local", "turn"})


async def play_warning(dog: Any, warning_id: str, text: str) -> None:
    if not isinstance(warning_id, str) or not warning_id.strip() or len(warning_id) > 160:
        raise AdapterError("invalid_input", "warning_id must be a short string")
    if not isinstance(text, str) or not text.strip() or len(text) > 400:
        raise AdapterError("invalid_input", "warning text must be 1..400 characters")
    trace = getattr(dog, "trace", None)
    if isinstance(trace, list):
        trace.append(f"play_warning:{warning_id}")
    await dog.say(text)


async def execute(dog: Any, command: Mapping[str, Any]) -> str:
    if not isinstance(command, Mapping):
        raise AdapterError("invalid_input", "dog command must be an object")
    payload = command.get("payload", command)
    if not isinstance(payload, Mapping):
        raise AdapterError("invalid_input", "dog command payload must be an object")
    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise AdapterError("invalid_input", "dog command action is missing")
    if action == "play_warning":
        warning_id = payload.get("warning_id")
        text = payload.get("text")
        await play_warning(
            dog,
            warning_id if isinstance(warning_id, str) else "",
            text if isinstance(text, str) else "",
        )
        return action
    if action in {"stop", "halt"}:
        await dog.halt()
        return action
    if action in _MOTION:
        if type(dog).__name__ == "RealDog":
            raise AdapterError("unsupported", f"{action} is not a direct real-dog motion")
        trace = getattr(dog, "trace", None)
        if isinstance(trace, list):
            trace.append(action)
        return action
    raise AdapterError("invalid_input", f"unknown dog command {action!r}")
