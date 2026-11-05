"""Live Grok calls on real camera bytes (issue #62).

The rehearsal connector (``assess_frame``) only accepts hashed fixture JPEGs and
stays that way. This module is the live path: the JPEG comes straight from the
drone or dog camera, the reading is labelled ``simulated: false``, and nothing
here can move a robot. Ground's live mission decides what a reading means.

The key is read from ``XAI_API_KEY`` or from ``~/.config/patrol/xai.env``
(``XAI_API_KEY=...``). It never appears in a return value, an error or a log.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.signal.client import (
    API_URL,
    DEFAULT_IMAGE_MODEL,
    PostJson,
    _content_text,
    _parse_model_json,
    call_model,
    post_json,
)
from patrol.ground.signal.decision import reading_from_model
from patrol.ground.signal.errors import SignalError

KEY_FILE = Path.home() / ".config" / "patrol" / "xai.env"
LIVE_TIMEOUT_S = 8.0

_CAMERA_HINT = {
    "drone": "This frame is from a small indoor drone camera looking over a closed demo area.",
    "dog": "This frame is from the front camera of a quadruped robot at about knee height.",
}


def load_api_key(environ: Mapping[str, str] | None = None, key_file: Path = KEY_FILE) -> str:
    env = os.environ if environ is None else environ
    value = env.get("XAI_API_KEY", "").strip()
    if value:
        return value
    try:
        for line in key_file.read_text(encoding="utf-8").splitlines():
            name, sep, raw = line.partition("=")
            if sep and name.strip() in {"XAI_API_KEY", "export XAI_API_KEY"}:
                value = raw.strip().strip('"').strip("'")
                if value:
                    return value
    except OSError:
        pass
    raise SignalError("unavailable", "XAI_API_KEY is not set and ~/.config/patrol/xai.env has no key")


def presence_prompt(camera: str, target: str) -> str:
    hint = _CAMERA_HINT.get(camera, "")
    return (
        f"{hint} Target: {target}. Answer person_visible only if THAT target is visible; "
        "other people who do not match the target do not count (answer not_visible). "
        "If visible, give the tightest box around the target person only. "
        "In reason, describe the person and scene in one plain sentence "
        "(clothing, posture, what they are doing)."
    )


def assess_live(
    jpeg: bytes,
    *,
    camera: str,
    target: str = "a person in the closed demo area",
    api_key: str | None = None,
    transport: PostJson | None = None,
    model: str = DEFAULT_IMAGE_MODEL,
) -> dict[str, object]:
    """One presence reading on real bytes. Raises ``SignalError`` on any failure."""

    if not jpeg.startswith(b"\xff\xd8"):
        raise SignalError("invalid_input", "frame is not a JPEG")
    key = api_key or load_api_key()
    started = time.monotonic()
    raw = call_model(
        jpeg,
        model=model,
        prompt=presence_prompt(camera, target),
        api_key=key,
        transport=transport,
        timeout_s=LIVE_TIMEOUT_S,
    )
    reading = reading_from_model(raw)
    return {
        "camera": camera,
        "model_id": model,
        "target_state": reading.target_state,
        "confidence": reading.confidence,
        "box_xyxy_norm": list(reading.box) if reading.box else None,
        "reason": reading.reason,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "simulated": False,
    }


_ALERT_SYSTEM = (
    "You write the alert for a security patrol demo in a closed museum gallery. "
    "Reply with one JSON object and no other text. Keys: "
    "alert (two short sentences for the operator: what was seen, by which camera, current status), "
    "spoken (one short polite sentence the robot dog says aloud to the person, asking them to "
    "leave the closed area; no threats). Never give movement or device commands."
)


def compose_alert(
    observations: list[Mapping[str, object]],
    *,
    api_key: str | None = None,
    transport: PostJson | None = None,
    model: str = DEFAULT_IMAGE_MODEL,
) -> dict[str, str]:
    """Text-only Grok call: operator alert plus the sentence the dog speaks."""

    key = api_key or load_api_key()
    lines = [
        f"- {o.get('camera')} camera: {o.get('target_state')} ({o.get('reason')})" for o in observations
    ]
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _ALERT_SYSTEM},
            {"role": "user", "content": "Observations so far:\n" + "\n".join(lines)},
        ],
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    sender = post_json if transport is None else transport
    status, raw = sender(API_URL, json.dumps(body).encode("utf-8"), headers, LIVE_TIMEOUT_S)
    if status != 200:
        raise SignalError("api_error", f"xAI returned HTTP {status}; no alert was written")
    try:
        parsed = json.loads(raw.decode("utf-8"))
        text = _content_text(parsed["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalError("invalid_input", "xAI alert reply was not readable") from exc
    value = _parse_model_json(text)
    alert = value.get("alert")
    spoken = value.get("spoken")
    if not isinstance(alert, str) or not alert.strip():
        raise SignalError("invalid_input", "xAI alert reply had no alert text")
    if not isinstance(spoken, str) or not spoken.strip():
        spoken = "This area is closed. Please leave the gallery."
    return {"alert": alert.strip()[:400], "spoken": spoken.strip()[:200], "model_id": model}
