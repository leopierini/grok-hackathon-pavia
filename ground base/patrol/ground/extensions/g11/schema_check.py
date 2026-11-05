"""Strict subset of the v2 message schema. Unknown fields fail closed."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

_KINDS = frozenset(
    {
        "capabilities.report",
        "drone.observation",
        "dog.observation",
        "rssi.window",
        "navigation.candidates",
        "vision.request",
        "vision.decision",
        "motion.proposal",
        "dog.command",
        "drone.command",
        "command.ack",
        "proximity.evidence",
        "mission.event",
        "heartbeat",
    }
)


class SchemaFault(Exception):
    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


def fixture_root() -> Path:
    return Path(__file__).resolve().parents[4] / "fixtures" / "ground" / "g11"


def load_schema() -> dict[str, object]:
    text = (fixture_root() / "message.schema.json").read_text(encoding="utf-8")
    loaded = json.loads(text, object_pairs_hook=_pairs)
    if not isinstance(loaded, dict):
        raise SchemaFault("payload_shape", "schema root")
    return loaded


def validate_message(message: object, schema: dict[str, object]) -> None:
    validate(message, schema, schema, "")
    if not isinstance(message, dict):
        raise SchemaFault("not_object", "root")
    kind = message.get("kind")
    defs = schema.get("$defs")
    if not isinstance(kind, str) or not isinstance(defs, dict) or kind not in defs:
        raise SchemaFault("unknown_kind", "kind")
    branch = defs[kind]
    if not isinstance(branch, dict):
        raise SchemaFault("payload_shape", "definition")
    validate(message.get("payload"), branch, schema, "payload")


def validate(
    instance: object,
    schema: dict[str, object],
    root: dict[str, object],
    path: str,
) -> None:
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str):
            raise SchemaFault("payload_shape", "ref")
        validate(instance, _resolve(ref, root), root, path)
        rest = {key: value for key, value in schema.items() if key != "$ref"}
        if rest:
            validate(instance, rest, root, path)
        return
    if "anyOf" in schema:
        options = schema["anyOf"]
        if not isinstance(options, list) or not options:
            raise SchemaFault(_code(path), "anyOf")
        for option in options:
            if not isinstance(option, dict):
                continue
            try:
                validate(instance, option, root, path)
            except SchemaFault:
                continue
            else:
                return
        raise SchemaFault(_code(path), path or "anyOf")
    if "const" in schema and instance != schema["const"]:
        code = "protocol_version" if path == "protocol_version" else _code(path)
        raise SchemaFault(code, path or "const")
    if "enum" in schema:
        enum = schema["enum"]
        if not isinstance(enum, list) or instance not in enum:
            code = "unknown_kind" if path == "kind" else _code(path)
            raise SchemaFault(code, path or "enum")
    declared = schema.get("type")
    if isinstance(declared, str) and not _matches_type(instance, declared):
        raise SchemaFault(_code(path), path or declared)
    if declared == "object" and isinstance(instance, dict):
        _object(instance, schema, root, path)
    elif declared == "array" and isinstance(instance, list):
        _array(instance, schema, root, path)
    elif declared == "string" and isinstance(instance, str):
        _string(instance, schema, path)
    elif declared in {"integer", "number"} and _matches_type(instance, str(declared)):
        _number(instance, schema, path)


def _object(
    instance: dict[str, object],
    schema: dict[str, object],
    root: dict[str, object],
    path: str,
) -> None:
    props = schema.get("properties")
    if schema.get("additionalProperties") is False and isinstance(props, dict):
        extra = [key for key in instance if key not in props]
        if extra:
            code = "unknown_field" if path == "" else "payload_shape"
            raise SchemaFault(code, ",".join(sorted(extra)))
    required = schema.get("required")
    if isinstance(required, list):
        missing = [key for key in required if isinstance(key, str) and key not in instance]
        if missing:
            code = "missing_field" if path == "" else "payload_shape"
            raise SchemaFault(code, ",".join(str(item) for item in missing))
    maximum = schema.get("maxProperties")
    if isinstance(maximum, int) and not isinstance(maximum, bool) and len(instance) > maximum:
        raise SchemaFault(_code(path), "maxProperties")
    if not isinstance(props, dict):
        return
    for key, value in instance.items():
        child = props.get(key)
        if isinstance(child, dict):
            child_path = key if path == "" else f"{path}.{key}"
            validate(value, child, root, child_path)


def _array(
    instance: list[object],
    schema: dict[str, object],
    root: dict[str, object],
    path: str,
) -> None:
    minimum = schema.get("minItems")
    maximum = schema.get("maxItems")
    if isinstance(minimum, int) and not isinstance(minimum, bool) and len(instance) < minimum:
        raise SchemaFault(_code(path), "minItems")
    if isinstance(maximum, int) and not isinstance(maximum, bool) and len(instance) > maximum:
        raise SchemaFault(_code(path), "maxItems")
    items = schema.get("items")
    if not isinstance(items, dict):
        return
    for index, value in enumerate(instance):
        validate(value, items, root, f"{path}[{index}]")


def _string(instance: str, schema: dict[str, object], path: str) -> None:
    minimum = schema.get("minLength")
    maximum = schema.get("maxLength")
    if isinstance(minimum, int) and not isinstance(minimum, bool) and len(instance) < minimum:
        raise SchemaFault(_code(path), "minLength")
    if isinstance(maximum, int) and not isinstance(maximum, bool) and len(instance) > maximum:
        raise SchemaFault(_code(path), "maxLength")
    pattern = schema.get("pattern")
    if isinstance(pattern, str) and re.fullmatch(pattern, instance) is None:
        raise SchemaFault(_code(path), "pattern")
    if schema.get("format") == "date-time" and not _date_time(instance):
        raise SchemaFault(_code(path), "date-time")


def _number(instance: object, schema: dict[str, object], path: str) -> None:
    if isinstance(instance, bool) or not isinstance(instance, (int, float)):
        raise SchemaFault(_code(path), "number")
    if not math.isfinite(float(instance)):
        raise SchemaFault(_code(path), "number")
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    exclusive = schema.get("exclusiveMinimum")
    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
        if float(instance) < float(minimum):
            raise SchemaFault(_code(path), "minimum")
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
        if float(instance) > float(maximum):
            raise SchemaFault(_code(path), "maximum")
    if isinstance(exclusive, (int, float)) and not isinstance(exclusive, bool):
        if float(instance) <= float(exclusive):
            raise SchemaFault(_code(path), "exclusiveMinimum")


def _matches_type(instance: object, declared: str) -> bool:
    if declared == "object":
        return isinstance(instance, dict)
    if declared == "array":
        return isinstance(instance, list)
    if declared == "string":
        return isinstance(instance, str)
    if declared == "boolean":
        return isinstance(instance, bool)
    if declared == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if declared == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if declared == "null":
        return instance is None
    return False


def _date_time(value: str) -> bool:
    if "T" not in value:
        return False
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _resolve(ref: str, root: dict[str, object]) -> dict[str, object]:
    if not ref.startswith("#/"):
        raise SchemaFault("payload_shape", "ref")
    node: object = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SchemaFault("payload_shape", "ref")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaFault("payload_shape", "ref")
    return node


def _code(path: str) -> str:
    if path == "payload" or path.startswith("payload.") or path.startswith("payload["):
        return "payload_shape"
    return "invalid_type"


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate key")
        found[key] = value
    return found
