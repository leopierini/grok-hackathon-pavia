"""Slot lookup. A missing provider raises; it does not act as an approval."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from patrol.ground.kernel.catalog import SLOT_BY_NAME
from patrol.ground.kernel.contracts import FeaturePort
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.v2_catalog import V2_SLOTS


class FeatureMap:
    def __init__(self) -> None:
        self._ports: dict[str, FeaturePort] = {}

    def register(self, slot: str, port: FeaturePort) -> None:
        if slot not in SLOT_BY_NAME and slot not in V2_SLOTS:
            raise fault("unknown_slot", f"unknown slot {slot}")
        if slot in self._ports:
            raise fault("duplicate_slot", f"{slot} is already registered")
        self._ports[slot] = port

    def get(self, slot: str) -> FeaturePort:
        if slot not in SLOT_BY_NAME and slot not in V2_SLOTS:
            raise fault("unknown_slot", f"unknown slot {slot}")
        port = self._ports.get(slot)
        if port is None:
            raise fault(
                "missing_provider",
                f"{slot} is not installed",
                recovery_required=True,
            )
        return port

    def installed(self) -> Mapping[str, str]:
        return MappingProxyType(
            {
                slot: V2_SLOTS[slot] if slot in V2_SLOTS else SLOT_BY_NAME[slot].owner
                for slot in self._ports
            }
        )
