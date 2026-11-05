"""The one approved flight. Unknown profiles never reach the motors."""

from __future__ import annotations

import json
from pathlib import Path

from patrol.contract import AdapterError, LaunchOrigin, Zone

DEFAULT_PROFILE = (
    Path(__file__).resolve().parents[2] / "config" / "profiles" / "room_2_view_v1.json"
)


def load_profile(path: Path | None = None) -> dict:
    profile_path = Path(path) if path else DEFAULT_PROFILE
    try:
        data = json.loads(profile_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AdapterError("invalid_input", f"cannot read profile: {exc}") from exc
    if data.get("id") != "room_2_view_v1":
        raise AdapterError("invalid_input", "profile file is not room_2_view_v1")
    return data


def allow(profile_id: str, zone: Zone, origin: LaunchOrigin, path: Path | None = None) -> dict:
    """Reject a bad id, zone, or origin before any takeoff."""
    if profile_id != "room_2_view_v1":
        raise AdapterError("invalid_input", f"unknown profile {profile_id!r}")
    profile = load_profile(path)
    if zone != profile["zone"]:
        raise AdapterError("invalid_input", "profile is not for this zone")
    if origin not in profile["launch_origins"]:
        raise AdapterError(
            "unsupported",
            "this profile launches from the floor only",
        )
    return profile
