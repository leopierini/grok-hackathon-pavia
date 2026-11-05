"""Shared setup for gateway tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

from patrol.contract import RunContext
from patrol.ground.extensions.g08.gateway import AdapterGateway
from patrol.ground.extensions.g08.implementation import create
from patrol.ground.extensions.g08.support import Bundle
from patrol.ground.kernel.contracts import KernelContext, Ticket
from patrol.ground.kernel.deadlines import context_for_stage
from patrol.ground.kernel.settings import make_settings
from patrol.ground.testing.builders import build_test_services, service_ports


def run(body: object) -> None:
    if not callable(body):
        raise AssertionError("test body must be callable")
    asyncio.run(body())


async def open_gateway(
    output: Path,
    *,
    transport: str = "ethernet",
    modes: Mapping[str, str] | None = None,
) -> tuple[KernelContext, Bundle, AdapterGateway]:
    services = build_test_services(output_dir=output)
    bundle = Bundle(services.kernel)
    created = create(services.kernel, service_ports(services))
    if not isinstance(created, AdapterGateway):
        raise AssertionError("factory did not return the gateway")
    await created.build(
        make_settings(
            dog_transport=transport,
            profile_identity=f"dog.{transport}",
            modes=modes,
            adapter_configs={
                "dog": {"transport": transport, "profile": f"dog.{transport}"},
                "drone": {},
                "grok": {},
            },
        ),
        output,
        resolver=bundle.resolver(),
    )
    return services.kernel, bundle, created


def permit(kernel: KernelContext, stage: str) -> tuple[Ticket, RunContext]:
    ticket = kernel.authority.issue(stage, stage)
    context = context_for_stage(
        stage,
        kernel.clock.monotonic() + 100,
        30,
        kernel.authority.cancel_event,
        kernel.clock,
        real_adapter=False,
    )
    return ticket, context
