"""Public patrol calls. The dog, drone, and AI implementations are not in this repo.

Ground records the call and does not perform it. Obstacle avoidance, Wi-Fi
bearing, image judgement, and landing on the QR code stay with those teammates.
"""

from __future__ import annotations

from typing import Any

DOG = "dog"
DRONE = "drone"
HELD = "held"

SITUATIONS = frozenset(
    {
        "awaiting_ai",
        "nothing_seen",
        "intruder_seen",
        "intruder_in_dog_camera",
        "safe_to_land",
        "not_safe",
    }
)
VERDICTS = SITUATIONS - {"awaiting_ai"}


class PatrolRejected(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class PatrolBoard:
    """The calls Ground may make, and the situation it is waiting on."""

    def __init__(self) -> None:
        self.phase = "idle"
        self.calls: list[dict[str, Any]] = []
        self.situation = "awaiting_ai"
        self.summary = "No AI verdict has been received."
        self.frames: list[dict[str, str]] = []
        self.land_called = False
        self.detail = "Patrol is idle. Start patrol does not move the dog or the drone."

    def start(self) -> str:
        if self.phase == "waiting":
            raise PatrolRejected("Patrol is already waiting for the drone.")
        self.phase = "waiting"
        self.land_called = False
        self._hold(
            "start_patrol",
            DRONE,
            "The drone tree is not in this repo, so the search was not started.",
        )
        self.detail = (
            "Patrol is waiting. The drone has not reported an intruder, so find_drone was not called."
        )
        return self.detail

    def intruder_reported(self) -> str:
        """The drone teammate says it sees someone. Ground does not check the picture."""
        if self.phase != "waiting":
            raise PatrolRejected("An intruder report is only accepted while patrol is waiting.")
        self._hold(
            "find_drone",
            DOG,
            "The dog tree is changing, and the Wi-Fi point is not computed here, so find_drone was not sent.",
        )
        self.situation = "intruder_seen"
        self.summary = "The drone reported an intruder. Ground did not judge the image."
        self.detail = "find_drone is recorded and was not sent. The dog's own walker would take the Wi-Fi point."
        return self.detail

    def stop(self) -> str:
        if self.phase != "waiting":
            raise PatrolRejected("Start patrol before stopping it.")
        self.phase = "stopped"
        self._hold(
            "return_home",
            DOG,
            "The dog tree is changing, so return home was recorded and not sent.",
        )
        if self.situation == "safe_to_land":
            self._hold(
                "land",
                DRONE,
                "The drone tree is not in this repo. Landing was authorized and not sent.",
            )
            self.land_called = True
            self.detail = "Stop patrol recorded return home. Landing was authorized and not sent."
        else:
            self.land_called = False
            self.detail = (
                "Stop patrol recorded return home. Landing stays closed until the AI situation is safe_to_land."
            )
        return self.detail

    def record_frame(self, source: str, artifact_id: str) -> None:
        if source not in {DOG, DRONE}:
            raise PatrolRejected("A frame source must be dog or drone.")
        token = artifact_id.strip()
        if not token:
            raise PatrolRejected("A frame needs an artifact id.")
        self.frames.append({"source": source, "artifact_id": token})

    def apply_verdict(self, verdict: str, summary: str) -> None:
        """Store a verdict the AI teammate already made. This does not look at pixels."""
        if verdict not in VERDICTS:
            raise PatrolRejected("The AI verdict is not one of the situation names.")
        text = summary.strip()
        if not text:
            raise PatrolRejected("An AI verdict needs a summary.")
        self.situation = verdict
        self.summary = text

    def view(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "detail": self.detail,
            "situation": self.situation,
            "summary": self.summary,
            "land_called": self.land_called,
            "frames": list(self.frames),
            "calls": list(self.calls),
        }

    def _hold(self, name: str, target: str, reason: str) -> None:
        self.calls.append(
            {
                "name": name,
                "target": target,
                "status": HELD,
                "sent": False,
                "reason": reason,
            }
        )
