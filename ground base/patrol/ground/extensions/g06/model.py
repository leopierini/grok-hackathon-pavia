"""Evidence types owned by GROUND-06.

These are the validator's result objects. The kernel's ``EvidenceResult`` and
``CaptureInterval`` stay the shared contract; ``patrol.ground.base`` adapts
between the two.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from patrol.contract import Frame, Mode, Zone

SourceName = str

GROUND_ERROR_CODES: frozenset[str] = frozenset(
    {
        "invalid_type",
        "invalid_source",
        "invalid_zone",
        "invalid_mode",
        "invalid_path",
        "invalid_simulation_flag",
        "source_mismatch",
        "zone_mismatch",
        "simulation_mismatch",
        "relative_path",
        "invalid_output_root",
        "not_found",
        "not_regular_file",
        "symlink_escape",
        "containment_escape",
        "empty_file",
        "oversized",
        "not_jpeg",
        "truncated_jpeg",
        "corrupt_jpeg",
        "decoder_error",
        "unreadable",
        "null_timestamp",
        "naive_timestamp",
        "malformed_timestamp",
        "future_timestamp",
        "pre_request",
        "outside_interval",
        "missing_interval",
        "invalid_interval",
        "disappeared",
        "changed_during_validation",
        "clock_error",
    }
)


@dataclass(frozen=True)
class GroundError:
    code: str
    detail: str
    recovery_required: bool = False

    def __post_init__(self) -> None:
        if self.code not in GROUND_ERROR_CODES:
            raise ValueError(f"undeclared ground error code: {self.code}")


@dataclass(frozen=True)
class GroundEvent:
    kind: str
    ticket: object | None
    payload: Mapping[str, object]


@dataclass(frozen=True)
class CaptureInterval:
    """UTC bounds of the operation that was allowed to capture a live frame."""

    started_at: str
    ended_at: str
    started_monotonic: float | None = None
    ended_monotonic: float | None = None


@dataclass(frozen=True)
class EvidenceLimits:
    max_bytes: int = 8 * 1024 * 1024
    max_pixels: int = 8_000_000


@dataclass(frozen=True)
class EvidenceResult:
    status: str
    frame: Frame | None
    identity: Mapping[str, object] | None
    provenance: Mapping[str, object] | None
    reason: str
    detail: str
    error: GroundError | None
    events: tuple[GroundEvent, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "detail": self.detail,
            "frame": None
            if self.frame is None
            else {
                "path": self.frame.path,
                "source": self.frame.source,
                "zone": self.frame.zone,
                "captured_at": self.frame.captured_at,
                "simulated": self.frame.simulated,
            },
            "identity": None if self.identity is None else dict(self.identity),
            "provenance": None if self.provenance is None else dict(self.provenance),
            "error": None
            if self.error is None
            else {
                "code": self.error.code,
                "detail": self.error.detail,
                "recovery_required": self.error.recovery_required,
            },
            "events": [
                {"kind": event.kind, "payload": dict(event.payload)} for event in self.events
            ],
        }


class EvidencePort(Protocol):
    async def validate(
        self,
        frame: Frame,
        *,
        expected_source: SourceName,
        zone: Zone,
        mode: Mode,
        output_root: Path,
        interval: CaptureInterval | None,
    ) -> EvidenceResult: ...


@dataclass
class KernelContext:
    """Host object the evidence tests pass in. It is not the shared kernel."""

    clock: object
    io: object
    limits: EvidenceLimits = field(default_factory=EvidenceLimits)
    authority: object | None = None


@dataclass
class ServicePorts:
    """Peers the validator must not call."""

    config: object = None
    state: object = None
    journal: object = None
    executor: object = None
    evidence: object = None
    console: object = None
    adapters: object = None
    workflow: object = None
    safety: object = None
    dog: object = None
    drone: object = None
    reasoner: object = None


def freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(dict(values))
