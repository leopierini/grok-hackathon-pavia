"""Prompt transport, halt bypass, and scripted input."""

from __future__ import annotations

import asyncio
from pathlib import Path

from patrol.contract import Frame, Incident
from patrol.ground.extensions.g07.implementation import ConsoleService, create
from patrol.ground.kernel.contracts import BaseServices, WaitSpec
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput


def test_scripted_and_pipe_input_emit_the_same_commands(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        iterator = console.commands()
        scripted: list[str] = []
        for line in ("status", "arm", "quit"):
            await console.submit_turn((line,))
            scripted.append((await anext(iterator)).name)
        piped: list[str] = []
        with create_pipe_input() as pipe:
            await console.attach_prompt(pipe, DummyOutput(), patch=False)
            await asyncio.sleep(0)
            pipe.send_text("status\narm\nquit\n")
            for _index in range(3):
                piped.append((await asyncio.wait_for(anext(iterator), timeout=2)).name)
        assert scripted == piped == ["status", "arm", "quit"]
        assert any(event.kind == "shutdown_requested" for event in console.events)
        await console.close()

    asyncio.run(body())


def test_eof_signal_does_not_leave_an_input_thread(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(console.confirm(WaitSpec("arrival", "room_2", "eof", 30.0)))
        await asyncio.sleep(0)
        await console.submit_signal("eof")
        result = await pending
        assert result.detail == "cancelled"
        assert any(event.kind == "shutdown_requested" for event in console.events)
        assert services.kernel.authority.cancelled is True
        await console.close()
        await console.close()
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def test_halt_bypasses_a_blocked_command_handler(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        services.kernel.barriers.arm("handler")
        entered = asyncio.Event()

        async def handler() -> None:
            async for command in console.commands():
                if command.name == "status":
                    entered.set()
                    await services.kernel.barriers.wait("handler")
                if command.name == "halt":
                    return

        worker = asyncio.create_task(handler())
        try:
            await asyncio.sleep(0)
            await console.submit_turn(("status",))
            await entered.wait()
            await console.submit_turn(("halt",))
            assert services.kernel.authority.cancelled is True
            assert worker.done() is False
        finally:
            services.kernel.barriers.release("handler")
            await console.close()
            await worker

    asyncio.run(body())


def test_renderer_failure_still_latches_halt(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)

        def boom(_message: str) -> None:
            raise RuntimeError("renderer down")

        console.set_writer(boom)
        await console.submit_turn(("halt",))
        assert services.kernel.authority.cancelled is True
        assert console.renderer_errors == 1
        assert "renderer:isolated" in console.trace
        await console.close()

    asyncio.run(body())


def test_rejected_text_does_not_mutate_zone_or_call_devices(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        frame = Frame("C:/simulated/phone.jpg", "phone", "room_2", None, True)
        incident = Incident(
            "m1",
            "room_2",
            "a person or an object left in a marked closed area",
            frame,
        )
        services.state.open(incident, make_settings())
        console = _console(services)
        await console.submit_turn(("dog.run_route",))
        await console.submit_turn(("status\x1b",))
        snapshot = services.state.snapshot()
        assert snapshot.incident is not None
        assert snapshot.incident.zone == "room_2"
        assert snapshot.incident.target == incident.target
        assert "state.apply" not in services.state.trace
        devices = services.adapters.devices
        assert devices.calls == []
        await console.close()

    asyncio.run(body())


def test_close_is_idempotent_and_collects_tasks(tmp_path: Path) -> None:
    services = _services(tmp_path)

    async def body() -> None:
        console = _console(services)
        pending = asyncio.create_task(console.confirm(WaitSpec("arrival", "entrance", "end", 25.0)))
        await asyncio.sleep(0)
        await console.close()
        result = await pending
        await console.close()
        assert result.detail == "closed"
        assert services.kernel.tasks.pending() == ()

    asyncio.run(body())


def _services(tmp_path: Path) -> BaseServices:
    return build_test_services(clock_mode="manual", seed=7, output_dir=tmp_path)


def _console(services: BaseServices) -> ConsoleService:
    return create(services.kernel, service_ports(services))
