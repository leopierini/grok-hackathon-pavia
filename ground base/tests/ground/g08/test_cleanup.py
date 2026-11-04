"""Close attempts every adapter and keeps the original fault visible."""

from __future__ import annotations

from pathlib import Path

import pytest
from patrol.contract import AdapterError
from patrol.ground.kernel.faults import GroundFault
from tests.ground.g08.helpers import open_gateway, permit, run


def test_cleanup_attempts_every_adapter(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.dog.route_result = AdapterError("device_error", "boom")
        bundle.dog.close_error = RuntimeError("dog close failed")
        bundle.drone.close_error = RuntimeError("drone close failed")
        ticket, context = permit(kernel, "cleanup")
        with pytest.raises(GroundFault):
            await gateway.invoke(
                "dog",
                "run_route",
                ("room_2", context),
                ticket=ticket,
                context=context,
            )
        with pytest.raises(GroundFault) as closed:
            await gateway.close()
        detail = closed.value.error.detail
        assert detail.startswith("primary: dog.run_route: AdapterError: device_error: boom")
        assert "dog: RuntimeError: dog close failed" in detail
        assert "drone: RuntimeError: drone close failed" in detail
        assert bundle.log.count("dog.close") == 1
        assert bundle.log.count("drone.close") == 1
        assert bundle.log.count("reasoner.close") == 1
        with pytest.raises(GroundFault) as again:
            await gateway.close()
        assert again.value.error.detail == detail
        assert bundle.log.count("reasoner.close") == 1

    run(body)
