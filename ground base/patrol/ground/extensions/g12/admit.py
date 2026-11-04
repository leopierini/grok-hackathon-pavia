"""Admit capability reports and arm only validated, owned features.

This module does not open sockets, connect adapters, or grant motion.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from patrol.ground.kernel.contracts import (
    FeatureResult,
    GroundError,
    GroundEvent,
    GroundSettings,
    SessionSnapshot,
    Ticket,
)
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.kernel.snapshots import idle_snapshot
from patrol.ground.kernel.validation import freeze_map

SLOT = "feature.v2_capabilities"
SCHEMA = "ground-task-v2"
MISSION_ID = "demo-20261104-001"

FLAGS: tuple[str, ...] = (
    "controlled_motion",
    "downward_video",
    "rssi_receiver",
    "lidar",
    "slam",
    "target_range",
)
OWNED: dict[str, frozenset[str]] = {
    "drone": frozenset({"controlled_motion", "downward_video"}),
    "dog": frozenset({"controlled_motion", "lidar", "slam", "target_range"}),
    "pi": frozenset({"rssi_receiver"}),
}
REQUIRED_COMMANDS: dict[tuple[str, str], tuple[str, ...]] = {
    ("drone", "controlled_motion"): (
        "hover",
        "land",
        "search_step",
        "takeoff",
        "track_step",
    ),
    ("dog", "controlled_motion"): ("halt", "move_local", "stand", "turn"),
    ("pi", "rssi_receiver"): ("read_window",),
}
ENVELOPE_KEYS = frozenset(
    {
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
    }
)
PAYLOAD_KEYS = frozenset(
    {
        "device_id",
        "role",
        "model",
        "software_version",
        "supported_commands",
        "camera_ids",
        "pose_frames",
        "features",
        "validated",
        "acceptance_evidence_ref",
    }
)
SECRET_KEYS = frozenset(
    {
        "password",
        "passwd",
        "psk",
        "wifi_password",
        "secret",
        "token",
        "api_key",
        "credential",
        "credentials",
        "authorization",
    }
)
CAMERAS = frozenset({"front", "downward"})
ROLES = frozenset({"dog", "drone", "pi"})


@dataclass(frozen=True)
class Rejection:
    status: str
    code: str
    detail: str


@dataclass(frozen=True)
class ConnectedProfile:
    dog_device_id: str
    drone_device_id: str
    pi_device_id: str
    router_device_id: str
    router_networking: str
    flight_intent: str
    pi_required: bool
    dog_transport: str
    profile_transport: str | None


@dataclass(frozen=True)
class PeerRecord:
    message_id: str
    mission_id: str
    epoch: int
    seq: int
    role: str
    device_id: str
    model: str
    software_version: str
    supported_commands: tuple[str, ...]
    acceptance_evidence_ref: str | None
    validated: bool
    simulated: bool
    reported: Mapping[str, bool]
    armed: Mapping[str, bool]
    disarm_reasons: tuple[str, ...]
    canonical: str


def demo_settings(
    *,
    flight_intent: str = "autonomous_search",
    pi_required: bool = True,
    dog_transport: str = "ethernet",
    profile_transport: str | None = None,
    router_networking: str = "failed",
) -> GroundSettings:
    """Profile used by the bundled examples. The router is not the Pi."""
    transport = dog_transport if profile_transport is None else profile_transport
    return make_settings(
        dog_transport=dog_transport,
        profile_identity=f"dog.{dog_transport}",
        launch_tier="floor",
        adapter_configs={
            "dog": {"device_id": "dog-01", "transport": transport},
            "drone": {"device_id": "drone-01", "flight_intent": flight_intent},
            "pi": {"device_id": "pi-01", "required": pi_required},
            "router": {"device_id": "router-back", "networking": router_networking},
        },
    )


def demo_snapshot(
    settings: GroundSettings,
    *,
    epoch: int = 1,
    mission_id: str | None = MISSION_ID,
    armed: bool = False,
    halt_latched: bool = False,
    recovery_required: bool = False,
) -> SessionSnapshot:
    base = idle_snapshot(
        epoch=epoch,
        modes=dict(settings.modes),
        dog_transport=settings.dog_transport,
    )
    return replace(
        base,
        epoch=epoch,
        armed=armed,
        halt_latched=halt_latched,
        recovery_required=recovery_required,
        mission_id=mission_id,
        dog_transport=settings.dog_transport,
    )


def load_envelopes() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    root = repo_root() / "fixtures" / "ground" / "g12"
    return (
        _read_object(root / "drone-capabilities.json"),
        _read_object(root / "dog-capabilities.json"),
        _read_object(root / "pi-capabilities.json"),
    )


def copy_envelope(envelope: Mapping[str, object]) -> dict[str, object]:
    raw: object = json.loads(json.dumps(dict(envelope), sort_keys=True))
    parsed = _as_object(raw, "envelope")
    if isinstance(parsed, Rejection):
        raise fault("invalid_input", parsed.detail)
    return parsed


def with_payload(envelope: Mapping[str, object], **changes: object) -> dict[str, object]:
    copied = copy_envelope(envelope)
    payload = copied.get("payload")
    if not isinstance(payload, dict):
        raise fault("invalid_input", "payload must be an object")
    updated = dict(payload)
    updated.update(changes)
    copied["payload"] = updated
    return copied


def with_features(envelope: Mapping[str, object], **flags: bool) -> dict[str, object]:
    copied = copy_envelope(envelope)
    payload = copied.get("payload")
    if not isinstance(payload, dict):
        raise fault("invalid_input", "payload must be an object")
    features = payload.get("features")
    if not isinstance(features, dict):
        raise fault("invalid_input", "features must be an object")
    updated = dict(features)
    updated.update(flags)
    payload_copy = dict(payload)
    payload_copy["features"] = updated
    copied["payload"] = payload_copy
    return copied


class Ledger:
    """One armed record per role. A repeated message id does not add another."""

    def __init__(self) -> None:
        self.records: dict[str, PeerRecord] = {}
        self.owners: dict[tuple[str, str], str] = {}

    def apply(
        self,
        reports: tuple[Mapping[str, object], ...],
        settings: GroundSettings,
        snapshot: SessionSnapshot,
        ticket: Ticket | None,
        *,
        cancelled: bool = False,
    ) -> FeatureResult:
        if cancelled:
            return self._project(
                None,
                snapshot,
                ticket,
                (),
                (),
                Rejection("blocked", "cancelled", "cancellation is latched"),
            )
        pre = _precheck(reports, settings, snapshot, ticket)
        if isinstance(pre, Rejection):
            return self._project(None, snapshot, ticket, (), (), pre)
        profile = pre
        pending: list[PeerRecord] = []
        replayed: list[str] = []
        seen: dict[str, PeerRecord] = {}
        seen_roles: set[tuple[str, str]] = set()
        for raw in reports:
            parsed = _parse(raw, profile, snapshot)
            if isinstance(parsed, Rejection):
                return self._project(profile, snapshot, ticket, (), (), parsed)
            identity = (parsed.mission_id, parsed.role)
            existing = self.records.get(parsed.message_id) or seen.get(parsed.message_id)
            if existing is not None:
                if existing.canonical != parsed.canonical:
                    return self._project(
                        profile,
                        snapshot,
                        ticket,
                        (),
                        (),
                        Rejection("failed", "rejected", "report_id_conflict"),
                    )
                replayed.append(parsed.message_id)
                continue
            if identity in self.owners or identity in seen_roles:
                return self._project(
                    profile,
                    snapshot,
                    ticket,
                    (),
                    (),
                    Rejection("failed", "owner_mismatch", "role_already_admitted"),
                )
            seen[parsed.message_id] = parsed
            seen_roles.add(identity)
            pending.append(parsed)
        for record in pending:
            self.records[record.message_id] = record
            self.owners[(record.mission_id, record.role)] = record.message_id
        return self._project(profile, snapshot, ticket, tuple(pending), tuple(replayed), None)

    def _project(
        self,
        profile: ConnectedProfile | None,
        snapshot: SessionSnapshot,
        ticket: Ticket | None,
        new_records: tuple[PeerRecord, ...],
        replayed: tuple[str, ...],
        forced: Rejection | None,
    ) -> FeatureResult:
        mission = snapshot.mission_id or ""
        if not mission and new_records:
            mission = new_records[0].mission_id
        view = _view(self.records, mission, snapshot.epoch)
        features = _combined(view)
        dog_motion = _flag(view.get("dog"), "controlled_motion")
        slam = _flag(view.get("dog"), "slam")
        lidar = _flag(view.get("dog"), "lidar")
        reactive = lidar is True and slam is not True
        navigation = "slam_eligible" if slam else "unresolved"
        rssi = features["rssi_receiver"]
        search = "not_requested"
        if profile is not None and profile.flight_intent == "autonomous_search":
            search = "armed" if features["controlled_motion"] else "blocked"
        homing = "armed" if rssi else "blocked"
        vision = "not_applicable" if rssi else "available"
        natural = _profile_block(profile, snapshot, view, search, rssi)
        chosen = forced if forced is not None else natural
        status = "ok" if chosen is None else chosen.status
        reason = "" if chosen is None else chosen.detail
        error = None if chosen is None else GroundError(chosen.code, chosen.detail, False)
        if status == "ok" and profile is not None and profile.flight_intent == "supervised":
            if features["controlled_motion"] is not True:
                continuation = "supervised"
            else:
                continuation = "admitted"
        elif status == "ok":
            continuation = "admitted"
        else:
            continuation = "unresolved"
        decision = {"ok": "admitted", "blocked": "blocked"}.get(status, "rejected")
        router = _router(profile)
        peers = {role: _public_peer(record) for role, record in sorted(view.items())}
        events: tuple[GroundEvent, ...] = ()
        if forced is None:
            events = tuple(_event(record, ticket) for record in new_records)
        data = freeze_map(
            {
                "slot": SLOT,
                "schema_version": SCHEMA,
                "decision": decision,
                "continuation": continuation,
                "features": features,
                "dog_controlled_motion": dog_motion,
                "peers": peers,
                "navigation_mode": navigation,
                "reactive_avoidance_eligible": reactive,
                "slam_eligible": slam,
                "autonomous_search": search,
                "rssi_homing": homing,
                "vision_only_dog_approach": vision,
                "reason": reason,
                "armed_record_count": len(view),
                "replayed": replayed,
                "router": router,
                "motion_permission": False,
                "session_armed": False,
            }
        )
        return FeatureResult(status, data, events, error)


def _precheck(
    reports: object,
    settings: object,
    snapshot: object,
    ticket: Ticket | None,
) -> ConnectedProfile | Rejection:
    if not isinstance(settings, GroundSettings):
        return Rejection("failed", "invalid_input", "settings are required")
    if not isinstance(snapshot, SessionSnapshot):
        return Rejection("failed", "invalid_input", "snapshot is required")
    if isinstance(reports, (str, bytes)) or not isinstance(reports, tuple):
        return Rejection("failed", "invalid_input", "reports must be a tuple of envelopes")
    if snapshot.armed is True:
        return Rejection("failed", "unsafe_state", "session is already armed")
    if snapshot.halt_latched or snapshot.recovery_required or snapshot.flight_lock:
        return Rejection("blocked", "recovery_required", "recovery is still latched")
    if snapshot.dog_transport != settings.dog_transport:
        return Rejection("blocked", "contract_mismatch", "transport_profile_conflict")
    profile = _profile(settings)
    if isinstance(profile, Rejection):
        return profile
    if ticket is not None:
        if not isinstance(ticket, Ticket):
            return Rejection("failed", "invalid_input", "ticket is not current")
        if ticket.epoch != snapshot.epoch:
            return Rejection("failed", "stale_ticket", "ticket epoch is not current")
        if snapshot.mission_id and ticket.mission_id != snapshot.mission_id:
            return Rejection("failed", "rejected", "ticket_mission_mismatch")
    return profile


def _profile(settings: GroundSettings) -> ConnectedProfile | Rejection:
    dog = _config(settings, "dog")
    drone = _config(settings, "drone")
    pi = _config(settings, "pi")
    router = _config(settings, "router")
    if (
        isinstance(dog, Rejection)
        or isinstance(drone, Rejection)
        or isinstance(pi, Rejection)
        or isinstance(router, Rejection)
    ):
        found = dog if isinstance(dog, Rejection) else None
        found = drone if found is None and isinstance(drone, Rejection) else found
        found = pi if found is None and isinstance(pi, Rejection) else found
        found = router if found is None and isinstance(router, Rejection) else found
        return found if found is not None else Rejection(
            "failed", "invalid_input", "profile is incomplete"
        )
    dog_id = _text(dog, "device_id")
    drone_id = _text(drone, "device_id")
    pi_id = _text(pi, "device_id")
    router_id = _text(router, "device_id")
    networking = _text(router, "networking")
    intent = _text(drone, "flight_intent")
    if (
        isinstance(dog_id, Rejection)
        or isinstance(drone_id, Rejection)
        or isinstance(pi_id, Rejection)
        or isinstance(router_id, Rejection)
        or isinstance(networking, Rejection)
        or isinstance(intent, Rejection)
    ):
        for item in (dog_id, drone_id, pi_id, router_id, networking, intent):
            if isinstance(item, Rejection):
                return item
    if intent not in {"autonomous_search", "supervised"}:
        return Rejection("failed", "invalid_input", "flight intent is not a known profile")
    required = pi.get("required")
    if not isinstance(required, bool):
        return Rejection("failed", "invalid_input", "pi required flag must be a boolean")
    profile_transport: str | None = None
    if "transport" in dog:
        raw_transport = dog.get("transport")
        if not isinstance(raw_transport, str) or not raw_transport:
            return Rejection("failed", "invalid_input", "dog transport profile is invalid")
        profile_transport = raw_transport
    ids = (dog_id, drone_id, pi_id, router_id)
    if not all(isinstance(item, str) for item in ids):
        return Rejection("failed", "invalid_input", "profile device id is invalid")
    if router_id in {dog_id, drone_id, pi_id}:
        return Rejection("failed", "invalid_input", "router must be a different device")
    if len({dog_id, drone_id, pi_id}) < 3:
        return Rejection("failed", "invalid_input", "peer device ids must be distinct")
    return ConnectedProfile(
        str(dog_id),
        str(drone_id),
        str(pi_id),
        str(router_id),
        str(networking),
        str(intent),
        required,
        settings.dog_transport,
        profile_transport,
    )


def _parse(
    raw: Mapping[str, object],
    profile: ConnectedProfile,
    snapshot: SessionSnapshot,
) -> PeerRecord | Rejection:
    if _secret(raw):
        return Rejection("failed", "invalid_input", "credential field is not stored")
    if not isinstance(raw, Mapping):
        return Rejection("failed", "invalid_input", "envelope must be an object")
    extra = [key for key in raw if key not in ENVELOPE_KEYS]
    if extra:
        return Rejection("failed", "invalid_input", "unknown envelope field")
    missing = ENVELOPE_KEYS - set(raw)
    if missing:
        return Rejection("failed", "invalid_input", "envelope is missing a required field")
    if raw.get("protocol_version") != "2.0-draft":
        return Rejection("failed", "rejected", "protocol_version must be 2.0-draft")
    if raw.get("kind") != "capabilities.report":
        return Rejection("failed", "rejected", "kind must be capabilities.report")
    if raw.get("destination") != "ground":
        return Rejection("failed", "rejected", "destination_mismatch")
    message_id = _identifier(raw.get("message_id"), "message_id")
    mission_id = _identifier(raw.get("mission_id"), "mission_id")
    epoch = _whole(raw.get("epoch"), "epoch")
    seq = _whole(raw.get("seq"), "seq")
    sent_at = raw.get("sent_at")
    simulated = raw.get("simulated")
    if isinstance(message_id, Rejection):
        return message_id
    if isinstance(mission_id, Rejection):
        return mission_id
    if isinstance(epoch, Rejection):
        return epoch
    if isinstance(seq, Rejection):
        return seq
    if not isinstance(sent_at, str) or "T" not in sent_at:
        return Rejection("failed", "invalid_input", "sent_at is required")
    if not isinstance(simulated, bool):
        return Rejection("failed", "invalid_input", "simulated must be a boolean")
    nullable = _nullable(raw.get("correlation_id"), "correlation_id")
    expires = _nullable(raw.get("expires_at"), "expires_at")
    if isinstance(nullable, Rejection):
        return nullable
    if isinstance(expires, Rejection):
        return expires
    payload = _as_object(raw.get("payload"), "payload")
    if isinstance(payload, Rejection):
        return payload
    if _secret(payload):
        return Rejection("failed", "invalid_input", "credential field is not stored")
    record = _payload(payload, profile, simulated)
    if isinstance(record, Rejection):
        return record
    if snapshot.mission_id and mission_id != snapshot.mission_id:
        return Rejection("failed", "rejected", "mission_mismatch")
    if epoch != snapshot.epoch:
        return Rejection("blocked", "epoch_mismatch", "report epoch is not current")
    if raw.get("source") != record[0]:
        return Rejection("failed", "rejected", "source_role_mismatch")
    (
        role,
        device_id,
        model,
        version,
        commands,
        evidence,
        validated,
        reported,
        armed,
        reasons,
    ) = record
    normalized = {
        "protocol_version": "2.0-draft",
        "message_id": message_id,
        "mission_id": mission_id,
        "epoch": epoch,
        "seq": seq,
        "sent_at": sent_at,
        "source": role,
        "destination": "ground",
        "kind": "capabilities.report",
        "correlation_id": raw.get("correlation_id"),
        "expires_at": raw.get("expires_at"),
        "simulated": simulated,
        "payload": {
            "device_id": device_id,
            "role": role,
            "model": model,
            "software_version": version,
            "supported_commands": list(commands),
            "camera_ids": list(_cameras_from(payload)),
            "pose_frames": list(_frames_from(payload)),
            "features": dict(reported),
            "validated": validated,
            "acceptance_evidence_ref": evidence,
        },
    }
    return PeerRecord(
        message_id=str(message_id),
        mission_id=str(mission_id),
        epoch=epoch,
        seq=seq,
        role=str(role),
        device_id=str(device_id),
        model=str(model),
        software_version=str(version),
        supported_commands=commands,
        acceptance_evidence_ref=evidence,
        validated=validated,
        simulated=simulated,
        reported=reported,
        armed=armed,
        disarm_reasons=reasons,
        canonical=json.dumps(normalized, sort_keys=True, separators=(",", ":")),
    )


def _payload(
    payload: Mapping[str, object],
    profile: ConnectedProfile,
    simulated: bool,
) -> tuple[
    str,
    str,
    str,
    str,
    tuple[str, ...],
    str | None,
    bool,
    Mapping[str, bool],
    Mapping[str, bool],
    tuple[str, ...],
] | Rejection:
    extra = [key for key in payload if key not in PAYLOAD_KEYS]
    if extra:
        return Rejection("failed", "invalid_input", "unknown payload field")
    missing = PAYLOAD_KEYS - set(payload)
    if missing:
        return Rejection("failed", "invalid_input", "payload is missing a required field")
    role = payload.get("role")
    if role not in ROLES:
        return Rejection("failed", "rejected", "role_not_admitted")
    device_id = _identifier(payload.get("device_id"), "device_id")
    model = _identifier(payload.get("model"), "model")
    version = _identifier(payload.get("software_version"), "software_version")
    if isinstance(device_id, Rejection):
        return device_id
    if isinstance(model, Rejection):
        return model
    if isinstance(version, Rejection):
        return version
    if device_id == profile.router_device_id:
        return Rejection("failed", "rejected", "router_is_not_a_peer")
    expected = {
        "dog": profile.dog_device_id,
        "drone": profile.drone_device_id,
        "pi": profile.pi_device_id,
    }[str(role)]
    if device_id != expected:
        return Rejection("failed", "rejected", "role_device_mismatch")
    commands = _strings(payload.get("supported_commands"), "supported_commands", limit=64)
    cameras = _strings(
        payload.get("camera_ids"),
        "camera_ids",
        limit=2,
        allowed=CAMERAS,
    )
    frames = _strings(payload.get("pose_frames"), "pose_frames", limit=16)
    if isinstance(commands, Rejection):
        return commands
    if isinstance(cameras, Rejection):
        return cameras
    if isinstance(frames, Rejection):
        return frames
    reported = _reported(payload.get("features"))
    if isinstance(reported, Rejection):
        return reported
    validated = payload.get("validated")
    if not isinstance(validated, bool):
        return Rejection("failed", "invalid_input", "validated must be a boolean")
    evidence = payload.get("acceptance_evidence_ref")
    if evidence is not None and not isinstance(evidence, str):
        return Rejection("failed", "invalid_input", "acceptance evidence must be a string or null")
    if evidence == "":
        evidence = None
    if simulated is False and isinstance(evidence, str) and "synthetic-only" in evidence:
        return Rejection("failed", "contract_mismatch", "synthetic_evidence_marked_live")
    missing_commands = _missing_commands(str(role), reported, commands)
    if missing_commands:
        return Rejection(
            "failed",
            "forbidden_command",
            "missing_command:" + ",".join(missing_commands),
        )
    armed, reasons = _arm(str(role), reported, validated, evidence, cameras)
    return (
        str(role),
        str(device_id),
        str(model),
        str(version),
        commands,
        evidence if isinstance(evidence, str) else None,
        validated,
        reported,
        armed,
        reasons,
    )


def _reported(value: object) -> Mapping[str, bool] | Rejection:
    parsed = _as_object(value, "features")
    if isinstance(parsed, Rejection):
        return parsed
    extra = [key for key in parsed if key not in FLAGS]
    if extra:
        return Rejection("failed", "invalid_input", "unknown feature field")
    missing = [flag for flag in FLAGS if flag not in parsed]
    if missing:
        return Rejection("failed", "invalid_input", "feature map is incomplete")
    flags: dict[str, bool] = {}
    for flag in FLAGS:
        item = parsed[flag]
        if not isinstance(item, bool):
            return Rejection("failed", "invalid_input", f"{flag} must be a boolean")
        flags[flag] = item
    return flags


def _missing_commands(
    role: str,
    reported: Mapping[str, bool],
    commands: tuple[str, ...],
) -> tuple[str, ...]:
    owned = set(commands)
    missing: list[str] = []
    for (owner, flag), needed in REQUIRED_COMMANDS.items():
        if owner != role or reported.get(flag) is not True:
            continue
        for command in needed:
            if command not in owned:
                missing.append(command)
    return tuple(sorted(set(missing)))


def _arm(
    role: str,
    reported: Mapping[str, bool],
    validated: bool,
    evidence: str | None,
    cameras: tuple[str, ...],
) -> tuple[Mapping[str, bool], tuple[str, ...]]:
    reasons: list[str] = []
    eligible = validated is True and isinstance(evidence, str) and bool(evidence)
    if validated is not True:
        reasons.append("validated_false")
    if not isinstance(evidence, str) or not evidence:
        reasons.append("acceptance_evidence_missing")
    owned = OWNED[role]
    armed = {flag: False for flag in FLAGS}
    for flag in FLAGS:
        if reported.get(flag) is not True:
            continue
        if flag not in owned:
            reasons.append(f"not_owned_by_role:{flag}")
            continue
        if not eligible:
            continue
        if flag == "downward_video" and "downward" not in cameras:
            reasons.append("downward_camera_id_missing")
            continue
        armed[flag] = True
    return armed, tuple(reasons)


def _profile_block(
    profile: ConnectedProfile | None,
    snapshot: SessionSnapshot,
    view: Mapping[str, PeerRecord],
    search: str,
    rssi: bool,
) -> Rejection | None:
    if profile is None:
        return None
    if profile.profile_transport not in {None, snapshot.dog_transport, profile.dog_transport}:
        return Rejection("blocked", "contract_mismatch", "transport_profile_conflict")
    if profile.profile_transport not in {None, profile.dog_transport}:
        return Rejection("blocked", "contract_mismatch", "transport_profile_conflict")
    if "drone" not in view:
        return Rejection("blocked", "unavailable", "drone_report_missing")
    if "dog" not in view:
        return Rejection("blocked", "unavailable", "dog_report_missing")
    if profile.pi_required and "pi" not in view:
        return Rejection("blocked", "unavailable", "pi_report_missing")
    if search == "blocked":
        return Rejection("blocked", "rejected", "controlled_motion_reported_false")
    if profile.pi_required and rssi is not True:
        return Rejection("blocked", "rejected", "rssi_receiver_reported_false")
    return None


def _view(
    records: Mapping[str, PeerRecord],
    mission: str,
    epoch: int,
) -> dict[str, PeerRecord]:
    view: dict[str, PeerRecord] = {}
    for record in records.values():
        if record.mission_id == mission and record.epoch == epoch:
            view[record.role] = record
    return view


def _combined(view: Mapping[str, PeerRecord]) -> dict[str, bool]:
    return {
        "controlled_motion": _flag(view.get("drone"), "controlled_motion"),
        "downward_video": _flag(view.get("drone"), "downward_video"),
        "rssi_receiver": _flag(view.get("pi"), "rssi_receiver"),
        "lidar": _flag(view.get("dog"), "lidar"),
        "slam": _flag(view.get("dog"), "slam"),
        "target_range": _flag(view.get("dog"), "target_range"),
    }


def _flag(record: PeerRecord | None, name: str) -> bool:
    if record is None:
        return False
    return record.armed.get(name) is True


def _router(profile: ConnectedProfile | None) -> dict[str, object]:
    if profile is None:
        return {"device_id": "", "networking": "", "peer": False}
    return {
        "device_id": profile.router_device_id,
        "networking": profile.router_networking,
        "peer": False,
    }


def _public_peer(record: PeerRecord) -> dict[str, object]:
    return {
        "device_id": record.device_id,
        "role": record.role,
        "model": record.model,
        "software_version": record.software_version,
        "supported_commands": record.supported_commands,
        "acceptance_evidence_ref": record.acceptance_evidence_ref,
        "validated": record.validated,
        "message_id": record.message_id,
        "mission_id": record.mission_id,
        "epoch": record.epoch,
        "simulated": record.simulated,
        "features": dict(record.armed),
        "reported_features": dict(record.reported),
        "disarm_reasons": record.disarm_reasons,
    }


def _event(record: PeerRecord, ticket: Ticket | None) -> GroundEvent:
    return GroundEvent(
        "state_changed",
        ticket,
        freeze_map(
            {
                "message_id": record.message_id,
                "mission_id": record.mission_id,
                "epoch": record.epoch,
                "seq": record.seq,
                "role": record.role,
                "device_id": record.device_id,
                "model": record.model,
                "software_version": record.software_version,
                "supported_commands": record.supported_commands,
                "acceptance_evidence_ref": record.acceptance_evidence_ref,
                "simulated": record.simulated,
                "features": dict(record.armed),
                "reported_features": dict(record.reported),
            }
        ),
    )


def _config(settings: GroundSettings, name: str) -> Mapping[str, object] | Rejection:
    value = settings.adapter_configs.get(name)
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        return Rejection("failed", "invalid_input", f"{name} profile is required")
    return value


def _text(mapping: Mapping[str, object], key: str) -> str | Rejection:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        return Rejection("failed", "invalid_input", f"{key} is required")
    return value


def _identifier(value: object, label: str) -> str | Rejection:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        return Rejection("failed", "invalid_input", f"{label} is required")
    return value


def _whole(value: object, label: str) -> int | Rejection:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return Rejection("failed", "invalid_input", f"{label} must be a non-negative integer")
    return value


def _nullable(value: object, label: str) -> str | None | Rejection:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return Rejection("failed", "invalid_input", f"{label} must be a string or null")
    return value


def _strings(
    value: object,
    label: str,
    *,
    limit: int,
    allowed: frozenset[str] | None = None,
) -> tuple[str, ...] | Rejection:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return Rejection("failed", "invalid_input", f"{label} must be a list")
    if len(value) > limit:
        return Rejection("failed", "invalid_input", f"{label} is too long")
    found: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 160:
            return Rejection("failed", "invalid_input", f"{label} entries must be strings")
        if allowed is not None and item not in allowed:
            return Rejection("failed", "invalid_input", f"{label} contains an unknown value")
        if item in found:
            return Rejection("failed", "invalid_input", f"duplicate {label}")
        found.append(item)
    return tuple(found)


def _as_object(value: object, label: str) -> dict[str, object] | Rejection:
    if not isinstance(value, dict):
        return Rejection("failed", "invalid_input", f"{label} must be an object")
    out: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return Rejection("failed", "invalid_input", f"{label} keys must be strings")
        out[key] = item
    return out


def _secret(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in SECRET_KEYS:
                return True
            if _secret(item):
                return True
        return False
    if isinstance(value, list):
        return any(_secret(item) for item in value)
    return False


def _read_object(path: Path) -> dict[str, object]:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    parsed = _as_object(raw, path.name)
    if isinstance(parsed, Rejection):
        raise fault("invalid_input", parsed.detail)
    return parsed


def _cameras_from(payload: Mapping[str, object]) -> tuple[str, ...]:
    return _sequence_strings(payload.get("camera_ids"))


def _frames_from(payload: Mapping[str, object]) -> tuple[str, ...]:
    return _sequence_strings(payload.get("pose_frames"))


def _sequence_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return ()
    return tuple(item for item in value if isinstance(item, str))
