"""Turn one Ground ``vision.request`` into a ``vision.decision``.

Order of work: require ``XAI_API_KEY``, resolve the artifact, check SHA-256,
send the JPEG, then build the decision. A missing key or a missing artifact
raises ``SignalError`` before a success result is possible.
"""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.signal.artifacts import load_fixture_jpeg
from patrol.ground.signal.client import (
    PostJson,
    build_user_prompt,
    call_model,
    model_for_request,
    require_api_key,
)
from patrol.ground.signal.decision import decision_from_reading, reading_from_model
from patrol.ground.signal.errors import SignalError


def assess_frame(
    request: Mapping[str, object],
    *,
    transport: PostJson | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Answer one vision request. The API key never leaves this function's client call."""

    api_key = require_api_key(environ)
    if request.get("kind") != "vision.request":
        raise SignalError("invalid_input", "request kind must be vision.request")
    payload = request.get("payload")
    if not isinstance(payload, Mapping):
        raise SignalError("invalid_input", "request payload must be an object")
    frame = payload.get("frame")
    if not isinstance(frame, Mapping):
        raise SignalError("invalid_input", "request frame must be an object")
    image_ref = frame.get("image_ref")
    digest = frame.get("sha256")
    if not isinstance(image_ref, str) or not isinstance(digest, str):
        raise SignalError("invalid_input", "request frame needs an artifact URI and sha256")
    if request.get("simulated") is not True or frame.get("simulated") is not True:
        raise SignalError("unsafe_state", "rehearsal image evidence must stay simulated")
    jpeg = load_fixture_jpeg(image_ref, digest)
    model_id = model_for_request(payload.get("model_id"))
    prompt = build_user_prompt(payload)
    raw = call_model(
        jpeg,
        model=model_id,
        prompt=prompt,
        api_key=api_key,
        transport=transport,
    )
    reading = reading_from_model(raw)
    return decision_from_reading(request, reading, model_id=model_id)
