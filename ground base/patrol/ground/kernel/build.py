"""Kernel assembly. Construction does not connect devices or start tasks."""

from __future__ import annotations

from patrol.ground.kernel.authority import SessionAuthority
from patrol.ground.kernel.barriers import BarrierSet
from patrol.ground.kernel.clock import ManualClock, RealClock
from patrol.ground.kernel.contracts import KernelContext
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.features import FeatureMap
from patrol.ground.kernel.io import FaultyIO
from patrol.ground.kernel.simulator import KernelSimulator
from patrol.ground.kernel.tasks import RetainedTasks
from patrol.ground.kernel.validation import BoundaryValidation


def build_kernel(
    *,
    clock_mode: str = "manual",
    seed: int = 0,
    mode: str = "simulation",
) -> KernelContext:
    if clock_mode == "manual":
        clock: ManualClock | RealClock = ManualClock()
    elif clock_mode == "real":
        clock = RealClock()
    else:
        raise fault("invalid_input", "clock mode must be manual or real")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise fault("invalid_input", "seed must be an integer")
    if mode not in {"simulation", "live"}:
        raise fault("invalid_input", "kernel mode must be simulation or live")
    simulator = KernelSimulator()
    context = KernelContext(
        clock=clock,
        io=FaultyIO(),
        authority=SessionAuthority(),
        tasks=RetainedTasks(),
        features=FeatureMap(),
        result_validation=BoundaryValidation(),
        simulator=simulator,
        barriers=BarrierSet(),
        mode=mode,
        seed=seed,
    )
    simulator.bind(context)
    return context
