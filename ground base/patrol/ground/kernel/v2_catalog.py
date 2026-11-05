"""Gate C ownership for the drone-first providers, separate from the v1 ABI."""

from __future__ import annotations

V2_SCHEMA = "ground-task-v2"
V2_SLOTS: dict[str, str] = {
    f"feature.v2_{name}": f"{number:02d}"
    for number, name in enumerate(
        (
            "envelope",
            "capabilities",
            "drone_observation",
            "frame",
            "vision_schedule",
            "vision_decision",
            "drone_command",
            "drone_ack",
            "beacon",
            "dog_navigation",
            "rssi",
            "rssi_homing",
            "dog_command",
            "dog_ack",
            "dog_acquire",
            "proximity",
            "recovery",
            "safety",
            "logs",
            "links",
            "metrics",
            "rehearsal",
        ),
        start=11,
    )
}
