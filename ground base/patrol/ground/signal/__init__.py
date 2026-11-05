"""Vik's signal connector. Ground calls ``assess_frame`` for a real Grok reply.

Importing this package does not read ``XAI_API_KEY`` and does not open a socket.
"""

from patrol.ground.signal.client import require_api_key
from patrol.ground.signal.connector import assess_frame
from patrol.ground.signal.errors import SignalError

__all__ = ["SignalError", "assess_frame", "require_api_key"]
