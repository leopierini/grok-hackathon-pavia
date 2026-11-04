"""Seeded peer doubles for a task that has no neighbouring providers."""

from __future__ import annotations

from pathlib import Path

from patrol.ground.kernel.build import build_kernel
from patrol.ground.kernel.contracts import BaseServices, ServicePorts
from patrol.ground.testing.devices import DeviceBundle
from patrol.ground.testing.services import (
    AdapterDouble,
    ConfigDouble,
    ConsoleDouble,
    EvidenceDouble,
    ExecutorDouble,
    JournalDouble,
    SafetyDouble,
    StateDouble,
    WorkflowDouble,
)


def build_test_services(
    *,
    clock_mode: str = "manual",
    seed: int = 0,
    scenario: str = "blocked_resolved",
    output_dir: Path,
) -> BaseServices:
    kernel = build_kernel(clock_mode=clock_mode, seed=seed, mode="simulation")
    devices = DeviceBundle(kernel, scenario=scenario, output_dir=output_dir)
    return BaseServices(
        kernel=kernel,
        config=ConfigDouble(kernel),
        state=StateDouble(kernel),
        journal=JournalDouble(kernel),
        executor=ExecutorDouble(kernel),
        evidence=EvidenceDouble(kernel),
        console=ConsoleDouble(kernel),
        adapters=AdapterDouble(kernel, devices),
        workflow=WorkflowDouble(kernel),
        safety=SafetyDouble(kernel),
    )


def service_ports(services: BaseServices) -> ServicePorts:
    return ServicePorts(
        config=services.config,
        state=services.state,
        journal=services.journal,
        executor=services.executor,
        evidence=services.evidence,
        console=services.console,
        adapters=services.adapters,
        workflow=services.workflow,
        safety=services.safety,
    )
