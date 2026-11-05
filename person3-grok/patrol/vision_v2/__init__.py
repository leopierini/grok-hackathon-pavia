"""Vision v2 adapter. Vik sends ``vision.decision`` only on this path.

Real WebSocket transport is unset. ``python -m patrol.vision_v2`` exits 2.
"""

from patrol.vision_v2.decision import build_decision, build_request

__all__ = ["build_decision", "build_request"]
