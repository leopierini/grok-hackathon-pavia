"""Failures for the vision signal connector. Ground does not see the API key."""

from __future__ import annotations


class SignalError(Exception):
    """Closed failure. No decision is returned and no robot call is made."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
