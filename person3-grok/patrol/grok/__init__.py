"""Grok reasoner factory. Real mode does not run: transport and key stay outside this tree."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from patrol.contract import AdapterError
from patrol.grok.fake import FakeReasoner

__all__ = ["create_reasoner", "FakeReasoner"]


def create_reasoner(
    mode: str,
    config: Mapping[str, object],
    output_dir: str | Path,
) -> FakeReasoner:
    """Return the fake reasoner. ``real`` is refused without opening a socket."""
    if mode == "fake":
        return FakeReasoner(config, Path(output_dir))
    if mode == "real":
        raise AdapterError(
            "unsupported",
            "real Grok transport is unset (no host, port, or auth in this tree)",
        )
    raise AdapterError("invalid_input", f"unknown reasoner mode: {mode}")
