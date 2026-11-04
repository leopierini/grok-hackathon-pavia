"""Shared doubles for the v2 journal. Construction does not emit."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from patrol.ground.extensions.g29.implementation import LogFeature, create
from patrol.ground.kernel.contracts import BaseServices, FeatureRequest, Ticket
from patrol.ground.testing.builders import build_test_services


@pytest.fixture
def services(tmp_path: Path) -> BaseServices:
    return build_test_services(output_dir=tmp_path)


@pytest.fixture
def feature(services: BaseServices) -> LogFeature:
    created = create(services)
    if not isinstance(created, LogFeature):
        raise AssertionError("factory did not return the journal")
    return created


def run(test: Callable[[], Awaitable[None]]) -> None:
    import asyncio

    asyncio.run(test())


def request(
    name: str,
    payload: dict[str, object],
    ticket: Ticket | None = None,
) -> FeatureRequest:
    return FeatureRequest("stage", name, ticket, payload)


def fixture_root() -> Path:
    return Path(__file__).resolve().parents[3] / "fixtures" / "ground" / "g29"


def load_example(name: str) -> dict[str, object]:
    loaded = json.loads((fixture_root() / "examples" / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} is not an object")
    return loaded


def load_catalog() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    text = (fixture_root() / "example-events.jsonl").read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if not isinstance(loaded, dict):
            raise AssertionError("catalog line is not an object")
        rows.append(loaded)
    return rows


def journal_count(services: BaseServices) -> int:
    records = getattr(services.journal, "records", None)
    if not isinstance(records, list):
        raise AssertionError("journal double has no records")
    return len(records)
