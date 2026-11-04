"""StatePort factory. The one-argument form exists so the Task 01 harness can run it."""

from __future__ import annotations

from typing import overload

from patrol.ground.extensions.g03.harness import SimulationFeature
from patrol.ground.extensions.g03.store import SessionStore
from patrol.ground.kernel.contracts import BaseServices, KernelContext, ServicePorts
from patrol.ground.kernel.faults import fault

__all__ = ["SessionStore", "SimulationFeature", "create"]


@overload
def create(kernel: BaseServices, peers: None = None) -> SimulationFeature: ...


@overload
def create(kernel: KernelContext, peers: ServicePorts) -> SessionStore: ...


def create(
    kernel: KernelContext | BaseServices,
    peers: ServicePorts | None = None,
) -> SessionStore | SimulationFeature:
    if isinstance(kernel, BaseServices):
        if peers is not None:
            raise fault("invalid_input", "simulation create accepts services alone")
        return SimulationFeature(kernel)
    if peers is None:
        raise fault("invalid_input", "peers are required")
    return SessionStore(kernel, peers)
