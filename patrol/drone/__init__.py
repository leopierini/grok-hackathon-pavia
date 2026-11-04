"""Drone adapter. Fake mode imports no flight SDK and opens no sockets."""

from pathlib import Path
from typing import Any, Mapping

from patrol.contract import AdapterError, DronePort, Mode

from patrol.drone.fake import FakeDrone

__all__ = ["FakeDrone", "RealDrone", "create_drone"]


def create_drone(
    *,
    mode: Mode,
    config: Mapping[str, Any],
    output_dir: Path,
) -> DronePort:
    """Build a drone adapter. Does not connect or fly."""
    if mode not in ("fake", "real"):
        raise AdapterError("invalid_input", f"unknown mode {mode!r}")
    if not isinstance(config, Mapping):
        raise AdapterError("invalid_input", "config must be a mapping")
    output = Path(output_dir)
    if mode == "fake":
        return FakeDrone(config=config, output_dir=output)
    from patrol.drone.real import RealDrone

    return RealDrone(config=config, output_dir=output)


def __getattr__(name: str):
    if name == "RealDrone":
        from patrol.drone.real import RealDrone

        return RealDrone
    raise AttributeError(name)
