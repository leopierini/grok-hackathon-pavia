"""Project a mission into the operator snapshot. Missing numbers stay null."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from patrol.contract import CONTRACT_VERSION
from patrol.ground.extensions.g29.classify import LOG_SCHEMA, LOGS_STATUS
from patrol.ground.kernel.catalog import SCHEMA_VERSION
from patrol.ground.operator.config import apply_timing, explain_unset, redacted_config
from patrol.ground.operator.describe import describe_message

Json = dict[str, Any]
_V2 = "2.0-draft"


def command_views(commands: Sequence[object], messages: Sequence[object]) -> list[Json]:
    acks = [item for item in messages if isinstance(item, Mapping) and item.get("kind") == "command.ack"]
    views: list[Json] = []
    for command in commands:
        if not isinstance(command, Mapping):
            continue
        payload = _map(command.get("payload"))
        command_id = payload.get("command_id")
        matched = []
        for item in acks:
            body = _map(item.get("payload"))
            if body.get("command_id") == command_id:
                matched.append((item, body))
        states = [str(body.get("state")) for _, body in matched]
        if "rejected" in states:
            lifecycle = "rejected"
        elif "completed" in states:
            lifecycle = "completed"
        elif "running" in states:
            lifecycle = "running"
        elif "accepted" in states:
            lifecycle = "accepted"
        else:
            lifecycle = "issued"
        if "accepted" in states and "completed" not in states and "rejected" not in states:
            note = "Accepted by the device. Execution is not complete."
        elif "rejected" in states:
            note = "The device rejected the command. It is not retried from this console."
        elif "completed" in states:
            note = "A completed acknowledgement is recorded. Landing is a separate verdict."
        else:
            note = "No acknowledgement has been applied yet."
        views.append(
            {
                "command_id": command_id,
                "message_id": command.get("message_id"),
                "correlation_id": command.get("correlation_id"),
                "destination": command.get("destination"),
                "action": payload.get("action"),
                "lease_ms": payload.get("lease_ms"),
                "expires_at": command.get("expires_at"),
                "simulated": command.get("simulated"),
                "lifecycle": lifecycle,
                "execution_note": note,
                "acks": [
                    {
                        "state": body.get("state"),
                        "reason_code": body.get("reason_code"),
                        "verified": body.get("verified"),
                        "observed_motion": body.get("observed_motion"),
                        "sent_at": item.get("sent_at"),
                        "message_id": item.get("message_id"),
                    }
                    for item, body in matched
                ],
            }
        )
    return views


def evidence_views(
    messages: Sequence[object],
    trace: Sequence[object],
    *,
    observed_at: str | None,
    evidence_age_ms: int | None,
) -> list[Json]:
    views: list[Json] = []
    seen: set[str] = set()
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        payload = _map(message.get("payload"))
        frame = _map(payload.get("frame"))
        if not isinstance(frame.get("frame_id"), str):
            continue
        frame_id = frame["frame_id"]
        if frame_id in seen:
            continue
        seen.add(frame_id)
        age = _age_ms(frame.get("captured_at"), observed_at)
        stale: bool | None
        if age is None or evidence_age_ms is None:
            stale = None
            stale_reason = "age is unknown; it is not treated as fresh or as zero"
        elif age > evidence_age_ms:
            stale = True
            stale_reason = "display age is older than the configured evidence budget"
        else:
            stale = False
            stale_reason = "display age is inside the configured evidence budget"
        views.append(
            {
                "source": message.get("source"),
                "kind": message.get("kind"),
                "camera_id": frame.get("camera_id"),
                "frame_id": frame_id,
                "camera_epoch": frame.get("camera_epoch"),
                "captured_at": frame.get("captured_at"),
                "age_ms": age,
                "stale": stale,
                "stale_reason": stale_reason,
                "calibration_id": frame.get("camera_to_body_calibration_id"),
                "sha256": frame.get("sha256"),
                "image_ref": frame.get("image_ref"),
                "simulated": frame.get("simulated"),
                "provenance": "simulated" if frame.get("simulated") is True else "unknown",
                "media": "snapshot",
                "validation_status": _validation(frame_id, trace),
                "width_px": frame.get("width_px"),
                "height_px": frame.get("height_px"),
            }
        )
    return views


def rssi_points(messages: Sequence[object]) -> list[Json]:
    points: list[Json] = []
    for message in messages:
        if not isinstance(message, Mapping) or message.get("kind") != "rssi.window":
            continue
        payload = _map(message.get("payload"))
        samples = payload.get("samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, Mapping):
                continue
            value = sample.get("rssi_dbm")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            points.append(
                {
                    "at": sample.get("captured_at"),
                    "rssi_dbm": float(value),
                    "message_id": message.get("message_id"),
                    "quality": payload.get("quality"),
                }
            )
    return points


def numeric_metrics(metrics: object) -> list[Json]:
    found: list[Json] = []

    def walk(node: object, prefix: str) -> None:
        if not isinstance(node, Mapping):
            return
        seconds = node.get("seconds")
        if isinstance(seconds, (int, float)) and not isinstance(seconds, bool):
            found.append({"name": prefix or "seconds", "value": float(seconds)})
            return
        for key, value in node.items():
            if key in {"reason", "status", "log_schema"}:
                continue
            walk(value, f"{prefix}.{key}" if prefix else str(key))

    walk(metrics, "")
    return found


def readiness_checks(state: Mapping[str, Any]) -> list[Json]:
    config = _map(state.get("config"))
    modes = _map(config.get("modes"))
    transport = str(config.get("dog_transport") or "unknown")
    checks = [
        _check(
            "dog-link",
            "Dog control link",
            "pass" if transport in {"ethernet", "wifi"} else "unknown",
            False,
            f"{transport} profile selected. Ethernet and Wi-Fi do not hand over automatically.",
        ),
        _check(
            "tello-link",
            "Tello control and video",
            "unknown" if modes.get("drone") == "fake" else "fail",
            modes.get("drone") == "real",
            "Simulated drone link. A real Tello connection is not open.",
        ),
        _check(
            "vision-net",
            "Internet for real vision",
            "unknown",
            False,
            "Fake Grok does not use the network. Real vision would need a verified uplink.",
        ),
        _check(
            "pi-path",
            "Pi telemetry path",
            "pass" if config.get("pi_data_path") else "unknown",
            False,
            f"Configured path: {config.get('pi_data_path') or 'unset'}. The broken router is not the Pi.",
        ),
        _check(
            "directional",
            "Directional drone control",
            "unknown",
            False,
            "Unverified. No acceptance evidence enables directional motion.",
        ),
        _check(
            "flight-profile",
            "4 m flight profile",
            "pass",
            False,
            "Proposed only. Enabled remains false.",
        ),
        _check(
            "thresholds",
            "Venue proximity thresholds",
            "unknown"
            if config.get("dog_range_max_m") is None or config.get("drone_horizontal_max_m") is None
            else "pass",
            False,
            "Unset thresholds stay unknown. They are not converted to zero.",
        ),
    ]
    if state.get("real_modes") is True or state.get("mode") == "live":
        checks.append(
            _check("live", "Live transports", "fail", True, "Live operation is refused and is not simulated instead.")
        )
    return checks


def build_snapshot(state: Mapping[str, Any]) -> Json:
    messages = [item for item in state.get("messages", []) if isinstance(item, Mapping)]
    trace = [item for item in state.get("trace", []) if isinstance(item, Mapping)]
    commands = [item for item in state.get("commands", []) if isinstance(item, Mapping)]
    config = _map(state.get("config"))
    observed_at = state.get("observed_at") if isinstance(state.get("observed_at"), str) else None
    evidence = evidence_views(
        messages,
        trace,
        observed_at=observed_at,
        evidence_age_ms=config.get("evidence_age_ms") if isinstance(config.get("evidence_age_ms"), int) else None,
    )
    command_rows = command_views(commands, list(messages))
    active = next((row for row in reversed(command_rows) if row["lifecycle"] in {"issued", "accepted", "running"}), None)
    return {
        "transport": state.get("mode"),
        "connection": state.get("connection") or "connected",
        "updated_at": state.get("updated_at"),
        "cursor": state.get("cursor") or 0,
        "session_epoch": state.get("session_epoch"),
        "kernel": {
            "contract_v1": CONTRACT_VERSION,
            "protocol_v2": _V2,
            "kernel_schema": SCHEMA_VERSION,
            "log_schema": LOG_SCHEMA,
            "log_schema_status": LOGS_STATUS,
            "providers": state.get("providers") or [],
            "missing_providers": state.get("missing_providers") or [],
        },
        "mission": {
            "run_id": state.get("run_id"),
            "mission_id": state.get("mission_id"),
            "mission_epoch": state.get("mission_epoch"),
            "phase": state.get("phase") or "IDLE",
            "phase_history": state.get("phase_history") or [],
            "foundation_phase": state.get("foundation_phase"),
            "armed": state.get("armed") is True,
            "worker": state.get("worker") or "idle",
            "scenario": state.get("scenario"),
            "seed": state.get("seed"),
            "dog_transport": config.get("dog_transport"),
            "goal_reached": state.get("goal_reached") is True,
            "landing_verified": state.get("landing_verified") is True,
            "recovery_required": state.get("recovery_required") is True,
            "outcome": state.get("outcome"),
            "reason": state.get("reason") or "",
            "halt_latched": state.get("halt_latched") is True,
            "halt_accepted": state.get("halt_accepted") is True,
            "halt_delivered": state.get("halt_delivered"),
            "supervised": state.get("supervised") is True,
            "waiting_for": "grok" if state.get("waiting_for_model") is True else None,
            "active_operation": state.get("active_operation"),
            "active_command_id": None if active is None else active.get("command_id"),
            "live_call_count": state.get("live_call_count") if isinstance(state.get("live_call_count"), int) else 0,
            "observed_at": observed_at,
        },
        "devices": _devices(messages, config, str(state.get("mode") or "simulation")),
        "readiness": readiness_checks(state),
        "links": _links(config),
        "dog_demo": state.get("dog_demo")
        or {
            "profile": "ethernet-now",
            "dog": "192.168.123.161",
            "laptop": "192.168.123.222",
            "drone": "simulated script",
            "pi": "not mounted; later this laptop Wi-Fi joins only the ground AP",
            "active": False,
            "last": None,
        },
        "patrol": state.get("patrol")
        or {
            "phase": "idle",
            "detail": "Patrol is idle.",
            "situation": "awaiting_ai",
            "summary": "No AI verdict has been received.",
            "land_called": False,
            "frames": [],
            "calls": [],
        },
        "capabilities": {
            "dog": _capability(messages, "dog"),
            "drone": _capability(messages, "drone"),
            "pi": _capability(messages, "pi"),
            "admission": _trace_brief(trace, 12),
        },
        "commands": command_rows,
        "chain": _chain(messages, trace, command_rows),
        "evidence": evidence,
        "vision": _vision(messages, trace, state),
        "navigation": _navigation(messages, trace),
        "safety": {
            "halt_latched": state.get("halt_latched") is True,
            "halt_accepted": state.get("halt_accepted") is True,
            "halt_delivered": state.get("halt_delivered"),
            "recovery_required": state.get("recovery_required") is True,
            "reason": state.get("reason") or "",
            "late_model": state.get("notes") or [],
            "step_control": state.get("step_control"),
        },
        "activity": state.get("activity") or [],
        "journal_count": state.get("journal_count") or 0,
        "provider_journal": state.get("provider_journal") or [],
        "writer_state": state.get("writer_state") or "idle",
        "metrics": state.get("metrics"),
        "metric_chart": numeric_metrics(state.get("metrics")),
        "config": redacted_config(config) if config else {},
        "config_apply": apply_timing(),
        "unset": explain_unset(config) if config else [],
        "actions": state.get("actions") or {},
        "next_action": state.get("next_action") or "",
        "live_blockers": state.get("live_blockers") or [],
        "scenarios": state.get("scenarios") or [],
    }


def _devices(messages: list[Mapping[str, Any]], config: Mapping[str, Any], mode: str) -> Json:
    modes = _map(config.get("modes"))
    profiles = _map(config.get("connection_profiles"))
    live = mode == "live" or any(value == "real" for value in modes.values())
    provenance = "unavailable" if live else "replay" if mode == "replay" else "simulated"
    connection = "refused" if live else "replay" if mode == "replay" else "simulated"
    dog = _latest(messages, "dog.observation")
    drone = _latest(messages, "drone.observation")
    return {
        "dog": _device(
            "Go2 PRO",
            "dog",
            modes.get("dog") if not live else "real",
            provenance,
            connection,
            profiles.get("dog"),
            dog,
            "Dog adapter is owned by Ground. The browser does not open it.",
        ),
        "drone": _device(
            "Tello EDU",
            "drone",
            modes.get("drone") if not live else "real",
            provenance,
            connection,
            profiles.get("drone"),
            drone,
            "Tello stays behind the existing drone adapter. Directional control is unverified.",
        ),
        "pi": _device(
            "Raspberry Pi on the dog",
            "pi",
            "fake" if not live else "real",
            provenance,
            connection,
            profiles.get("pi"),
            _latest(messages, "rssi.window") or _latest(messages, "heartbeat"),
            "The Pi measures the drone beacon. It is not the broken router.",
        ),
        "vision": _device(
            "xAI Grok",
            "vision",
            modes.get("grok") if not live else "real",
            provenance,
            connection,
            profiles.get("vision"),
            _latest(messages, "vision.decision"),
            "Model text is not a motor command.",
        ),
        "router": {
            "name": "Back-enclosure router",
            "role": "router",
            "mode": "unavailable",
            "provenance": "unavailable",
            "connection": "unavailable",
            "profile": None,
            "detail": "The broken router is not the Raspberry Pi and is not a data path.",
            "telemetry": {},
            "error": "unavailable",
        },
    }


def _device(
    name: str,
    role: str,
    mode: object,
    provenance: str,
    connection: str,
    profile: object,
    message: Mapping[str, Any] | None,
    detail: str,
) -> Json:
    payload = _map(None if message is None else message.get("payload"))
    telemetry = {
        key: payload.get(key)
        for key in (
            "flight_state",
            "height_estimate_m",
            "height_reference",
            "battery_percent",
            "standing",
            "stationary",
            "transport",
            "navigation_mode",
            "quality",
            "median_rssi_dbm",
            "model_id",
            "target_state",
        )
        if key in payload
    }
    return {
        "name": name,
        "role": role,
        "mode": mode,
        "provenance": provenance,
        "connection": connection,
        "profile": profile,
        "last_observation_at": None if message is None else message.get("sent_at"),
        "detail": detail,
        "telemetry": telemetry,
        "error": None if connection != "refused" else "live connection refused",
    }


def _capability(messages: list[Mapping[str, Any]], role: str) -> Json | None:
    for message in reversed(messages):
        if message.get("kind") != "capabilities.report":
            continue
        payload = _map(message.get("payload"))
        if payload.get("role") == role or message.get("source") == role:
            return dict(payload)
    return None


def _links(config: Mapping[str, Any]) -> list[Json]:
    transport = config.get("dog_transport")
    return [
        {
            "name": "Dog control",
            "medium": transport,
            "detail": (
                "Now: this laptop's Ethernet adapter at 192.168.123.222 talks to the dog at "
                "192.168.123.161. Later: a Pi 4 holds that cable, and this laptop's one Wi-Fi "
                "radio joins only the ground network."
            ),
        },
        {
            "name": "Tello control and video",
            "medium": "wifi",
            "detail": "The drone access point is not the dog tether and is not the Pi path.",
        },
        {
            "name": "Internet for real vision",
            "medium": "uplink",
            "detail": "Required only for a real Grok call. Simulation does not open it.",
        },
        {
            "name": "Pi telemetry",
            "medium": config.get("pi_data_path"),
            "detail": "Must stay up beside dog control and Tello video. The router is not this path.",
        },
    ]


def _vision(messages: list[Mapping[str, Any]], trace: list[Mapping[str, Any]], state: Mapping[str, Any]) -> Json:
    request = _latest(messages, "vision.request")
    decision = _latest(messages, "vision.decision")
    proposal = _latest(messages, "motion.proposal")
    request_body = _map(None if request is None else request.get("payload"))
    decision_body = _map(None if decision is None else decision.get("payload"))
    proposal_body = None if proposal is None else proposal.get("payload")
    return {
        "request": None if request is None else {"message_id": request.get("message_id"), **request_body},
        "decision": None if decision is None else {"message_id": decision.get("message_id"), **decision_body},
        "proposal": proposal_body,
        "model_id": decision_body.get("model_id") or request_body.get("model_id"),
        "prompt_version": decision_body.get("prompt_version") or request_body.get("prompt_version"),
        "waiting": state.get("waiting_for_model") is True,
        "provider_result": _trace_brief(trace, 16),
        "latency_note": "Latency is reported only when task 31 measured it. A missing value stays unknown.",
    }


def _navigation(messages: list[Mapping[str, Any]], trace: list[Mapping[str, Any]]) -> Json:
    observation = _latest(messages, "dog.observation")
    candidates = _latest(messages, "navigation.candidates")
    drone = _latest(messages, "drone.observation")
    windows = [item for item in messages if item.get("kind") == "rssi.window"]
    pose = None
    nav_mode = None
    if observation is not None:
        payload = _map(observation.get("payload"))
        pose = payload.get("pose")
        nav_mode = payload.get("navigation_mode")
    beacon = None
    if drone is not None:
        beacon = _map(drone.get("payload")).get("beacon")
    candidate_body = _map(None if candidates is None else candidates.get("payload"))
    return {
        "navigation_mode": nav_mode,
        "pose": pose,
        "map_id": candidate_body.get("map_id"),
        "map_epoch": candidate_body.get("map_epoch"),
        "map_renderable": False,
        "map_reason": "Map identity can be present. No occupancy grid or map image is published, so no map is drawn.",
        "candidates": candidate_body.get("candidates") or [],
        "blocked": candidate_body.get("blocked"),
        "candidate_reason": candidate_body.get("reason"),
        "beacon": beacon,
        "rssi_windows": [item.get("payload") for item in windows],
        "rssi_points": rssi_points(list(messages)),
        "selection": _trace_brief(trace, 22),
        "navigation_result": _trace_brief(trace, 20),
        "dog_motion_note": "The dog stays stopped while a drone command is running.",
    }


def _chain(messages: list[Mapping[str, Any]], trace: list[Mapping[str, Any]], commands: list[Json]) -> list[Json]:
    kinds = {str(item.get("kind")) for item in messages}
    ack_states = {str(row.get("lifecycle")) for row in commands}
    steps = [
        ("observation", "Observation", any(kind.endswith("observation") for kind in kinds)),
        ("vision_request", "Vision request", "vision.request" in kinds),
        ("decision", "Decision or proposal", "vision.decision" in kinds or "motion.proposal" in kinds),
        ("approval", "Ground approval", any(row.get("task") == 17 and row.get("status") == "ok" for row in trace)),
        ("command", "Device command", any(kind.endswith("command") for kind in kinds)),
        ("accepted", "Accepted ACK", "accepted" in ack_states or "running" in ack_states or "completed" in ack_states),
        ("running", "Running ACK", "running" in ack_states or "completed" in ack_states),
        ("final", "Final result", "completed" in ack_states or "rejected" in ack_states),
    ]
    return [
        {
            "id": key,
            "label": label,
            "state": "present" if present else "missing",
            "detail": "Recorded in this run." if present else "Not recorded. Missing is not success.",
        }
        for key, label, present in steps
    ]


def _latest(messages: list[Mapping[str, Any]], kind: str) -> Mapping[str, Any] | None:
    for message in reversed(messages):
        if message.get("kind") == kind:
            return message
    return None


def _trace_brief(trace: list[Mapping[str, Any]], task: int) -> Json | None:
    rows = [row for row in trace if row.get("task") == task]
    if not rows:
        return None
    last = rows[-1]
    data = _map(last.get("data"))
    keys = (
        "action",
        "candidate_id",
        "reason",
        "status",
        "autonomous_search",
        "motion_permission",
        "features",
        "hold_state",
        "dog_motion_allowed",
        "mode",
        "track_id",
        "decision",
        "continuation",
        "landing_verified",
        "recovery_required",
        "goal_reached",
    )
    brief = {key: data.get(key) for key in keys if key in data}
    if not brief:
        encoded = json.dumps(data, default=str)
        brief = data if len(encoded) <= 4000 else {"omitted": "provider payload is large; use the run export"}
    return {"status": last.get("status"), "error": last.get("error"), "name": last.get("name"), "data": brief}


def _validation(frame_id: str, trace: Sequence[object]) -> str:
    status = "not recorded"
    for row in trace:
        if not isinstance(row, Mapping) or row.get("task") != 14:
            continue
        if frame_id in json.dumps(row.get("data"), default=str):
            status = str(row.get("status"))
    return status


def _age_ms(captured: object, observed: object) -> int | None:
    if not isinstance(captured, str) or not isinstance(observed, str):
        return None
    try:
        start = datetime.fromisoformat(captured.replace("Z", "+00:00"))
        end = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((end - start).total_seconds() * 1000)


def _check(check_id: str, label: str, status: str, blocking: bool, detail: str) -> Json:
    return {"id": check_id, "label": label, "status": status, "blocking": blocking, "detail": detail}


def describe_latest(messages: list[object]) -> str:
    if not messages or not isinstance(messages[-1], Mapping):
        return "No journal row yet."
    return describe_message(messages[-1])


def _map(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}
