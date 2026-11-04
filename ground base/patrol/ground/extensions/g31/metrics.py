"""Demo timings from one ordered journal.

Durations use a single monotonic domain. A missing endpoint is null with a
reason. An empty journal is null throughout, not zero. Model accuracy stays
null unless a labeled evaluation manifest is supplied.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

METRIC_NAMES: tuple[str, ...] = (
    "mission_start_to_drone_target_s",
    "detection_to_stable_hold_s",
    "stable_hold_to_dog_activation_s",
    "dog_activation_to_dog_camera_s",
    "mission_start_to_proximity_s",
    "dog_activation_to_proximity_s",
    "goal_to_verified_landing_s",
    "vision_latency_s",
    "evidence_age_at_use_s",
    "dropped_stale_frame_count",
    "command_latency_s",
    "rssi_windows_by_quality",
    "beacon_epoch_resets",
    "no_progress_stops",
    "blocked_candidate_events",
    "model_accuracy",
)

_SECRET_FIELDS = frozenset(
    {"api_key", "apikey", "token", "authorization", "password", "aes_key", "secret"}
)
_INTERVALS = (
    "mission_start_to_drone_target_s",
    "detection_to_stable_hold_s",
    "stable_hold_to_dog_activation_s",
    "dog_activation_to_dog_camera_s",
    "mission_start_to_proximity_s",
    "dog_activation_to_proximity_s",
    "goal_to_verified_landing_s",
)


class MeasureFailure(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class Mark:
    ms: int
    domain: str


@dataclass(frozen=True)
class Record:
    message_id: str
    mission_id: str | None
    kind: str
    event: str
    monotonic: Mark | None
    sent_at: str | None
    command_id: str | None
    request_id: str | None
    frame_id: str | None
    track_id: str | None
    beacon_epoch: int | None
    hold_state: str | None
    quality: str | None
    blocked: bool | None
    ack_state: str | None
    verified: bool | None
    reason_code: str | None
    action: str | None
    target_state: str | None
    stage: str | None
    frame_mark: Mark | None
    frame_captured_at: str | None
    drop_reason: str | None
    proximity_verified: bool
    simulated: bool | None


def compute_metrics(
    journal: object,
    *,
    mission_start_monotonic: object,
    clock: object,
    evaluation: object = None,
    run_id: object = None,
) -> dict[str, object]:
    """Return metrics, denominators, and reasons. Raise MeasureFailure to reject."""
    records, rejected = _records(journal)
    domain, quality, utc_pairs = _clock(clock)
    start = _mission_start(mission_start_monotonic, domain)
    chosen_run = _run_id(run_id, records)
    if not records:
        metrics = _empty_metrics()
        if evaluation is not None:
            metrics["model_accuracy"] = _accuracy(evaluation)
        return _envelope(
            metrics,
            denominators=_denominators(0, 0, 0, 0, 0, evaluation),
            run_id=chosen_run,
            domain=domain,
            quality=quality,
            rejected=rejected,
            evidence="simulated",
        )
    used = _dedupe(records)
    metrics = _filled_metrics(
        used,
        start=start,
        utc_pairs=utc_pairs,
        evaluation=evaluation,
    )
    evidence = "simulated" if all(item.simulated is True for item in used) else "unlabeled"
    return _envelope(
        metrics,
        denominators=_denominators(
            len(records),
            len(used),
            sum(1 for item in used if item.kind == "vision.request"),
            sum(1 for item in used if item.kind in {"dog.command", "drone.command"}),
            sum(1 for item in used if item.kind == "rssi.window"),
            evaluation,
        ),
        run_id=chosen_run,
        domain=domain,
        quality=quality,
        rejected=rejected,
        evidence=evidence,
    )


def _envelope(
    metrics: dict[str, object],
    *,
    denominators: dict[str, object],
    run_id: str | None,
    domain: str,
    quality: dict[str, object],
    rejected: list[str],
    evidence: str,
) -> dict[str, object]:
    reasons: dict[str, str] = {}
    for name, value in metrics.items():
        if isinstance(value, dict):
            reason = value.get("unavailable_reason")
            if isinstance(reason, str):
                reasons[name] = reason
    return {
        "schema_version": "ground-metrics-v2",
        "metric_names": list(METRIC_NAMES),
        "metrics": metrics,
        "denominators": denominators,
        "unavailable_reasons": reasons,
        "run_id": run_id,
        "clock_domain": domain,
        "clock_quality": quality,
        "rejected_fields": sorted(set(rejected)),
        "evidence": evidence,
    }


def _empty_metrics() -> dict[str, object]:
    metrics: dict[str, object] = {}
    for name in _INTERVALS:
        metrics[name] = _gap("empty_journal")
    metrics["vision_latency_s"] = {"pairs": None, "unavailable_reason": "empty_journal"}
    metrics["evidence_age_at_use_s"] = {"samples": None, "unavailable_reason": "empty_journal"}
    for name in (
        "dropped_stale_frame_count",
        "beacon_epoch_resets",
        "no_progress_stops",
        "blocked_candidate_events",
    ):
        metrics[name] = {"count": None, "unavailable_reason": "empty_journal"}
    metrics["command_latency_s"] = {"commands": None, "unavailable_reason": "empty_journal"}
    metrics["rssi_windows_by_quality"] = {"counts": None, "unavailable_reason": "empty_journal"}
    metrics["model_accuracy"] = _accuracy_null("empty_journal")
    return metrics


def _filled_metrics(
    used: list[Record],
    *,
    start: Mark | None,
    utc_pairs: bool,
    evaluation: object,
) -> dict[str, object]:
    detection = _first(used, lambda item: item.event == "drone_target_acquired")
    hold = _after(used, detection, lambda item: item.hold_state == "stable")
    activation = _after(
        used,
        hold if hold is not None else detection,
        lambda item: item.event == "dog_dispatched",
    )
    if activation is None:
        activation = _first(used, lambda item: item.event == "dog_dispatched")
    camera = _dog_camera(used, activation, detection)
    proximity = _first(
        used, lambda item: item.event == "demo_goal_reached" or item.proximity_verified
    )
    goal = _first(used, lambda item: item.event == "demo_goal_reached")
    landing_blocked = any(_landing_unverified(item) for item in used)
    landing = None if landing_blocked else _verified_landing(used, goal)
    metrics: dict[str, object] = {
        "mission_start_to_drone_target_s": _span(
            start, _mark(detection), "mission_start_missing", "drone_target_missing"
        ),
        "detection_to_stable_hold_s": _span(
            _mark(detection), _mark(hold), "drone_target_missing", "stable_hold_missing"
        ),
        "stable_hold_to_dog_activation_s": _span(
            _mark(hold), _mark(activation), "stable_hold_missing", "dog_activation_missing"
        ),
        "dog_activation_to_dog_camera_s": _camera_interval(activation, camera, detection),
        "mission_start_to_proximity_s": _span(
            start, _mark(proximity), "mission_start_missing", "proximity_missing"
        ),
        "dog_activation_to_proximity_s": _span(
            _mark(activation), _mark(proximity), "dog_activation_missing", "proximity_missing"
        ),
        "goal_to_verified_landing_s": _landing_interval(goal, landing, landing_blocked),
    }
    pairs, ages = _vision(used, utc_pairs=utc_pairs)
    metrics["vision_latency_s"] = pairs
    metrics["evidence_age_at_use_s"] = ages
    metrics["dropped_stale_frame_count"] = _count(sum(1 for item in used if _stale_drop(item)))
    metrics["command_latency_s"] = _commands(used)
    metrics["rssi_windows_by_quality"] = _rssi(used)
    metrics["beacon_epoch_resets"] = _count(_beacon_resets(used))
    metrics["no_progress_stops"] = _count(
        sum(1 for item in used if item.event == "no_progress_stop")
    )
    metrics["blocked_candidate_events"] = _count(sum(1 for item in used if item.blocked is True))
    metrics["model_accuracy"] = _accuracy(evaluation)
    return metrics


def _camera_interval(
    activation: Record | None,
    camera: Record | None | str,
    detection: Record | None,
) -> dict[str, object]:
    if isinstance(camera, str):
        return _gap(camera)
    if activation is None:
        return _gap("dog_activation_missing")
    if camera is None:
        return _gap("dog_camera_acquisition_missing")
    if detection is not None and detection.track_id and camera.track_id != detection.track_id:
        return _gap("track_mismatch")
    return _span(_mark(activation), _mark(camera), "dog_activation_missing", "monotonic_missing")


def _landing_interval(
    goal: Record | None,
    landing: Record | None,
    blocked: bool,
) -> dict[str, object]:
    if blocked:
        return _gap("landing_unverified")
    if goal is None:
        return _gap("goal_missing")
    if landing is None:
        return _gap("verified_landing_missing")
    return _span(_mark(goal), _mark(landing), "goal_missing", "verified_landing_missing")


def _dog_camera(
    used: list[Record],
    activation: Record | None,
    detection: Record | None,
) -> Record | None | str:
    track = None if detection is None else detection.track_id
    found_wrong_track = False
    found_hidden = False
    for item in used[(_index(used, activation) + 1) if activation is not None else 0 :]:
        if item.kind != "vision.decision" or not _dog_stage(item):
            continue
        if item.target_state != "person_visible":
            found_hidden = True
            continue
        if track and item.track_id != track:
            found_wrong_track = True
            continue
        return item
    if found_wrong_track:
        return "track_mismatch"
    if found_hidden:
        return "target_not_visible"
    return None


def _vision(used: list[Record], *, utc_pairs: bool) -> tuple[dict[str, object], dict[str, object]]:
    dropped = {item.frame_id for item in used if _stale_drop(item) and item.frame_id}
    requests = [item for item in used if item.kind == "vision.request" and item.request_id]
    decisions: dict[str, Record] = {}
    for item in used:
        if item.kind == "vision.decision" and item.request_id and item.request_id not in decisions:
            decisions[item.request_id] = item
    if not requests and not decisions:
        return (
            {"pairs": None, "unavailable_reason": "no_vision_pairs"},
            {"samples": None, "unavailable_reason": "no_vision_pairs"},
        )
    pairs: list[dict[str, object]] = []
    samples: list[dict[str, object]] = []
    for request in requests:
        request_id = request.request_id or ""
        decision = decisions.get(request_id)
        if decision is None:
            pairs.append(_pair(request_id, None, "vision_decision_missing", "monotonic"))
            samples.append(_pair(request_id, None, "vision_decision_missing", "monotonic"))
            continue
        if decision.frame_id and decision.frame_id in dropped:
            pairs.append(_pair(request_id, None, "stale_frame_dropped", "monotonic"))
            samples.append(_pair(request_id, None, "stale_frame_dropped", "monotonic"))
            continue
        pairs.append(_latency_pair(request, decision, utc_pairs))
        samples.append(_age_sample(request, decision, utc_pairs))
    return (
        {"pairs": pairs, "unavailable_reason": None},
        {"samples": samples, "unavailable_reason": None},
    )


def _latency_pair(request: Record, decision: Record, utc_pairs: bool) -> dict[str, object]:
    request_id = request.request_id or ""
    if request.monotonic is not None and decision.monotonic is not None:
        row = _span(request.monotonic, decision.monotonic, "monotonic_missing", "monotonic_missing")
        return _pair(
            request_id, row["seconds"], cast(str | None, row["unavailable_reason"]), "monotonic"
        )
    if utc_pairs:
        delta = _utc_seconds(request.sent_at, decision.sent_at)
        if delta is None:
            return _pair(request_id, None, "timestamp_missing", "utc_sent_at")
        if delta < 0:
            return _pair(request_id, None, "out_of_order", "utc_sent_at")
        return _pair(request_id, delta, None, "utc_sent_at")
    return _pair(request_id, None, "monotonic_missing", "monotonic")


def _age_sample(request: Record, decision: Record, utc_pairs: bool) -> dict[str, object]:
    request_id = request.request_id or ""
    if request.frame_mark is not None and decision.monotonic is not None:
        row = _span(
            request.frame_mark, decision.monotonic, "frame_time_missing", "monotonic_missing"
        )
        return _pair(
            request_id, row["seconds"], cast(str | None, row["unavailable_reason"]), "monotonic"
        )
    if utc_pairs:
        delta = _utc_seconds(request.frame_captured_at, decision.sent_at)
        if delta is None:
            return _pair(request_id, None, "frame_time_missing", "utc_sent_at")
        if delta < 0:
            return _pair(request_id, None, "out_of_order", "utc_sent_at")
        return _pair(request_id, delta, None, "utc_sent_at")
    return _pair(request_id, None, "frame_time_missing", "monotonic")


def _commands(used: list[Record]) -> dict[str, object]:
    issued: dict[str, Record] = {}
    order: list[str] = []
    acks: dict[str, dict[str, Record]] = {}
    for item in used:
        if item.kind in {"dog.command", "drone.command"} and item.command_id:
            if item.command_id not in issued:
                issued[item.command_id] = item
                order.append(item.command_id)
        if item.kind == "command.ack" and item.command_id and item.ack_state:
            bucket = acks.setdefault(item.command_id, {})
            if item.ack_state not in bucket:
                bucket[item.ack_state] = item
            if item.command_id not in order:
                order.append(item.command_id)
    if not order:
        return {"commands": None, "unavailable_reason": "no_commands"}
    rows: list[dict[str, object]] = []
    for command_id in order:
        issue = issued.get(command_id)
        states = acks.get(command_id, {})
        row: dict[str, object] = {"command_id": command_id}
        for label, state in (
            ("accept_s", "accepted"),
            ("run_s", "running"),
            ("complete_s", "completed"),
        ):
            ack = states.get(state)
            if issue is None:
                row[label] = None
                row[f"{label}_reason"] = "command_issue_missing"
                continue
            if ack is None:
                row[label] = None
                row[f"{label}_reason"] = f"ack_{state}_missing"
                continue
            spanned = _span(
                issue.monotonic, ack.monotonic, "monotonic_missing", "monotonic_missing"
            )
            row[label] = spanned["seconds"]
            row[f"{label}_reason"] = spanned["unavailable_reason"]
        rows.append(row)
    return {"commands": rows, "unavailable_reason": None}


def _rssi(used: list[Record]) -> dict[str, object]:
    counts: dict[str, int] = {}
    seen = False
    for item in used:
        if item.kind != "rssi.window":
            continue
        seen = True
        label = item.quality if item.quality else "unavailable"
        counts[label] = counts.get(label, 0) + 1
    if not seen:
        return {"counts": None, "unavailable_reason": "no_rssi_windows"}
    return {"counts": dict(sorted(counts.items())), "unavailable_reason": None}


def _beacon_resets(used: list[Record]) -> int:
    resets = 0
    previous: int | None = None
    for item in used:
        changed = (
            item.beacon_epoch is not None and previous is not None and item.beacon_epoch != previous
        )
        if item.event == "beacon_epoch_reset" or changed:
            resets += 1
        if item.beacon_epoch is not None:
            previous = item.beacon_epoch
    return resets


def _accuracy(evaluation: object) -> dict[str, object]:
    if evaluation is None:
        return _accuracy_null("no_labeled_evaluation")
    if not isinstance(evaluation, dict):
        raise MeasureFailure("invalid_input", "evaluation manifest must be an object")
    images = evaluation.get("images")
    if not isinstance(images, list):
        raise MeasureFailure("invalid_input", "evaluation images must be a list")
    if not images:
        return _accuracy_null("empty_evaluation")
    tp = fp = tn = fn = reviews = failed = 0
    for image in images:
        if not isinstance(image, dict):
            raise MeasureFailure("invalid_input", "evaluation image must be an object")
        label = image.get("label")
        decision = image.get("decision")
        if label not in {"positive", "negative"} or not isinstance(decision, str):
            raise MeasureFailure("invalid_input", "evaluation label or decision is invalid")
        if decision == "review":
            reviews += 1
            continue
        if decision == "failed":
            failed += 1
            continue
        if decision not in {"dispatch", "dismiss"}:
            raise MeasureFailure("invalid_input", "evaluation decision is invalid")
        positive = label == "positive"
        if decision == "dispatch" and positive:
            tp += 1
        elif decision == "dispatch":
            fp += 1
        elif positive:
            fn += 1
        else:
            tn += 1
    total = len(images)
    positives = sum(
        1 for image in images if isinstance(image, dict) and image.get("label") == "positive"
    )
    accuracy: float | None = (tp + tn) / total
    recall: float | None = None if positives == 0 else tp / positives
    precision: float | None = None if tp + fp == 0 else tp / (tp + fp)
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "reviews": reviews,
        "failed": failed,
        "unavailable_reason": None if precision is not None else "no_dispatches",
        "recall_reason": None if recall is not None else "no_positive_images",
    }


def _accuracy_null(reason: str) -> dict[str, object]:
    return {
        "accuracy": None,
        "precision": None,
        "recall": None,
        "tp": None,
        "fp": None,
        "tn": None,
        "fn": None,
        "reviews": None,
        "failed": None,
        "unavailable_reason": reason,
        "recall_reason": reason,
    }


def _records(journal: object) -> tuple[list[Record], list[str]]:
    if isinstance(journal, str) or not isinstance(journal, list):
        raise MeasureFailure("invalid_input", "journal must be an ordered list")
    rejected: list[str] = []
    records: list[Record] = []
    for index, raw in enumerate(journal):
        if not isinstance(raw, dict):
            raise MeasureFailure("invalid_input", "journal record must be an object")
        _collect_secrets(raw, rejected)
        records.append(_normalize(raw, index))
    return records, rejected


def _normalize(raw: dict[object, object], index: int) -> Record:
    payload = raw.get("payload", raw.get("summary"))
    body = payload if isinstance(payload, dict) else {}
    kind = _text(raw.get("kind")) or _text(body.get("kind")) or ""
    event = (
        _text(raw.get("event")) or _text(raw.get("event_name")) or _text(body.get("event")) or kind
    )
    message_id = _text(raw.get("message_id")) or f"journal-{index}"
    domain = _text(raw.get("clock_domain"))
    monotonic = _mark_from(raw.get("monotonic_ms"), raw.get("monotonic_s"), domain, "monotonic")
    frame_domain = _text(raw.get("frame_clock_domain")) or domain
    frame_mark = _mark_from(
        raw.get("frame_monotonic_ms"),
        raw.get("frame_monotonic_s"),
        frame_domain,
        "frame monotonic",
    )
    frame = body.get("frame")
    frame_body = frame if isinstance(frame, dict) else {}
    beacon = body.get("beacon")
    beacon_body = beacon if isinstance(beacon, dict) else {}
    details = body.get("details")
    detail_body = details if isinstance(details, dict) else {}
    dog = body.get("dog")
    dog_body = dog if isinstance(dog, dict) else {}
    drone = body.get("drone")
    drone_body = drone if isinstance(drone, dict) else {}
    track = (
        _text(raw.get("track_id"))
        or _text(body.get("track_id"))
        or _text(detail_body.get("track_id"))
        or _person_track(body.get("detections"))
    )
    blocked = _optional_bool(
        raw.get("blocked") if "blocked" in raw else body.get("blocked"), "blocked"
    )
    verified = _optional_bool(
        raw.get("verified") if "verified" in raw else body.get("verified"),
        "verified",
    )
    simulated = _optional_bool(raw.get("simulated"), "simulated")
    proximity = kind == "proximity.evidence" and _proximity_ok(body, dog_body, drone_body)
    ack_state = _text(body.get("state")) if kind == "command.ack" else None
    supplied_ack = raw.get("ack_state")
    if isinstance(supplied_ack, str):
        ack_state = supplied_ack
    return Record(
        message_id=message_id,
        mission_id=_text(raw.get("mission_id")),
        kind=kind,
        event=event,
        monotonic=monotonic,
        sent_at=_text(raw.get("sent_at")),
        command_id=_text(raw.get("command_id")) or _text(body.get("command_id")),
        request_id=_text(raw.get("request_id")) or _text(body.get("request_id")),
        frame_id=_text(raw.get("frame_id"))
        or _text(body.get("frame_id"))
        or _text(frame_body.get("frame_id")),
        track_id=track,
        beacon_epoch=_optional_int(
            raw.get("beacon_epoch")
            if "beacon_epoch" in raw
            else body.get("beacon_epoch", beacon_body.get("beacon_epoch")),
            "beacon_epoch",
        ),
        hold_state=_text(raw.get("hold_state"))
        or _text(beacon_body.get("hold_state"))
        or _text(body.get("hold_state")),
        quality=_text(raw.get("quality")) or _text(body.get("quality")),
        blocked=blocked if "blocked" in raw or "blocked" in body else None,
        ack_state=ack_state if isinstance(ack_state, str) else None,
        verified=verified,
        reason_code=_text(raw.get("reason_code")) or _text(body.get("reason_code")),
        action=_text(raw.get("action")) or _text(body.get("action")),
        target_state=_text(raw.get("target_state")) or _text(body.get("target_state")),
        stage=_text(raw.get("stage")) or _text(body.get("stage")),
        frame_mark=frame_mark,
        frame_captured_at=_text(raw.get("frame_captured_at"))
        or _text(body.get("frame_captured_at"))
        or _text(frame_body.get("captured_at")),
        drop_reason=_text(raw.get("reason")) or _text(body.get("reason")),
        proximity_verified=proximity,
        simulated=simulated,
    )


def _proximity_ok(
    body: dict[object, object],
    dog_body: dict[object, object],
    drone_body: dict[object, object],
) -> bool:
    confirmed = body.get("operator_confirmed")
    association = dog_body.get("association_valid")
    if confirmed is not True or association is not True:
        if confirmed is not None and confirmed is not True and not isinstance(confirmed, bool):
            raise MeasureFailure("invalid_input", "operator_confirmed must be a boolean")
        return False
    return _real(dog_body.get("range_m")) and _real(drone_body.get("horizontal_offset_m"))


def _dedupe(records: list[Record]) -> list[Record]:
    seen: set[str] = set()
    kept: list[Record] = []
    for item in records:
        if item.message_id in seen:
            continue
        seen.add(item.message_id)
        kept.append(item)
    return kept


def _clock(clock: object) -> tuple[str, dict[str, object], bool]:
    if not isinstance(clock, dict):
        raise MeasureFailure("invalid_input", "clock notes must be an object")
    domain = clock.get("domain")
    if not isinstance(domain, str) or not domain.strip():
        raise MeasureFailure("invalid_input", "clock domain is required")
    quality = clock.get("quality")
    if quality is not None and not isinstance(quality, str):
        raise MeasureFailure("invalid_input", "clock quality must be a string")
    bound = clock.get("utc_error_bound_ms")
    if bound is not None:
        if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
            raise MeasureFailure(
                "invalid_input", "utc_error_bound_ms must be a non-negative integer"
            )
    pairs = clock.get("utc_pairs_allowed", False)
    if not isinstance(pairs, bool):
        raise MeasureFailure("invalid_input", "utc_pairs_allowed must be a boolean")
    return (
        domain,
        {
            "quality": quality,
            "utc_error_bound_ms": bound,
            "utc_pairs_allowed": pairs,
        },
        pairs,
    )


def _mission_start(value: object, domain: str) -> Mark | None:
    if value is None:
        return None
    return Mark(_number_ms(value, "mission_start_monotonic"), domain)


def _run_id(run_id: object, records: list[Record]) -> str | None:
    if isinstance(run_id, str) and run_id.strip():
        return run_id
    if run_id is not None:
        raise MeasureFailure("invalid_input", "run_id must be a string")
    for item in records:
        if item.mission_id:
            return item.mission_id
    return None


def _span(
    start: Mark | None,
    end: Mark | None,
    missing_start: str,
    missing_end: str,
) -> dict[str, object]:
    if start is None:
        return _gap(missing_start)
    if end is None:
        return _gap(missing_end)
    if start.domain != end.domain:
        raise MeasureFailure(
            "rejected",
            f"monotonic domains {start.domain} and {end.domain} cannot be subtracted",
        )
    if end.ms < start.ms:
        return _gap("out_of_order")
    return {"seconds": (end.ms - start.ms) / 1000, "unavailable_reason": None}


def _gap(reason: str) -> dict[str, object]:
    return {"seconds": None, "unavailable_reason": reason}


def _count(value: int) -> dict[str, object]:
    return {"count": value, "unavailable_reason": None}


def _pair(
    request_id: str,
    seconds: object,
    reason: str | None,
    clock: str,
) -> dict[str, object]:
    return {
        "request_id": request_id,
        "seconds": seconds,
        "unavailable_reason": reason,
        "clock": clock,
    }


def _mark(record: Record | None) -> Mark | None:
    if record is None:
        return None
    return record.monotonic


def _mark_from(
    ms_value: object, seconds_value: object, domain: str | None, label: str
) -> Mark | None:
    if ms_value is None and seconds_value is None:
        return None
    if not domain:
        raise MeasureFailure("invalid_input", f"clock_domain is required for {label}")
    if ms_value is not None:
        if isinstance(ms_value, bool) or not isinstance(ms_value, int):
            raise MeasureFailure("invalid_input", f"{label} milliseconds must be an integer")
        return Mark(ms_value, domain)
    return Mark(_number_ms(seconds_value, label), domain)


def _number_ms(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeasureFailure("invalid_input", f"{label} must be a number")
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        raise MeasureFailure("invalid_input", f"{label} must be finite")
    return int(round(number * 1000))


def _utc_seconds(start: str | None, end: str | None) -> float | None:
    if start is None or end is None:
        return None
    start_ms = _utc_ms(start)
    end_ms = _utc_ms(end)
    if start_ms is None or end_ms is None:
        return None
    return (end_ms - start_ms) / 1000


def _utc_ms(value: str) -> int | None:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    delta = parsed.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def _denominators(
    raw: int,
    used: int,
    vision_requests: int,
    commands: int,
    windows: int,
    evaluation: object,
) -> dict[str, object]:
    labeled: int | None = None
    if isinstance(evaluation, dict) and isinstance(evaluation.get("images"), list):
        labeled = len(cast(list[object], evaluation["images"]))
    return {
        "journal_records": raw,
        "records_used": used,
        "vision_requests": vision_requests,
        "commands": commands,
        "rssi_windows": windows,
        "labeled_images": labeled,
    }


def _landing_unverified(item: Record) -> bool:
    if item.event == "landing_unverified":
        return True
    return item.reason_code == "landing_not_verified" or (
        item.ack_state == "unknown"
        and item.kind == "command.ack"
        and item.command_id == "cmd-drone-land-001"
    )


def _verified_landing(used: list[Record], goal: Record | None) -> Record | None:
    land_ids = {item.command_id for item in used if item.action == "land" and item.command_id}
    begin = _index(used, goal)
    for item in used[begin + 1 :]:
        if item.kind != "command.ack" or item.command_id not in land_ids:
            continue
        if item.ack_state == "completed" and item.verified is True:
            return item
    return None


def _stale_drop(item: Record) -> bool:
    return item.event == "frame_dropped" and item.drop_reason in {None, "stale"}


def _dog_stage(item: Record) -> bool:
    """Dog acquisition is the dog stage or the dog camera frame.

    The decision example omits ``stage``; the request and frame id carry it.
    """
    stage = item.stage or ""
    frame = item.frame_id or ""
    return "dog" in stage or frame.startswith("dog-")


def _first(used: list[Record], predicate: Callable[[Record], bool]) -> Record | None:
    for item in used:
        if predicate(item):
            return item
    return None


def _after(
    used: list[Record],
    origin: Record | None,
    predicate: Callable[[Record], bool],
) -> Record | None:
    if origin is None:
        return None
    for item in used[_index(used, origin) + 1 :]:
        if predicate(item):
            return item
    return None


def _index(used: list[Record], record: Record | None) -> int:
    if record is None:
        return -1
    for index, item in enumerate(used):
        if item.message_id == record.message_id:
            return index
    return -1


def _person_track(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        if item.get("label") == "person":
            track = item.get("track_id")
            if isinstance(track, str) and track:
                return track
    return None


def _optional_bool(value: object, label: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise MeasureFailure("invalid_input", f"{label} must be a boolean")
    return value


def _optional_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise MeasureFailure("invalid_input", f"{label} must be an integer")
    return value


def _real(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _collect_secrets(value: object, found: list[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower().replace("-", "_") in _SECRET_FIELDS:
                found.append(key.lower().replace("-", "_"))
            else:
                _collect_secrets(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_secrets(item, found)
