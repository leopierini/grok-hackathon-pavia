"""Validated GroundSettings values. File loading belongs to the config provider."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import cast

from patrol.ground.kernel.catalog import (
    DOG_TRANSPORTS,
    LAUNCH_TIERS,
    MODES,
    SCENARIOS,
    ZONES,
)
from patrol.ground.kernel.contracts import GroundSettings
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map, freeze_str_map


def make_settings(
    *,
    zones: tuple[str, ...] = ("entrance", "room_2", "display"),
    profile_by_zone: Mapping[str, str] | None = None,
    launch_tier: str = "floor",
    dog_transport: str = "ethernet",
    profile_identity: str = "dog.ethernet",
    arrival_timeout_s: float = 15.0,
    flight_ready_timeout_s: float = 30.0,
    incident_timeout_s: float = 180.0,
    route_limit_s: float = 30.0,
    flight_limit_s: float = 30.0,
    model_limit_s: float = 20.0,
    prepare_limit_s: float = 10.0,
    capture_limit_s: float = 10.0,
    connect_limit_s: float = 10.0,
    output_root: str = "artifacts",
    adapter_configs: Mapping[str, Mapping[str, object]] | None = None,
    modes: Mapping[str, str] | None = None,
    scenario: str = "blocked_resolved",
) -> GroundSettings:
    zone_values = tuple(zones)
    if not zone_values or any(zone not in ZONES for zone in zone_values):
        raise fault("invalid_input", "zones must use the frozen zone names")
    if launch_tier not in LAUNCH_TIERS:
        raise fault("invalid_input", "unknown launch tier")
    if dog_transport not in DOG_TRANSPORTS:
        raise fault("invalid_input", "dog transport must be ethernet or wifi")
    if scenario not in SCENARIOS:
        raise fault("invalid_input", "unknown scenario")
    if not isinstance(profile_identity, str) or not profile_identity:
        raise fault("invalid_input", "profile identity is required")
    if not isinstance(output_root, str) or not output_root:
        raise fault("invalid_input", "output root is required")
    mode_map = freeze_str_map(modes or {"dog": "fake", "drone": "fake", "grok": "fake"})
    modes_ok = set(mode_map) == {"dog", "drone", "grok"} and all(
        mode in MODES for mode in mode_map.values()
    )
    if not modes_ok:
        raise fault("invalid_input", "modes must name dog, drone, and grok as fake or real")
    profiles = freeze_str_map(profile_by_zone or {"room_2": "room_2_view_v1"})
    for zone in profiles:
        if zone not in ZONES:
            raise fault("invalid_input", "profile map contains an unknown zone")
    private: dict[str, Mapping[str, object]] = {}
    for key, value in (adapter_configs or {}).items():
        if not isinstance(key, str) or isinstance(value, (str, bytes)):
            raise fault("invalid_input", "adapter config must be a mapping")
        if not isinstance(value, Mapping):
            raise fault("invalid_input", "adapter config must be a mapping")
        private[key] = freeze_map(value)
    return GroundSettings(
        zones=zone_values,
        profile_by_zone=profiles,
        launch_tier=launch_tier,
        dog_transport=dog_transport,
        profile_identity=profile_identity,
        arrival_timeout_s=_positive(arrival_timeout_s, "arrival_timeout_s"),
        flight_ready_timeout_s=_positive(flight_ready_timeout_s, "flight_ready_timeout_s"),
        incident_timeout_s=_positive(incident_timeout_s, "incident_timeout_s"),
        route_limit_s=_positive(route_limit_s, "route_limit_s"),
        flight_limit_s=_positive(flight_limit_s, "flight_limit_s"),
        model_limit_s=_positive(model_limit_s, "model_limit_s"),
        prepare_limit_s=_positive(prepare_limit_s, "prepare_limit_s"),
        capture_limit_s=_positive(capture_limit_s, "capture_limit_s"),
        connect_limit_s=_positive(connect_limit_s, "connect_limit_s"),
        output_root=output_root,
        adapter_configs=cast(
            "Mapping[str, Mapping[str, object]]",
            freeze_map(private),
        ),
        modes=mode_map,
        scenario=scenario,
    )


def redact(settings: GroundSettings) -> Mapping[str, object]:
    return {
        "zones": list(settings.zones),
        "profile_by_zone": dict(settings.profile_by_zone),
        "launch_tier": settings.launch_tier,
        "dog_transport": settings.dog_transport,
        "profile_identity": settings.profile_identity,
        "modes": dict(settings.modes),
        "scenario": settings.scenario,
        "output_root": settings.output_root,
        "adapter_configs": "redacted",
    }


def _positive(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fault("invalid_input", f"{label} must be a real number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise fault("invalid_input", f"{label} must be a positive finite number")
    return number
