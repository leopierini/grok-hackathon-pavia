"""Post-dispatch presence labels. Grok only says still-there, gone, or unsure."""

from __future__ import annotations

PRESENCE_PROMPT_VERSION = "patrol-presence-v1"

PRESENCE_STATES = frozenset({"person_visible", "not_visible", "uncertain", "timeout"})

# Dog front after YOLO has already dispatched. Drone downward uses the same prompt.
DOG_STAGE = "dog_approach"
DOG_CAMERA = "front"
DRONE_STAGE = "drone_track"
DRONE_CAMERA = "downward"

STANDOFF_M = 2.0
WARNING_ID = "go-away"
WARNING_TEXT = "go away"


def presence_state(scenario: str) -> str:
    """Map a fake scenario name onto a presence state."""
    table = {
        "still_there": "person_visible",
        "person_visible": "person_visible",
        "gone": "not_visible",
        "not_visible": "not_visible",
        "unsure": "uncertain",
        "uncertain": "uncertain",
        "timeout": "timeout",
    }
    try:
        return table[scenario]
    except KeyError as exc:
        raise ValueError(f"unknown presence scenario: {scenario}") from exc


def image_direction(box_xyxy_norm: tuple[float, float, float, float] | list[float] | None) -> str:
    """Thirds of the frame from the box centre x. No box means unknown."""
    if not box_xyxy_norm:
        return "unknown"
    centre_x = (float(box_xyxy_norm[0]) + float(box_xyxy_norm[2])) / 2.0
    if centre_x < (1.0 / 3.0):
        return "left"
    if centre_x < (2.0 / 3.0):
        return "center"
    return "right"


def suggested_action(stage: str, state: str) -> str:
    """Scene label for a presence state. These are not motor commands."""
    if state == "timeout":
        return "review"
    if state == "uncertain":
        return "review"
    if state == "not_visible":
        return "stop"
    if state != "person_visible":
        raise ValueError(f"unknown presence state: {state}")
    if stage in {DOG_STAGE, "dog_acquire"}:
        return "approach"
    if stage in {DRONE_STAGE, "drone_search"}:
        return "hold"
    raise ValueError(f"unknown stage: {stage}")
