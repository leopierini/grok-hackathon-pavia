"""Approve one allowlisted drone primitive. The drone port is not called."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from patrol.ground.extensions.g17.policy import CommandDraft, Decision, decide
from patrol.ground.extensions.g17.samples import (
    TRACK_AT,
    armed_context,
    features_of,
    operator_context,
    payload_of,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_drone_command"
SCHEMA = "ground-task-v2"


def _copy(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _copy(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy(item) for item in value]
    return value


@dataclass(frozen=True)
class _Issued:
    command: Mapping[str, object]
    event: GroundEvent
    command_id: str
    primitive_id: str
    lease_ms: int
    deadline_ms: int
    camera_id: str
    beacon_epoch: int | None
    action: str
    supervised: bool


class DroneCommandFeature:
    """One approval yields one command record. Replay keeps that record."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self._issued: dict[tuple[str, int, str], _Issued] = {}
        self._identities: dict[tuple[str, int, str], object] = {}
        self._extra = 0
        self._seq = 0

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if request.kind == "diagnostic":
            return await self._diagnostic(request)
        return self._approve(request)

    def _approve(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request.payload, Mapping):
            return self._invalid(request, "payload must be an object")
        context = dict(request.payload)
        if context.get("evaluated_at") is None:
            context["evaluated_at"] = _format_utc(self.services.kernel.clock.utc_now())
        context["halt_latched"] = self.services.kernel.authority.cancelled
        if request.ticket is not None and not isinstance(request.ticket, Ticket):
            return self._invalid(request, "ticket must be a Ticket")
        if (
            isinstance(request.ticket, Ticket)
            and request.ticket.epoch != self.services.kernel.authority.epoch
        ):
            return self._refused(
                request,
                Decision(False, "blocked", "stale_ticket", "stale_ticket", True, None),
            )
        decision = decide(context)
        if decision.ok and decision.dog_command is not None:
            return self._forward_dog(request, decision.dog_command)
        if not decision.ok or decision.draft is None:
            return self._refused(request, decision)
        draft = decision.draft
        key = (draft.mission_id, draft.epoch, draft.idempotency_key)
        identity = _copy(
            {
                "proposal": context.get("proposal"),
                "operator_request": context.get("operator_request"),
            }
        )
        if key in self._issued:
            if identity != self._identities[key]:
                return self._invalid(request, "approval id reused with a changed request")
            return self._success(request, self._issued[key], replayed=True)
        issued = self._issue(request, decision.draft, context)
        self._issued[key] = issued
        self._identities[key] = identity
        return self._success(request, issued, replayed=False)

    def _issue(
        self,
        request: FeatureRequest,
        draft: CommandDraft,
        context: Mapping[str, object],
    ) -> _Issued:
        allowlist = _body(context.get("allowlist"))
        command_id = _preset_text(allowlist, "command_ids", draft.idempotency_key)
        if command_id is None:
            self._extra += 1
            command_id = f"cmd-drone-x{self._extra:03d}"
        message_id = _preset_text(allowlist, "message_ids", draft.idempotency_key)
        if message_id is None:
            message_id = f"msg-{command_id}"
        seq = _preset_int(allowlist, "seq", draft.idempotency_key)
        if seq is None:
            self._seq += 1
            seq = self._seq
        sent = _parse_utc(draft.evaluated_at)
        command = {
            "protocol_version": "2.0-draft",
            "message_id": message_id,
            "mission_id": draft.mission_id,
            "epoch": draft.epoch,
            "seq": seq,
            "sent_at": draft.evaluated_at,
            "source": "ground",
            "destination": "drone",
            "kind": "drone.command",
            "correlation_id": draft.correlation_id,
            "expires_at": _format_utc(sent + timedelta(milliseconds=draft.deadline_ms)),
            "simulated": draft.simulated,
            "payload": {
                "command_id": command_id,
                "proposal_id": draft.proposal_id,
                "action": draft.action,
                "primitive_id": draft.primitive_id,
                "lease_ms": draft.lease_ms,
                "requested_height_m": draft.requested_height_m,
                "height_reference": draft.height_reference,
                "evidence_frame_id": draft.evidence_frame_id,
                "track_id": draft.track_id,
                "camera_id": draft.camera_id,
                "beacon_epoch": draft.beacon_epoch,
                "reason": draft.reason,
            },
        }
        event = GroundEvent(
            "decision_received",
            request.ticket if isinstance(request.ticket, Ticket) else None,
            freeze_map(
                {
                    "message_id": message_id,
                    "mission_id": draft.mission_id,
                    "epoch": draft.epoch,
                    "command_id": command_id,
                    "frame_id": draft.evidence_frame_id,
                    "track_id": draft.track_id,
                    "beacon_epoch": draft.beacon_epoch,
                    "camera_epoch": draft.camera_epoch,
                    "map_epoch": None,
                    "kind": "drone.command",
                }
            ),
        )
        return _Issued(
            command=command,
            event=event,
            command_id=command_id,
            primitive_id=draft.primitive_id,
            lease_ms=draft.lease_ms,
            deadline_ms=draft.deadline_ms,
            camera_id=draft.camera_id,
            beacon_epoch=draft.beacon_epoch,
            action=draft.action,
            supervised=draft.supervised,
        )

    def _success(
        self,
        request: FeatureRequest,
        issued: _Issued,
        *,
        replayed: bool,
    ) -> FeatureResult:
        reason = "operator-supervised" if issued.supervised else "approved"
        data = freeze_map(
            {
                "command": _copy(issued.command),
                "command_id": issued.command_id,
                "primitive_id": issued.primitive_id,
                "lease_ms": issued.lease_ms,
                "deadline_ms": issued.deadline_ms,
                "camera_id": issued.camera_id,
                "beacon_epoch": issued.beacon_epoch,
                "action": issued.action,
                "reason": reason,
                "replayed": replayed,
                "supervised": issued.supervised,
                "live_call_count": self._live_calls(),
            }
        )
        return FeatureResult("ok", data, (issued.event,), None)

    def _forward_dog(
        self,
        request: FeatureRequest,
        command: Mapping[str, object],
    ) -> FeatureResult:
        payload = command.get("payload")
        action = payload.get("action") if isinstance(payload, Mapping) else None
        command_id = payload.get("command_id") if isinstance(payload, Mapping) else None
        data = freeze_map(
            {
                "command": _copy(command),
                "command_id": command_id,
                "primitive_id": None,
                "action": action,
                "reason": "approved",
                "replayed": False,
                "supervised": False,
                "live_call_count": self._live_calls(),
            }
        )
        event = GroundEvent(
            "decision_received",
            request.ticket if isinstance(request.ticket, Ticket) else None,
            freeze_map(
                {
                    "kind": "dog.command",
                    "command_id": command_id,
                    "action": action,
                    "reason": "approved",
                }
            ),
        )
        return FeatureResult("ok", data, (event,), None)

    def _refused(self, request: FeatureRequest, decision: Decision) -> FeatureResult:
        code = decision.code or "rejected"
        detail = decision.reason or "rejected"
        error = GroundError(code, detail, decision.recovery_required)
        event = GroundEvent(
            "decision_received",
            request.ticket if isinstance(request.ticket, Ticket) else None,
            freeze_map({"kind": "drone.command", "reason": detail, "command_id": None}),
        )
        data = freeze_map(
            {
                "command": None,
                "reason": detail,
                "replayed": False,
                "supervised": False,
                "live_call_count": self._live_calls(),
            }
        )
        status = decision.status if decision.status in {"blocked", "failed"} else "failed"
        return FeatureResult(status, data, (event,), error)

    def _invalid(self, request: FeatureRequest, detail: str) -> FeatureResult:
        return self._refused(
            request,
            Decision(False, "failed", "invalid_input", detail, False, None),
        )

    async def _diagnostic(self, request: FeatureRequest) -> FeatureResult:
        handlers: dict[str, Callable[[], Awaitable[FeatureResult]]] = {
            "approve_track": self._approve_track,
            "controlled_motion_off": self._controlled_motion_off,
            "land_deadline": self._land_deadline,
            "five_meter": self._five_meter,
            "replay": self._replay,
            "calibration_null": self._calibration_null,
            "no_drone_port": self._no_drone_port,
            "supervised_rejection": self._supervised_rejection,
            "sdk_text": self._sdk_text,
            "height_unknown": self._height_unknown,
            "expired_proposal": self._expired_proposal,
            "search_bounded": self._search_bounded,
            "search_cap": self._search_cap,
            "hover_when_blocked": self._hover_when_blocked,
            "supervised_step": self._supervised_step,
            "dog_target": self._dog_target,
            "lease_5000": self._lease_5000,
            "bool_string": self._bool_string,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return self._harness(
                False,
                "failed",
                "invalid_input",
                f"unknown drone command case {request.name}",
                ("failed", request.name),
                authorized=False,
            )
        try:
            return await handler()
        except Exception as exc:  # noqa: BLE001 - harness records the case, it does not crash
            return self._harness(
                False,
                "failed",
                "internal",
                f"{type(exc).__name__}: {exc}",
                ("failed", type(exc).__name__),
                authorized=False,
            )

    async def _approve_track(self) -> FeatureResult:
        result = self._approve(_stage(armed_context()))
        payload = _command_payload(result)
        ok = (
            result.status == "ok"
            and payload is not None
            and payload.get("action") == "track_step"
            and payload.get("primitive_id") == "verified-left-step-v1"
            and payload.get("lease_ms") == 300
            and payload.get("beacon_epoch") == 4
            and payload.get("evidence_frame_id") == "drone-downward-001"
            and payload.get("track_id") == "target-001"
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "track_step",
            (
                "action:track_step",
                "primitive:verified-left-step-v1",
                "lease_ms:300",
                "beacon_epoch:4",
                "no_drone_call",
            ),
            authorized=True,
            failure="track step was not approved",
        )

    async def _controlled_motion_off(self) -> FeatureResult:
        context = armed_context()
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = False
        return self._expect_block(
            context,
            "controlled_motion_disabled",
            ("rejected:controlled_motion_disabled", "no_drone_call"),
        )

    async def _land_deadline(self) -> FeatureResult:
        context = operator_context("land", "operator-land-001")
        result = self._approve(_stage(context))
        payload = _command_payload(result)
        ok = (
            result.status == "ok"
            and payload is not None
            and payload.get("action") == "land"
            and payload.get("primitive_id") == "verified-floor-land-v1"
            and payload.get("lease_ms") == 500
            and result.data.get("deadline_ms") == 8000
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "land",
            (
                "action:land",
                "primitive:verified-floor-land-v1",
                "lease_ms:500",
                "deadline_ms:8000",
                "no_drone_call",
            ),
            authorized=True,
            failure="land deadline was not separate from the motion lease",
        )

    async def _five_meter(self) -> FeatureResult:
        context = armed_context()
        payload_of(_as_dict(context["proposal"]))["reason"] = "move five meters left"
        return self._expect_block(
            context,
            "displacement_rejected",
            ("rejected:displacement_rejected", "no_drone_call"),
        )

    async def _replay(self) -> FeatureResult:
        context = armed_context()
        first = self._approve(_stage(context))
        second = self._approve(_stage(context))
        ok = (
            first.status == "ok"
            and second.status == "ok"
            and first.data.get("command_id") == "cmd-drone-001"
            and second.data.get("command_id") == first.data.get("command_id")
            and second.data.get("command") == first.data.get("command")
            and second.data.get("replayed") is True
            and len(self._issued) == 1
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "replayed",
            ("command_id:cmd-drone-001", "allocations:1", "no_drone_call"),
            authorized=True,
            failure="replaying the proposal allocated another command",
        )

    async def _calibration_null(self) -> FeatureResult:
        context = armed_context()
        context["calibration"] = None
        return self._expect_block(
            context,
            "calibration_missing",
            ("rejected:calibration_missing", "no_drone_call"),
        )

    async def _no_drone_port(self) -> FeatureResult:
        context = operator_context("land", "operator-land-001")
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = False
        result = self._approve(_stage(context))
        calls = self._calls()
        ok = result.status == "ok" and "drone.land" not in calls and "drone.inspect" not in calls
        return self._harness(
            ok,
            "ok",
            "",
            "land",
            ("drone.inspect:0", "drone.land:0", "no_drone_call"),
            authorized=True,
            failure="the provider called the drone port",
        )

    async def _supervised_rejection(self) -> FeatureResult:
        context = operator_context("track_step", "operator-track-blocked", direction_hint="left")
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = False
        return self._expect_block(
            context,
            "controlled_motion_disabled",
            ("rejected:controlled_motion_disabled", "supervised_label_absent", "no_drone_call"),
        )

    async def _sdk_text(self) -> FeatureResult:
        context = armed_context()
        payload_of(_as_dict(context["proposal"]))["reason"] = "send_rc_control 0 0 0 0"
        return self._expect_block(
            context,
            "sdk_text_rejected",
            ("rejected:sdk_text_rejected", "no_drone_call"),
        )

    async def _height_unknown(self) -> FeatureResult:
        context = armed_context()
        context["requested_height_m"] = 4
        context["height_reference"] = "unknown"
        return self._expect_block(
            context,
            "height_reference_mismatch",
            ("rejected:height_reference_mismatch", "no_drone_call"),
        )

    async def _expired_proposal(self) -> FeatureResult:
        context = armed_context()
        context["evaluated_at"] = "2026-11-04T13:00:10.700Z"
        return self._expect_block(
            context,
            "expired_proposal",
            ("rejected:expired_proposal", "no_drone_call"),
        )

    async def _search_bounded(self) -> FeatureResult:
        context = _search_context(0, 0, "proposal-search-000")
        result = self._approve(_stage(context))
        payload = _command_payload(result)
        ok = (
            result.status == "ok"
            and payload is not None
            and payload.get("action") == "search_step"
            and payload.get("primitive_id") == "verified-search-right-v1"
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "search_step",
            (
                "action:search_step",
                "primitive:verified-search-right-v1",
                "allowlist_only",
                "step:0",
                "cap:2",
                "no_drone_call",
            ),
            authorized=True,
            failure="search left the seeded allowlist",
        )

    async def _search_cap(self) -> FeatureResult:
        context = _search_context(0, 2, "proposal-search-capped")
        return self._expect_block(
            context,
            "search_cap_exhausted",
            ("rejected:search_cap_exhausted", "no_drone_call"),
        )

    async def _hover_when_blocked(self) -> FeatureResult:
        context = operator_context("hover", "operator-hover-001")
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = False
        result = self._approve(_stage(context))
        payload = _command_payload(result)
        ok = (
            result.status == "ok"
            and payload is not None
            and payload.get("action") == "hover"
            and payload.get("primitive_id") == "verified-hold-v1"
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "hover",
            (
                "action:hover",
                "primitive:verified-hold-v1",
                "controlled_motion:false",
                "no_drone_call",
            ),
            authorized=True,
            failure="hover was refused while tracking was blocked",
        )

    async def _supervised_step(self) -> FeatureResult:
        context = operator_context(
            "search_step",
            "operator-supervised-001",
            evaluated_at=TRACK_AT,
            supervised=True,
        )
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = False
        result = self._approve(_stage(context))
        payload = _command_payload(result)
        ok = (
            result.status == "ok"
            and result.data.get("supervised") is True
            and payload is not None
            and payload.get("primitive_id") == "operator-supervised-step-v1"
            and not self._calls()
        )
        return self._harness(
            ok,
            "ok",
            "",
            "operator-supervised",
            (
                "action:search_step",
                "primitive:operator-supervised-step-v1",
                "labeled:operator-supervised",
                "no_drone_call",
            ),
            authorized=True,
            failure="supervised search was not labeled",
        )

    async def _dog_target(self) -> FeatureResult:
        context = armed_context()
        payload_of(_as_dict(context["proposal"]))["target_component"] = "dog"
        calls = self._calls()
        result = self._approve(_stage(context))
        ok = (
            result.status == "blocked"
            and result.error is not None
            and result.error.detail == "wrong_component"
            and self._calls() == calls
            and "dog.run_route" not in self._calls()
        )
        return self._harness(
            ok,
            "blocked",
            "rejected",
            "wrong_component",
            ("rejected:wrong_component", "dog.run_route:0", "no_drone_call"),
            authorized=False,
            failure="a dog proposal was not rejected",
        )

    async def _lease_5000(self) -> FeatureResult:
        context = armed_context()
        context["lease_ms"] = 5000
        return self._expect_block(
            context,
            "lease_exceeds_motion_cap",
            ("rejected:lease_exceeds_motion_cap", "no_drone_call"),
        )

    async def _bool_string(self) -> FeatureResult:
        context = armed_context()
        features_of(_as_dict(context["capabilities"]))["controlled_motion"] = "true"
        result = self._approve(_stage(context))
        ok = (
            result.status == "failed"
            and result.error is not None
            and result.error.code == "invalid_input"
            and result.error.detail == "controlled_motion must be a boolean"
            and not self._calls()
        )
        return self._harness(
            ok,
            "failed",
            "invalid_input",
            "controlled_motion must be a boolean",
            ("rejected:not_a_boolean", "no_drone_call"),
            authorized=False,
            failure="a string boolean armed controlled motion",
        )

    def _expect_block(
        self,
        context: Mapping[str, object],
        reason: str,
        trace: tuple[str, ...],
    ) -> FeatureResult:
        result = self._approve(_stage(context))
        ok = (
            result.status == "blocked"
            and result.error is not None
            and result.error.code == "rejected"
            and result.error.detail == reason
            and result.data.get("command") is None
            and not self._calls()
        )
        return self._harness(
            ok,
            "blocked",
            "rejected",
            reason,
            trace,
            authorized=False,
            failure=f"expected rejection {reason}",
        )

    def _harness(
        self,
        ok: bool,
        status: str,
        code: str,
        detail: str,
        trace: tuple[str, ...],
        *,
        authorized: bool,
        failure: str = "",
    ) -> FeatureResult:
        calls = self._calls()
        if calls or self._live_calls():
            ok = False
            status = "failed"
            code = "unsafe_state"
            detail = "simulation called a device"
            authorized = False
        if not ok:
            status = "failed"
            code = code or "internal"
            detail = failure or detail
            authorized = False
        error = None if status == "ok" else GroundError(code, detail, code == "unsafe_state")
        data = freeze_map(
            {
                "authorized": authorized,
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": len(calls),
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        )
        return FeatureResult(status, data, (), error)

    def _calls(self) -> list[str]:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", None)
        if isinstance(calls, list):
            return [str(item) for item in calls]
        return []

    def _live_calls(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        value = getattr(devices, "live_call_count", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value


def create(services: BaseServices) -> DroneCommandFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "drone command create expects base services")
    return DroneCommandFeature(services)


def _stage(context: Mapping[str, object]) -> FeatureRequest:
    return FeatureRequest("stage", SLOT, None, context)


def _search_context(seed: int, steps: int, proposal_id: str) -> dict[str, object]:
    context = armed_context()
    proposal = _as_dict(context["proposal"])
    body = payload_of(proposal)
    body["action"] = "search"
    body["proposal_id"] = proposal_id
    context["seed"] = seed
    context["search_steps_taken"] = steps
    context["evaluated_at"] = TRACK_AT
    return context


def _command_payload(result: FeatureResult) -> Mapping[str, object] | None:
    command = result.data.get("command")
    if not isinstance(command, Mapping):
        return None
    payload = command.get("payload")
    if not isinstance(payload, Mapping):
        return None
    return payload


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise fault("invalid_input", "fixture must be an object")
    return value


def _body(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return {}
    if "kind" in value and isinstance(value.get("payload"), Mapping):
        payload = value.get("payload")
        if isinstance(payload, Mapping):
            return payload
    return value


def _preset_text(allowlist: Mapping[str, object], group: str, key: str) -> str | None:
    table = allowlist.get(group)
    if not isinstance(table, Mapping):
        return None
    value = table.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _preset_int(allowlist: Mapping[str, object], group: str, key: str) -> int | None:
    table = allowlist.get(group)
    if not isinstance(table, Mapping):
        return None
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _parse_utc(value: str) -> datetime:
    body = value[:-1] if value.endswith("Z") else value
    parsed = (
        datetime.strptime(body, "%Y-%m-%dT%H:%M:%S.%f")
        if "." in body
        else datetime.strptime(body, "%Y-%m-%dT%H:%M:%S")
    )
    return parsed.replace(tzinfo=UTC)


def _format_utc(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    millis = utc.microsecond // 1000
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"
