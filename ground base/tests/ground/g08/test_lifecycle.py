"""Single ownership, profiles, and quiescent recreation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from patrol.ground.extensions.g08.implementation import create
from patrol.ground.extensions.g08.support import Bundle
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports
from tests.ground.g08.helpers import open_gateway, permit, run


def test_duplicate_owner_and_real_stub_are_rejected(tmp_path: Path) -> None:
    async def body() -> None:
        _kernel, bundle, gateway = await open_gateway(tmp_path)
        with pytest.raises(GroundFault) as duplicate:
            await gateway.build(
                make_settings(
                    adapter_configs={
                        "dog": {"transport": "ethernet"},
                        "drone": {},
                        "grok": {},
                    }
                ),
                tmp_path,
                resolver=bundle.resolver(),
            )
        assert duplicate.value.error.detail == "duplicate dog connection"
        await gateway.close()

        services = build_test_services(output_dir=tmp_path / "real")
        replacement = Bundle(services.kernel)
        created = create(services.kernel, service_ports(services))
        with pytest.raises(GroundFault) as substituted:
            await created.build(  # type: ignore[union-attr]
                make_settings(modes={"dog": "real", "drone": "fake", "grok": "fake"}),
                tmp_path / "real",
                resolver=replacement.resolver(),
            )
        assert substituted.value.error.detail == "real-to-fake substitution"
        assert replacement.log == []

    run(body)


def test_profile_switch_uses_one_dog_after_close(tmp_path: Path) -> None:
    async def body() -> None:
        profiles = json.loads(
            (repo_root() / "fixtures" / "ground" / "g08" / "profiles.json").read_text(
                encoding="utf-8"
            )
        )
        assert profiles["ethernet"]["transport"] == "ethernet"
        assert profiles["wifi"]["transport"] == "wifi"
        _kernel, bundle, gateway = await open_gateway(tmp_path, transport="ethernet")
        await gateway.close()
        await gateway.build(
            make_settings(
                dog_transport="wifi",
                profile_identity="dog.wifi",
                adapter_configs={
                    "dog": profiles["wifi"],
                    "drone": {},
                    "grok": {},
                },
            ),
            tmp_path,
            resolver=bundle.resolver(),
        )
        assert gateway.live_components().count("dog") == 1
        dog_configs = [
            item["config"]["transport"]  # type: ignore[index]
            for item in bundle.kwargs
            if item["component"] == "dog"
        ]
        assert dog_configs == ["ethernet", "wifi"]
        await gateway.close()
        services = build_test_services(output_dir=tmp_path / "mismatch")
        mismatched = Bundle(services.kernel)
        created = create(services.kernel, service_ports(services))
        with pytest.raises(GroundFault) as mismatch:
            await created.build(  # type: ignore[union-attr]
                make_settings(
                    dog_transport="ethernet",
                    adapter_configs={"dog": {"transport": "wifi"}, "drone": {}, "grok": {}},
                ),
                tmp_path / "mismatch",
                resolver=mismatched.resolver(),
            )
        assert mismatch.value.error.code == "invalid_input"
        assert mismatch.value.error.detail == (
            "dog config transport does not match the selected profile"
        )

    run(body)


def test_cancelled_outer_call_still_blocks_recreation(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.dog.hold = "pending-route"
        kernel.barriers.arm("pending-route")
        ticket, context = permit(kernel, "pending")
        first = asyncio.create_task(
            gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        )
        for _ in range(30):
            await asyncio.sleep(0)
            if "dog.run_route" in bundle.log:
                break
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        with pytest.raises(GroundFault) as blocked:
            await gateway.build(make_settings(), tmp_path, resolver=bundle.resolver())
        assert blocked.value.error.detail == "pending worker blocks recreation"
        kernel.barriers.release("pending-route")
        pending = [task for task in gateway._workers if not task.done()]
        if pending:
            await asyncio.gather(*pending)
        await gateway.close()
        await gateway.build(make_settings(), tmp_path, resolver=bundle.resolver())
        assert gateway.live_components().count("dog") == 1
        await gateway.close()

    run(body)
