"""Static manifest loader. Factories are import paths, never shell commands."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from patrol.ground.kernel.catalog import SCHEMA_VERSION, SLOT_BY_NAME
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.v2_catalog import V2_SCHEMA, V2_SLOTS

_V2_SCHEMA = V2_SCHEMA
_FACTORY = re.compile(
    r"^patrol\.ground\.extensions\.(g\d{2})\.(implementation|scenarios):([A-Za-z_][A-Za-z0-9_]*)$"
)
_TASK = re.compile(r"^GROUND-(\d{2})$")
_ALLOWED_KEYS = frozenset(
    {"schema_version", "task_id", "slot", "factory", "scenario_factory"}
)
_COMMAND_MARKERS = ("\n", "\r", ";", "|", "&", "`", "$(")


@dataclass(frozen=True)
class ExtensionManifest:
    schema_version: str
    task_id: str
    slot: str
    factory: str
    scenario_factory: str
    path: Path
    directory: Path


def _owner(manifest: ExtensionManifest) -> str:
    """v2 slots are admitted by name. They are not rows in the v1 slot table."""
    if manifest.schema_version == _V2_SCHEMA:
        return V2_SLOTS[manifest.slot]
    return SLOT_BY_NAME[manifest.slot].owner


def _accept_slot(schema: str, slot: str) -> None:
    if schema == _V2_SCHEMA:
        if slot in V2_SLOTS:
            return
        raise fault("unknown_slot", f"unknown slot {slot}")
    if slot not in SLOT_BY_NAME:
        raise fault("unknown_slot", f"unknown slot {slot}")


def normalize_task(value: str) -> str:
    text = value.strip().lower().removeprefix("ground-")
    if not text.isdigit():
        raise fault("invalid_input", "task id must be a number from 01 to 32")
    number = int(text)
    if number < 1 or number > 32:
        raise fault("invalid_input", "task id must be a number from 01 to 32")
    return f"{number:02d}"


def discover(root: Path, *, only_task: str | None = None) -> tuple[ExtensionManifest, ...]:
    base = Path(root).resolve()
    if only_task is None:
        if not base.is_dir():
            return ()
        directories = [
            path
            for path in base.iterdir()
            if path.is_dir() and re.fullmatch(r"g\d{2}", path.name)
        ]
    else:
        directories = [base / f"g{normalize_task(only_task)}"]
    found: list[ExtensionManifest] = []
    for directory in directories:
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            if only_task is not None:
                raise fault("missing_provider", f"no manifest for task {only_task}")
            continue
        found.append(parse_manifest(manifest_path, base))
    found.sort(key=lambda item: item.task_id)
    seen_slots: dict[str, str] = {}
    seen_tasks: dict[str, str] = {}
    for manifest in found:
        if manifest.slot in seen_slots:
            raise fault(
                "duplicate_slot",
                f"{manifest.slot} is claimed by {seen_slots[manifest.slot]} and {manifest.task_id}",
            )
        if manifest.task_id in seen_tasks:
            raise fault("duplicate_task", f"{manifest.task_id} is declared more than once")
        owner = _owner(manifest)
        if manifest.task_id != f"GROUND-{owner}":
            raise fault(
                "owner_mismatch",
                f"{manifest.slot} belongs to GROUND-{owner}",
            )
        seen_slots[manifest.slot] = manifest.task_id
        seen_tasks[manifest.task_id] = manifest.slot
    return tuple(found)


def parse_manifest(path: Path, root: Path) -> ExtensionManifest:
    manifest_path = Path(path)
    base = Path(root).resolve()
    try:
        resolved = manifest_path.resolve()
        resolved.relative_to(base)
    except ValueError as exc:
        raise fault("path_escape", "manifest path escapes the extension root") from exc
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise fault("io_fault", "manifest could not be read", recovery_required=True) from exc
    try:
        raw = json.loads(text, object_pairs_hook=_pairs)
    except ValueError as exc:
        raise fault("invalid_input", "manifest is not valid json") from exc
    if not isinstance(raw, dict):
        raise fault("invalid_input", "manifest must be an object")
    extra = [key for key in raw if key not in _ALLOWED_KEYS]
    if extra:
        raise fault("forbidden_command", "manifest contains an unsupported field")
    missing = _ALLOWED_KEYS - set(raw)
    if missing:
        raise fault("invalid_input", "manifest is missing a required field")
    schema = _text_field(raw["schema_version"], "schema_version")
    if schema not in {SCHEMA_VERSION, _V2_SCHEMA}:
        raise fault("schema_mismatch", f"unsupported schema {schema}")
    task_id = _text_field(raw["task_id"], "task_id")
    slot = _text_field(raw["slot"], "slot")
    factory = _text_field(raw["factory"], "factory")
    scenario_factory = _text_field(raw["scenario_factory"], "scenario_factory")
    match = _TASK.fullmatch(task_id)
    if match is None:
        raise fault("invalid_input", "task_id must look like GROUND-01")
    directory = resolved.parent
    if directory.name != f"g{match.group(1)}":
        raise fault("path_escape", "task id does not match its directory")
    _accept_slot(schema, slot)
    _check_factory(factory, directory)
    _check_factory(scenario_factory, directory)
    return ExtensionManifest(
        schema_version=schema,
        task_id=task_id,
        slot=slot,
        factory=factory,
        scenario_factory=scenario_factory,
        path=resolved,
        directory=directory,
    )


def load_callable(manifest: ExtensionManifest, which: str) -> Callable[..., object]:
    spec = manifest.factory if which == "factory" else manifest.scenario_factory
    matched = _FACTORY.fullmatch(spec)
    if matched is None:
        raise fault("forbidden_command", "factory is not a module attribute path")
    filename = matched.group(2) + ".py"
    attribute = matched.group(3)
    module_path = (manifest.directory / filename).resolve()
    try:
        module_path.relative_to(manifest.directory.resolve())
    except ValueError as exc:
        raise fault("path_escape", "factory file escapes its extension directory") from exc
    if not module_path.is_file():
        raise fault("missing_provider", f"{filename} is missing")
    module_name = f"_ground_{manifest.task_id}_{matched.group(2)}"
    loaded = importlib.util.spec_from_file_location(module_name, module_path)
    if loaded is None or loaded.loader is None:
        raise fault("invalid_input", "factory module could not be loaded")
    module = importlib.util.module_from_spec(loaded)
    sys.modules[module_name] = module
    try:
        loaded.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    target = getattr(module, attribute, None)
    if not callable(target):
        raise fault("invalid_input", "factory attribute is not callable")
    return cast(Callable[..., object], target)


def _check_factory(value: str, directory: Path) -> None:
    if any(marker in value for marker in _COMMAND_MARKERS) or ".." in value:
        raise fault("forbidden_command", "factory contains an executable command")
    matched = _FACTORY.fullmatch(value)
    if matched is None:
        raise fault("forbidden_command", "factory must be an extension attribute path")
    if matched.group(1) != directory.name:
        raise fault("path_escape", "factory module escapes its extension directory")
    filename = directory / f"{matched.group(2)}.py"
    if not filename.is_file():
        raise fault("missing_provider", f"{filename.name} is missing")


def _text_field(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{label} must be a string")
    return value.strip()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate key")
        found[key] = value
    return found
