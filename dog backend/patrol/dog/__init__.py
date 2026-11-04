"""Dog adapter package. Importing it never imports the Unitree vendor library."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from patrol.contract import AdapterError, DogPort, Mode

from .fake import FakeDog

__all__ = ["create_dog", "FakeDog", "RealDog"]


def create_dog(*, mode: Mode, config: Mapping[str, Any], output_dir: Path) -> DogPort:
    """Instantiate a dog adapter. Synchronous; no connection, motion, or I/O."""
    if not isinstance(config, Mapping):
        raise AdapterError("invalid_input", "dog config must be a mapping")
    if mode == "fake":
        return FakeDog(config=config, output_dir=Path(output_dir))
    if mode == "real":
        try:
            from .real import RealDog
        except ImportError as exc:
            raise AdapterError("unsupported", f"real dog adapter unavailable: {exc}") from exc
        return RealDog(config=config, output_dir=Path(output_dir))
    raise AdapterError("invalid_input", f"unknown dog mode {mode!r}")


def __getattr__(name: str) -> Any:
    if name == "RealDog":  # lazy: only real mode pays for the vendor import
        from .real import RealDog
        return RealDog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
