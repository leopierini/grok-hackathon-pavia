"""Task-owned copies of the drone contract examples."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from patrol.ground.kernel.paths import repo_root

TRACK_AT = "2026-11-04T13:00:10.210Z"
HOLD_AT = "2026-11-04T13:00:11.000Z"


def fixture_dir() -> Path:
    return repo_root() / "fixtures" / "ground" / "g17"


def load(name: str) -> dict[str, object]:
    text = (fixture_dir() / name).read_text(encoding="utf-8")
    raw: object = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be an object")
    loaded: dict[str, object] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ValueError(f"{name} has a non-string key")
        loaded[key] = value
    return loaded


def payload_of(document: Mapping[str, object]) -> dict[str, object]:
    body = document["payload"]
    if not isinstance(body, dict):
        raise ValueError("fixture payload must be an object")
    return cast(dict[str, object], body)


def features_of(document: Mapping[str, object]) -> dict[str, object]:
    features = payload_of(document)["features"]
    if not isinstance(features, dict):
        raise ValueError("fixture features must be an object")
    return cast(dict[str, object], features)


def armed_context() -> dict[str, object]:
    return {
        "proposal": load("ai-to-drone-proposal.json"),
        "operator_request": None,
        "capabilities": load("drone-capabilities.json"),
        "observation": load("drone-observation.json"),
        "allowlist": load("allowlist.json"),
        "calibration": True,
        "beacon_epoch": 4,
        "evaluated_at": TRACK_AT,
        "armed": True,
        "search_steps_taken": 0,
        "seed": 0,
    }


def operator_request(action: str, request_id: str, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "request_id": request_id,
        "action": action,
        "track_id": "target-001",
        "camera_id": "downward",
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "simulated": True,
        "reason": "Operator request for one allowlisted primitive.",
    }
    body.update(extra)
    return body


def operator_context(
    action: str,
    request_id: str,
    *,
    evaluated_at: str = HOLD_AT,
    **extra: object,
) -> dict[str, object]:
    context = armed_context()
    context["proposal"] = None
    context["operator_request"] = operator_request(action, request_id, **extra)
    context["evaluated_at"] = evaluated_at
    return context
