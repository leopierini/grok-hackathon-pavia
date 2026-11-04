"""Shared builders for GROUND-04 tests."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.extensions.g04.implementation import Journal, JournalLimits, create
from patrol.ground.extensions.g04.peers import ServicePorts
from patrol.ground.extensions.g04.writer import ArtifactWriter
from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.clock import ManualClock

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "ground" / "g04"
MODES = {"dog": "fake", "drone": "fake", "grok": "fake"}


class IdleIO:
    """Evidence IO double. The journal must not call it."""

    async def snapshot(self, path: Path) -> object:
        raise AssertionError("journal called evidence snapshot")

    async def read(self, path: Path, *, max_bytes: int) -> bytes:
        raise AssertionError("journal called evidence read")

    async def decode_jpeg(self, data: bytes, *, max_pixels: int) -> tuple[int, int]:
        raise AssertionError("journal called jpeg decode")


class Probe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> object:
        def record(*_args: object, **_kwargs: object) -> None:
            self.calls.append(name)

        return record


def journal_for(
    *,
    writer: ArtifactWriter | None = None,
    sanitizer: object | None = None,
    limits: JournalLimits | None = None,
    peers: ServicePorts | None = None,
    authority: object | None = None,
) -> tuple[Journal, ManualClock, ServicePorts]:
    clock = ManualClock()
    kernel = build_kernel(clock_mode="manual", seed=0, mode="simulation")
    kernel.clock = clock
    if authority is not None:
        kernel.authority = authority  # type: ignore[assignment]
    bound = peers or ServicePorts()
    created = create(kernel, bound, writer=writer, sanitizer=sanitizer, limits=limits)
    assert isinstance(created, Journal)
    return created, clock, bound


def event(
    name: str,
    *,
    mission: str = "m-1",
    state: str = "IDLE",
    seed: int = 0,
) -> dict[str, object]:
    return {
        "mission_id": mission,
        "state": state,
        "event": name,
        "zone": "room_2",
        "target": "person",
        "modes": dict(MODES),
        "data": {"seed": seed},
    }


def summary(mission: str = "m-1", *, error: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {
        "contract_version": "1.0",
        "mission_id": mission,
        "zone": "room_2",
        "modes": dict(MODES),
        "dispatch": "dispatch",
        "outcome": "alerted",
        "arrival_confirmed": False,
        "arrival_method": "simulated",
        "time_to_arrival_s": None,
        "inspection_requested": False,
        "launch_tier": "floor",
        "flight_state": "grounded",
        "recovery_required": False,
        "alert": "simulated",
    }
    if error is not None:
        body["error"] = error
        body["cleanup_error"] = "summary replace failed"
    return body
