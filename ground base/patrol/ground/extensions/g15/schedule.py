"""Latest-frame vision sampling. This module never calls a model or a device."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from patrol.ground.kernel.contracts import Clock
from patrol.ground.kernel.faults import fault

PLACEHOLDER_MODEL = "CONFIGURE_VERIFIED_IMAGE_MODEL"
PROVIDER = "xai"
PROTOCOL = "2.0-draft"

_STAGES = frozenset({"drone_search", "drone_track", "dog_acquire", "dog_approach"})
_TRACK_REQUIRED = frozenset({"drone_track", "dog_acquire", "dog_approach"})
_DRONE_STAGES = frozenset({"drone_search", "drone_track"})
_PAYLOAD_KEYS = frozenset(
    {
        "stage",
        "target_description",
        "frame",
        "frames",
        "settings",
        "active_track_id",
        "in_flight",
        "settle",
        "sample",
        "clock_error_ms",
    }
)
_SETTING_KEYS = frozenset(
    {
        "sample_ms",
        "timeout_ms",
        "evidence_age_ms",
        "max_in_flight",
        "model_id",
        "prompt_version",
        "scene_context",
        "mission_id",
        "epoch",
        "simulated",
    }
)
_FRAME_KEYS = (
    "frame_id",
    "image_ref",
    "sha256",
    "captured_at",
    "camera_id",
    "camera_epoch",
    "width_px",
    "height_px",
    "camera_frame_id",
    "camera_to_body_calibration_id",
    "simulated",
)
_SCENE_KEYS = frozenset({"staged_demo", "area_closed_by_operator"})
_INTENT = ("criminal", "crime", "guilt", "guilty", "intruder", "weapon")


@dataclass(frozen=True)
class ScheduleSettings:
    sample_ms: int
    timeout_ms: int
    evidence_age_ms: int
    model_id: str
    prompt_version: str
    scene_context: Mapping[str, bool]
    mission_id: str
    epoch: int
    simulated: bool

    @property
    def model_unresolved(self) -> bool:
        return self.model_id.startswith("CONFIGURE_")


@dataclass(frozen=True)
class Candidate:
    frame: Mapping[str, object]
    captured_at: datetime
    stage: str
    target: str
    track_id: str | None

    @property
    def frame_id(self) -> str:
        value = self.frame["frame_id"]
        if not isinstance(value, str):
            raise fault("internal", "frame id was not stored as a string")
        return value


@dataclass(frozen=True)
class Decision:
    status: str
    outcome: str
    message: Mapping[str, object] | None
    drop_reason: str | None
    dropped_frame_count: int
    dropped_on_call: int
    request_id: str | None
    frame_id: str | None
    model_id: str | None
    model_unresolved: bool
    in_flight: bool
    held_frame_id: str | None
    expired_request_id: str | None
    unusable_request_ids: tuple[str, ...]
    error_code: str | None = None
    error_detail: str | None = None


@dataclass
class _InFlight:
    request_id: str
    frame_id: str
    expires_mono: float
    message: Mapping[str, object]


def format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise fault("invalid_input", "timestamp must be UTC")
    utc = value.astimezone(UTC)
    millis = utc.microsecond // 1000
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{millis:03d}Z"


def parse_utc(value: str, label: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise fault("invalid_input", f"{label} is not a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise fault("invalid_input", f"{label} must be UTC")
    return parsed.astimezone(UTC)


class VisionScheduler:
    """Keep one vision.request in flight and sample the newest fresh frame."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._settings: ScheduleSettings | None = None
        self._inflight: _InFlight | None = None
        self._external = False
        self._held: Candidate | None = None
        self._last_emit: float | None = None
        self._seq = 0
        self._epoch: int | None = None
        self._dropped = 0
        self._unusable: list[str] = []
        self._allow_future_ms = 0

    @property
    def dropped_frame_count(self) -> int:
        return self._dropped

    @property
    def unusable_request_ids(self) -> tuple[str, ...]:
        return tuple(self._unusable)

    def submit(self, payload: Mapping[str, object]) -> Decision:
        _reject_unknown(payload, _PAYLOAD_KEYS, "schedule request")
        expired = self._apply_controls(payload)
        clock_error = _optional_int(payload, "clock_error_ms")
        self._allow_future_ms = clock_error
        frames = self._candidates(payload)
        settings = self._require_settings()
        if clock_error > settings.evidence_age_ms:
            return self._block_for_clock(frames, expired)
        dropped_on_call, reason = self._drop_stale_held()
        fresh: list[Candidate] = []
        for candidate in frames:
            age = self._age_ms(candidate.captured_at)
            if age + clock_error > settings.evidence_age_ms:
                dropped_on_call += 1
                self._dropped += 1
                reason = "stale"
                continue
            fresh.append(candidate)
        chosen, superseded = self._choose(fresh)
        if superseded:
            dropped_on_call += superseded
            self._dropped += superseded
            reason = "superseded"
        if chosen is None:
            return self._idle(payload, expired, dropped_on_call, reason)
        if self._busy() or not self._interval_open():
            self._held = chosen
            return self._decision(
                status="ok",
                outcome="held",
                drop_reason=reason,
                dropped_on_call=dropped_on_call,
                expired=expired,
                frame_id=chosen.frame_id,
                held=chosen,
            )
        return self._emit(chosen, settings, expired, dropped_on_call, reason)

    def _apply_controls(self, payload: Mapping[str, object]) -> str | None:
        retired: str | None = None
        if "settings" in payload:
            parsed = _settings(payload["settings"])
            self._settings = parsed
            retired = self._note_epoch(parsed.epoch)
        if "sample" in payload:
            _bool(payload["sample"], "sample")
        expired = self._expire() or retired
        if "in_flight" in payload:
            if _bool(payload["in_flight"], "in_flight"):
                if self._inflight is None:
                    self._external = True
            else:
                self._retire_current()
                self._external = False
        if "settle" in payload and _bool(payload["settle"], "settle"):
            self._retire_current()
            self._external = False
        return expired

    def _candidates(self, payload: Mapping[str, object]) -> list[Candidate]:
        raw: list[object] = []
        if "frame" in payload and payload["frame"] is not None:
            raw.append(payload["frame"])
        if "frames" in payload:
            listed = payload["frames"]
            if isinstance(listed, (str, bytes)) or not isinstance(listed, list):
                raise fault("invalid_input", "frames must be a list")
            raw.extend(listed)
        if not raw:
            if "stage" in payload:
                self._reject_track(payload)
            return []
        stage, target, track = self._reject_track(payload)
        if "target_description" not in payload:
            raise fault("invalid_input", "target description is required")
        parsed: list[Candidate] = []
        for item in raw:
            frame, captured = _frame(item, stage)
            parsed.append(Candidate(frame, captured, stage, target, track))
        return parsed

    def _reject_track(self, payload: Mapping[str, object]) -> tuple[str, str, str | None]:
        if "stage" not in payload:
            raise fault("invalid_input", "stage is required")
        stage = _stage(payload["stage"])
        target = ""
        if "target_description" in payload:
            target = _text(payload["target_description"], "target_description")
            _reject_intent(target)
        track = None
        if "active_track_id" in payload:
            track = _optional_id(payload["active_track_id"], "active_track_id")
        if stage in _TRACK_REQUIRED and track is None:
            raise fault("rejected", f"{stage} requires an active_track_id")
        return stage, target, track

    def _block_for_clock(self, frames: list[Candidate], expired: str | None) -> Decision:
        dropped = len(frames) + (0 if self._held is None else 1)
        self._dropped += dropped
        self._held = None
        return self._decision(
            status="blocked",
            outcome="blocked",
            drop_reason="clock_uncertainty",
            dropped_on_call=dropped,
            expired=expired,
            error_code="rejected",
            error_detail="clock uncertainty exceeds the evidence age budget",
        )

    def _drop_stale_held(self) -> tuple[int, str | None]:
        settings = self._require_settings()
        if self._held is None:
            return 0, None
        if self._age_ms(self._held.captured_at) + self._allow_future_ms <= settings.evidence_age_ms:
            return 0, None
        self._held = None
        self._dropped += 1
        return 1, "stale"

    def _choose(self, fresh: list[Candidate]) -> tuple[Candidate | None, int]:
        chosen = self._held
        dropped = 0
        for candidate in fresh:
            if chosen is None or candidate.captured_at >= chosen.captured_at:
                if chosen is not None:
                    dropped += 1
                chosen = candidate
            else:
                dropped += 1
        self._held = None
        return chosen, dropped

    def _idle(
        self,
        payload: Mapping[str, object],
        expired: str | None,
        dropped_on_call: int,
        reason: str | None,
    ) -> Decision:
        settled = _settled(payload)
        if dropped_on_call and reason == "stale":
            outcome = "dropped"
        elif expired is not None:
            outcome = "expired"
            reason = None
        elif settled:
            outcome = "settled"
            reason = None
        elif payload.get("sample") is True:
            outcome = "settled"
            reason = None
        else:
            raise fault("invalid_input", "schedule request needs a frame")
        return self._decision(
            status="ok",
            outcome=outcome,
            drop_reason=reason,
            dropped_on_call=dropped_on_call,
            expired=expired,
        )

    def _emit(
        self,
        candidate: Candidate,
        settings: ScheduleSettings,
        expired: str | None,
        dropped_on_call: int,
        reason: str | None,
    ) -> Decision:
        self._seq += 1
        request_id = f"vision-{self._seq:03d}"
        now = self._clock.utc_now()
        mono = self._clock.monotonic()
        expires = now + timedelta(milliseconds=settings.timeout_ms)
        message: dict[str, object] = {
            "protocol_version": PROTOCOL,
            "message_id": f"msg-{request_id}",
            "mission_id": settings.mission_id,
            "epoch": settings.epoch,
            "seq": self._seq,
            "sent_at": format_utc(now),
            "source": "ground",
            "destination": "vision",
            "kind": "vision.request",
            "correlation_id": None,
            "expires_at": format_utc(expires),
            "simulated": settings.simulated,
            "payload": {
                "request_id": request_id,
                "provider": PROVIDER,
                "model_id": settings.model_id,
                "prompt_version": settings.prompt_version,
                "stage": candidate.stage,
                "frame": dict(candidate.frame),
                "target_description": candidate.target,
                "active_track_id": candidate.track_id,
                "scene_context": {
                    "staged_demo": settings.scene_context["staged_demo"],
                    "area_closed_by_operator": settings.scene_context["area_closed_by_operator"],
                },
                "max_evidence_age_ms": settings.evidence_age_ms,
            },
        }
        self._inflight = _InFlight(
            request_id,
            candidate.frame_id,
            mono + (settings.timeout_ms / 1000),
            message,
        )
        self._external = False
        self._held = None
        self._last_emit = mono
        return self._decision(
            status="ok",
            outcome="emitted",
            message=message,
            drop_reason=reason,
            dropped_on_call=dropped_on_call,
            expired=expired,
            request_id=request_id,
            frame_id=candidate.frame_id,
        )

    def _expire(self) -> str | None:
        current = self._inflight
        if current is None:
            return None
        if self._clock.monotonic() < current.expires_mono:
            return None
        self._remember(current.request_id)
        self._inflight = None
        return current.request_id

    def _retire_current(self) -> None:
        current = self._inflight
        if current is None:
            return
        self._remember(current.request_id)
        self._inflight = None

    def _remember(self, request_id: str) -> None:
        if request_id not in self._unusable:
            self._unusable.append(request_id)

    def _note_epoch(self, epoch: int) -> str | None:
        if self._epoch is None:
            self._epoch = epoch
            return None
        if epoch == self._epoch:
            return None
        retired = None if self._inflight is None else self._inflight.request_id
        self._retire_current()
        self._external = False
        if self._held is not None:
            self._dropped += 1
            self._held = None
        self._epoch = epoch
        return retired

    def _busy(self) -> bool:
        return self._inflight is not None or self._external

    def _interval_open(self) -> bool:
        settings = self._require_settings()
        if self._last_emit is None:
            return True
        elapsed = (self._clock.monotonic() - self._last_emit) * 1000
        return round(elapsed) >= settings.sample_ms

    def _age_ms(self, captured_at: datetime) -> int:
        delta = (self._clock.utc_now() - captured_at).total_seconds() * 1000
        age = int(round(delta))
        if age >= 0:
            return age
        if -age > self._allow_future_ms:
            raise fault("rejected", "frame captured_at is ahead of the ground clock")
        return 0

    def _require_settings(self) -> ScheduleSettings:
        if self._settings is None:
            raise fault("invalid_input", "scheduler settings are required")
        return self._settings

    def _decision(
        self,
        *,
        status: str,
        outcome: str,
        drop_reason: str | None,
        dropped_on_call: int,
        expired: str | None,
        message: Mapping[str, object] | None = None,
        request_id: str | None = None,
        frame_id: str | None = None,
        held: Candidate | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> Decision:
        settings = self._settings
        active = self._inflight.request_id if self._inflight is not None else request_id
        held_id = None if self._held is None else self._held.frame_id
        if held is not None:
            held_id = held.frame_id
        return Decision(
            status=status,
            outcome=outcome,
            message=message,
            drop_reason=drop_reason,
            dropped_frame_count=self._dropped,
            dropped_on_call=dropped_on_call,
            request_id=active,
            frame_id=frame_id if frame_id is not None else held_id,
            model_id=None if settings is None else settings.model_id,
            model_unresolved=False if settings is None else settings.model_unresolved,
            in_flight=self._busy(),
            held_frame_id=held_id,
            expired_request_id=expired,
            unusable_request_ids=tuple(self._unusable),
            error_code=error_code,
            error_detail=error_detail,
        )


def _settings(value: object) -> ScheduleSettings:
    raw = _mapping(value, "settings")
    _reject_unknown(raw, _SETTING_KEYS, "settings")
    missing = _SETTING_KEYS - set(raw)
    if missing:
        names = ", ".join(sorted(missing))
        raise fault("invalid_input", f"settings missing {names}")
    sample_ms = _positive(raw["sample_ms"], "sample_ms")
    timeout_ms = _positive(raw["timeout_ms"], "timeout_ms")
    evidence_age_ms = _positive(raw["evidence_age_ms"], "evidence_age_ms")
    if _positive(raw["max_in_flight"], "max_in_flight") != 1:
        raise fault("rejected", "max_in_flight must be 1")
    model_id = _text(raw["model_id"], "model_id")
    if model_id != model_id.strip() or " " in model_id:
        raise fault("invalid_input", "model_id must be a single token")
    scene = _scene(raw["scene_context"])
    return ScheduleSettings(
        sample_ms=sample_ms,
        timeout_ms=timeout_ms,
        evidence_age_ms=evidence_age_ms,
        model_id=model_id,
        prompt_version=_text(raw["prompt_version"], "prompt_version"),
        scene_context=scene,
        mission_id=_text(raw["mission_id"], "mission_id"),
        epoch=_nonnegative(raw["epoch"], "epoch"),
        simulated=_bool(raw["simulated"], "simulated"),
    )


def _scene(value: object) -> Mapping[str, bool]:
    raw = _mapping(value, "scene_context")
    _reject_unknown(raw, _SCENE_KEYS, "scene_context")
    missing = _SCENE_KEYS - set(raw)
    if missing:
        raise fault("invalid_input", "scene_context is incomplete")
    return {
        "staged_demo": _bool(raw["staged_demo"], "staged_demo"),
        "area_closed_by_operator": _bool(raw["area_closed_by_operator"], "area_closed_by_operator"),
    }


def _frame(value: object, stage: str) -> tuple[dict[str, object], datetime]:
    raw = _mapping(value, "frame")
    _reject_unknown(raw, frozenset(_FRAME_KEYS), "frame")
    missing = [key for key in _FRAME_KEYS if key not in raw]
    if missing:
        raise fault("invalid_input", "frame is missing " + ", ".join(missing))
    camera = raw["camera_id"]
    if camera not in {"front", "downward"}:
        raise fault("invalid_input", "camera_id must be front or downward")
    if stage in _DRONE_STAGES and camera != "downward":
        raise fault("rejected", f"{stage} requires the downward camera")
    if stage not in _DRONE_STAGES and camera != "front":
        raise fault("rejected", f"{stage} requires the front camera")
    image_ref = _text(raw["image_ref"], "image_ref")
    if not image_ref.startswith("artifact://") or image_ref == "artifact://":
        raise fault("rejected", "image reference must be an artifact URI")
    captured = parse_utc(_text(raw["captured_at"], "captured_at"), "captured_at")
    copied: dict[str, object] = {
        "frame_id": _text(raw["frame_id"], "frame_id"),
        "image_ref": image_ref,
        "sha256": _sha256(raw["sha256"]),
        "captured_at": raw["captured_at"],
        "camera_id": camera,
        "camera_epoch": _nonnegative(raw["camera_epoch"], "camera_epoch"),
        "width_px": _positive(raw["width_px"], "width_px"),
        "height_px": _positive(raw["height_px"], "height_px"),
        "camera_frame_id": _text(raw["camera_frame_id"], "camera_frame_id"),
        "camera_to_body_calibration_id": _optional_id(
            raw["camera_to_body_calibration_id"],
            "camera_to_body_calibration_id",
        ),
        "simulated": _bool(raw["simulated"], "simulated"),
    }
    return copied, captured


def _stage(value: object) -> str:
    if not isinstance(value, str) or value not in _STAGES:
        raise fault("invalid_input", "unknown vision stage")
    return value


def _reject_intent(text: str) -> None:
    folded = text.casefold()
    if any(phrase in folded for phrase in _INTENT):
        raise fault("rejected", "target description must not ask for criminal intent")


def _sha256(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise fault("invalid_input", "sha256 must be 64 lowercase hex characters")
    if any(character not in "0123456789abcdef" for character in value):
        raise fault("invalid_input", "sha256 must be 64 lowercase hex characters")
    return value


def _settled(payload: Mapping[str, object]) -> bool:
    if payload.get("settle") is True:
        return True
    return "in_flight" in payload and payload["in_flight"] is False


def _optional_int(payload: Mapping[str, object], key: str) -> int:
    if key not in payload:
        return 0
    return _nonnegative(payload[key], key)


def _reject_unknown(value: Mapping[str, object], allowed: frozenset[str], label: str) -> None:
    unknown = sorted(key for key in value if key not in allowed)
    if unknown:
        raise fault("invalid_input", f"{label} has unknown fields: {', '.join(unknown)}")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        raise fault("invalid_input", f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise fault("invalid_input", f"{label} must be a string")
    return value


def _optional_id(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise fault("invalid_input", f"{label} must be a string or null")
    return value


def _bool(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise fault("invalid_input", f"{label} must be a boolean")
    return value


def _nonnegative(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise fault("invalid_input", f"{label} must be a non-negative integer")
    return value


def _positive(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise fault("invalid_input", f"{label} must be a positive integer")
    return value
