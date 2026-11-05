"""Extra link-check edges: types, real mode, and direct probes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.ground.extensions.g30.implementation import create
from patrol.ground.extensions.g30.probe import scripted_probe
from patrol.ground.kernel.contracts import FeatureRequest
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g30.test_ready import _event, _feature, _run


def test_direct_probe_matches_the_ethernet_fixture(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    probe = scripted_probe("ethernet_ready")

    async def body() -> None:
        scripted = await feature.execute(
            FeatureRequest("diagnostic", "ethernet_ready", None, {"seed": 0})
        )
        direct = await feature.execute(
            FeatureRequest("diagnostic", "check", None, {"probe": probe})
        )
        assert direct.status == scripted.status
        assert direct.data["detail"] == scripted.data["detail"]
        assert _event(direct)["profile"] == "ethernet-tether"

    asyncio.run(body())


def test_wired_pi_path_is_ready(tmp_path: Path) -> None:
    probe = scripted_probe("ethernet_ready")
    probe["pi_path"] = "wired"
    feature = _feature(tmp_path)

    async def body() -> None:
        result = await feature.execute(
            FeatureRequest("diagnostic", "check", None, {"probe": probe})
        )
        assert result.status == "ok"
        assert _event(result)["pi_path"] == "wired"

    asyncio.run(body())


def test_physical_probe_is_labeled_only_when_the_fixture_says_so(tmp_path: Path) -> None:
    probe = scripted_probe("ethernet_ready")
    probe["probe_mode"] = "real"
    probe["evidence"] = "physically_demonstrated"
    links = probe["links"]
    assert isinstance(links, dict)
    for name in ("dog", "drone", "pi", "internet"):
        link = links[name]
        assert isinstance(link, dict)
        link["simulated"] = False
    feature = _feature(tmp_path)

    async def body() -> None:
        result = await feature.execute(
            FeatureRequest("diagnostic", "check", None, {"probe": probe})
        )
        event = _event(result)
        assert result.status == "ok"
        assert result.data["simulated"] is False
        assert event["evidence"] == "physically_demonstrated"
        assert event["ready"] is True

    asyncio.run(body())


def test_edges(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    expected = {
        "wifi_no_acceptance": "blocked:wifi_acceptance",
        "no_fallback": "blocked:transport_switch",
        "simulated_real_mode": "blocked:simulated_probe",
        "physical_claim": "blocked:physical_claim",
        "string_tether": "blocked:tether_accepted_type",
        "pi_link_down": "blocked:pi_link",
        "internet_down": "blocked:internet_link",
        "not_simultaneous": "blocked:not_simultaneous",
        "unknown_pi_path": "blocked:unknown_pi_path",
        "pi_data_path": "blocked:pi_data_path",
    }
    for name, detail in expected.items():
        result = _run(feature, name)
        assert result.data["detail"] == detail, name
        assert result.status != "ok"


def test_repair_and_unknown_fields_do_not_run(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    repair = scripted_probe("ethernet_ready")
    repair["actions"] = ["repair_router"]
    unknown = scripted_probe("ethernet_ready")
    unknown["firewall"] = "off"

    async def body() -> None:
        repaired = await feature.execute(
            FeatureRequest("diagnostic", "check", None, {"probe": repair})
        )
        rejected = await feature.execute(
            FeatureRequest("diagnostic", "check", None, {"probe": unknown})
        )
        assert repaired.status == "failed"
        assert repaired.error is not None
        assert repaired.error.code == "forbidden_command"
        assert repaired.data["detail"] == "blocked:forbidden_action"
        assert "action:repair_router" in repaired.data["trace"]
        assert rejected.status == "failed"
        assert rejected.error is not None
        assert rejected.error.code == "invalid_input"
        rendered = json.dumps(dict(rejected.data))
        assert "off" not in rendered

    asyncio.run(body())


def test_factory_and_unknown_case(tmp_path: Path) -> None:
    with pytest.raises(GroundFault) as caught:
        create(None)  # type: ignore[arg-type]
    assert caught.value.error.code == "invalid_input"
    feature = _feature(tmp_path)
    result = _run(feature, "not_a_case")
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_input"
