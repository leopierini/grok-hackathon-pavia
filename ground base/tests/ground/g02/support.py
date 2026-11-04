"""Shared builders for configuration tests."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g02.implementation import ConfigService, create
from patrol.ground.testing.builders import build_test_services, service_ports

FAKE: dict[str, str] = {"dog": "fake", "drone": "fake", "grok": "fake"}


def service(tmp_path: Path) -> ConfigService:
    services = build_test_services(output_dir=tmp_path / "out")
    return create(services.kernel, service_ports(services))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise AssertionError("expected a mapping")
