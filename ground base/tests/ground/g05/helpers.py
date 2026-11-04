"""Shared constructors for executor tests."""

from __future__ import annotations

from pathlib import Path

from patrol.contract import RunContext
from patrol.ground.extensions.g05.implementation import OperationExecutor, create
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.testing.builders import build_test_services, service_ports


def make_executor(
    tmp_path: Path,
    *,
    clock_mode: str = "manual",
) -> tuple[OperationExecutor, BaseServices]:
    services = build_test_services(clock_mode=clock_mode, output_dir=tmp_path, seed=0)
    return create(services.kernel, service_ports(services)), services


def manual(services: BaseServices) -> ManualClock:
    clock = services.kernel.clock
    if not isinstance(clock, ManualClock):
        raise AssertionError("expected the manual clock")
    return clock


async def finished(context: RunContext) -> str:
    del context
    return "done"
