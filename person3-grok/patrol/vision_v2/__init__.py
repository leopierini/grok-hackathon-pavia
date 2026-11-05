"""Vision v2 adapter. Vik sends ``vision.decision`` only on this path.

``python -m patrol.vision_v2`` prints the published ``/ws/robot/v2`` endpoint.
The operator serves it on 127.0.0.1:8765 and checks ``GROUND_OPERATOR_TOKEN``.
"""

from patrol.vision_v2.artifacts import ArtifactError, resolve_artifact
from patrol.vision_v2.decision import build_decision, build_request

__all__ = ["ArtifactError", "build_decision", "build_request", "resolve_artifact"]
