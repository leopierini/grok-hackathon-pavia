"""Journal accepted v2 messages. Enqueue is not durability.

The proposed field list is still waiting on the team. Records carry
``log_schema`` ``proposed-1`` so a later field is a revision, not a new
meaning stuffed into an existing string.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from patrol.ground.extensions.g29.classify import (
    CATEGORIES,
    JOURNAL_EVENT,
    LOG_SCHEMA,
    LOGS_STATUS,
    SLOT,
    TASK_SCHEMA,
    category_for,
    correlation,
    missing_correlation,
    normalize_name,
    sanitize,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    EventRecord,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map, freeze_str_map

_SIM_CASES = frozenset(
    {
        "each_kind",
        "missing_command_id",
        "goal_and_landing",
        "secret_redacted",
        "flush_failed",
        "replay_once",
        "image_hash",
        "null_rssi",
    }
)
_REQUIRED = (
    "protocol_version",
    "message_id",
    "mission_id",
    "epoch",
    "seq",
    "sent_at",
    "source",
    "destination",
    "kind",
    "correlation_id",
    "expires_at",
    "simulated",
    "payload",
)
_SOURCES = frozenset({"ground", "drone", "dog", "pi", "vision", "operator"})
_DESTINATIONS = frozenset({"ground", "drone", "dog", "pi", "vision", "all"})
_KINDS = frozenset(
    {
        "capabilities.report",
        "heartbeat",
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
    }
)
_IDENTITY = (
    "message_id",
    "mission_id",
    "epoch",
    "source",
    "destination",
    "kind",
    "sent_at",
)


def create(services: BaseServices) -> LogFeature:
    """Build the v2 journal. Construction does not emit or flush."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "log create expects base services")
    return LogFeature(services)


