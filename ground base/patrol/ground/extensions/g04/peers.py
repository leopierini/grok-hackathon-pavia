"""Peer bag for journal tests.

The journal stores this object and must not call it. The real service graph
uses ``patrol.ground.kernel.contracts.ServicePorts`` instead.
"""

from __future__ import annotations


class ServicePorts:
    def __init__(self, **peers: object) -> None:
        self._peers = dict(peers)
        for name, value in peers.items():
            setattr(self, name, value)

    def __getattr__(self, name: str) -> object:
        if name in self._peers:
            return self._peers[name]
        return None
