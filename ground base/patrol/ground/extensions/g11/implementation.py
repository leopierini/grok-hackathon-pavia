"""Validate v2 envelopes. This provider never calls a dog, drone, or model."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime
from typing import cast

from patrol.ground.extensions.g11.schema_check import (
    SchemaFault,
    fixture_root,
    load_schema,
    validate_message,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    EventRecord,
    FeaturePort,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map, freeze_str_map

SLOT = "feature.v2_envelope"
SCHEMA_VERSION = "ground-task-v2"
_EXPIRY_KINDS = frozenset({"dog.command", "drone.command", "motion.proposal", "vision.request"})
_CORRELATION = (
    "correlation_id",
    "frame_id",
    "track_id",
    "beacon_epoch",
    "map_epoch",
    "camera_epoch",
)
_FRAME_ALIASES = {"evidence_frame_id": "frame_id"}
_ROUTES: dict[str, frozenset[tuple[str, str]]] = {
    "capabilities.report": frozenset(
        {
            ("dog", "ground"),
            ("drone", "ground"),
            ("pi", "ground"),
            ("vision", "ground"),
        }
    ),
    "drone.observation": frozenset({("drone", "ground")}),
    "dog.observation": frozenset({("dog", "ground")}),
    "rssi.window": frozenset({("pi", "ground")}),
    "navigation.candidates": frozenset({("dog", "ground")}),
    "vision.request": frozenset({("ground", "vision")}),
    "vision.decision": frozenset({("vision", "ground")}),
    "motion.proposal": frozenset({("vision", "ground")}),
    "dog.command": frozenset({("ground", "dog")}),
    "drone.command": frozenset({("ground", "drone")}),
    "command.ack": frozenset({("dog", "ground"), ("drone", "ground")}),
    "proximity.evidence": frozenset({("ground", "ground")}),
    "mission.event": frozenset({("ground", "all")}),
    "heartbeat": frozenset({("pi", "ground"), ("dog", "ground"), ("drone", "ground")}),
}
_ERROR_FOR = {
    "unknown_field": "invalid_input",
    "missing_field": "invalid_input",
    "invalid_type": "invalid_input",
    "not_object": "invalid_input",
    "invalid_json": "invalid_input",
    "utf8_bom": "invalid_input",
    "trailing_json": "invalid_input",
    "missing_message": "invalid_input",
    "expected_direction": "invalid_input",
    "protocol_version": "schema_mismatch",
    "unknown_kind": "validation_failed",
    "payload_shape": "validation_failed",
    "direction": "rejected",
    "expiry_required": "validation_failed",
    "expired": "expired_deadline",
    "epoch_mismatch": "epoch_mismatch",
    "simulated_synthetic": "contract_mismatch",
    "command_conflict": "contract_mismatch",
    "message_immutable": "contract_mismatch",
    "stale_epoch": "stale_ticket",
    "mission_mismatch": "rejected",
    "sequence_replay": "rejected",
}
_SECRET_WORDS = ("token", "secret", "api_key", "authorization", "bearer", "password")
_SKIP_INDEX = frozenset(
    {
        "message.schema.json",
        "trailing-comma.json",
        "comment.json",
        "second-value.json",
        "truncated.json",
        "bom.json",
    }
)


class _ParseProblem(Exception):
    def __init__(self, diagnostic: str, reason: str) -> None:
        self.diagnostic = diagnostic
        self.reason = reason
        super().__init__(diagnostic)


class _Stored:
    def __init__(self, message: dict[str, object], result: FeatureResult) -> None:
        self.message = message
        self.payload = cast(dict[str, object], message["payload"])
        self.result = result


class EnvelopeGate:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self._schema = load_schema()
        self._messages: dict[str, _Stored] = {}
        self._commands: dict[str, _Stored] = {}
        self._sequences: dict[tuple[str, int, str], int] = {}
        self._hashes, self._examples = _synthetic_index()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if request.kind == "diagnostic" and "message" not in request.payload:
            return await self._scenario(request.name)
        return await self._validate(request)

    async def _scenario(self, name: str) -> FeatureResult:
        handlers: dict[str, Callable[[], Awaitable[FeatureResult]]] = {
            "accepted_examples": self._accepted_examples,
            "duplicate_command": self._duplicate_command,
            "wrong_source": self._wrong_source,
            "expired_and_null": self._expired_and_null,
            "late_epoch": self._late_epoch,
            "journal_projection": self._journal_projection,
        }
        handler = handlers.get(name)
        if handler is None:
            detail = f"unknown envelope case {name}"
            return self._probe(
                False,
                detail,
                ("unknown_case",),
                status="failed",
                error=GroundError("invalid_input", detail, False),
            )
        try:
            return await handler()
        except GroundFault as exc:
            return self._probe(
                False,
                exc.error.detail,
                ("failed", exc.error.code),
                status="failed",
                error=exc.error,
            )

    async def _accepted_examples(self) -> FeatureResult:
        self._arm()
        observation = await self._validate(self._guard(_load_fixture("drone-observation.json")))
        command = await self._validate(self._guard(_load_fixture("ground-to-dog-command.json")))
        pose_null = observation.data.get("pose") is None
        ok = (
            observation.status == "ok"
            and command.status == "ok"
            and observation.data.get("kind") == "drone.observation"
            and command.data.get("kind") == "dog.command"
            and pose_null
            and _call_count(self.services) == 0
        )
        trace = ("drone.observation", "dog.command", "pose_null", "adapters_idle")
        return self._checked(ok, "accepted", trace, authorized=True)

    async def _duplicate_command(self) -> FeatureResult:
        self._arm()
        request = self._guard(_load_fixture("ground-to-dog-command.json"))
        first = await self._validate(request)
        second = await self._validate(request)
        records = _records(self.services)
        accepted = [record for record in records if record.event == "decision_received"]
        ok = (
            first.status == "ok"
            and second is first
            and len(accepted) == 1
            and _call_count(self.services) == 0
        )
        return self._checked(ok, "one_stored", ("accepted", "replay", "stored:1"), authorized=True)

    async def _wrong_source(self) -> FeatureResult:
        self._arm()
        message = _load_fixture("ground-to-drone-command.json")
        message["source"] = "vision"
        result = await self._validate(self._guard(message))
        ok = (
            result.status == "blocked"
            and result.error is not None
            and result.error.detail == "direction"
            and _call_count(self.services) == 0
        )
        return self._checked(ok, "direction", ("direction", "adapters_idle"), authorized=False)

    async def _expired_and_null(self) -> FeatureResult:
        self._arm()
        expired = _load_fixture("ground-to-dog-command.json")
        expired["expires_at"] = "2025-12-31T00:00:00Z"
        missing = _load_fixture("drone-vision-request.json")
        missing["expires_at"] = None
        halt = _load_fixture("ground-to-dog-halt.json")
        halt["expires_at"] = "2025-12-31T00:00:00Z"
        expired_result = await self._validate(self._guard(expired))
        missing_result = await self._validate(self._guard(missing))
        halt_result = await self._validate(self._guard(halt))
        ok = (
            _detail(expired_result) == "expired"
            and _detail(missing_result) == "expiry_required"
            and halt_result.status == "ok"
            and halt_result.data.get("safety_command") is True
            and _call_count(self.services) == 0
        )
        return self._checked(
            ok,
            "rejected_before_invoke",
            ("expired", "expiry_required", "halt_schema_valid", "adapters_idle"),
            authorized=False,
        )

    async def _late_epoch(self) -> FeatureResult:
        self._arm()
        barriers = self.services.kernel.barriers
        barriers.arm("g11.parse")
        request = self._guard(_load_fixture("ground-to-dog-command.json"), barrier="g11.parse")
        task = asyncio.create_task(self._validate(request))
        await _spin(lambda: _barrier_holding(barriers, "g11.parse"))
        self.services.kernel.authority.reset_generation("reconnect")
        barriers.release("g11.parse")
        result = await task
        stored = "msg-ground-to-dog-command" in self._messages
        ok = _detail(result) == "stale_epoch" and not stored and _call_count(self.services) == 0
        return self._checked(
            ok,
            "stale",
            ("held", "epoch_changed", "stale_epoch", "not_stored"),
            authorized=False,
        )

    async def _journal_projection(self) -> FeatureResult:
        self._arm()
        result = await self._validate(self._guard(_load_fixture("drone-observation.json")))
        records = _records(self.services)
        record = records[-1] if records else None
        text = json.dumps(_jsonable(record.data) if record is not None else {}, default=str).lower()
        event_text = json.dumps(
            _jsonable(result.events[0].payload) if result.events else {},
            default=str,
        ).lower()
        fields = ("mission_id", "epoch", "kind", "message_id")
        present = record is not None and all(key in record.data for key in fields)
        clean = present and all(
            word not in text and word not in event_text for word in _SECRET_WORDS
        )
        ok = (
            result.status == "ok"
            and clean
            and record is not None
            and record.data.get("kind") == "drone.observation"
        )
        return self._checked(
            ok,
            "journal_projected",
            ("journal", "mission", "epoch", "kind", "message_id", "no_key_material"),
            authorized=True,
        )

    async def _validate(self, request: FeatureRequest) -> FeatureResult:
        message: dict[str, object] | None = None
        try:
            text = _decode(request.payload.get("message"))
            message = _parse_json(text)
            validate_message(message, self._schema)
        except _ParseProblem as exc:
            return self._reject(exc.diagnostic, exc.reason, message, request.ticket)
        except SchemaFault as exc:
            return self._reject(exc.code, exc.reason, message, request.ticket)
        source = message.get("source")
        destination = message.get("destination")
        kind = message.get("kind")
        payload = message.get("payload")
        if (
            not isinstance(source, str)
            or not isinstance(destination, str)
            or not isinstance(kind, str)
            or not isinstance(payload, dict)
        ):
            return self._reject("invalid_type", "envelope", message, request.ticket)
        expected_source = request.payload.get("expected_source")
        expected_destination = request.payload.get("expected_destination")
        if not isinstance(expected_source, str) or not isinstance(expected_destination, str):
            return self._reject("expected_direction", "expected", message, request.ticket)
        route = _ROUTES.get(kind)
        role = payload.get("role")
        if (
            expected_source != source
            or expected_destination != destination
            or route is None
            or (source, destination) not in route
            or (kind == "capabilities.report" and role != source)
        ):
            return self._reject("direction", "route", message, request.ticket)
        if _synthetic_claim(message, self._hashes, self._examples):
            return self._reject("simulated_synthetic", "simulated", message, request.ticket)
        message_id = message.get("message_id")
        if not isinstance(message_id, str):
            return self._reject("invalid_type", "message_id", message, request.ticket)
        current = self._current_epoch()
        requested_epoch = request.payload.get("epoch")
        if (
            isinstance(requested_epoch, bool)
            or not isinstance(requested_epoch, int)
            or requested_epoch != current
            or message.get("epoch") != current
        ):
            return self._reject("epoch_mismatch", "epoch", message, request.ticket)
        mission = self._open_mission()
        if mission is not None and message.get("mission_id") != mission:
            return self._reject("mission_mismatch", "mission_id", message, request.ticket)
        known = self._messages.get(message_id)
        if known is not None:
            if known.message == message:
                return known.result
            return self._reject("message_immutable", "message_id", message, request.ticket)
        # ACKs share the command_id with a different lifecycle payload.
        command_id = payload.get("command_id") if kind in {"dog.command", "drone.command"} else None
        if isinstance(command_id, str):
            previous = self._commands.get(command_id)
            if previous is not None and previous.payload == payload:
                self._messages[message_id] = _Stored(_clone(message), previous.result)
                return previous.result
        if kind in _EXPIRY_KINDS:
            expires_at = message.get("expires_at")
            if expires_at is None:
                return self._reject("expiry_required", "expires_at", message, request.ticket)
            still_valid = _safety(kind, payload) or not _expired(
                expires_at,
                self.services.kernel.clock.utc_now(),
            )
            if not still_valid:
                return self._reject("expired", "expires_at", message, request.ticket)
        current = self._current_epoch()
        request_epoch = request.payload.get("epoch")
        message_epoch = message.get("epoch")
        if isinstance(request_epoch, bool) or not isinstance(request_epoch, int):
            return self._reject("invalid_type", "epoch", message, request.ticket)
        if request_epoch != current or message_epoch != current:
            return self._reject("epoch_mismatch", "epoch", message, request.ticket)
        open_mission = self._open_mission()
        if open_mission is not None and message.get("mission_id") != open_mission:
            return self._reject("mission_mismatch", "mission_id", message, request.ticket)
        captured = current
        barrier = request.payload.get("barrier")
        if barrier is not None:
            if not isinstance(barrier, str) or not barrier:
                return self._reject("invalid_type", "barrier", message, request.ticket)
            await asyncio.sleep(0)
            await self.services.kernel.barriers.wait(barrier)
            if self._current_epoch() != captured:
                return self._reject("stale_epoch", "epoch", message, request.ticket)
            # Another parser may have committed while this one awaited a barrier.
            known = self._messages.get(message_id)
            if known is not None:
                if known.message == message:
                    return known.result
                return self._reject("message_immutable", "message_id", message, request.ticket)
        if isinstance(command_id, str):
            previous = self._commands.get(command_id)
            if previous is not None and previous.payload != payload:
                return self._reject("command_conflict", "command_id", message, request.ticket)
        sequence_key = (str(message["mission_id"]), current, str(message["source"]))
        sequence = message["seq"]
        if not isinstance(sequence, int) or isinstance(sequence, bool):
            return self._reject("invalid_type", "seq", message, request.ticket)
        if sequence <= self._sequences.get(sequence_key, -1) and not _safety(kind, payload):
            return self._reject("sequence_replay", "seq", message, request.ticket)
        result = self._accept(message, request.ticket, safety=_safety(kind, payload))
        self._sequences[sequence_key] = max(sequence, self._sequences.get(sequence_key, -1))
        stored = _Stored(_clone(message), result)
        self._messages[message_id] = stored
        if isinstance(command_id, str):
            self._commands[command_id] = stored
        return result

    def _accept(
        self,
        message: dict[str, object],
        ticket: Ticket | None,
        *,
        safety: bool,
    ) -> FeatureResult:
        data = _accepted_data(message, safety=safety)
        projected = freeze_map(_projection(message, "accepted"))
        event = GroundEvent("decision_received", ticket, projected)
        self._journal("decision_received", message, "accepted", ticket)
        return FeatureResult("ok", freeze_map(data), (event,), None)

    def _reject(
        self,
        diagnostic: str,
        reason: str,
        message: dict[str, object] | None,
        ticket: Ticket | None,
    ) -> FeatureResult:
        code = _ERROR_FOR.get(diagnostic, "invalid_input")
        projected = _projection(message, diagnostic)
        projected["reason"] = reason
        event = GroundEvent("composition_rejected", ticket, freeze_map(dict(projected)))
        self._journal("composition_rejected", message, diagnostic, ticket)
        data = dict(projected)
        data["stale"] = diagnostic == "stale_epoch"
        return FeatureResult(
            "blocked",
            freeze_map(data),
            (event,),
            GroundError(code, diagnostic, False),
        )

    def _open_mission(self) -> str | None:
        try:
            snapshot = self.services.state.snapshot()
        except GroundFault as exc:
            if exc.error.code != "not_admitted":
                raise
            return None
        return snapshot.mission_id

    def _current_epoch(self) -> int:
        authority_epoch = self.services.kernel.authority.epoch
        try:
            snapshot = self.services.state.snapshot()
        except GroundFault as exc:
            if exc.error.code != "not_admitted":
                raise
            return authority_epoch
        return authority_epoch if snapshot.epoch != authority_epoch else snapshot.epoch

    def _journal(
        self,
        event_name: str,
        message: dict[str, object] | None,
        diagnostic: str,
        ticket: Ticket | None,
    ) -> None:
        journal = self.services.journal
        records = getattr(journal, "records", None)
        sequence = len(records) + 1 if isinstance(records, list) else 1
        clock = self.services.kernel.clock
        mission = None if message is None else message.get("mission_id")
        record = EventRecord(
            sequence=sequence,
            timestamp_utc=clock.utc_now().isoformat(),
            elapsed_s=clock.monotonic(),
            mission_id=mission if isinstance(mission, str) else None,
            ticket=ticket,
            state=None,
            event=event_name,
            zone=None,
            target=None,
            modes=freeze_str_map({}),
            data=freeze_map(_projection(message, diagnostic)),
        )
        emit = getattr(journal, "emit", None)
        if callable(emit):
            emit(record)

    def _arm(self) -> None:
        if self.services.kernel.authority.epoch == 0:
            self.services.kernel.authority.reset_generation("admit-demo")

    def _guard(
        self,
        message: Mapping[str, object],
        *,
        barrier: str | None = None,
    ) -> FeatureRequest:
        payload: dict[str, object] = {
            "message": json.dumps(message, separators=(",", ":")),
            "expected_source": message["source"],
            "expected_destination": message["destination"],
            "epoch": message["epoch"],
        }
        if barrier is not None:
            payload["barrier"] = barrier
        return FeatureRequest("guard", "v2_envelope", None, freeze_map(payload))

    def _checked(
        self,
        ok: bool,
        detail: str,
        trace: tuple[str, ...],
        *,
        authorized: bool,
    ) -> FeatureResult:
        if ok:
            return self._probe(authorized, detail, trace)
        return self._probe(
            False,
            "case_check_failed",
            ("case_check_failed",),
            status="failed",
            error=GroundError("validation_failed", "case_check_failed", False),
        )

    def _probe(
        self,
        authorized: bool,
        detail: str,
        trace: tuple[str, ...],
        *,
        status: str = "ok",
        error: GroundError | None = None,
    ) -> FeatureResult:
        data = freeze_map(
            {
                "authorized": authorized,
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": _call_count(self.services),
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA_VERSION,
            }
        )
        return FeatureResult(status, data, (), error)


def create(services: BaseServices) -> FeaturePort:
    return EnvelopeGate(services)


def _accepted_data(message: dict[str, object], *, safety: bool) -> dict[str, object]:
    payload = message["payload"]
    data: dict[str, object] = {
        "diagnostic": "accepted",
        "kind": message["kind"],
        "message_id": message["message_id"],
        "mission_id": message["mission_id"],
        "epoch": message["epoch"],
        "source": message["source"],
        "destination": message["destination"],
        "simulated": message["simulated"],
        "expires_at": message.get("expires_at"),
        "safety_command": safety,
        "stale": False,
        "pose": _pose(payload),
    }
    if isinstance(payload, dict):
        command_id = payload.get("command_id")
        if isinstance(command_id, str):
            data["command_id"] = command_id
    for key, value in _correlation(message).items():
        data[key] = value
    return data


def _pose(payload: object) -> object:
    if not isinstance(payload, dict) or "pose" not in payload:
        return "absent"
    if payload["pose"] is None:
        return None
    return "present"


def _correlation(message: dict[str, object]) -> dict[str, object]:
    found: dict[str, list[object]] = {}
    _walk(message, found)
    selected: dict[str, object] = {}
    for key in _CORRELATION:
        values = found.get(key, [])
        present: list[object] = []
        for value in values:
            if value is not None and value not in present:
                present.append(value)
        if len(present) == 1:
            selected[key] = present[0]
        elif len(present) > 1:
            selected[key] = tuple(present)
        elif values:
            selected[key] = None
    return selected


def _walk(node: object, found: dict[str, list[object]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            name = _FRAME_ALIASES.get(key, key)
            if name in _CORRELATION:
                found.setdefault(name, []).append(value)
            _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def _projection(message: dict[str, object] | None, diagnostic: str) -> dict[str, object]:
    projected: dict[str, object] = {"diagnostic": diagnostic}
    if message is None:
        return projected
    for key in ("mission_id", "kind", "message_id"):
        value = message.get(key)
        if isinstance(value, str):
            projected[key] = value
    epoch = message.get("epoch")
    if isinstance(epoch, int) and not isinstance(epoch, bool):
        projected["epoch"] = epoch
    return projected


def _synthetic_claim(
    message: dict[str, object],
    hashes: frozenset[str],
    examples: frozenset[str],
) -> bool:
    simulated: list[bool] = []
    found: list[str] = []
    _collect_claims(message, simulated, found)
    if simulated and all(simulated):
        return False
    message_id = message.get("message_id")
    if isinstance(message_id, str) and message_id in examples and False in simulated:
        return True
    return False in simulated and any(item in hashes for item in found)


def _collect_claims(node: object, simulated: list[bool], hashes: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "simulated" and isinstance(value, bool):
                simulated.append(value)
            if key == "sha256" and isinstance(value, str):
                hashes.append(value)
            _collect_claims(value, simulated, hashes)
    elif isinstance(node, list):
        for item in node:
            _collect_claims(item, simulated, hashes)


def _safety(kind: str, payload: Mapping[str, object]) -> bool:
    action = payload.get("action")
    dog_halt = kind == "dog.command" and action == "halt"
    drone_land = kind == "drone.command" and action == "land"
    return dog_halt or drone_land


def _expired(value: object, now: datetime) -> bool:
    if not isinstance(value, str):
        return True
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        return True
    return parsed <= now


def _decode(raw: object) -> str:
    if isinstance(raw, bytes):
        if raw.startswith(b"\xef\xbb\xbf"):
            raise _ParseProblem("utf8_bom", "bom")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _ParseProblem("invalid_json", "utf-8") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise _ParseProblem("missing_message", "message")
    if text.startswith("\ufeff"):
        raise _ParseProblem("utf8_bom", "bom")
    if not text.strip():
        raise _ParseProblem("missing_message", "empty")
    return text


def _parse_json(text: str) -> dict[str, object]:
    try:
        value, end = json.JSONDecoder(object_pairs_hook=_pairs).raw_decode(text)
    except ValueError as exc:
        raise _ParseProblem("invalid_json", "json") from exc
    if text[end:].strip():
        raise _ParseProblem("trailing_json", "trailing")
    if not isinstance(value, dict):
        raise _ParseProblem("not_object", "root")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    found: dict[str, object] = {}
    for key, value in pairs:
        if key in found:
            raise ValueError("duplicate key")
        found[key] = value
    return found


def _clone(message: dict[str, object]) -> dict[str, object]:
    cloned = json.loads(json.dumps(message))
    if not isinstance(cloned, dict):
        raise _ParseProblem("invalid_json", "clone")
    return cast(dict[str, object], cloned)


def _synthetic_index() -> tuple[frozenset[str], frozenset[str]]:
    hashes: set[str] = set()
    examples: set[str] = set()
    for path in sorted(fixture_root().glob("*.json")):
        if path.name in _SKIP_INDEX:
            continue
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(loaded, dict) and loaded.get("simulated") is True:
            message_id = loaded.get("message_id")
            if isinstance(message_id, str):
                examples.add(message_id)
        found: list[str] = []
        _collect_claims(loaded, [], found)
        hashes.update(found)
    return frozenset(hashes), frozenset(examples)


def _load_fixture(name: str) -> dict[str, object]:
    loaded = json.loads((fixture_root() / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise fault("invalid_input", f"{name} is not an object")
    return cast(dict[str, object], loaded)


def _call_count(services: BaseServices) -> int:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0


def _records(services: BaseServices) -> list[EventRecord]:
    records = getattr(services.journal, "records", None)
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, EventRecord)]


def _detail(result: FeatureResult) -> str:
    if result.error is None:
        return ""
    return result.error.detail


def _jsonable(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _barrier_holding(barriers: object, name: str) -> bool:
    waiters = getattr(barriers, "_waiters", None)
    if not isinstance(waiters, dict):
        return False
    waiting = waiters.get(name)
    return isinstance(waiting, list) and bool(waiting)


async def _spin(ready: Callable[[], bool]) -> None:
    for _ in range(50):
        if ready():
            return
        await asyncio.sleep(0)
    raise fault("timeout", "envelope barrier was not observed")
