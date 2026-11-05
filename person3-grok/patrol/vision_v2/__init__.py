"""Vision v2 adapter. Vik sends ``vision.decision`` only on this path.

Real WebSocket transport is unset. ``python -m patrol.vision_v2`` exits 2.
"""

from patrol.vision_v2.artifacts import ArtifactError, resolve_artifact
from patrol.vision_v2.decision import build_decision, build_request

__all__ = ["ArtifactError", "build_decision", "build_request", "resolve_artifact"]
