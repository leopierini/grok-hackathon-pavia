"""Typed failures. GroundError stays a value; this exception carries one."""

from __future__ import annotations

from patrol.ground.kernel.catalog import ERROR_CODES
from patrol.ground.kernel.contracts import GroundError


class GroundFault(Exception):
    def __init__(self, error: GroundError) -> None:
        if error.code not in ERROR_CODES:
            error = GroundError("internal", "undeclared error code", True)
        self.error = error
        super().__init__(f"{error.code}: {error.detail}")


def fault(
    code: str,
    detail: str,
    *,
    recovery_required: bool = False,
) -> GroundFault:
    if code not in ERROR_CODES:
        return GroundFault(
            GroundError("internal", "undeclared error code", True)
        )
    return GroundFault(GroundError(code, detail, recovery_required))
