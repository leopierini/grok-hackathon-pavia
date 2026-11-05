"""Approve one leased dog.command, or a halt that outranks ordinary motion.

Frame dog/base_link uses +x forward, +y left, +z up, and positive yaw
counterclockwise. This module does not map those axes onto Unitree sport
commands. The dog app must test that mapping and recheck the step locally.
The command has no altitude field. Operator up/down is a ground-frame request.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
    Ticket,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_dog_command"
SCHEMA = "ground-task-v2"
LEASE_CAP_MS = 500
PROTOCOL = "2.0-draft"
FRAME = "dog/base_link"

REJECT_CANDIDATE = "candidate is not in the safe list"
REJECT_DURATION = "duration_ms exceeds 500"
REJECT_LEASE = "lease_ms exceeds 500"
REJECT_AVOIDANCE = "avoidance_enabled is not true"
REJECT_STANDING = "standing is not true"
REJECT_TETHER = "ethernet step exceeds tether budget"
REJECT_HALT = "ordinary motion is refused while halt is latched"
REJECT_ALTITUDE = "altitude is not a dog command field"
REJECT_BEACON = "beacon_epoch is required for an RSSI step"
REJECT_BLOCKED = "candidate list is blocked"
REJECT_UNSAFE = "candidate is not safe"
REJECT_EXPIRED = "candidate is expired"
REJECT_VISION = "vision step is not active"

_ALTITUDE_KEYS = frozenset(
    {
        "altitude",
        "altitude_m",
        "z_m",
        "requested_height_m",
        "height_m",
        "vertical_m",
        "linear_z_m_s",
    }
)
_ENVELOPE_KEYS = (
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
_PAYLOAD_KEYS = (
    "command_id",
    "proposal_id",
    "action",
    "lease_ms",
    "motion",
    "track_id",
    "beacon_epoch",
    "safety_snapshot_id",
    "reason",
)
_MOTION_KEYS = (
    "frame_id",
    "linear_x_m_s",
    "linear_y_m_s",
    "angular_z_rad_s",
    "duration_ms",
    "candidate_id",
    "snapshot_id",
    "map_epoch",
)
_MOVE_REASON = (
    "Synthetic approved bounded step in dog/base_link "
    "(+x forward, +y left, +z up, positive yaw counterclockwise). "
    "The dog app must test its own Unitree mapping and recheck before motion. "
    "Not a hardware setting."
)
_HALT_REASON = (
    "Operator halt; posture-preserving stop, not a lie-down. "
    "The dog app must recheck. Recipient safety priority applies."
)
_TOP_LEVEL = frozenset(
    {
        "proposal",
        "selection",
        "candidates",
        "readiness",
        "halt_latched",
        "issue_halt",
        "safety_snapshot_id",
        "duration_ms",
        "lease_ms",
        "linear_x_m_s",
        "linear_y_m_s",
        "angular_z_rad_s",
        "operator_axis",
        "action",
        "guidance",
        "beacon_epoch",
        "track_id",
        "candidate_id",
        "simulated",
        "motion",
        "mission_id",
        "epoch",
    }
)
_SELECTION_KEYS = frozenset(
    {
        "selection_id",
        "proposal_id",
        "guidance",
        "action",
        "candidate_id",
        "track_id",
        "beacon_epoch",
        "safety_snapshot_id",
        "lease_ms",
        "duration_ms",
        "linear_x_m_s",
        "linear_y_m_s",
        "angular_z_rad_s",
        "operator_axis",
        "snapshot_id",
        "map_epoch",
    }
)
_MOTION_INPUT_KEYS = frozenset({"linear_x_m_s", "linear_y_m_s", "angular_z_rad_s", "duration_ms"})
_READINESS_KEYS = frozenset(
    {
        "standing",
        "stationary",
        "avoidance_enabled",
        "transport",
        "tether_budget_m",
        "step_distance_m",
        "vision_active",
    }
)
_AXES = frozenset({"up", "down", "forward", "back", "left", "right"})
_STEP_ACTIONS = frozenset({"stand", "move_local", "turn"})
_PRESENCE_ACTIONS = frozenset({"approach", "stop", "play_warning", "follow", "return_home"})
_PRESENCE_REASON = (
    "Vision-guided presence command. No navigation candidate is required. "
    "The dog app must recheck before it moves or speaks."
)


class _Reject(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class _Invalid(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class _Issued:
    envelope: dict[str, object]
    command_id: str
    replayed: bool
    action: str


@dataclass(frozen=True)
class _HaltOrder:
    mission_id: str
    epoch: int
    simulated: bool
    lease_ms: int
    track_id: str | None
    beacon_epoch: int | None
    safety_snapshot_id: str


@dataclass(frozen=True)
class _PresenceOrder:
    mission_id: str
    epoch: int
    simulated: bool
    action: str
    lease_ms: int
    track_id: str | None
    beacon_epoch: int | None
    safety_snapshot_id: str
    proposal_id: str | None
    correlation_id: str | None
    warning_id: str | None
    text: str | None
    standoff_m: float | None
    reason: str


@dataclass(frozen=True)
class _StepOrder:
    mission_id: str
    epoch: int
    simulated: bool
    action: str
    candidate_id: str
    track_id: str
    beacon_epoch: int | None
    safety_snapshot_id: str
    lease_ms: int
    duration_ms: int
    linear_x_m_s: float
    linear_y_m_s: float
    angular_z_rad_s: float
    operator_axis: str | None
    guidance: str
    proposal_id: str | None
    correlation_id: str | None
    selection_id: str
    vision_active: bool
    transport: str
    tether_budget_m: float | None
    step_distance_m: float | None
    snapshot_id: str | None
    map_epoch: int | None
    candidates: dict[str, object]


class _Store:
    def __init__(self) -> None:
        self.issued: dict[tuple[str, ...], dict[str, object]] = {}
        self.move_count = 0
        self.halt_count = 0
        self.presence_count = 0
        self.seq = 0


def create(services: BaseServices) -> DogCommandFeature:
    """Build the dog-command feature. Construction does not touch a robot."""
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "dog command create takes base services")
    return DogCommandFeature(services)


class DogCommandFeature:
    """One command id per selection. A later identical request is not a second move."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.store = _Store()
        self.observations: dict[str, object] = {}
        self._diagnostic = False
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("expected a FeatureRequest")
        if request.kind == "diagnostic":
            self._diagnostic = True
            try:
                return await self._simulate(request)
            finally:
                self._diagnostic = False
        if request.kind not in {"command", "stage", "guard"}:
            return _failed("feature request kind is not supported")
        return await self._approve(request)

    async def _approve(self, request: FeatureRequest) -> FeatureResult:
        before = tuple(self._calls())
        try:
            payload = request.payload if isinstance(request.payload, Mapping) else None
            landing = None if payload is None else _drone_landing(payload)
            if landing is not None:
                result = await self._route_landing(request, landing)
            else:
                issued = self._issue(request)
                result = _ok(request.ticket, issued)
        except _Reject as rejected:
            result = _blocked(rejected.detail)
        except _Invalid as invalid:
            result = _failed(invalid.detail)
        if tuple(self._calls()) != before:
            return _failed("dog port was called")
        return result

    async def _route_landing(
        self,
        request: FeatureRequest,
        proposal: Mapping[str, object],
    ) -> FeatureResult:
        from patrol.ground.extensions.g17.implementation import create as create_drone
        from patrol.ground.extensions.g17.samples import armed_context

        context = armed_context()
        context["proposal"] = {str(key): value for key, value in proposal.items()}
        sent_at = proposal.get("sent_at")
        if isinstance(sent_at, str):
            context["evaluated_at"] = sent_at
        capabilities = context.get("capabilities")
        if isinstance(capabilities, dict):
            raw_body = capabilities.get("payload")
            if isinstance(raw_body, dict):
                commands = raw_body.get("supported_commands")
                if isinstance(commands, list) and "land_on_dog" not in commands:
                    body = dict(raw_body)
                    body["supported_commands"] = [*commands, "land_on_dog"]
                    copied = dict(capabilities)
                    copied["payload"] = body
                    context["capabilities"] = copied
        drone = create_drone(self.services)
        routed = FeatureRequest(
            kind="command",
            name="approve",
            ticket=request.ticket,
            payload=freeze_map(context),
        )
        return await drone.execute(routed)

    def _issue(self, request: FeatureRequest) -> _Issued:
        payload = _as_dict(dict(request.payload), "payload")
        _reject_altitude(payload)
        _reject_unknown(payload, _TOP_LEVEL, "payload")
        order = _parse(request, payload)
        if isinstance(order, _HaltOrder):
            return self._issue_halt(order)
        if isinstance(order, _PresenceOrder):
            if not self._diagnostic:
                self._require_current_ticket(request)
            return self._issue_presence(order)
        if not self._diagnostic:
            authority = self.services.kernel.authority
            if authority.cancelled:
                raise _Reject(REJECT_HALT)
            if request.ticket is None or request.ticket.epoch != authority.epoch:
                raise _Reject("ticket epoch is not current")
        return self._issue_step(order)

    def _require_current_ticket(self, request: FeatureRequest) -> None:
        authority = self.services.kernel.authority
        if authority.cancelled:
            raise _Reject(REJECT_HALT)
        if request.ticket is None or request.ticket.epoch != authority.epoch:
            raise _Reject("ticket epoch is not current")

    def _issue_halt(self, order: _HaltOrder) -> _Issued:
        key = (
            "halt",
            order.mission_id,
            str(order.epoch),
            order.safety_snapshot_id,
            order.track_id or "",
            "none" if order.beacon_epoch is None else str(order.beacon_epoch),
        )
        stored = self.store.issued.get(key)
        if stored is not None:
            command_id = _payload(stored)["command_id"]
            if not isinstance(command_id, str):
                raise _Invalid("stored halt command id is unreadable")
            return _Issued(_clone(stored), command_id, True, "halt")
        self.store.halt_count += 1
        self.store.seq += 1
        command_id = f"cmd-dog-halt-{self.store.halt_count:03d}"
        envelope = _envelope(
            command_id=command_id,
            seq=self.store.seq,
            mission_id=order.mission_id,
            epoch=order.epoch,
            simulated=order.simulated,
            correlation_id=None,
            lease_ms=order.lease_ms,
            sent_at=self.services.kernel.clock.utc_now(),
            body=_command_body(
                command_id=command_id,
                proposal_id=None,
                action="halt",
                lease_ms=order.lease_ms,
                motion=None,
                track_id=order.track_id,
                beacon_epoch=order.beacon_epoch,
                safety_snapshot_id=order.safety_snapshot_id,
                reason=_HALT_REASON,
            ),
        )
        self.store.issued[key] = _clone(envelope)
        return _Issued(envelope, command_id, False, "halt")

    def _issue_presence(self, order: _PresenceOrder) -> _Issued:
        key = (
            "presence",
            order.mission_id,
            str(order.epoch),
            order.action,
            order.proposal_id or "",
            order.track_id or "",
            "none" if order.beacon_epoch is None else str(order.beacon_epoch),
            order.safety_snapshot_id,
        )
        stored = self.store.issued.get(key)
        if stored is not None:
            command_id = _payload(stored)["command_id"]
            if not isinstance(command_id, str):
                raise _Invalid("stored presence command id is unreadable")
            return _Issued(_clone(stored), command_id, True, order.action)
        self.store.presence_count += 1
        self.store.seq += 1
        command_id = f"cmd-dog-presence-{self.store.presence_count:03d}"
        extras: dict[str, object] = {}
        if order.warning_id is not None:
            extras["warning_id"] = order.warning_id
        if order.text is not None:
            extras["text"] = order.text
        if order.standoff_m is not None:
            extras["standoff_m"] = order.standoff_m
        envelope = _envelope(
            command_id=command_id,
            seq=self.store.seq,
            mission_id=order.mission_id,
            epoch=order.epoch,
            simulated=order.simulated,
            correlation_id=order.correlation_id,
            lease_ms=order.lease_ms,
            sent_at=self.services.kernel.clock.utc_now(),
            body=_command_body(
                command_id=command_id,
                proposal_id=order.proposal_id,
                action=order.action,
                lease_ms=order.lease_ms,
                motion=None,
                track_id=order.track_id,
                beacon_epoch=order.beacon_epoch,
                safety_snapshot_id=order.safety_snapshot_id,
                reason=order.reason,
                extras=extras,
            ),
        )
        self.store.issued[key] = _clone(envelope)
        return _Issued(envelope, command_id, False, order.action)

    def _issue_step(self, order: _StepOrder) -> _Issued:
        if order.guidance == "rssi" and order.beacon_epoch is None:
            raise _Reject(REJECT_BEACON)
        if order.guidance == "vision" and order.vision_active is not True:
            raise _Reject(REJECT_VISION)
        candidate = _select_candidate(order, self.services.kernel.clock.utc_now())
        _check_tether(order)
        linear_x, linear_y = _apply_axis(
            order.operator_axis,
            order.linear_x_m_s,
            order.linear_y_m_s,
        )
        motion = {
            "frame_id": FRAME,
            "linear_x_m_s": linear_x,
            "linear_y_m_s": linear_y,
            "angular_z_rad_s": order.angular_z_rad_s,
            "duration_ms": order.duration_ms,
            "candidate_id": candidate["candidate_id"],
            "snapshot_id": candidate["snapshot_id"],
            "map_epoch": candidate["map_epoch"],
        }
        _reject_altitude(motion)
        _exact(motion, _MOTION_KEYS, "motion")
        key = (
            "step",
            order.mission_id,
            str(order.epoch),
            order.selection_id,
            order.proposal_id or "",
            str(candidate["candidate_id"]),
            order.action,
            "none" if order.beacon_epoch is None else str(order.beacon_epoch),
            order.safety_snapshot_id,
        )
        stored = self.store.issued.get(key)
        if stored is not None:
            command_id = _payload(stored)["command_id"]
            if not isinstance(command_id, str):
                raise _Invalid("stored command id is unreadable")
            previous = _payload(stored)
            if (
                previous.get("motion") != motion
                or previous.get("lease_ms") != order.lease_ms
                or previous.get("track_id") != order.track_id
            ):
                raise _Invalid("selection id reused with changed motion, lease, or track")
            return _Issued(_clone(stored), command_id, True, order.action)
        self.store.move_count += 1
        self.store.seq += 1
        command_id = f"cmd-dog-{self.store.move_count:03d}"
        envelope = _envelope(
            command_id=command_id,
            seq=self.store.seq,
            mission_id=order.mission_id,
            epoch=order.epoch,
            simulated=order.simulated,
            correlation_id=order.correlation_id,
            lease_ms=order.lease_ms,
            sent_at=self.services.kernel.clock.utc_now(),
            body=_command_body(
                command_id=command_id,
                proposal_id=order.proposal_id,
                action=order.action,
                lease_ms=order.lease_ms,
                motion=motion,
                track_id=order.track_id,
                beacon_epoch=order.beacon_epoch,
                safety_snapshot_id=order.safety_snapshot_id,
                reason=_MOVE_REASON,
            ),
        )
        self.store.issued[key] = _clone(envelope)
        return _Issued(envelope, command_id, False, order.action)

    async def _simulate(self, request: FeatureRequest) -> FeatureResult:
        handlers = {
            "example_move": self._case_example_move,
            "example_halt": self._case_example_halt,
            "unknown_candidate": self._case_unknown_candidate,
            "tether_overrun": self._case_tether,
            "halt_latched_move": self._case_halt_latched,
            "replay_selection": self._case_replay,
            "dog_port_quiet": self._case_dog_port,
            "duration_rejected": self._case_duration,
            "avoidance_null": self._case_avoidance,
            "altitude_rejected": self._case_altitude,
            "vision_step": self._case_vision,
            "rssi_missing_beacon": self._case_rssi_beacon,
            "halt_despite_block": self._case_halt_despite,
            "operator_up": self._case_operator_up,
            "homing_selection": self._case_homing,
            "wifi_no_cable": self._case_wifi,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return self._project(
                _failed(f"unknown dog command case {request.name}"),
                detail=f"unknown dog command case {request.name}",
                trace=("failed", "invalid_input"),
            )
        try:
            return await handler()
        except _Invalid as exc:
            return self._project(
                _failed(exc.detail),
                detail=exc.detail,
                trace=("failed", "invalid_input"),
            )

    async def _case_example_move(self) -> FeatureResult:
        result = await self._approve(self._example_request())
        return self._project_move(result, "example_move")

    async def _case_example_halt(self) -> FeatureResult:
        result = await self._approve(self._halt_request())
        return self._project_halt(result, "example_halt")

    async def _case_unknown_candidate(self) -> FeatureResult:
        proposal = _load("proposal.json")
        body = dict(_payload(proposal))
        body["candidate_id"] = "candidate-missing"
        proposal["payload"] = body
        approved = await self._approve(self._example_request(proposal=proposal))
        return self._project_rejection(approved)

    async def _case_tether(self) -> FeatureResult:
        readiness = _load("readiness.json")
        readiness["step_distance_m"] = 3.0
        readiness["tether_budget_m"] = 1.0
        approved = await self._approve(self._example_request(readiness=readiness))
        return self._project_rejection(approved)

    async def _case_halt_latched(self) -> FeatureResult:
        request = self._example_request()
        payload = dict(request.payload)
        payload["halt_latched"] = True
        return self._project_rejection(await self._approve(_command_request(payload)))

    async def _case_replay(self) -> FeatureResult:
        request = self._example_request()
        first = await self._approve(request)
        second = await self._approve(request)
        first_id = first.data.get("command_id")
        second_id = second.data.get("command_id")
        quiet = self._calls() == []
        ok = (
            first.status == "ok"
            and second.status == "ok"
            and first_id == "cmd-dog-001"
            and second_id == first_id
            and second.data.get("replayed") is True
            and len(self.store.issued) == 1
            and quiet
        )
        detail = "replay" if ok else "replay did not keep one command id"
        trace = (
            f"command_id:{first_id}",
            f"replay_command_id:{second_id}",
            f"issued_count:{len(self.store.issued)}",
            "dog_port_not_called" if quiet else "dog_port_called",
        )
        if not ok:
            return self._project(_failed(detail), detail=detail, trace=trace)
        return self._project(second, detail=detail, trace=trace)

    async def _case_dog_port(self) -> FeatureResult:
        result = await self._approve(self._example_request())
        quiet = self._calls() == []
        command_id = result.data.get("command_id")
        ok = result.status == "ok" and quiet and command_id == "cmd-dog-001"
        trace = (
            "dog_port_not_called" if quiet else "dog_port_called",
            f"device_calls:{len(self._calls())}",
            "kind:dog.command",
            f"command_id:{command_id}",
        )
        if not ok:
            return self._project(
                _failed("dog port was called"),
                detail="dog port was called",
                trace=trace,
            )
        return self._project(result, detail="dog_port_quiet", trace=trace)

    async def _case_duration(self) -> FeatureResult:
        request = self._example_request()
        payload = dict(request.payload)
        payload["duration_ms"] = 2000
        return self._project_rejection(await self._approve(_command_request(payload)))

    async def _case_avoidance(self) -> FeatureResult:
        readiness = _load("readiness.json")
        readiness["avoidance_enabled"] = None
        approved = await self._approve(self._example_request(readiness=readiness))
        return self._project_rejection(approved)

    async def _case_altitude(self) -> FeatureResult:
        request = self._example_request()
        payload = dict(request.payload)
        payload["altitude_m"] = 4.0
        return self._project_rejection(await self._approve(_command_request(payload)))

    async def _case_vision(self) -> FeatureResult:
        readiness = _load("readiness.json")
        readiness["vision_active"] = True
        selection = _load("selection.json")
        selection["guidance"] = "vision"
        selection["beacon_epoch"] = None
        selection["selection_id"] = "vision-step-01"
        result = await self._approve(
            self._example_request(
                proposal=None,
                selection=selection,
                readiness=readiness,
                include_proposal=False,
            )
        )
        command = _as_command(result)
        beacon = _payload(command).get("beacon_epoch")
        ok = result.status == "ok" and beacon is None and self._calls() == []
        trace = (
            "kind:dog.command",
            "action:move_local",
            "beacon:null",
            "guidance:vision",
            "dog_port_not_called" if self._calls() == [] else "dog_port_called",
            f"command_id:{result.data.get('command_id')}",
        )
        if not ok:
            return self._project(
                _failed("vision step was not approved"),
                detail="vision step was not approved",
                trace=trace,
            )
        return self._project(result, detail="vision_step", trace=trace)

    async def _case_rssi_beacon(self) -> FeatureResult:
        selection = _load("selection.json")
        selection.pop("beacon_epoch", None)
        result = await self._approve(
            self._example_request(proposal=None, selection=selection, include_proposal=False)
        )
        return self._project_rejection(result)

    async def _case_halt_despite(self) -> FeatureResult:
        readiness = _load("readiness.json")
        readiness["standing"] = None
        readiness["avoidance_enabled"] = None
        payload: dict[str, object] = {
            "issue_halt": True,
            "halt_latched": True,
            "readiness": readiness,
            "candidates": _load("candidates.json"),
            "candidate_id": "candidate-missing",
            "track_id": "target-001",
            "beacon_epoch": 3,
            "safety_snapshot_id": "safety-stop-001",
            "lease_ms": 500,
            "simulated": True,
        }
        approved = await self._approve(_command_request(payload))
        return self._project_halt(approved, "halt_despite_block")

    async def _case_operator_up(self) -> FeatureResult:
        selection = _load("selection.json")
        selection["operator_axis"] = "up"
        result = await self._approve(
            self._example_request(proposal=None, selection=selection, include_proposal=False)
        )
        command = _as_command(result)
        motion = _payload(command).get("motion")
        linear_x = motion.get("linear_x_m_s") if isinstance(motion, dict) else None
        altitude = _contains_altitude(command)
        ok = (
            result.status == "ok"
            and linear_x == 0.1
            and not altitude
            and isinstance(motion, dict)
            and motion.get("frame_id") == FRAME
            and self._calls() == []
        )
        trace = (
            "axis:up",
            f"linear_x:{_num(linear_x)}",
            "linear_y:0.0",
            "no_altitude" if not altitude else "altitude_present",
            f"frame:{motion.get('frame_id') if isinstance(motion, dict) else 'missing'}",
            "dog_port_not_called" if self._calls() == [] else "dog_port_called",
            f"command_id:{result.data.get('command_id')}",
        )
        if not ok:
            return self._project(
                _failed("operator up was not a ground step"),
                detail="operator up was not a ground step",
                trace=trace,
            )
        return self._project(result, detail="operator_up", trace=trace)

    async def _case_homing(self) -> FeatureResult:
        result = await self._approve(
            self._example_request(
                proposal=None,
                selection=_load("selection.json"),
                include_proposal=False,
            )
        )
        command = _as_command(result)
        ok = (
            result.status == "ok"
            and command.get("correlation_id") is None
            and _payload(command).get("proposal_id") == "proposal-dog-001"
            and self._calls() == []
        )
        motion = _payload(command).get("motion")
        candidate = motion.get("candidate_id") if isinstance(motion, dict) else None
        trace = (
            "kind:dog.command",
            "action:move_local",
            "correlation:null",
            "proposal:proposal-dog-001",
            f"candidate:{candidate}",
            "dog_port_not_called" if self._calls() == [] else "dog_port_called",
            f"command_id:{result.data.get('command_id')}",
        )
        if not ok:
            return self._project(
                _failed("homing selection was not approved"),
                detail="homing selection was not approved",
                trace=trace,
            )
        return self._project(result, detail="homing_selection", trace=trace)

    async def _case_wifi(self) -> FeatureResult:
        readiness = _load("readiness.json")
        readiness["transport"] = "wifi"
        readiness["step_distance_m"] = 9.0
        readiness["tether_budget_m"] = 1.0
        result = await self._approve(self._example_request(readiness=readiness))
        ok = result.status == "ok" and self._calls() == []
        trace = (
            "transport:wifi",
            "kind:dog.command",
            "dog_port_not_called" if self._calls() == [] else "dog_port_called",
            f"command_id:{result.data.get('command_id')}",
        )
        if not ok:
            return self._project(
                _failed("wifi step was rejected"),
                detail="wifi step was rejected",
                trace=trace,
            )
        return self._project(result, detail="wifi_no_cable", trace=trace)

    def _example_request(
        self,
        *,
        proposal: dict[str, object] | None = None,
        selection: dict[str, object] | None = None,
        readiness: dict[str, object] | None = None,
        include_proposal: bool = True,
    ) -> FeatureRequest:
        if proposal is None and include_proposal:
            proposal = _load("proposal.json")
        payload: dict[str, object] = {
            "candidates": _load("candidates.json"),
            "readiness": readiness if readiness is not None else _load("readiness.json"),
            "safety_snapshot_id": "safety-001",
            "halt_latched": False,
            "issue_halt": False,
            "simulated": True,
        }
        if proposal is not None:
            payload["proposal"] = proposal
        if selection is not None:
            payload["selection"] = selection
        return _command_request(payload)

    def _halt_request(self) -> FeatureRequest:
        return _command_request(
            {
                "issue_halt": True,
                "halt_latched": False,
                "track_id": "target-001",
                "beacon_epoch": 3,
                "safety_snapshot_id": "safety-stop-001",
                "lease_ms": 500,
                "simulated": True,
                "mission_id": "demo-20261104-001",
                "epoch": 1,
            }
        )

    def _project_move(self, result: FeatureResult, detail: str) -> FeatureResult:
        if result.status != "ok":
            return self._project_rejection(result)
        command = _as_command(result)
        return self._project(result, detail=detail, trace=_move_trace(command, self._calls()))

    def _project_halt(self, result: FeatureResult, detail: str) -> FeatureResult:
        if result.status != "ok":
            return self._project_rejection(result)
        command = _as_command(result)
        return self._project(result, detail=detail, trace=_halt_trace(command, self._calls()))

    def _project_rejection(self, result: FeatureResult) -> FeatureResult:
        detail = result.error.detail if result.error is not None else "missing error"
        return self._project(result, detail=detail, trace=("rejected", detail))

    def _project(
        self,
        result: FeatureResult,
        *,
        detail: str,
        trace: tuple[str, ...],
    ) -> FeatureResult:
        if self._live() != 0:
            result = _failed("simulation made a live device call")
            detail = "simulation made a live device call"
            trace = ("dog_port_called",)
        data = freeze_map(
            {
                "authorized": result.status == "ok",
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": len(self._calls()),
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        )
        return FeatureResult(result.status, data, (), result.error)

    def _calls(self) -> list[str]:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", None)
        if isinstance(calls, list):
            return [str(item) for item in calls]
        return []

    def _live(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        value = getattr(devices, "live_call_count", 0)
        if isinstance(value, bool) or not isinstance(value, int):
            return 0
        return value


def _parse(request: FeatureRequest, payload: dict[str, object]) -> _HaltOrder | _StepOrder:
    proposal = _optional_object(payload, "proposal")
    selection = _optional_object(payload, "selection")
    if proposal is not None:
        _check_proposal(proposal)
    if selection is not None:
        _reject_unknown(selection, _SELECTION_KEYS, "selection")
    motion_input = _optional_object(payload, "motion")
    if motion_input is not None:
        _reject_unknown(motion_input, _MOTION_INPUT_KEYS, "motion")
    action = _merged_action(payload, selection, proposal)
    if _flag(payload, "issue_halt") or action == "halt":
        return _parse_halt(request, payload, selection, proposal)
    if action in _PRESENCE_ACTIONS:
        return _parse_presence(request, payload, selection, proposal, action)
    return _parse_step(request, payload, selection, proposal, motion_input, action)


def _parse_halt(
    request: FeatureRequest,
    payload: dict[str, object],
    selection: dict[str, object] | None,
    proposal: dict[str, object] | None,
) -> _HaltOrder:
    mission_id, epoch, simulated = _identity(request, payload, proposal, None)
    lease_ms = _bounded_ms(_first(selection, payload, "lease_ms", 500), "lease_ms")
    track = _optional_text(_first_present(selection, payload, "track_id"))
    if proposal is not None and track is None:
        track = _optional_text(_payload(proposal).get("track_id"))
    beacon = _optional_beacon(_first_present(selection, payload, "beacon_epoch"))
    safety = _required_text(
        _first_present(selection, payload, "safety_snapshot_id"),
        "safety_snapshot_id",
    )
    return _HaltOrder(mission_id, epoch, simulated, lease_ms, track, beacon, safety)


def _parse_presence(
    request: FeatureRequest,
    payload: dict[str, object],
    selection: dict[str, object] | None,
    proposal: dict[str, object] | None,
    action: str,
) -> _PresenceOrder:
    proposal_body = _payload(proposal) if proposal is not None else {}
    mission_id, epoch, simulated = _identity(
        request,
        payload,
        proposal,
        payload.get("candidates"),
    )
    lease_ms = _bounded_ms(_first(selection, payload, "lease_ms", 500), "lease_ms")
    track = _optional_text(_first_present(selection, payload, "track_id"))
    if proposal is not None and track is None:
        track = _optional_text(proposal_body.get("track_id"))
    beacon = _agree_beacon(selection, payload, proposal_body if proposal is not None else None)
    safety = _required_text(
        _first_present(selection, payload, "safety_snapshot_id"),
        "safety_snapshot_id",
    )
    proposal_id = _optional_text(_first_present(selection, None, "proposal_id"))
    if proposal_id is None and proposal is not None:
        proposal_id = _optional_text(proposal_body.get("proposal_id"))
    correlation = proposal.get("message_id") if proposal is not None else None
    if correlation is not None:
        correlation = _required_text(correlation, "proposal message_id")
    stated = proposal_body.get("reason")
    reason = stated if isinstance(stated, str) and stated.strip() else _PRESENCE_REASON
    warning_id = None
    text = None
    standoff_m = None
    if action == "play_warning":
        warning_id = _required_text(proposal_body.get("warning_id"), "warning_id")
        text = _required_text(proposal_body.get("text"), "text")
    if action == "follow" and proposal_body.get("standoff_m") is not None:
        standoff_m = _positive_number(proposal_body.get("standoff_m"), "standoff_m")
    return _PresenceOrder(
        mission_id,
        epoch,
        simulated,
        action,
        lease_ms,
        track,
        beacon,
        safety,
        proposal_id,
        correlation,
        warning_id,
        text,
        standoff_m,
        reason,
    )


def _parse_step(
    request: FeatureRequest,
    payload: dict[str, object],
    selection: dict[str, object] | None,
    proposal: dict[str, object] | None,
    motion_input: dict[str, object] | None,
    action: str,
) -> _StepOrder:
    if _flag(payload, "halt_latched"):
        raise _Reject(REJECT_HALT)
    readiness = _required_object(payload, "readiness")
    _reject_unknown(readiness, _READINESS_KEYS, "readiness")
    _require_true(readiness.get("standing"), "standing")
    _require_true(readiness.get("stationary"), "stationary")
    _require_true(readiness.get("avoidance_enabled"), "avoidance_enabled")
    transport = readiness.get("transport")
    if transport not in {"ethernet", "wifi"}:
        raise _Invalid("transport must be ethernet or wifi")
    vision_active = False
    if "vision_active" in readiness:
        vision_active = _require_bool(readiness["vision_active"], "vision_active")
    mission_id, epoch, simulated = _identity(request, payload, proposal, payload.get("candidates"))
    proposal_body = _payload(proposal) if proposal is not None else {}
    candidate_id = _agree_text(
        "candidate_id",
        _present(selection, "candidate_id"),
        _present(payload, "candidate_id"),
        proposal_body.get("candidate_id") if proposal is not None else None,
    )
    track_id = _agree_text(
        "track_id",
        _present(selection, "track_id"),
        _present(payload, "track_id"),
        proposal_body.get("track_id") if proposal is not None else None,
    )
    beacon = _agree_beacon(selection, payload, proposal_body if proposal is not None else None)
    guidance = _optional_text(_first_present(selection, payload, "guidance"))
    if guidance is None:
        guidance = "vision" if vision_active and beacon is None else "rssi"
    if guidance not in {"rssi", "vision"}:
        raise _Invalid("guidance must be rssi or vision")
    safety = _required_text(
        _first_present(selection, payload, "safety_snapshot_id"),
        "safety_snapshot_id",
    )
    lease_ms = _bounded_ms(_first(selection, payload, "lease_ms", 300), "lease_ms")
    duration_source = _first(motion_input, selection, "duration_ms", None)
    if duration_source is None:
        duration_source = payload.get("duration_ms", 300)
    duration_ms = _bounded_ms(duration_source, "duration_ms")
    linear_x = _velocity(
        _first(motion_input, selection, "linear_x_m_s", None),
        payload,
        "linear_x_m_s",
        action,
    )
    linear_y = _velocity(
        _first(motion_input, selection, "linear_y_m_s", None),
        payload,
        "linear_y_m_s",
        action,
    )
    angular = _velocity(
        _first(motion_input, selection, "angular_z_rad_s", None),
        payload,
        "angular_z_rad_s",
        action,
    )
    if action == "turn" and not _has_number(motion_input, selection, payload, "angular_z_rad_s"):
        raise _Invalid("turn requires angular_z_rad_s")
    axis = _optional_text(_first_present(selection, payload, "operator_axis"))
    if axis is not None and axis not in _AXES:
        raise _Invalid("operator_axis is not a ground-frame direction")
    proposal_id = _optional_text(_first_present(selection, None, "proposal_id"))
    if proposal_id is None and proposal is not None:
        proposal_id = _optional_text(proposal_body.get("proposal_id"))
    correlation = proposal.get("message_id") if proposal is not None else None
    if correlation is not None:
        correlation = _required_text(correlation, "proposal message_id")
    selection_id = _optional_text(_present(selection, "selection_id"))
    if selection_id is None:
        selection_id = proposal_id or candidate_id
    snapshot_id = _optional_text(_present(selection, "snapshot_id"))
    map_epoch = _optional_epoch(_present(selection, "map_epoch"))
    budget = _optional_distance(readiness, "tether_budget_m")
    distance = _optional_distance(readiness, "step_distance_m")
    candidates = payload.get("candidates")
    if not isinstance(candidates, dict):
        raise _Invalid("candidates must be an object")
    return _StepOrder(
        mission_id=mission_id,
        epoch=epoch,
        simulated=simulated,
        action=action,
        candidate_id=candidate_id,
        track_id=track_id,
        beacon_epoch=beacon,
        safety_snapshot_id=safety,
        lease_ms=lease_ms,
        duration_ms=duration_ms,
        linear_x_m_s=linear_x,
        linear_y_m_s=linear_y,
        angular_z_rad_s=angular,
        operator_axis=axis,
        guidance=guidance,
        proposal_id=proposal_id,
        correlation_id=correlation,
        selection_id=selection_id,
        vision_active=vision_active,
        transport=str(transport),
        tether_budget_m=budget,
        step_distance_m=distance,
        snapshot_id=snapshot_id,
        map_epoch=map_epoch,
        candidates=_as_dict(candidates, "candidates"),
    )


def _select_candidate(order: _StepOrder, now: datetime) -> dict[str, object]:
    message = order.candidates
    if message.get("kind") != "navigation.candidates":
        raise _Invalid("candidates kind is not navigation.candidates")
    body = _payload(message)
    blocked = body.get("blocked")
    if not isinstance(blocked, bool):
        raise _Invalid("blocked must be a boolean")
    if blocked is True:
        raise _Reject(REJECT_BLOCKED)
    raw = body.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise _Reject(REJECT_CANDIDATE)
    matches: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise _Invalid("candidate must be an object")
        candidate = _as_dict(item, "candidate")
        if candidate.get("candidate_id") == order.candidate_id:
            matches.append(candidate)
    if not matches:
        raise _Reject(REJECT_CANDIDATE)
    if len(matches) != 1:
        raise _Reject("candidate id is ambiguous")
    chosen = matches[0]
    if chosen.get("safe") is not True:
        raise _Reject(REJECT_UNSAFE)
    if chosen.get("frame_id") != FRAME:
        raise _Reject("candidate frame is not dog/base_link")
    snapshot = _required_text(chosen.get("snapshot_id"), "snapshot_id")
    map_epoch = chosen.get("map_epoch")
    if isinstance(map_epoch, bool) or not isinstance(map_epoch, int) or map_epoch < 0:
        raise _Invalid("map_epoch must be a non-negative integer")
    if order.snapshot_id is not None and order.snapshot_id != snapshot:
        raise _Reject("snapshot_id does not match the candidate")
    if order.map_epoch is not None and order.map_epoch != map_epoch:
        raise _Reject("map_epoch does not match the candidate")
    valid_until = chosen.get("valid_until")
    if not isinstance(valid_until, str):
        raise _Invalid("candidate valid_until is required")
    if now >= _parse_utc(valid_until):
        raise _Reject(REJECT_EXPIRED)
    return {
        "candidate_id": order.candidate_id,
        "snapshot_id": snapshot,
        "map_epoch": map_epoch,
    }


def _check_tether(order: _StepOrder) -> None:
    if order.transport != "ethernet":
        return
    if order.tether_budget_m is None or order.step_distance_m is None:
        raise _Reject("ethernet tether budget is required")
    if order.step_distance_m > order.tether_budget_m:
        raise _Reject(REJECT_TETHER)


def _apply_axis(axis: str | None, linear_x: float, linear_y: float) -> tuple[float, float]:
    if axis is None:
        return linear_x, linear_y
    if axis in {"up", "forward"}:
        magnitude = abs(linear_x) if linear_x != 0 else 0.1
        return magnitude, linear_y
    if axis in {"down", "back"}:
        magnitude = abs(linear_x) if linear_x != 0 else 0.1
        return -magnitude, linear_y
    if axis == "left":
        magnitude = abs(linear_y) if linear_y != 0 else 0.1
        return linear_x, magnitude
    magnitude = abs(linear_y) if linear_y != 0 else 0.1
    return linear_x, -magnitude


def _drone_landing(payload: Mapping[str, object]) -> dict[str, object] | None:
    proposal = payload.get("proposal")
    if not isinstance(proposal, Mapping):
        return None
    if proposal.get("kind") != "motion.proposal":
        return None
    body = proposal.get("payload")
    if not isinstance(body, Mapping):
        return None
    if body.get("target_component") != "drone" or body.get("action") != "land_on_dog":
        return None
    return {str(key): value for key, value in proposal.items()}


def _check_proposal(message: dict[str, object]) -> None:
    if message.get("kind") != "motion.proposal":
        raise _Invalid("proposal kind is not motion.proposal")
    body = _payload(message)
    if body.get("target_component") != "dog":
        raise _Reject("proposal target_component is not dog")
    if not isinstance(body.get("action"), str) or not str(body.get("action")):
        raise _Invalid("proposal action is missing")


def _merged_action(
    payload: dict[str, object],
    selection: dict[str, object] | None,
    proposal: dict[str, object] | None,
) -> str:
    for source in (selection, payload):
        if source is not None and "action" in source:
            action = source["action"]
            if action not in _STEP_ACTIONS and action != "halt":
                raise _Invalid("action is not a dog command")
            return str(action)
    if proposal is not None:
        semantic = _payload(proposal).get("action")
        if semantic == "land_on_dog":
            raise _Reject("land_on_dog is a drone command")
        if semantic in _STEP_ACTIONS or semantic == "halt":
            return str(semantic)
        # A bridge presence proposal has no planner candidate. Keep the word
        # instead of inventing a walk that then fails candidate_id.
        if semantic in _PRESENCE_ACTIONS and _candidate_absent(selection, payload, proposal):
            return str(semantic)
        # approach is the published homing step when a candidate is attached.
        # Any other proposal word is refused so a stop, a warning, a follow,
        # or a return home cannot become a walk.
        if semantic == "approach":
            return "move_local"
        if isinstance(semantic, str) and semantic:
            raise _Reject("proposal action is not a dog step")
    return "move_local"


def _candidate_absent(
    selection: dict[str, object] | None,
    payload: dict[str, object],
    proposal: dict[str, object] | None,
) -> bool:
    proposal_body = _payload(proposal) if proposal is not None else None
    for source in (selection, payload, proposal_body):
        if source is not None and source.get("candidate_id") is not None:
            return False
    return True


def _identity(
    request: FeatureRequest,
    payload: dict[str, object],
    proposal: dict[str, object] | None,
    candidates: object,
) -> tuple[str, int, bool]:
    missions: list[str] = []
    epochs: list[int] = []
    if request.ticket is not None:
        missions.append(_required_text(request.ticket.mission_id, "mission_id"))
        epochs.append(_epoch_value(request.ticket.epoch, "epoch"))
    if proposal is not None:
        missions.append(_required_text(proposal.get("mission_id"), "mission_id"))
        epochs.append(_epoch_value(proposal.get("epoch"), "epoch"))
    if isinstance(candidates, dict):
        missions.append(_required_text(candidates.get("mission_id"), "mission_id"))
        epochs.append(_epoch_value(candidates.get("epoch"), "epoch"))
    if "mission_id" in payload:
        missions.append(_required_text(payload.get("mission_id"), "mission_id"))
    if "epoch" in payload:
        epochs.append(_epoch_value(payload.get("epoch"), "epoch"))
    if not missions or not epochs:
        raise _Invalid("mission_id is required")
    if any(item != missions[0] for item in missions):
        raise _Reject("mission_id does not match")
    if any(item != epochs[0] for item in epochs):
        raise _Reject("epoch does not match")
    flags: list[bool] = []
    if "simulated" in payload:
        flags.append(_require_bool(payload["simulated"], "simulated"))
    if proposal is not None and "simulated" in proposal:
        flags.append(_require_bool(proposal["simulated"], "simulated"))
    if isinstance(candidates, dict) and "simulated" in candidates:
        flags.append(_require_bool(candidates["simulated"], "simulated"))
    if flags and any(item is not flags[0] for item in flags):
        raise _Reject("simulated does not match")
    return missions[0], epochs[0], flags[0] if flags else True


def _agree_text(label: str, *values: object) -> str:
    present = [item for item in values if item is not None]
    if not present:
        raise _Invalid(f"{label} is required")
    texts = [_required_text(item, label) for item in present]
    if any(item != texts[0] for item in texts):
        raise _Reject(f"{label} does not match")
    return texts[0]


def _agree_beacon(
    selection: dict[str, object] | None,
    payload: dict[str, object],
    proposal_body: dict[str, object] | None,
) -> int | None:
    found: list[int | None] = []
    for source in (selection, payload, proposal_body):
        if source is not None and "beacon_epoch" in source:
            found.append(_optional_beacon(source.get("beacon_epoch")))
    if not found:
        return None
    if any(item != found[0] for item in found):
        raise _Reject("beacon_epoch does not match")
    return found[0]


def _bounded_ms(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _Invalid(f"{label} must be an integer")
    if value > LEASE_CAP_MS:
        if label == "duration_ms":
            raise _Reject(REJECT_DURATION)
        raise _Reject(REJECT_LEASE)
    if value < 1:
        raise _Invalid(f"{label} is below 1")
    return value


def _velocity(preferred: object, payload: dict[str, object], name: str, action: str) -> float:
    if preferred is not None:
        return _finite(preferred, name)
    if name in payload:
        return _finite(payload[name], name)
    if action == "move_local" and name == "linear_x_m_s":
        return 0.1
    return 0.0


def _has_number(
    motion: dict[str, object] | None,
    selection: dict[str, object] | None,
    payload: dict[str, object],
    name: str,
) -> bool:
    return any(source is not None and name in source for source in (motion, selection, payload))


def _first(
    primary: dict[str, object] | None,
    secondary: dict[str, object] | None,
    key: str,
    default: object,
) -> object:
    if primary is not None and key in primary:
        return primary[key]
    if secondary is not None and key in secondary:
        return secondary[key]
    return default


def _first_present(
    primary: dict[str, object] | None,
    secondary: dict[str, object] | None,
    key: str,
) -> object:
    if primary is not None and key in primary:
        return primary[key]
    if secondary is not None and key in secondary:
        return secondary[key]
    return None


def _present(source: dict[str, object] | None, key: str) -> object:
    if source is None or key not in source:
        return None
    return source[key]


def _flag(payload: dict[str, object], key: str) -> bool:
    if key not in payload:
        return False
    return _require_bool(payload[key], key)


def _require_bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise _Invalid(f"{label} must be a boolean")
    return value


def _require_true(value: object, label: str) -> None:
    if value is True:
        return
    if label == "standing":
        raise _Reject(REJECT_STANDING)
    if label == "avoidance_enabled":
        raise _Reject(REJECT_AVOIDANCE)
    raise _Reject(f"{label} is not true")


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or value == "" or len(value) > 160:
        raise _Invalid(f"{label} must be a short string")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value == "" or len(value) > 160:
        raise _Invalid("identifier must be a short string")
    return value


def _optional_beacon(value: object) -> int | None:
    if value is None:
        return None
    return _epoch_value(value, "beacon_epoch")


def _optional_epoch(value: object) -> int | None:
    if value is None:
        return None
    return _epoch_value(value, "map_epoch")


def _epoch_value(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise _Invalid(f"{label} must be a non-negative integer")
    return value


def _optional_distance(source: dict[str, object], key: str) -> float | None:
    if key not in source or source[key] is None:
        return None
    number = _finite(source[key], key)
    if number < 0:
        raise _Invalid(f"{key} must be non-negative")
    return number


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Invalid(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise _Invalid(f"{label} must be finite")
    return number


def _optional_object(payload: dict[str, object], key: str) -> dict[str, object] | None:
    if key not in payload or payload[key] is None:
        return None
    value = payload[key]
    if not isinstance(value, dict):
        raise _Invalid(f"{key} must be an object")
    return _as_dict(value, key)


def _required_object(payload: dict[str, object], key: str) -> dict[str, object]:
    found = _optional_object(payload, key)
    if found is None:
        raise _Invalid(f"{key} is required")
    return found


def _reject_unknown(source: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = [key for key in source if key not in allowed and key not in _ALTITUDE_KEYS]
    if unknown:
        raise _Invalid(f"{label} contains an unsupported field")


def _reject_altitude(source: Mapping[str, object]) -> None:
    for key, value in source.items():
        if key in {"proposal", "candidates", "readiness"}:
            continue
        if key in _ALTITUDE_KEYS:
            raise _Reject(REJECT_ALTITUDE)
        if isinstance(value, dict) and key in {"selection", "motion"}:
            _reject_altitude_tree(value)


def _reject_altitude_tree(source: Mapping[str, object]) -> None:
    for key, value in source.items():
        if key in _ALTITUDE_KEYS:
            raise _Reject(REJECT_ALTITUDE)
        if isinstance(value, dict):
            _reject_altitude_tree(_as_dict(value, key))


def _contains_altitude(value: object) -> bool:
    if isinstance(value, dict):
        return any(key in _ALTITUDE_KEYS or _contains_altitude(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_altitude(item) for item in value)
    return False


def _envelope(
    *,
    command_id: str,
    seq: int,
    mission_id: str,
    epoch: int,
    simulated: bool,
    correlation_id: str | None,
    lease_ms: int,
    sent_at: datetime,
    body: dict[str, object],
) -> dict[str, object]:
    moment = sent_at.astimezone(UTC)
    expires = moment + timedelta(milliseconds=lease_ms)
    envelope = {
        "protocol_version": PROTOCOL,
        "message_id": f"msg-{command_id}",
        "mission_id": mission_id,
        "epoch": epoch,
        "seq": seq,
        "sent_at": _format_utc(moment),
        "source": "ground",
        "destination": "dog",
        "kind": "dog.command",
        "correlation_id": correlation_id,
        "expires_at": _format_utc(expires),
        "simulated": simulated,
        "payload": body,
    }
    _exact(envelope, _ENVELOPE_KEYS, "envelope")
    return envelope


def _command_body(
    *,
    command_id: str,
    proposal_id: str | None,
    action: str,
    lease_ms: int,
    motion: dict[str, object] | None,
    track_id: str | None,
    beacon_epoch: int | None,
    safety_snapshot_id: str,
    reason: str,
    extras: Mapping[str, object] | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "command_id": command_id,
        "proposal_id": proposal_id,
        "action": action,
        "lease_ms": lease_ms,
        "motion": motion,
        "track_id": track_id,
        "beacon_epoch": beacon_epoch,
        "safety_snapshot_id": safety_snapshot_id,
        "reason": reason,
    }
    extra_keys: list[str] = []
    if extras is not None:
        for key in ("warning_id", "text", "standoff_m"):
            if key in extras:
                body[key] = extras[key]
                extra_keys.append(key)
    _exact(body, _PAYLOAD_KEYS + tuple(extra_keys), "payload")
    return body


def _positive_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        raise _Invalid(f"{label} must be a positive number")
    number = float(value)
    if number <= 0:
        raise _Invalid(f"{label} must be a positive number")
    return number


def _exact(value: Mapping[str, object], expected: tuple[str, ...], label: str) -> None:
    if tuple(value) != expected:
        raise _Invalid(f"{label} keys drifted")


def _ok(ticket: Ticket | None, issued: _Issued) -> FeatureResult:
    event_kind = "halt_requested" if issued.action == "halt" else "operation_started"
    events: tuple[GroundEvent, ...] = ()
    if not issued.replayed:
        body = _payload(issued.envelope)
        motion = body.get("motion")
        frame_id = motion.get("frame_id") if isinstance(motion, dict) else None
        map_epoch = motion.get("map_epoch") if isinstance(motion, dict) else None
        candidate_id = motion.get("candidate_id") if isinstance(motion, dict) else None
        events = (
            GroundEvent(
                event_kind,
                ticket,
                freeze_map(
                    {
                        "message_id": issued.envelope["message_id"],
                        "mission_id": issued.envelope["mission_id"],
                        "epoch": issued.envelope["epoch"],
                        "command_id": issued.command_id,
                        "kind": "dog.command",
                        "action": issued.action,
                        "track_id": body.get("track_id"),
                        "beacon_epoch": body.get("beacon_epoch"),
                        "map_epoch": map_epoch,
                        "frame_id": frame_id,
                        "candidate_id": candidate_id,
                    }
                ),
            ),
        )
    data = freeze_map(
        {
            "command": _clone(issued.envelope),
            "command_id": issued.command_id,
            "replayed": issued.replayed,
            "dog_port_called": False,
            "slot": SLOT,
            "schema_version": SCHEMA,
        }
    )
    return FeatureResult("ok", data, events, None)


def _blocked(detail: str) -> FeatureResult:
    return FeatureResult(
        "blocked",
        freeze_map({"dog_port_called": False, "slot": SLOT, "schema_version": SCHEMA}),
        (),
        GroundError("rejected", detail, False),
    )


def _failed(detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map({"dog_port_called": False, "slot": SLOT, "schema_version": SCHEMA}),
        (),
        GroundError("invalid_input", detail, False),
    )


def _command_request(payload: dict[str, object]) -> FeatureRequest:
    return FeatureRequest(
        kind="command",
        name="approve",
        ticket=Ticket("demo-20261104-001", 1, "dog-command"),
        payload=freeze_map(payload),
    )


def _load(name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / "g23" / name
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _clone(_as_dict(raw, name))


def _as_command(result: FeatureResult) -> dict[str, object]:
    command = result.data.get("command")
    if not isinstance(command, dict):
        return {}
    return _as_dict(command, "command")


def _payload(message: Mapping[str, object]) -> dict[str, object]:
    body = message.get("payload")
    if not isinstance(body, dict):
        raise _Invalid("payload must be an object")
    return _as_dict(body, "payload")


def _as_dict(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _Invalid(f"{label} must be an object")
    found: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise _Invalid(f"{label} keys must be strings")
        found[key] = item
    return found


def _clone(value: dict[str, object]) -> dict[str, object]:
    cloned: object = json.loads(json.dumps(value))
    return _as_dict(cloned, "command")


def _format_utc(moment: datetime) -> str:
    utc = moment.astimezone(UTC)
    millis = utc.microsecond // 1000
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def _parse_utc(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _Invalid("candidate valid_until is not a timestamp") from exc
    if moment.tzinfo is None:
        raise _Invalid("candidate valid_until is not a timestamp")
    return moment.astimezone(UTC)


def _num(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "invalid"
    number = float(value)
    if number == 0.0:
        return "0.0"
    return format(number, ".6f").rstrip("0").rstrip(".")


def _move_trace(command: Mapping[str, object], calls: list[str]) -> tuple[str, ...]:
    body = _payload(command)
    motion = body.get("motion")
    if not isinstance(motion, dict):
        motion = {}
    reason = body.get("reason")
    reason_text = reason if isinstance(reason, str) else ""
    altitude = _contains_altitude(command)
    quiet = calls == []
    kind = command.get("kind")
    return (
        f"kind:{kind}",
        f"action:{body.get('action')}",
        f"frame:{motion.get('frame_id')}",
        f"candidate:{motion.get('candidate_id')}",
        f"snapshot:{motion.get('snapshot_id')}",
        f"map_epoch:{motion.get('map_epoch')}",
        f"track:{body.get('track_id')}",
        f"beacon:{_shown(body.get('beacon_epoch'))}",
        f"lease:{body.get('lease_ms')}",
        f"duration:{motion.get('duration_ms')}",
        f"linear_x:{_num(motion.get('linear_x_m_s'))}",
        f"linear_y:{_num(motion.get('linear_y_m_s'))}",
        f"angular_z:{_num(motion.get('angular_z_rad_s'))}",
        f"proposal:{_shown(body.get('proposal_id'))}",
        f"correlation:{_shown(command.get('correlation_id'))}",
        f"source:{command.get('source')}",
        f"destination:{command.get('destination')}",
        f"simulated:{str(command.get('simulated')).lower()}",
        "envelope:" + ",".join(command),
        "payload:" + ",".join(body),
        "motion:" + ",".join(motion),
        "no_altitude" if not altitude else "altitude_present",
        (
            "proposal_not_command"
            if kind == "dog.command" and "direction_hint" not in body
            else "proposal_leaked"
        ),
        "recheck_required" if "recheck" in reason_text.lower() else "recheck_missing",
        "dog_port_not_called" if quiet else "dog_port_called",
        f"command_id:{body.get('command_id')}",
    )


def _halt_trace(command: Mapping[str, object], calls: list[str]) -> tuple[str, ...]:
    body = _payload(command)
    reason = body.get("reason")
    reason_text = reason if isinstance(reason, str) else ""
    posture = (
        body.get("action") == "halt"
        and body.get("motion") is None
        and "not a lie-down" in reason_text
    )
    return (
        "kind:dog.command",
        "action:halt",
        "motion:null",
        f"proposal:{_shown(body.get('proposal_id'))}",
        f"correlation:{_shown(command.get('correlation_id'))}",
        f"lease:{body.get('lease_ms')}",
        f"track:{_shown(body.get('track_id'))}",
        f"beacon:{_shown(body.get('beacon_epoch'))}",
        f"safety:{body.get('safety_snapshot_id')}",
        "no_altitude" if not _contains_altitude(command) else "altitude_present",
        "posture_stop" if posture else "posture_missing",
        "dog_port_not_called" if calls == [] else "dog_port_called",
        f"command_id:{body.get('command_id')}",
        "envelope:" + ",".join(command),
        "payload:" + ",".join(body),
    )


def _shown(value: object) -> str:
    if value is None:
        return "null"
    return str(value)
