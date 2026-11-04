"""Factory resolution, frozen keywords, and boundary types."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import pytest
from patrol.contract import DogStatus
from patrol.ground.extensions.g08.implementation import create
from patrol.ground.extensions.g08.snapshots import EVIDENCE_GAPS
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports
from tests.ground.g08.helpers import open_gateway, permit, run


def test_import_does_not_load_vendor_or_public_adapters() -> None:
    banned = (
        "patrol.dog",
        "patrol.drone",
        "patrol.grok",
        "djitellopy",
        "unitree_webrtc_connect",
        "xai_sdk",
    )
    assert all(name not in sys.modules for name in banned)


def test_private_stub_receives_exact_keywords(tmp_path: Path) -> None:
    async def body() -> None:
        _kernel, bundle, gateway = await open_gateway(tmp_path)
        assert len(bundle.kwargs) == 3
        for item in bundle.kwargs:
            assert set(item) == {"component", "mode", "config", "output_dir"}
            assert item["mode"] == "fake"
            output = item["output_dir"]
            assert isinstance(output, str)
            assert Path(output).is_absolute()
            config = item["config"]
            assert not isinstance(config, (str, bytes))
            assert isinstance(config, Mapping)
        dog = next(item for item in bundle.kwargs if item["component"] == "dog")
        assert dog["config"]["transport"] == "ethernet"  # type: ignore[index]
        await gateway.close()

    run(body)


def test_public_resolver_does_not_call_private_stubs(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(output_dir=tmp_path)
        created = create(services.kernel, service_ports(services))
        called = False

        def stub(*, mode: str, config: Mapping[str, object], output_dir: str) -> object:
            del mode, config, output_dir
            nonlocal called
            called = True
            return object()

        with pytest.raises(GroundFault) as caught:
            await created.build(  # type: ignore[union-attr]
                make_settings(),
                tmp_path,
                resolver={"source": "public", "dog": stub, "drone": stub, "reasoner": stub},
            )
        assert caught.value.error.code == "unavailable"
        assert "no private fallback" in caught.value.error.detail
        assert called is False

    run(body)


def test_wrong_factory_and_status_types_fail_at_the_boundary(tmp_path: Path) -> None:
    async def body() -> None:
        services = build_test_services(output_dir=tmp_path)
        created = create(services.kernel, service_ports(services))

        def bad(*, mode: str, config: Mapping[str, object], output_dir: str) -> str:
            del mode, config, output_dir
            return "not-an-adapter"

        with pytest.raises(GroundFault) as caught:
            await created.build(  # type: ignore[union-attr]
                make_settings(),
                tmp_path,
                resolver={
                    "source": "private-stub",
                    "dog": bad,
                    "drone": bad,
                    "reasoner": bad,
                },
            )
        assert caught.value.error.code == "contract_mismatch"

        kernel, bundle, gateway = await open_gateway(tmp_path / "typed")
        bundle.dog.connect_result = DogStatus(True, cast(Any, "yes"), None, None)
        with pytest.raises(GroundFault) as status_error:
            await gateway.connect("dog")
        assert status_error.value.error.code == "contract_mismatch"
        assert "standing" in status_error.value.error.detail
        ticket, context = permit(kernel, "takeoff")
        with pytest.raises(GroundFault) as forbidden:
            await gateway.invoke("drone", "takeoff", (), ticket=ticket, context=context)
        assert forbidden.value.error.code == "forbidden_command"
        assert "drone.takeoff" not in bundle.log
        assert "no_public_workers_idle" in EVIDENCE_GAPS
        await gateway.close()

    run(body)
