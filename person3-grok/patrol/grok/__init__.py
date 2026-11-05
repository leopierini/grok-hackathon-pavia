"""Grok reasoner factory.

``fake`` returns the v1 scripted reasoner. ``real`` reads ``XAI_API_KEY`` and
still does not call xAI: this factory is the v1 port (``assess_incident`` and
the other v1 methods). The demo image call is
``patrol.ground.signal.assess_frame`` in the Ground tree, which is the only
place that sends JPEG bytes. The key is never put in an error string.
"""

from __future__ import annotations

import os
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
    """Return the fake reasoner. ``real`` does not open a socket or call xAI."""
    if mode == "fake":
        return FakeReasoner(config, Path(output_dir))
    if mode == "real":
        key = os.environ.get("XAI_API_KEY", "")
        if not isinstance(key, str) or not key.strip():
            raise AdapterError(
                "unsupported",
                "XAI_API_KEY is unset; no model request was sent",
            )
        raise AdapterError(
            "unsupported",
            "create_reasoner is the v1 port and does not return a vision.decision; "
            "use patrol.ground.signal.assess_frame for the demo image call. "
            "No model request was sent from this factory.",
        )
    raise AdapterError("invalid_input", f"unknown reasoner mode: {mode}")
