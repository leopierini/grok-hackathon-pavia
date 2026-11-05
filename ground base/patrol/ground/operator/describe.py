"""Human-readable journal rows. Missing numbers stay null."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from patrol.ground.extensions.g29.classify import category_for

Json = dict[str, Any]


def describe_message(message: Mapping[str, Any]) -> str:
    kind = str(message.get("kind") or "message")
    source = str(message.get("source") or "unknown")
    payload = message.get("payload")
    body = _map(payload)
    if kind == "capabilities.report":
        return f"{source} reported capabilities for {body.get('model') or body.get('role') or source}."
    if kind == "drone.observation":
        flight = body.get("flight_state")
        height = body.get("height_estimate_m")
        reference = body.get("height_reference")
        return f"Drone observation: flight {flight}, height { _shown(height) } m ({reference})."
    if kind == "dog.observation":
        return (
            "Dog observation: "
            f"standing {body.get('standing')}, stationary {body.get('stationary')}, "
            f"transport {body.get('transport')}."
        )
    if kind == "rssi.window":
        return (
            f"Pi RSSI window quality {body.get('quality')}, "
            f"beacon epoch {body.get('beacon_epoch')}, median {_shown(body.get('median_rssi_dbm'))} dBm."
        )
    if kind == "navigation.candidates":
        rows = body.get("candidates")
        count = len(rows) if isinstance(rows, list) else 0
        blocked = body.get("blocked")
        return f"Dog planner published {count} candidates. Blocked is {blocked}."
    if kind == "vision.request":
        return f"Vision request {body.get('request_id')} for frame {body.get('frame_id') or 'unknown'}."
    if kind == "vision.decision":
        return (
            f"Grok decision {body.get('target_state')} on {body.get('frame_id')}. "
            "This is not motor authority."
        )
    if kind == "motion.proposal":
        return f"Proposal {body.get('action')} for {body.get('target_component')}. Ground must still approve it."
    if kind in {"drone.command", "dog.command"}:
        return (
            f"Ground command {body.get('command_id')} action {body.get('action')} "
            f"lease {_shown(body.get('lease_ms'))} ms."
        )
    if kind == "command.ack":
        return (
            f"ACK {body.get('state')} for {body.get('command_id')} "
            f"({body.get('reason_code') or 'no reason code'}). "
            "Accepted is not completion."
        )
    if kind == "proximity.evidence":
        return "Proximity evidence received. Dog range and drone offset stay separate."
    if kind == "mission.event":
        return f"Mission event {body.get('event') or kind}."
    return f"{source} {kind}."


def correlation_fields(message: Mapping[str, Any]) -> Json:
    payload = message.get("payload")
    body = _map(payload)
    frame = _map(body.get("frame"))
    beacon = _map(body.get("beacon"))
    track = body.get("track_id")
    if track is None and isinstance(body.get("detections"), list) and body["detections"]:
        first = body["detections"][0]
        if isinstance(first, Mapping):
            track = first.get("track_id")
    return {
        "message_id": message.get("message_id"),
        "correlation_id": message.get("correlation_id"),
        "mission_id": message.get("mission_id"),
        "epoch": message.get("epoch"),
        "seq": message.get("seq"),
        "source": message.get("source"),
        "destination": message.get("destination"),
        "kind": message.get("kind"),
        "sent_at": message.get("sent_at"),
        "expires_at": message.get("expires_at"),
        "simulated": message.get("simulated"),
        "command_id": body.get("command_id"),
        "request_id": body.get("request_id"),
        "frame_id": body.get("frame_id") or frame.get("frame_id"),
        "track_id": track,
        "beacon_epoch": body.get("beacon_epoch") if body.get("beacon_epoch") is not None else beacon.get("beacon_epoch"),
        "camera_epoch": body.get("camera_epoch") or frame.get("camera_epoch"),
        "map_epoch": body.get("map_epoch"),
    }


def journal_row(message: Mapping[str, Any]) -> Json:
    kind = str(message.get("kind") or "")
    payload = message.get("payload")
    body = _map(payload)
    category, event_name = category_for(kind, body)
    if not category:
        category = "observation"
    state = str(body.get("state") or "")
    severity = "info"
    if state == "rejected" or "fault" in kind or event_name == "landing_unverified":
        severity = "fault"
    elif state in {"unknown", "running"} or body.get("quality") in {"noisy", "stale", "unavailable"}:
        severity = "warn"
    fields = correlation_fields(message)
    return {
        **fields,
        "category": category,
        "event_name": event_name,
        "severity": severity,
        "summary": describe_message(message),
        "writer_state": "enqueued",
        "published": False,
        "ledger": "operator_feed",
        "payload": dict(body),
    }


def phase_row(entry: Mapping[str, Any]) -> Json:
    return {
        "kind": "phase",
        "source": "ground",
        "category": "session",
        "severity": "fault" if entry.get("phase") in {"FAULT", "ABORTED"} else "info",
        "summary": f"Phase {entry.get('phase')}: {entry.get('reason')}",
        "writer_state": "enqueued",
        "published": False,
        "ledger": "operator_feed",
        "sent_at": entry.get("at"),
        "payload": dict(entry),
    }


def _shown(value: object) -> str:
    if value is None:
        return "unknown"
    return str(value)


def _map(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
