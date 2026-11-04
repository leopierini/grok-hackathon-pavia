"""Optional absence, active link loss, and unknown telemetry."""

from __future__ import annotations

from pathlib import Path

from patrol.contract import DogStatus, DroneStatus
from patrol.ground.extensions.g08.snapshots import EVIDENCE_GAPS
from tests.ground.g08.helpers import open_gateway, permit, run


def test_optional_drone_differs_from_active_link_loss(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.drone.connect_result = DroneStatus(False, "unknown", None)
        drone = await gateway.connect("drone")
        assert drone.availability == "optional_unavailable"
        assert drone.recovery_required is False
        assert isinstance(drone.status, DroneStatus)
        assert drone.status.flight_state == "unknown"
        assert drone.status.battery_percent is None
        assert drone.device_sample_time is None
        assert drone.observed_at == kernel.clock.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        assert drone.evidence_gaps == EVIDENCE_GAPS

        bundle.drone.connect_result = DroneStatus(True, "grounded", 80)
        bundle.drone.status_result = DroneStatus(False, "unknown", None)
        linked = await gateway.connect("drone")
        assert linked.availability == "available"
        lost = await gateway.status("drone")
        assert lost.availability == "active_link_loss"
        assert lost.recovery_required is True
        assert isinstance(lost.status, DroneStatus)
        assert lost.status.flight_state == "unknown"
        assert lost.status.battery_percent is None

        ticket, context = permit(kernel, "ground-only")
        await gateway.connect("dog")
        frame = await gateway.invoke(
            "dog",
            "capture_frame",
            ("room_2", context),
            ticket=ticket,
            context=context,
        )
        assert getattr(frame, "source", None) == "dog"
        assert "drone.inspect" not in bundle.log
        await gateway.close()

    run(body)


def test_unknown_dog_fields_stay_unknown(tmp_path: Path) -> None:
    async def body() -> None:
        kernel, bundle, gateway = await open_gateway(tmp_path)
        bundle.dog.connect_result = DogStatus(True, None, None, None)
        snapshot = await gateway.connect("dog")
        assert snapshot.availability == "unknown"
        assert isinstance(snapshot.status, DogStatus)
        assert snapshot.status.standing is None
        assert snapshot.status.stationary is None
        assert snapshot.status.avoidance_enabled is None
        assert snapshot.status.connected is True
        assert snapshot.device_sample_time is None
        assert snapshot.observed_at == kernel.clock.utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        await gateway.close()

    run(body)
