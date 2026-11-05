"""Lazy factory resolution. Production never falls back to private stubs."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
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
            loaded = _load_sibling(module_name, attr)
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


_SIBLING_DIRS = {
    "patrol.dog": "dog backend",
    "patrol.grok": "person3-grok",
    "patrol.drone": "",
}


def _load_sibling(module_name: str, attr: str) -> Callable[..., object] | None:
    """Load a factory from its own tree when ``patrol`` is already Ground's package.

    Dog, drone, and Grok each ship a ``patrol`` package. Putting every tree on
    ``sys.path`` hides one of them, so a missed import is retried with that tree
    alone and Ground's package is put back afterwards.
    """
    root = _sibling_root(module_name)
    if root is None:
        return None
    try:
        return _import_from_root(root, module_name, attr)
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


def _sibling_root(module_name: str) -> Path | None:
    folder = _SIBLING_DIRS.get(module_name)
    if folder is None:
        return None
    team = _team_root()
    if team is None:
        return None
    root = team if folder == "" else team / folder
    package = root / "patrol"
    if not package.is_dir():
        return None
    return root


def _team_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        dog = parent / "dog backend" / "patrol" / "dog" / "__init__.py"
        grok = parent / "person3-grok" / "patrol" / "grok" / "__init__.py"
        drone = parent / "patrol" / "drone" / "__init__.py"
        if dog.is_file() and grok.is_file() and drone.is_file():
            return parent
    return None


def _path_has_patrol(entry: str) -> bool:
    base = Path.cwd() if entry == "" else Path(entry)
    try:
        return (base / "patrol").exists()
    except OSError:
        return False


def _import_from_root(root: Path, module_name: str, attr: str) -> Callable[..., object] | None:
    saved = {
        key: sys.modules[key]
        for key in list(sys.modules)
        if key == "patrol" or key.startswith("patrol.")
    }
    saved_path = sys.path[:]
    for key in saved:
        del sys.modules[key]
    # A later ``patrol/__init__.py`` (Ground) would beat a namespace tree such as
    # ``dog backend``. Search only this component's tree plus non-patrol entries.
    sys.path[:] = [str(root), *[entry for entry in saved_path if not _path_has_patrol(entry)]]
    try:
        module = importlib.import_module(module_name)
        target = getattr(module, attr, None)
    finally:
        foreign = {
            key: sys.modules.pop(key)
            for key in list(sys.modules)
            if key == "patrol" or key.startswith("patrol.")
        }
        sys.modules.update(saved)
        sys.path[:] = saved_path
        alias = module_name.replace(".", "_")
        for key, loaded in foreign.items():
            sys.modules[f"_ground_public.{alias}.{key}"] = loaded
    if not callable(target):
        return None
    return cast(Callable[..., object], target)
