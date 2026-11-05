"""External contract shape and Ground boundary types."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from patrol.contract import (
    CONTRACT_VERSION,
    AdapterError,
    DogPort,
    DronePort,
    ReasonerPort,
)
from patrol.ground.kernel import (
    COMMANDS,
    PHASES,
    SCHEMA_VERSION,
    GroundFault,
    Ticket,
    make_settings,
    require_bool,
)
from patrol.ground.kernel.paths import repo_root


def test_contract_block_matches_plan() -> None:
    plan = (repo_root() / "plan.md").read_text(encoding="utf-8")
    marker = "```python\nfrom __future__ import annotations\n"
    start = plan.index(marker) + len("```python\n")
    end = plan.index("\n```", start)
    expected = plan[start:end] + "\n"
    actual = (repo_root() / "patrol" / "contract.py").read_text(encoding="utf-8")
    assert actual.replace("\r\n", "\n") == expected.replace("\r\n", "\n")


def test_contract_version_and_signatures() -> None:
    assert CONTRACT_VERSION == "1.0"
    assert list(inspect.signature(DogPort.run_route).parameters) == ["self", "zone", "ctx"]
    assert list(inspect.signature(DogPort.capture_frame).parameters) == ["self", "zone", "ctx"]
    assert list(inspect.signature(DronePort.inspect).parameters) == ["self", "request", "ctx"]
    assert list(inspect.signature(ReasonerPort.resolve_incident).parameters) == [
        "self",
        "incident",
        "ground",
        "aerial",
        "ctx",
    ]
    error = AdapterError("cancelled", "stop")
    assert error.code == "cancelled"
    assert isinstance(Ticket("mission", 1, "stage"), Ticket)


def test_string_is_not_a_boolean() -> None:
    with pytest.raises(GroundFault) as caught:
        require_bool("false", label="simulated")
    assert caught.value.error.code == "invalid_input"
    assert require_bool(False, label="simulated") is False


def test_settings_reject_non_finite_and_boolean_limits() -> None:
    with pytest.raises(GroundFault):
        make_settings(arrival_timeout_s=float("nan"))
    with pytest.raises(GroundFault):
        make_settings(route_limit_s=True)  # type: ignore[arg-type]
    settings = make_settings()
    assert settings.dog_transport == "ethernet"
    assert settings.scenario == "blocked_resolved"


def test_frozen_names_exist() -> None:
    assert "WAIT_ARRIVAL" in PHASES
    assert "flight-ready" in COMMANDS
    assert SCHEMA_VERSION == "ground-task-v1"
    assert Path(repo_root() / "patrol" / "contract.py").is_file()
