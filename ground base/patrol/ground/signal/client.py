"""xAI chat call used only by the signal connector.

The key is read from ``XAI_API_KEY``. It is not accepted as a Ground argument
and it is not written into errors, decisions, or logs.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Protocol

from patrol.ground.signal.errors import SignalError

# Documented xAI chat endpoint. Not a robot host.
API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_IMAGE_MODEL = "grok-4.20-non-reasoning"
PLACEHOLDER_MODEL = "CONFIGURE_VERIFIED_IMAGE_MODEL"
TIMEOUT_S = 5.0

_SYSTEM = (
    "You answer one closed-demo vision check. "
    "Reply with one JSON object and no other text. "
    "Keys are target_state (person_visible, not_visible, or uncertain), "
    "confidence (a number from 0 to 1), "
    "box_xyxy_norm (xmin, ymin, xmax, ymax, each from 0 to 1, or null), "
    "and reason (one plain sentence about what is in the frame). "
    "Do not give movement instructions, distances, speeds, or device commands. "
    "A visible person is not permission to move anything."
)


class PostJson(Protocol):
    """HTTP POST that returns a status code and a body. Tests supply a fake."""

    def __call__(
        self,
        url: str,
        payload: bytes,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> tuple[int, bytes]: ...


def require_api_key(environ: Mapping[str, str] | None = None) -> str:
    """Return the key or raise. The value is not included in the error."""

    source = os.environ if environ is None else environ
    key = source.get("XAI_API_KEY", "")
    if not isinstance(key, str) or not key.strip():
        raise SignalError("unsupported", "XAI_API_KEY is unset; no model request was sent")
    return key.strip()


def model_for_request(requested: object) -> str:
    """Use a real image model. The placeholder in rehearsal requests is not callable."""

    if isinstance(requested, str):
        text = requested.strip()
        if text and text != PLACEHOLDER_MODEL:
            return text
    return DEFAULT_IMAGE_MODEL


def build_user_prompt(request_payload: Mapping[str, object]) -> str:
    frame = request_payload.get("frame")
    camera = ""
    frame_id = ""
    if isinstance(frame, Mapping):
        camera = str(frame.get("camera_id", ""))
        frame_id = str(frame.get("frame_id", ""))
    target = str(request_payload.get("target_description", ""))
    stage = str(request_payload.get("stage", ""))
    return (
        f"Stage: {stage}. Camera: {camera}. Frame: {frame_id}. "
        f"Target description: {target}. "
        "Say whether one person matching that description is visible. "
        "If several people are visible, use target_state uncertain."
    )


def post_json(
    url: str,
    payload: bytes,
    headers: Mapping[str, str],
    timeout_s: float,
) -> tuple[int, bytes]:
    """POST JSON. Network errors become ``SignalError`` and do not echo the key."""

    request = urllib.request.Request(
        url,
        data=payload,
        headers={str(key): str(value) for key, value in headers.items()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(getattr(response, "status", 200))
            body = response.read()
            return status, body
    except urllib.error.HTTPError as exc:
        try:
            _ignored = exc.read()
        except OSError:
            _ignored = b""
        return int(exc.code), b""
    except TimeoutError as exc:
        raise SignalError("timeout", "xAI request timed out; no decision was returned") from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        timed_out = isinstance(reason, TimeoutError) or "timed out" in str(reason).lower()
        if timed_out:
            raise SignalError("timeout", "xAI request timed out; no decision was returned") from exc
        raise SignalError("unavailable", "xAI request failed; no decision was returned") from exc


def call_model(
    jpeg: bytes,
    *,
    model: str,
    prompt: str,
    api_key: str,
    transport: PostJson | None = None,
    timeout_s: float = TIMEOUT_S,
) -> Mapping[str, object]:
    """Send JPEG bytes and return the model's JSON object."""

    encoded = base64.standard_b64encode(jpeg).decode("ascii")
    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "high"},
                    },
                ],
            },
        ],
    }
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    sender = post_json if transport is None else transport
    try:
        status, raw = sender(API_URL, payload, headers, timeout_s)
    except SignalError:
        raise
    except TimeoutError as exc:
        raise SignalError("timeout", "xAI request timed out; no decision was returned") from exc
    except OSError as exc:
        raise SignalError("unavailable", "xAI request failed; no decision was returned") from exc
    if status != 200:
        raise SignalError("api_error", f"xAI returned HTTP {status}; no decision was returned")
    return _reading_object(raw)


def _reading_object(raw: bytes) -> Mapping[str, object]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalError("invalid_input", "xAI reply was not JSON") from exc
    if not isinstance(parsed, dict):
        raise SignalError("invalid_input", "xAI reply was not a JSON object")
    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        raise SignalError("invalid_input", "xAI reply did not include a choice")
    first = choices[0]
    if not isinstance(first, dict):
        raise SignalError("invalid_input", "xAI reply choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise SignalError("invalid_input", "xAI reply did not include a message")
    content = message.get("content")
    text = _content_text(content)
    return _parse_model_json(text)


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)
    raise SignalError("invalid_input", "xAI reply content was empty")


def _parse_model_json(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    value: object
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise SignalError("invalid_input", "xAI reply was not a JSON object") from None
        try:
            value = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise SignalError("invalid_input", "xAI reply was not a JSON object") from exc
    if not isinstance(value, dict):
        raise SignalError("invalid_input", "xAI reply was not a JSON object")
    return {str(key): item for key, item in value.items()}
