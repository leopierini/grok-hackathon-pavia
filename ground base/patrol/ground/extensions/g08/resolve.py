"""Lazy factory resolution. Production never falls back to private stubs."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import cast

from patrol.ground.kernel.faults import fault

COMPONENTS: tuple[str, ...] = ("dog", "drone", "reasoner")
MODE_KEYS: dict[str, str] = {"dog": "dog", "drone": "drone", "reasoner": "grok"}
PUBLIC_FACTORIES: dict[str, tuple[str, str]] = {
    "dog": ("patrol.dog", "create_dog"),
    "drone": ("patrol.drone", "create_drone"),
    "reasoner": ("patrol.grok", "create_reasoner"),
}
MISSING_PUBLIC = (
    "public factory missing: "
    "patrol.dog:create_dog, patrol.drone:create_drone, patrol.grok:create_reasoner"
    "; no private fallback"
)


def resolve_factories(resolver: Mapping[str, object]) -> dict[str, Callable[..., object]]:
    if isinstance(resolver, (str, bytes)) or not isinstance(resolver, Mapping):
        raise fault("invalid_input", "resolver must be a mapping")
    source = resolver.get("source", "public")
    if not isinstance(source, str):
        raise fault("invalid_input", "resolver source must be a string")
    if source == "private-stub":
        return _private(resolver)
    if source != "public":
        raise fault("invalid_input", "resolver source must be public or private-stub")
    return _public()


def _private(resolver: Mapping[str, object]) -> dict[str, Callable[..., object]]:
    factories: dict[str, Callable[..., object]] = {}
    for name in COMPONENTS:
        target = resolver.get(name)
        if not callable(target):
            raise fault("invalid_input", f"private stub {name} factory is missing")
        factories[name] = target
    return factories


def _public() -> dict[str, Callable[..., object]]:
    factories: dict[str, Callable[..., object]] = {}
    missing: list[str] = []
    for name in COMPONENTS:
        module_name, attr = PUBLIC_FACTORIES[name]
        loaded = _load(module_name, attr)
        if loaded is None:
            missing.append(f"{module_name}:{attr}")
        else:
            factories[name] = loaded
    if missing:
        raise fault("unavailable", MISSING_PUBLIC)
    return factories


def _load(module_name: str, attr: str) -> Callable[..., object] | None:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing_name = exc.name or ""
        if missing_name == module_name or missing_name.startswith(module_name + "."):
            return None
        raise fault(
            "unavailable",
            f"public factory {module_name}:{attr} failed: {exc}",
        ) from exc
    except Exception as exc:
        raise fault(
            "unavailable",
            f"public factory {module_name}:{attr} failed: {type(exc).__name__}: {exc}",
        ) from exc
    target = getattr(module, attr, None)
    if not callable(target):
        return None
    return cast(Callable[..., object], target)
