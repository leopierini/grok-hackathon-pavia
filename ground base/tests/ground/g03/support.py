"""Shared session fixtures for GROUND-03 tests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g03.implementation import create
from patrol.ground.extensions.g03.script import Script, sample_incident
from patrol.ground.extensions.g03.store import SessionStore
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports


def open_session(
    tmp_path: Path,
    *,
    modes: Mapping[str, str] | None = None,
    transport: str = "ethernet",
    mission_id: str = "mission-1",
) -> tuple[object, SessionStore, Script]:
    services = build_test_services(output_dir=tmp_path)
    created = create(services.kernel, service_ports(services))
    if not isinstance(created, SessionStore):
        raise AssertionError("expected the state store")
    settings = make_settings(
        modes=dict(modes) if modes is not None else None,
        dog_transport=transport,
    )
    incident = sample_incident(mission_id)
    created.open(incident, settings)
    script = Script(services.kernel.authority, created, mission_id)
    return services, created, script
