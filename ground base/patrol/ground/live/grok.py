"""Grok for the live mission: the real xAI path and a scripted stand-in for simulation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_SPOKEN = "Attention please. This gallery is closed. Please leave the area now."


class RealGrok:
    name = "xai"

    def __init__(self, target: str = "a person in the closed demo area") -> None:
        from patrol.ground.signal.live import load_api_key

        self.target = target
        self._key = load_api_key()  # fail early, before anything flies

    def assess(self, jpeg: bytes, camera: str) -> dict[str, Any]:
        from patrol.ground.signal.live import assess_live

        return assess_live(jpeg, camera=camera, target=self.target, api_key=self._key)

    def alert(self, observations: list[Mapping[str, object]]) -> dict[str, str]:
        from patrol.ground.signal.live import compose_alert

        return compose_alert(observations, api_key=self._key)


class ScriptedGrok:
    """Simulation only. Drone frames: empty for ``empty_drone`` calls, then a person
    drifting right. Dog frames: empty for ``empty_dog`` calls, then a person."""

    name = "scripted"

    def __init__(self, empty_drone: int = 2, empty_dog: int = 1) -> None:
        self.empty_drone = empty_drone
        self.empty_dog = empty_dog
        self.calls = {"drone": 0, "dog": 0}

    def assess(self, jpeg: bytes, camera: str) -> dict[str, Any]:
        n = self.calls.get(camera, 0)
        self.calls[camera] = n + 1
        empty = self.empty_drone if camera == "drone" else self.empty_dog
        if n < empty:
            return {
                "camera": camera,
                "model_id": "scripted",
                "target_state": "not_visible",
                "confidence": None,
                "box_xyxy_norm": None,
                "reason": "An empty gallery floor.",
                "latency_ms": 5,
                "simulated": True,
            }
        cx = min(0.8, 0.45 + 0.08 * (n - empty))
        return {
            "camera": camera,
            "model_id": "scripted",
            "target_state": "person_visible",
            "confidence": 0.9,
            "box_xyxy_norm": [cx - 0.08, 0.2, cx + 0.08, 0.85],
            "reason": "A person in a dark jacket is standing in the gallery.",
            "latency_ms": 5,
            "simulated": True,
        }

    def alert(self, observations: list[Mapping[str, object]]) -> dict[str, str]:
        cams = ", ".join(sorted({str(o.get("camera")) for o in observations}))
        return {
            "alert": f"Person detected in the closed gallery ({cams} camera). Dog is on alert; drone is tracking.",
            "spoken": DEFAULT_SPOKEN,
            "model_id": "scripted",
        }
