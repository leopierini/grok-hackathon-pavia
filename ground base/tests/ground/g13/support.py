"""Shared setup for drone-observation tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g13.implementation import ObservationFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest
from patrol.ground.testing.builders import build_test_services

ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "ground" / "g13"


def services(output: Path) -> BaseServices:
    return build_test_services(clock_mode="manual", seed=0, output_dir=output)


def feature(output: Path) -> tuple[BaseServices, ObservationFeature]:
    peer = services(output)
    created = create(peer)
    if not isinstance(created, ObservationFeature):
        raise TypeError("observation factory did not return its feature")
    return peer, created


def load(name: str) -> dict[str, object]:
    raw = json.loads((ROOT / name).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("fixture must be an object")
    return raw


def request_for(
    envelope: Mapping[str, object],
    capability: Mapping[str, object],
    *,
    mission_epoch: int = 1,
    received_monotonic: float | None = None,
    height_label: str | None = None,
    ticket: object = None,
) -> FeatureRequest:
    payload: dict[str, object] = {
        "envelope": envelope,
        "capability": capability,
        "mission_epoch": mission_epoch,
    }
    if received_monotonic is not None:
        payload["received_monotonic"] = received_monotonic
    if height_label is not None:
        payload["height_label"] = height_label
    return FeatureRequest("stage", "drone.observation", ticket, payload)  # type: ignore[arg-type]
