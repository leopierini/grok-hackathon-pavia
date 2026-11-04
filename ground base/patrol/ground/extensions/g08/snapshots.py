"""Availability returned by the gateway. Device sample times are never invented."""

from __future__ import annotations

from dataclasses import dataclass

EVIDENCE_GAPS: tuple[str, ...] = (
    "sdk_capability_unproven",
    "worker_quiescence_unproven",
    "telemetry_freshness_unproven",
    "status_has_no_device_timestamp",
    "no_public_workers_idle",
    "no_public_reset",
)


@dataclass(frozen=True)
class ComponentSnapshot:
    component: str
    availability: str
    status: object
    observed_at: str
    device_sample_time: None
    recovery_required: bool
    detail: str
    generation: int
    dog_transport: str | None
    profile_identity: str | None
    evidence_gaps: tuple[str, ...]
