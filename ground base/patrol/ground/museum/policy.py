"""Ground authorizes every museum motor effect.

Grok answers still-there / gone / unsure. This policy turns an accepted
decision into contract commands through ``g17`` and the v2 schema. A decision
never reaches a peer. Halt latches the policy before any later command.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from patrol.ground.extensions.g11.schema_check import SchemaFault, load_schema, validate_message
from patrol.ground.extensions.g16.decide import assess
from patrol.ground.extensions.g17.policy import decide
from patrol.ground.extensions.g17.samples import armed_context
from patrol.ground.extensions.g18.messages import parse_command as parse_drone_command
from patrol.ground.extensions.g24.model import parse_command as parse_dog_command
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.museum.safety import decision_motor_phrase

MISSION = "demo-20261104-001"
SAFETY = "safety-presence-001"
WARNING_ID = "go-away"
WARNING_TEXT = "go away"
STANDOFF_M = 2.0
Json = dict[str, object]


class MuseumPolicy:
    """One armed session. Construction does not touch a device."""

    def __init__(self) -> None:
        self.schema = load_schema()
        self.armed = False
        self.halted = False
        self.warned = False
        self.closed = False
        self.track_id: str | None = None
        self.rejections: list[str] = []
        self._seq = 0

    def arm(self) -> None:
        self.armed = True

    def bind_track(self, track_id: str) -> None:
        """Ground assigns the track. The detector does not."""

        self.track_id = track_id

    def authorize_dispatch(self, evaluated_at: str, evidence_frame_id: str) -> list[Json]:
        """YOLO saw one person. Hover the drone and send the dog. No Grok call."""

        if not self._ready():
            return []
        hover = self._drone(
            "hold",
            "center",
            evaluated_at,
            evidence_frame_id,
            "proposal-hover-dispatch",
            "Drone holds after YOLO sees one person.",
        )
        follow = self._dog(
            "follow",
            evaluated_at,
            evidence_frame_id,
            "proposal-follow-dispatch",
            "Ground is sending the dog.",
            standoff_m=STANDOFF_M,
        )
        if hover is None or follow is None:
            return []
        return [hover, follow]

    def authorize_presence(
        self,
        decision: Mapping[str, object],
        request: Mapping[str, object],
        evaluated_at: str,
    ) -> list[Json]:
        """Map one accepted presence decision onto commands. Unsure moves nothing."""

        if self.halted:
            self.rejections.append("halt_latched")
            return []
        if not self._ready():
            return []
        phrase = decision_motor_phrase(decision)
        if phrase is not None:
            self.rejections.append(phrase)
            return []
        assessment = assess(
            decision,
            request,
            current_track_id=self.track_id,
            current_camera_epoch=1,
        )
        if assessment.status != "ok":
            self.rejections.append(f"g16:{assessment.error_detail}")
            return []
        if assessment.halt_latched:
            self.rejections.append("halt_preserved")
            return []
        payload = _payload(decision)
        request_payload = _payload(request)
        state = payload.get("target_state")
        stage = request_payload.get("stage")
        action = payload.get("suggested_action")
        frame_id = payload.get("frame_id")
        evidence = frame_id if isinstance(frame_id, str) else "dog-front-001"
        proposal_action = _proposal_action(assessment.proposal)
        if state == "uncertain" or action == "review" or assessment.outcome == "review":
            return []
        if stage == "drone_track" and state == "person_visible" and action == "hold":
            if proposal_action != "hold":
                self.rejections.append("drone_hold_missing")
                return []
            hover = self._drone(
                "hold",
                "center",
                evaluated_at,
                evidence,
                f"proposal-hold-{self._seq + 1}",
                "Drone holds while the person is still in the downward frame.",
            )
            return [hover] if hover is not None else []
        if stage == "dog_approach" and state == "person_visible" and action == "approach":
            if proposal_action != "approach":
                self.rejections.append("approach_not_executed")
                return []
            if not self.warned:
                warning = self._warn(evaluated_at, evidence, "proposal-warn-1")
                if warning is None:
                    return []
                self.warned = True
                return [warning]
            follow = self._dog(
                "follow",
                evaluated_at,
                evidence,
                "proposal-follow-again",
                "Person is still there. Follow at the published standoff.",
                standoff_m=STANDOFF_M,
            )
            warning = self._warn(evaluated_at, evidence, "proposal-warn-2")
            if follow is None or warning is None:
                return []
            return [follow, warning]
        if state == "not_visible" and action == "stop":
            if proposal_action != "stop" or self.closed:
                self.rejections.append("stop_not_accepted")
                return []
            stop = self._dog(
                "stop",
                evaluated_at,
                evidence,
                "proposal-stop",
                "Person is gone. Stop in place.",
            )
            land = self._drone(
                "land_on_dog",
                "unknown",
                evaluated_at,
                "drone-downward-001",
                "proposal-land-on-dog",
                "Person is gone. Land on the dog.",
            )
            home = self._dog(
                "return_home",
                evaluated_at,
                evidence,
                "proposal-return-home",
                "Person is gone. Return to the start mark.",
            )
            if stop is None or land is None or home is None:
                return []
            self.closed = True
            return [stop, land, home]
        self.rejections.append(f"ignored:{stage}:{state}:{action}")
        return []

    def halt_command(self, evaluated_at: str, reason: str) -> list[Json]:
        """One dog halt. Later presence reads authorize nothing."""

        if self.halted:
            return []
        self.halted = True
        self._seq += 1
        command: Json = {
            "protocol_version": "2.0-draft",
            "message_id": f"msg-halt-{self._seq}",
            "mission_id": MISSION,
            "epoch": 1,
            "seq": self._seq,
            "sent_at": evaluated_at,
            "source": "ground",
            "destination": "dog",
            "kind": "dog.command",
            "correlation_id": None,
            "expires_at": _plus(evaluated_at, 500),
            "simulated": True,
            "payload": {
                "command_id": f"cmd-halt-{self._seq}",
                "proposal_id": None,
                "action": "halt",
                "lease_ms": 500,
                "motion": None,
                "track_id": self.track_id,
                "beacon_epoch": None,
                "safety_snapshot_id": SAFETY,
                "reason": reason,
            },
        }
        if not self._accept_dog(command):
            self.rejections.append("halt_rejected")
            return []
        return [command]

    def rejection_of(self, message: Mapping[str, object]) -> str | None:
        """Contract check only. This does not authorize motion."""

        try:
            validate_message(message, self.schema)
        except SchemaFault as exc:
            return f"{exc.code}: {exc.reason}"
        return None

    def seal_proposal(self, proposal: Mapping[str, object], evaluated_at: str) -> Json | None:
        """Run one proposal through g17 and the schema. A refusal seals nothing."""

        target = _payload(proposal).get("target_component")
        if target == "drone":
            return self._seal_drone(proposal, evaluated_at)
        return self._seal_dog(proposal, evaluated_at)

    def _ready(self) -> bool:
        if not self.armed:
            self.rejections.append("not_armed")
            return False
        if self.track_id is None:
            self.rejections.append("track_unassigned")
            return False
        return True

    def _warn(self, evaluated_at: str, evidence: str, proposal_id: str) -> Json | None:
        return self._dog(
            "play_warning",
            evaluated_at,
            evidence,
            proposal_id,
            "Say the go-away warning.",
            warning_id=WARNING_ID,
            text=WARNING_TEXT,
        )

    def _dog(
        self,
        action: str,
        evaluated_at: str,
        evidence: str,
        proposal_id: str,
        reason: str,
        *,
        warning_id: str | None = None,
        text: str | None = None,
        standoff_m: float | None = None,
    ) -> Json | None:
        direction = "unknown" if action in {"stop", "return_home"} else "center"
        payload: Json = {
            "proposal_id": proposal_id,
            "target_component": "dog",
            "action": action,
            "direction_hint": direction,
            "track_id": self.track_id,
            "evidence_frame_id": evidence,
            "candidate_id": None,
            "beacon_epoch": None,
            "reason": reason,
        }
        if warning_id is not None and text is not None:
            payload["warning_id"] = warning_id
            payload["text"] = text
        if standoff_m is not None:
            payload["standoff_m"] = standoff_m
        proposal = self._proposal(proposal_id, evaluated_at, payload)
        return self._seal_dog(proposal, evaluated_at)

    def _drone(
        self,
        action: str,
        direction: str,
        evaluated_at: str,
        evidence: str,
        proposal_id: str,
        reason: str,
    ) -> Json | None:
        payload: Json = {
            "proposal_id": proposal_id,
            "target_component": "drone",
            "action": action,
            "direction_hint": direction,
            "track_id": self.track_id,
            "evidence_frame_id": evidence,
            "candidate_id": None,
            "beacon_epoch": None,
            "reason": reason,
        }
        proposal = self._proposal(proposal_id, evaluated_at, payload)
        return self._seal_drone(proposal, evaluated_at)

    def _proposal(self, proposal_id: str, evaluated_at: str, payload: Json) -> Json:
        self._seq += 1
        return {
            "protocol_version": "2.0-draft",
            "message_id": f"msg-{proposal_id}",
            "mission_id": MISSION,
            "epoch": 1,
            "seq": self._seq,
            "sent_at": evaluated_at,
            "source": "ground",
            "destination": "ground",
            "kind": "motion.proposal",
            "correlation_id": None,
            "expires_at": _plus(evaluated_at, 5000),
            "simulated": True,
            "payload": payload,
        }

    def _seal_dog(self, proposal: Mapping[str, object], evaluated_at: str) -> Json | None:
        fault = self.rejection_of(proposal)
        if fault is not None:
            self.rejections.append(fault)
            return None
        result = decide(
            {
                "proposal": proposal,
                "operator_request": None,
                "evaluated_at": evaluated_at,
                "safety_snapshot_id": SAFETY,
            }
        )
        if result.dog_command is None:
            self.rejections.append(f"g17:{result.code}:{result.reason}")
            return None
        command = dict(result.dog_command)
        if not self._accept_dog(command):
            return None
        return command

    def _seal_drone(self, proposal: Mapping[str, object], evaluated_at: str) -> Json | None:
        fault = self.rejection_of(proposal)
        if fault is not None:
            self.rejections.append(fault)
            return None
        context = copy.deepcopy(armed_context())
        context["proposal"] = proposal
        context["operator_request"] = None
        context["evaluated_at"] = evaluated_at
        capabilities = context.get("capabilities")
        if isinstance(capabilities, dict):
            body = capabilities.get("payload")
            if isinstance(body, dict):
                commands = body.get("supported_commands")
                if isinstance(commands, list) and "land_on_dog" not in commands:
                    commands.append("land_on_dog")
        result = decide(context)
        if not result.ok or result.draft is None:
            self.rejections.append(f"g17:{result.code}:{result.reason}")
            return None
        draft = result.draft
        self._seq += 1
        command: Json = {
            "protocol_version": "2.0-draft",
            "message_id": f"msg-cmd-{draft.idempotency_key}",
            "mission_id": draft.mission_id,
            "epoch": draft.epoch,
            "seq": self._seq,
            "sent_at": draft.evaluated_at,
            "source": "ground",
            "destination": "drone",
            "kind": "drone.command",
            "correlation_id": draft.correlation_id,
            "expires_at": _plus(draft.evaluated_at, draft.deadline_ms),
            "simulated": draft.simulated,
            "payload": {
                "command_id": f"cmd-{draft.idempotency_key}",
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
        try:
            validate_message(command, self.schema)
            parse_drone_command(command)
        except (SchemaFault, GroundFault, ValueError) as exc:
            self.rejections.append(f"drone_command:{exc}")
            return None
        return command

    def _accept_dog(self, command: Mapping[str, object]) -> bool:
        try:
            validate_message(command, self.schema)
            parse_dog_command(command)
        except (SchemaFault, GroundFault, ValueError) as exc:
            self.rejections.append(f"dog_command:{exc}")
            return False
        return True


def _payload(message: Mapping[str, object] | None) -> Mapping[str, object]:
    if message is None:
        return {}
    payload = message.get("payload")
    if isinstance(payload, Mapping):
        return payload
    return {}


def _proposal_action(proposal: Mapping[str, object] | None) -> str | None:
    action = _payload(proposal).get("action")
    return action if isinstance(action, str) else None


def _plus(stamp: str, milliseconds: int) -> str:
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)
    parsed += timedelta(milliseconds=milliseconds)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond // 1000:03d}Z"
