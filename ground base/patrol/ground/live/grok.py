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
    """Simulation only. Drone: empty for ``empty_drone`` calls, then a person.
    Dog: empty for ``empty_dog`` calls, then a person off to the right who grows as
    the dog approaches. After ``leave_after`` visible dog frames the person leaves
    and both cameras report empty."""

    name = "scripted"

    def __init__(self, empty_drone: int = 2, empty_dog: int = 1, leave_after: int | None = 9) -> None:
        self.empty_drone = empty_drone
        self.empty_dog = empty_dog
        self.leave_after = leave_after
        self.calls = {"drone": 0, "dog": 0}
        self.left = False

    @staticmethod
    def _empty(camera: str) -> dict[str, Any]:
        return {"camera": camera, "model_id": "scripted", "target_state": "not_visible", "confidence": None,
                "box_xyxy_norm": None, "reason": "An empty gallery floor.", "latency_ms": 5, "simulated": True}

    def assess(self, jpeg: bytes, camera: str) -> dict[str, Any]:
        n = self.calls.get(camera, 0)
        self.calls[camera] = n + 1
        empty = self.empty_drone if camera == "drone" else self.empty_dog
        if n < empty or self.left:
            return self._empty(camera)
        k = n - empty
        if camera == "dog":
            if self.leave_after is not None and k >= self.leave_after:
                self.left = True
                return self._empty(camera)
            cx = 0.72 if k == 0 else 0.5
            h = min(0.8, 0.3 + 0.07 * k)
            box = [cx - 0.08, 0.5 - h / 2, cx + 0.08, 0.5 + h / 2]
        else:
            cx = min(0.8, 0.45 + 0.08 * k)
            box = [cx - 0.08, 0.2, cx + 0.08, 0.85]
        return {"camera": camera, "model_id": "scripted", "target_state": "person_visible", "confidence": 0.9,
                "box_xyxy_norm": box, "reason": "A person in a dark jacket is standing in the gallery.",
                "latency_ms": 5, "simulated": True}

    def alert(self, observations: list[Mapping[str, object]]) -> dict[str, str]:
        cams = ", ".join(sorted({str(o.get("camera")) for o in observations}))
        return {
            "alert": f"Person detected in the closed gallery ({cams} camera). Dog is responding; drone is tracking.",
            "spoken": DEFAULT_SPOKEN,
            "model_id": "scripted",
        }
