"""A real writer failure must cross the Protocol bridge as an error."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from patrol.ground.base import ProtocolJournal
from patrol.ground.extensions.g04.implementation import Journal
from patrol.ground.extensions.g04.writer import FaultWriter
from patrol.ground.kernel.contracts import EventRecord
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.validation import freeze_map, freeze_str_map
from patrol.ground.testing.builders import build_test_services


@pytest.mark.parametrize("operation", ["emit", "flush", "publish"])
def test_base_journal_does_not_hide_writer_failure(tmp_path: Path, operation: str) -> None:
    async def run() -> None:
        services = build_test_services(output_dir=tmp_path)
        writer = FaultWriter()
        real = Journal(services.kernel, services, writer=writer)
        port = ProtocolJournal(real, modes={"dog": "fake", "drone": "fake", "grok": "fake"})
        await port.open("run", tmp_path)
        record = EventRecord(
            1,
            services.kernel.clock.utc_now().isoformat(),
            0.0,
            "mission",
            None,
            "session",
            "incident_accepted",
            None,
            None,
            freeze_str_map({}),
            freeze_map({"valid": True}),
        )
        try:
            if operation == "emit":
                await real.close()
                with pytest.raises(GroundFault) as caught:
                    port.emit(record)
            elif operation == "flush":
                port.emit(record)
                await port.flush()
                writer.fail = "permission"
                port.emit(record)
                with pytest.raises(GroundFault) as caught:
                    await port.flush()
            else:
                writer.fail = "rename"
                with pytest.raises(GroundFault) as caught:
                    await port.publish({"outcome": "unresolved"})
            assert caught.value.error.code == "io_fault"
        finally:
            writer.fail = None
            await real.close()

    asyncio.run(run())