class LogFeature:
    """One journal for accepted envelopes. Duplicate message ids are ignored."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.records: list[dict[str, object]] = []
        self.faults: list[dict[str, object]] = []
        self.cleanup_paths: tuple[str, ...] = ()
        self._by_id: dict[str, dict[str, object]] = {}
        self._sequence = 0
        self._opened = False

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failure("invalid_input", "expected a FeatureRequest")
        try:
            if request.name == "open":
                if self._opened:
                    return _failure("rejected", "journal is already bound")
                run_id = request.payload.get("run_id")
                output_root = request.payload.get("output_root")
                if not isinstance(run_id, str) or not isinstance(output_root, str):
                    return _failure("invalid_input", "run id and output root are required")
                await self.services.journal.open(run_id, output_root)
                self._opened = True
                return FeatureResult("ok", freeze_map({"writer_state": "open"}), (), None)
            if request.name in _SIM_CASES:
                return await self._simulate(request.name)
            if request.name == "accept":
                return await self._accept(request)
            if request.name == "flush":
                return await self._flush(request.ticket)
            if request.name == "publish":
                return await self._publish(request.ticket)
            if request.name == "catalog":
                return await self._catalog(request)
        except GroundFault as exc:
            return _failure(exc.error.code, exc.error.detail, recovery=exc.error.recovery_required)
        return _failure("invalid_input", f"unknown log request {request.name}")

    async def _accept(self, request: FeatureRequest) -> FeatureResult:
        envelope = parse_envelope(request.payload.get("envelope"))
        denylist = parse_denylist(request.payload.get("secret_fields", ()))
        return await self._store(envelope, denylist, request.ticket)

    async def _catalog(self, request: FeatureRequest) -> FeatureResult:
        raw_lines = request.payload.get("lines")
        if isinstance(raw_lines, str) or not isinstance(raw_lines, (list, tuple)):
            return _failure("invalid_input", "catalog lines must be a list of envelopes")
        denylist = parse_denylist(request.payload.get("secret_fields", ()))
        accepted = 0
        duplicates = 0
        rejected = 0
        first_code = "rejected"
        first_detail = ""
        events: list[GroundEvent] = []
        message_ids: list[str] = []
        for line in raw_lines:
            try:
                envelope = parse_envelope(line)
            except GroundFault as exc:
                rejected += 1
                if not first_detail:
                    first_code = exc.error.code
                    first_detail = exc.error.detail
                continue
            result = await self._store(envelope, denylist, request.ticket)
            message_id = result.data.get("message_id")
            if isinstance(message_id, str):
                message_ids.append(message_id)
            if result.status != "ok":
                rejected += 1
                if not first_detail and result.error is not None:
                    first_code = result.error.code
                    first_detail = result.error.detail
                continue
            if result.data.get("duplicate") is True:
                duplicates += 1
            else:
                accepted += 1
            events.extend(result.events)
        extra: dict[str, object] = {
            "accepted": accepted,
            "duplicates": duplicates,
            "rejected": rejected,
            "message_ids": tuple(message_ids),
        }
        if rejected:
            return _result(
                status="failed",
                published=False,
                writer_state=self._writer_state(),
                duplicate=False,
                category="persistence",
                event_name="catalog",
                message_id="",
                record=None,
                events=tuple(events),
                error=GroundError(first_code, first_detail or "catalog line rejected", False),
                extra=extra,
            )
        return _result(
            status="ok",
            published=False,
            writer_state=self._writer_state(),
            duplicate=False,
            category="persistence",
            event_name="catalog",
            message_id="",
            record=None,
            events=tuple(events),
            error=None,
            extra=extra,
        )

    async def _store(
        self,
        envelope: dict[str, object],
        denylist: set[str],
        ticket: Ticket | None,
    ) -> FeatureResult:
        message_id = _text(envelope.get("message_id"))
        kind = _text(envelope.get("kind"))
        payload = envelope.get("payload")
        if not isinstance(message_id, str) or not isinstance(kind, str):
            return _failure("invalid_input", "envelope identity is incomplete")
        if not isinstance(payload, dict):
            return _failure("invalid_input", "envelope identity is incomplete")
        body = cast(dict[str, object], payload)
        existing = self._by_id.get(message_id)
        if existing is not None:
            return _from_record(existing, duplicate=True, events=())
        if kind == "mission.event":
            event_name = body.get("event")
            if not isinstance(event_name, str) or not event_name.strip():
                return _failure("invalid_input", "mission event is missing event name")
        detail = missing_correlation(kind, body)
        if detail is not None:
            return _failure("rejected", detail)
        category, event_name = category_for(kind, body)
        if category not in CATEGORIES:
            return _failure("invalid_input", "message kind has no journal category")
        summary, redacted, reasons, artifacts, omitted = sanitize(body, denylist)
        copied = correlation(body)
        self._sequence += 1
        record: dict[str, object] = {
            "log_schema": LOG_SCHEMA,
            "logs_requirements_status": LOGS_STATUS,
            "protocol_version": "2.0-draft",
            "category": category,
            "event_name": event_name,
            "writer_state": "queued",
            "published": False,
            "sequence": self._sequence,
            "monotonic_s": float(self.services.kernel.clock.monotonic()),
            "clock_domain": "ground",
            "message_id": message_id,
            "mission_id": envelope.get("mission_id"),
            "epoch": envelope.get("epoch"),
            "seq": envelope.get("seq"),
            "source": envelope.get("source"),
            "destination": envelope.get("destination"),
            "kind": kind,
            "sent_at": envelope.get("sent_at"),
            "simulated": envelope.get("simulated"),
            "summary": summary,
            "redacted_fields": redacted,
            "measurement_reasons": reasons,
            "omitted_fields": omitted,
        }
        record.update(copied)
        if "artifact_ref" in artifacts:
            record["artifact_ref"] = artifacts["artifact_ref"]
        if "artifact_sha256" in artifacts:
            record["artifact_sha256"] = artifacts["artifact_sha256"]
        target = copied.get("track_id")
        stored = EventRecord(
            sequence=self._sequence,
            timestamp_utc=self.services.kernel.clock.utc_now().isoformat(),
            elapsed_s=float(self.services.kernel.clock.monotonic()),
            mission_id=_text(envelope.get("mission_id")),
            ticket=ticket,
            state=category,
            event=JOURNAL_EVENT[category],
            zone=None,
            target=target if isinstance(target, str) else None,
            modes=freeze_str_map({}),
            data=record,
        )
        try:
            await self._ensure_open(message_id)
            self.services.journal.emit(stored)
        except GroundFault:
            self._sequence -= 1
            raise
        self.records.append(record)
        self._by_id[message_id] = record
        event = GroundEvent(
            kind=JOURNAL_EVENT[category],
            ticket=ticket,
            payload=freeze_map(
                {
                    "message_id": message_id,
                    "category": category,
                    "event_name": event_name,
                    "log_schema": LOG_SCHEMA,
                    "writer_state": "queued",
                    "published": False,
                }
            ),
        )
        return _from_record(record, duplicate=False, events=(event,))

    async def _flush(self, ticket: Ticket | None) -> FeatureResult:
        await self._ensure_open("journal")
        try:
            await self.services.journal.flush()
        except Exception as exc:  # noqa: BLE001 - writer failures must not look saved
            detail = _failure_text(exc)
            return self._mark_failed(ticket, detail)
        if not self.records:
            return _result(
                status="ok",
                published=False,
                writer_state="queued",
                duplicate=False,
                category="persistence",
                event_name="flush",
                message_id="",
                record=None,
                events=(),
                error=None,
            )
        for record in self.records:
            if record.get("published") is True:
                continue
            record["writer_state"] = "flushed"
            record["published"] = False
        return _result(
            status="ok",
            published=False,
            writer_state="flushed",
            duplicate=False,
            category="persistence",
            event_name="flush",
            message_id="",
            record=None,
            events=(),
            error=None,
        )

    def _mark_failed(self, ticket: Ticket | None, detail: str) -> FeatureResult:
        for record in self.records:
            if record.get("published") is True:
                continue
            record["writer_state"] = "failed"
            record["published"] = False
        fault_record: dict[str, object] = {
            "log_schema": LOG_SCHEMA,
            "logs_requirements_status": LOGS_STATUS,
            "category": "persistence",
            "event_name": "flush_failed",
            "writer_state": "failed",
            "published": False,
            "reason": detail,
            "simulated": True,
        }
        self._sequence += 1
        stored = EventRecord(
            sequence=self._sequence,
            timestamp_utc=self.services.kernel.clock.utc_now().isoformat(),
            elapsed_s=float(self.services.kernel.clock.monotonic()),
            mission_id=None,
            ticket=ticket,
            state="persistence",
            event="persistence_fault",
            zone=None,
            target=None,
            modes=freeze_str_map({}),
            data=fault_record,
        )
        try:
            self.services.journal.emit(stored)
        except GroundFault:
            self._sequence -= 1
        else:
            self.faults.append(fault_record)
        event = GroundEvent(
            kind="persistence_fault",
            ticket=ticket,
            payload=freeze_map(
                {
                    "writer_state": "failed",
                    "published": False,
                    "reason": "flush_failed",
                    "log_schema": LOG_SCHEMA,
                }
            ),
        )
        return _result(
            status="failed",
            published=False,
            writer_state="failed",
            duplicate=False,
            category="persistence",
            event_name="flush_failed",
            message_id="",
            record=fault_record,
            events=(event,),
            error=GroundError("io_fault", detail, True),
        )

    async def _publish(self, ticket: Ticket | None) -> FeatureResult:
        del ticket
        if not self.records:
            return _failure("rejected", "publish requires a journaled record")
        if any(record.get("writer_state") != "flushed" for record in self.records):
            return _failure("rejected", "publish requires a successful flush")
        counts: dict[str, int] = {}
        for record in self.records:
            category = record.get("category")
            if isinstance(category, str):
                counts[category] = counts.get(category, 0) + 1
        summary: dict[str, object] = {
            "log_schema": LOG_SCHEMA,
            "logs_requirements_status": LOGS_STATUS,
            "published": True,
            "record_count": len(self.records),
            "categories": counts,
        }
        await self.services.journal.publish(summary)
        for record in self.records:
            record["published"] = True
            record["writer_state"] = "flushed"
        return _result(
            status="ok",
            published=True,
            writer_state="flushed",
            duplicate=False,
            category="persistence",
            event_name="publish",
            message_id="",
            record=None,
            events=(),
            error=None,
            extra={"record_count": len(self.records)},
        )

    def _writer_state(self) -> str:
        if not self.records:
            return "queued"
        states = {str(record.get("writer_state")) for record in self.records}
        if states == {"flushed"}:
            return "flushed"
        if "failed" in states:
            return "failed"
        return "queued"

    async def _ensure_open(self, run_id: str) -> None:
        if self._opened:
            return
        await self.services.journal.open(run_id, ".")
        self._opened = True

    async def _simulate(self, name: str) -> FeatureResult:
        try:
            if name == "each_kind":
                return await self._sim_each_kind()
            if name == "missing_command_id":
                return await self._sim_missing_command()
            if name == "goal_and_landing":
                return await self._sim_goal_and_landing()
            if name == "secret_redacted":
                return await self._sim_secret()
            if name == "flush_failed":
                return await self._sim_flush_failed()
            if name == "replay_once":
                return await self._sim_replay()
            if name == "image_hash":
                return await self._sim_image()
            if name == "null_rssi":
                return await self._sim_null_rssi()
        except GroundFault as exc:
            return self._check_failed(exc.error.detail)
        return self._check_failed(f"unknown simulation {name}")

    async def _sim_each_kind(self) -> FeatureResult:
        messages = _load_examples()
        if len(messages) != 32:
            return self._check_failed("expected 32 examples")
        for message in messages:
            result = await self._store(message, set(), None)
            if result.status != "ok":
                return self._check_failed("example was rejected")
            record = _record(result)
            if record is None:
                return self._check_failed("record missing")
            for field in _IDENTITY:
                if record.get(field) != message.get(field):
                    return self._check_failed(f"{field} was not copied")
            if record.get("category") not in CATEGORIES:
                return self._check_failed("category missing")
            if record.get("published") is not False or record.get("writer_state") != "queued":
                return self._check_failed("enqueue claimed durability")
        dog = self._by_id.get("msg-ground-to-dog-command")
        vision = self._by_id.get("msg-drone-vision-decision")
        if not isinstance(dog, dict) or dog.get("command_id") != "cmd-dog-001":
            return self._check_failed("command_id was not copied")
        if dog.get("category") != "command":
            return self._check_failed("dog command category")
        if not isinstance(vision, dict) or vision.get("frame_id") != "drone-downward-001":
            return self._check_failed("frame_id was not copied")
        if len(self.records) != 32:
            return self._check_failed("record count")
        return self._finish(
            authorized=True,
            detail="kinds_journaled",
            trace=("ids_copied", "categories_assigned"),
        )

    async def _sim_missing_command(self) -> FeatureResult:
        message = _envelope(
            "dog.command",
            {"action": "halt", "reason": "synthetic missing id"},
            message_id="msg-missing-command",
            source="ground",
            destination="dog",
        )
        result = await self._store(message, set(), None)
        if result.status == "ok" or result.error is None or result.error.code != "rejected":
            return self._check_failed("command without command_id was stored")
        if self.records:
            return self._check_failed("rejected command was journaled")
        if result.error.detail != "command record is missing command_id":
            return self._check_failed(result.error.detail)
        return self._finish(
            authorized=False,
            detail=result.error.detail,
            trace=("rejected", "command_id"),
            status="failed",
            error=result.error,
        )

    async def _sim_goal_and_landing(self) -> FeatureResult:
        goal = _load_named("event-demo_goal_reached.json")
        landing = _load_named("event-landing_unverified.json")
        goal_result = await self._store(goal, set(), None)
        landing_result = await self._store(landing, set(), None)
        goal_record = _record(goal_result)
        landing_record = _record(landing_result)
        if goal_record is None or landing_record is None:
            return self._check_failed("goal or landing was rejected")
        if goal_record.get("event_name") != "demo_goal_reached":
            return self._check_failed("goal event name changed")
        if landing_record.get("event_name") != "landing_unverified":
            return self._check_failed("landing event name changed")
        if goal_record.get("event_name") == landing_record.get("event_name"):
            return self._check_failed("goal and landing collapsed")
        goal_category = goal_record.get("category")
        landing_category = landing_record.get("category")
        if goal_category != "completion" or landing_category != "safety":
            return self._check_failed("goal and landing categories collapsed")
        return self._finish(
            authorized=True,
            detail="distinct_events",
            trace=("demo_goal_reached", "landing_unverified"),
        )

    async def _sim_secret(self) -> FeatureResult:
        message = _envelope(
            "dog.command",
            {
                "command_id": "cmd-secret-001",
                "api_key": "sk-test-value-not-for-journal",
                "authorization": "Bearer should-not-leak",
                "reason": "synthetic",
            },
            message_id="msg-secret",
            source="ground",
            destination="dog",
        )
        result = await self._store(
            message,
            {normalize_name(item) for item in ("api_key", "token", "authorization")},
            None,
        )
        record = _record(result)
        if record is None:
            return self._check_failed("secret fixture was rejected")
        line = json.dumps(record, sort_keys=True)
        if "sk-test-value-not-for-journal" in line or "Bearer should-not-leak" in line:
            return self._check_failed("secret value remained in the journal line")
        summary = record.get("summary")
        if not isinstance(summary, dict) or "api_key" in summary or "authorization" in summary:
            return self._check_failed("secret field remained in the summary")
        redacted = record.get("redacted_fields")
        if not isinstance(redacted, list) or "api_key" not in redacted:
            return self._check_failed("api_key rejection was not recorded")
        return self._finish(
            authorized=True,
            detail="api_key_absent",
            trace=("redacted:api_key", "value_absent"),
        )

    async def _sim_flush_failed(self) -> FeatureResult:
        message = _envelope(
            "capabilities.report",
            {"device_id": "dog-01", "role": "dog"},
            message_id="msg-flush",
            source="dog",
            destination="ground",
        )

        async def _boom() -> None:
            raise fault("io_fault", "journal flush failed", recovery_required=True)

        stored = await self._store(message, set(), None)
        if stored.status != "ok":
            return self._check_failed("flush fixture was rejected")
        journal = self.services.journal
        object.__setattr__(journal, "flush", _boom)
        result = await self._flush(None)
        published = getattr(journal, "published", None)
        record = self.records[0] if self.records else None
        event_kind = result.events[0].kind if result.events else ""
        if (
            result.status != "failed"
            or result.error is None
            or result.error.code != "io_fault"
            or event_kind != "persistence_fault"
            or published is not None
            or not isinstance(record, dict)
            or record.get("published") is not False
            or record.get("writer_state") != "failed"
        ):
            return self._check_failed("flush failure claimed the log was saved")
        return self._finish(
            authorized=False,
            detail="not_published",
            trace=("persistence_fault", "published_false"),
        )

    async def _sim_replay(self) -> FeatureResult:
        message = _envelope(
            "heartbeat",
            {"device_id": "pi-01", "healthy": True},
            message_id="msg-replay",
            source="pi",
            destination="ground",
        )
        first = await self._store(message, set(), None)
        second = await self._store(message, set(), None)
        journal_records = getattr(self.services.journal, "records", None)
        if (
            first.status != "ok"
            or second.data.get("duplicate") is not True
            or len(self.records) != 1
            or not isinstance(journal_records, list)
            or len(journal_records) != 1
        ):
            return self._check_failed("replay appended a second record")
        return self._finish(
            authorized=True,
            detail="one_record",
            trace=("replayed", "one_record"),
        )

    async def _sim_image(self) -> FeatureResult:
        digest = "a" * 64
        message = _envelope(
            "vision.request",
            {
                "request_id": "vision-img-001",
                "frame": {
                    "frame_id": "frame-img-001",
                    "image_ref": "artifact://demo/frame-img-001.jpg",
                    "sha256": digest,
                    "image_bytes": "RAW-IMAGE-BYTES-NOT-FOR-JOURNAL",
                },
            },
            message_id="msg-image",
            source="ground",
            destination="vision",
        )
        result = await self._store(message, set(), None)
        record = _record(result)
        if record is None:
            return self._check_failed("image fixture was rejected")
        line = json.dumps(record, sort_keys=True)
        omitted = record.get("omitted_fields")
        if (
            "RAW-IMAGE-BYTES-NOT-FOR-JOURNAL" in line
            or record.get("artifact_sha256") != digest
            or record.get("artifact_ref") != "artifact://demo/frame-img-001.jpg"
            or not isinstance(omitted, list)
            or "frame.image_bytes" not in omitted
        ):
            return self._check_failed("image bytes were journaled or the hash was dropped")
        return self._finish(
            authorized=True,
            detail="bytes_absent",
            trace=("hash_present", "bytes_absent"),
        )

    async def _sim_null_rssi(self) -> FeatureResult:
        message = _envelope(
            "rssi.window",
            {"median_rssi_dbm": None, "spread_db": 4, "beacon_epoch": 3},
            message_id="msg-null-rssi",
            source="pi",
            destination="ground",
        )
        result = await self._store(message, set(), None)
        record = _record(result)
        if record is None:
            return self._check_failed("rssi fixture was rejected")
        summary = record.get("summary")
        reasons = record.get("measurement_reasons")
        if not isinstance(summary, dict) or not isinstance(reasons, dict):
            return self._check_failed("rssi summary missing")
        median = summary.get("median_rssi_dbm")
        if median is not None or median == 0 or reasons.get("median_rssi_dbm") != "unknown":
            return self._check_failed("null rssi median was rewritten")
        if summary.get("spread_db") != 4:
            return self._check_failed("known rssi spread was dropped")
        return self._finish(
            authorized=True,
            detail="median_null",
            trace=("null_not_zero",),
        )

    def _finish(
        self,
        *,
        authorized: bool,
        detail: str,
        trace: tuple[str, ...],
        status: str = "ok",
        error: GroundError | None = None,
    ) -> FeatureResult:
        if self._live() != 0:
            status = "failed"
            error = GroundError("unsafe_state", "simulation made a live device call", True)
        data = freeze_map(
            {
                "authorized": authorized,
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": 0,
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": TASK_SCHEMA,
            }
        )
        return FeatureResult(status, data, (), error)

    def _check_failed(self, reason: str) -> FeatureResult:
        return self._finish(
            authorized=False,
            detail=reason,
            trace=("check_failed", reason),
            status="failed",
            error=GroundError("validation_failed", reason, False),
        )

    def _live(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        value = getattr(devices, "live_call_count", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value


def parse_envelope(value: object) -> dict[str, object]:
    """Accept one already-framed 2.0-draft message. This is not a motor command."""
    mapping = _as_dict(value)
    if mapping is None:
        raise fault("invalid_input", "envelope must be an object")
    missing = [key for key in _REQUIRED if key not in mapping]
    if missing:
        raise fault("invalid_input", "envelope is missing " + ", ".join(missing))
    if mapping.get("protocol_version") != "2.0-draft":
        raise fault("invalid_input", "protocol_version must be 2.0-draft")
    message_id = _required_text(mapping, "message_id")
    mission_id = _required_text(mapping, "mission_id")
    sent_at = _required_text(mapping, "sent_at")
    source = _required_text(mapping, "source")
    destination = _required_text(mapping, "destination")
    kind = _required_text(mapping, "kind")
    if source not in _SOURCES:
        raise fault("invalid_input", "envelope source is not recognized")
    if destination not in _DESTINATIONS:
        raise fault("invalid_input", "envelope destination is not recognized")
    if kind not in _KINDS:
        raise fault("invalid_input", "envelope kind is not recognized")
    epoch = _required_int(mapping, "epoch")
    seq = _required_int(mapping, "seq")
    simulated = mapping.get("simulated")
    if not isinstance(simulated, bool):
        raise fault("invalid_input", "simulated must be a boolean")
    _optional_text(mapping, "correlation_id")
    _optional_text(mapping, "expires_at")
    payload = _as_dict(mapping.get("payload"))
    if payload is None:
        raise fault("invalid_input", "payload must be an object")
    return {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": mission_id,
        "epoch": epoch,
        "seq": seq,
        "sent_at": sent_at,
        "source": source,
        "destination": destination,
        "kind": kind,
        "correlation_id": mapping.get("correlation_id"),
        "expires_at": mapping.get("expires_at"),
        "simulated": simulated,
        "payload": payload,
    }


def parse_denylist(value: object) -> set[str]:
    """Field names only. Callers supply the names; this list is not a secret value."""
    if value is None:
        return set()
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise fault("invalid_input", "secret_fields must be a list of names")
    names: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise fault("invalid_input", "secret_fields must be a list of names")
        names.add(normalize_name(item))
    return names


def _envelope(
    kind: str,
    payload: dict[str, object],
    *,
    message_id: str,
    source: str,
    destination: str,
) -> dict[str, object]:
    return {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": "demo-20261104-001",
        "epoch": 1,
        "seq": 1,
        "sent_at": "2026-11-04T13:00:00.000Z",
        "source": source,
        "destination": destination,
        "kind": kind,
        "correlation_id": None,
        "expires_at": None,
        "simulated": True,
        "payload": payload,
    }


def _load_examples() -> tuple[dict[str, object], ...]:
    root = repo_root() / "fixtures" / "ground" / "g29"
    index = _read_json(root / "examples-index.json")
    files = index.get("files")
    if not isinstance(files, list):
        raise fault("invalid_input", "examples index is missing files")
    loaded: list[dict[str, object]] = []
    root_resolved = root.resolve()
    for item in files:
        if not isinstance(item, str) or not item:
            raise fault("invalid_input", "examples index entry is not a path")
        path = (root / item).resolve()
        if not path.is_relative_to(root_resolved):
            raise fault("path_escape", "example path escapes the fixture directory")
        loaded.append(_read_json(path))
    return tuple(loaded)


def _load_named(name: str) -> dict[str, object]:
    if "/" in name or "\\" in name or name.startswith("."):
        raise fault("path_escape", "example name escapes the fixture directory")
    return _read_json(repo_root() / "fixtures" / "ground" / "g29" / "examples" / name)


def _read_json(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise fault("io_fault", "fixture could not be read", recovery_required=True) from exc
    if not isinstance(loaded, dict):
        raise fault("invalid_input", "fixture must be an object")
    return cast(dict[str, object], loaded)


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    if not isinstance(value, Mapping) or isinstance(value, (str, bytes)):
        return None
    copied: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        copied[key] = item
    return copied


def _required_text(mapping: Mapping[str, object], key: str) -> str:
    value = _text(mapping.get(key))
    if value is None:
        raise fault("invalid_input", f"{key} must be a string")
    return value


def _required_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{key} must be a non-negative integer")
    return value


def _optional_text(mapping: Mapping[str, object], key: str) -> None:
    value = mapping.get(key)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise fault("invalid_input", f"{key} must be a string or null")


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _failure_text(exc: Exception) -> str:
    if isinstance(exc, GroundFault) and exc.error.detail.strip():
        return exc.error.detail
    text = str(exc).strip()
    return text or "journal flush failed"


def _record(result: FeatureResult) -> dict[str, object] | None:
    value = result.data.get("record")
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _from_record(
    record: dict[str, object],
    *,
    duplicate: bool,
    events: tuple[GroundEvent, ...],
) -> FeatureResult:
    category = record.get("category")
    event_name = record.get("event_name")
    writer_state = record.get("writer_state")
    published = record.get("published")
    message_id = record.get("message_id")
    return _result(
        status="ok",
        published=published is True,
        writer_state=writer_state if isinstance(writer_state, str) else "queued",
        duplicate=duplicate,
        category=category if isinstance(category, str) else "",
        event_name=event_name if isinstance(event_name, str) else "",
        message_id=message_id if isinstance(message_id, str) else "",
        record=record,
        events=events,
        error=None,
    )


def _failure(code: str, detail: str, *, recovery: bool = False) -> FeatureResult:
    writer_state = "rejected" if code == "rejected" else "failed"
    return _result(
        status="failed",
        published=False,
        writer_state=writer_state,
        duplicate=False,
        category="",
        event_name="",
        message_id="",
        record=None,
        events=(),
        error=GroundError(code, detail, recovery),
    )


def _result(
    *,
    status: str,
    published: bool,
    writer_state: str,
    duplicate: bool,
    category: str,
    event_name: str,
    message_id: str,
    record: dict[str, object] | None,
    events: tuple[GroundEvent, ...],
    error: GroundError | None,
    extra: Mapping[str, object] | None = None,
) -> FeatureResult:
    payload: dict[str, object] = {
        "published": published,
        "writer_state": writer_state,
        "duplicate": duplicate,
        "category": category,
        "event_name": event_name,
        "log_schema": LOG_SCHEMA,
        "logs_requirements_status": LOGS_STATUS,
        "message_id": message_id,
    }
    if record is not None:
        payload["record"] = record
        redacted = record.get("redacted_fields")
        if isinstance(redacted, list):
            payload["redacted_fields"] = tuple(str(item) for item in redacted)
    if extra is not None:
        payload.update(dict(extra))
    return FeatureResult(status, freeze_map(payload), events, error)
