"""Turn a presence intent into the proposal and command messages we ask Ground to take.

The dog socket is never opened. ``dog.command`` / ``drone.command`` here are the
shapes Ground would forward. Ground's published schema rejects the new actions.
"""

from __future__ import annotations

from typing import Mapping

from patrol.trigger.presence import Intent

_SCHEMA_PROPOSAL_FIELDS = (
    "proposal_id",
    "target_component",
    "action",
    "direction_hint",
    "track_id",
    "evidence_frame_id",
    "candidate_id",
    "beacon_epoch",
    "reason",
)


def proposal_message(
    intent: Intent,
    *,
    mission_id: str,
    epoch: int,
    seq: int,
    track_id: str | None,
    evidence_frame_id: str | None,
    correlation_id: str | None,
    sent_at: str,
    expires_at: str,
    simulated: bool = True,
) -> dict[str, object]:
    """``motion.proposal`` from vision to ground, including the fields HAC-58 names."""
    if intent.action == "halt":
        raise ValueError("halt is a dog.command, not a motion.proposal")
    payload: dict[str, object] = {
        "proposal_id": f"proposal-{intent.action}-{seq}",
        "target_component": intent.target,
        "action": intent.action,
        "direction_hint": "unknown" if intent.action in {"stop", "return_home", "land_on_dog"} else "center",
        "track_id": track_id,
        "evidence_frame_id": evidence_frame_id,
        "candidate_id": None,
        "beacon_epoch": None,
        "reason": _reason(intent),
    }
    if intent.warning_id is not None:
        payload["warning_id"] = intent.warning_id
    if intent.text is not None:
        payload["text"] = intent.text
    if intent.standoff_m is not None:
        payload["standoff_m"] = intent.standoff_m
    return _envelope(
        message_id=f"msg-proposal-{intent.action}-{seq}",
        mission_id=mission_id,
        epoch=epoch,
        seq=seq,
        sent_at=sent_at,
        source="vision",
        destination="ground",
        kind="motion.proposal",
        correlation_id=correlation_id,
        expires_at=expires_at,
        simulated=simulated,
        payload=payload,
    )


def command_message(
    intent: Intent,
    *,
    mission_id: str,
    epoch: int,
    seq: int,
    track_id: str | None,
    evidence_frame_id: str | None,
    correlation_id: str | None,
    sent_at: str,
    expires_at: str,
    simulated: bool = True,
) -> dict[str, object]:
    """Command shape Ground would forward. Source is ground; we do not send it to a robot."""
    proposal_id = None if intent.action == "halt" else f"proposal-{intent.action}-{seq}"
    if intent.target == "drone" or intent.action == "land_on_dog":
        payload: dict[str, object] = {
            "command_id": f"cmd-{intent.action}-{seq}",
            "proposal_id": proposal_id,
            "action": intent.action,
            "primitive_id": "land-on-dog-v1" if intent.action == "land_on_dog" else "verified-floor-land-v1",
            "lease_ms": 500,
            "requested_height_m": None,
            "height_reference": "unknown",
            "evidence_frame_id": evidence_frame_id,
            "track_id": track_id,
            "camera_id": "downward",
            "beacon_epoch": None,
            "reason": _reason(intent),
        }
        kind = "drone.command"
        destination = "drone"
    else:
        payload = {
            "command_id": f"cmd-{intent.action}-{seq}",
            "proposal_id": proposal_id,
            "action": intent.action,
            "lease_ms": 500,
            "motion": None,
            "track_id": track_id,
            "beacon_epoch": None,
            "safety_snapshot_id": "safety-presence-001",
            "reason": _reason(intent),
        }
        kind = "dog.command"
        destination = "dog"
    return _envelope(
        message_id=f"msg-cmd-{intent.action}-{seq}",
        mission_id=mission_id,
        epoch=epoch,
        seq=seq,
        sent_at=sent_at,
        source="ground",
        destination=destination,
        kind=kind,
        correlation_id=correlation_id,
        expires_at=expires_at,
        simulated=simulated,
        payload=payload,
    )


def schema_shaped_proposal(message: Mapping[str, object]) -> dict[str, object]:
    """Drop warning_id, text, and standoff_m so the action enum is what the schema sees."""
    payload = message["payload"]
    if not isinstance(payload, Mapping):
        raise ValueError("payload")
    shaped = {key: payload[key] for key in _SCHEMA_PROPOSAL_FIELDS}
    copy = dict(message)
    copy["payload"] = shaped
    return copy


def _reason(intent: Intent) -> str:
    if intent.action == "play_warning":
        return "Say the go-away warning."
    if intent.action == "follow":
        return "Follow the tracked person at the published standoff."
    if intent.action == "stop":
        return "Stop in place. This is not an operator halt."
    if intent.action == "return_home":
        return "Return to the start mark."
    if intent.action == "land_on_dog":
        return "Land on the dog."
    if intent.action == "halt":
        return "Operator halt. Recipient safety priority applies."
    return intent.action


def _envelope(
    *,
    message_id: str,
    mission_id: str,
    epoch: int,
    seq: int,
    sent_at: str,
    source: str,
    destination: str,
    kind: str,
    correlation_id: str | None,
    expires_at: str | None,
    simulated: bool,
    payload: dict[str, object],
) -> dict[str, object]:
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
        "correlation_id": correlation_id,
        "expires_at": expires_at,
        "simulated": simulated,
        "payload": payload,
    }
