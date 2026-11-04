"""Vision sampling feature. It proposes vision.request messages and never moves a robot."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path

from patrol.ground.extensions.g15.schedule import (
    PLACEHOLDER_MODEL,
    Decision,
    VisionScheduler,
    format_utc,
)
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

_SLOT = "feature.v2_vision_schedule"
_SCHEMA = "ground-task-v2"
_TARGET = "A person in the operator-marked closed demo area."
_SHA = "0f0479fff4658167e274ded2e2bdc58a9cc45ebdd667c955fb2a2f636906470f"


def create(services: BaseServices) -> VisionSchedule:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "services are required")
    return VisionSchedule(services)


class VisionSchedule:
    """Feature port for feature.v2_vision_schedule.

    Diagnostic requests are the frozen Task 01 harness. Stage requests are the
    scheduler. v1 has no vision.request event kind, so the envelope is returned
    on the result instead of being forced into a retired event name.
    """

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self._scheduler = VisionScheduler(services.kernel.clock)
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return self._fault_result(fault("invalid_input", "expected a FeatureRequest"))
        if request.kind == "diagnostic":
            return await self._diagnostic(request)
        if request.kind != "stage":
            return self._fault_result(
                fault("invalid_input", "vision schedule requests must be stage requests")
            )
        if self.services.kernel.authority.cancelled:
            return self._fault_result(
                fault("cancelled", "cancellation is latched", recovery_required=True)
            )
        if request.ticket is not None:
            try:
                self.services.kernel.authority.require_current(request.ticket)
            except GroundFault as exc:
                return self._fault_result(exc)
        try:
            decision = self._scheduler.submit(request.payload)
        except GroundFault as exc:
            return self._fault_result(exc)
        return _from_decision(decision)

    async def _diagnostic(self, request: FeatureRequest) -> FeatureResult:
        handlers: dict[str, Callable[[], Awaitable[FeatureResult]]] = {
            "fresh_drone": self._fresh_drone,
            "inflight_newest": self._inflight_newest,
            "stale_drop": self._stale_drop,
            "dog_track": self._dog_track,
            "timeout_id": self._timeout_id,
            "drop_count": self._drop_count,
            "no_calls": self._no_calls,
            "example_keys": self._example_keys,
            "clock_uncertainty": self._clock_uncertainty,
            "placeholder_model": self._placeholder_model,
            "sample_interval": self._sample_interval,
            "cancelled": self._cancelled,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return self._failed("invalid_input", f"unknown vision case {request.name}")
        try:
            return await handler()
        except GroundFault as exc:
            return self._failed(exc.error.code, exc.error.detail)

    async def _fresh_drone(self) -> FeatureResult:
        result = await self._call(self._payload("drone-downward-001"))
        message = _map(result.data.get("message"))
        payload = _map(None if message is None else message.get("payload"))
        ok = (
            result.status == "ok"
            and result.data.get("outcome") == "emitted"
            and message is not None
            and message.get("kind") == "vision.request"
            and message.get("source") == "ground"
            and message.get("destination") == "vision"
            and payload is not None
            and payload.get("stage") == "drone_search"
            and payload.get("active_track_id") is None
            and payload.get("provider") == "xai"
            and payload.get("model_id") == PLACEHOLDER_MODEL
            and result.data.get("model_unresolved") is True
            and self._calls() == []
        )
        return self._gate(
            ok,
            "fresh drone frame was not scheduled",
            detail="one_drone_request",
            trace=("emitted", "drone_search", "track:null", "placeholder", "vision.request"),
        )

    async def _inflight_newest(self) -> FeatureResult:
        first = await self._call(self._payload("a"))
        self._advance(0.2)
        second = await self._call(self._payload("b"))
        self._advance(0.2)
        third = await self._call(self._payload("c"))
        self._advance(0.4)
        fourth = await self._call(self._payload("d"))
        self._advance(0.2)
        follow = await self._call(self._control(settle=True, sample=True))
        first_id = first.data.get("request_id")
        follow_message = _map(follow.data.get("message"))
        follow_payload = _map(None if follow_message is None else follow_message.get("payload"))
        follow_frame = _map(None if follow_payload is None else follow_payload.get("frame"))
        ok = (
            first.data.get("outcome") == "emitted"
            and second.data.get("outcome") == "held"
            and second.data.get("message") is None
            and second.data.get("request_id") == first_id
            and second.data.get("held_frame_id") == "b"
            and third.data.get("dropped_on_call") == 1
            and third.data.get("held_frame_id") == "c"
            and fourth.data.get("held_frame_id") == "d"
            and fourth.data.get("dropped_frame_count") == 2
            and follow.data.get("outcome") == "emitted"
            and follow.data.get("request_id") != first_id
            and follow_frame is not None
            and follow_frame.get("frame_id") == "d"
            and self._calls() == []
        )
        return self._gate(
            ok,
            "newest frame was not kept for the next open slot",
            detail="newest_follow_up",
            trace=(
                "emitted:a",
                "held:b",
                "dropped:b",
                "held:c",
                "dropped:c",
                "held:d",
                "follow_up:d",
                "dropped_frame_count:2",
            ),
        )

    async def _stale_drop(self) -> FeatureResult:
        frame = self._frame("old")
        self._advance(3.001)
        result = await self._call(self._payload("old", frame=frame))
        ok = (
            result.status == "ok"
            and result.data.get("outcome") == "dropped"
            and result.data.get("drop_reason") == "stale"
            and result.data.get("message") is None
            and result.data.get("dropped_frame_count") == 1
        )
        return self._gate(
            ok,
            "stale frame was not dropped",
            detail="evidence_age",
            trace=("dropped:stale", "no_request"),
        )

    async def _dog_track(self) -> FeatureResult:
        rejected = await self._call(
            self._payload("dog-front-001", stage="dog_acquire", camera="front", track=None)
        )
        accepted = await self._call(
            self._payload(
                "dog-front-001",
                stage="dog_acquire",
                camera="front",
                track="target-001",
            )
        )
        message = _map(accepted.data.get("message"))
        payload = _map(None if message is None else message.get("payload"))
        error = rejected.error
        ok = (
            rejected.status == "blocked"
            and error is not None
            and error.code == "rejected"
            and rejected.data.get("message") is None
            and accepted.data.get("outcome") == "emitted"
            and payload is not None
            and payload.get("stage") == "dog_acquire"
            and payload.get("active_track_id") == "target-001"
        )
        return self._gate(
            ok,
            "dog_acquire did not enforce the track id",
            detail="track_required",
            trace=("rejected:dog_acquire", "emitted:dog_acquire", "track:target-001"),
        )

    async def _timeout_id(self) -> FeatureResult:
        settings = self._settings({"timeout_ms": 1000})
        frame = self._frame("same")
        first = await self._call(self._payload("same", settings=settings, frame=frame))
        first_id = first.data.get("request_id")
        self._advance(1.001)
        quiet = await self._call(self._control(sample=True, settings=settings))
        retry = await self._call(self._payload("same", settings=settings, frame=frame))
        unusable = quiet.data.get("unusable_request_ids")
        retry_unusable = retry.data.get("unusable_request_ids")
        ok = (
            first.data.get("outcome") == "emitted"
            and first_id == "vision-001"
            and quiet.data.get("outcome") == "expired"
            and quiet.data.get("message") is None
            and quiet.data.get("expired_request_id") == first_id
            and isinstance(unusable, tuple)
            and first_id in unusable
            and retry.data.get("outcome") == "emitted"
            and retry.data.get("request_id") == "vision-002"
            and retry.data.get("frame_id") == "same"
            and isinstance(retry_unusable, tuple)
            and first_id in retry_unusable
        )
        return self._gate(
            ok,
            "timeout reused a request id or resent it automatically",
            detail="timeout_new_id",
            trace=(
                "emitted:vision-001",
                "expired:vision-001",
                "no_resend",
                "retry:vision-002",
                "same_frame",
            ),
        )

    async def _drop_count(self) -> FeatureResult:
        start = format_utc(self.services.kernel.clock.utc_now())
        self._advance(0.1)
        mid = format_utc(self.services.kernel.clock.utc_now())
        self._advance(0.1)
        newest = format_utc(self.services.kernel.clock.utc_now())
        result = await self._call(
            {
                "stage": "drone_search",
                "target_description": _TARGET,
                "settings": self._settings(),
                "active_track_id": None,
                "frames": [
                    self._frame("older", captured_at=start),
                    self._frame("mid", captured_at=mid),
                    self._frame("newest", captured_at=newest),
                ],
            }
        )
        message = _map(result.data.get("message"))
        payload = _map(None if message is None else message.get("payload"))
        frame = _map(None if payload is None else payload.get("frame"))
        ok = (
            result.data.get("outcome") == "emitted"
            and result.data.get("dropped_frame_count") == 2
            and frame is not None
            and frame.get("frame_id") == "newest"
            and message is not None
            and message.get("kind") == "vision.request"
        )
        return self._gate(
            ok,
            "a burst did not collapse to the newest frame",
            detail="drop_count",
            trace=("emitted:newest", "dropped_frame_count:2"),
        )

    async def _no_calls(self) -> FeatureResult:
        result = await self._call(self._payload("drone-downward-001"))
        message = _map(result.data.get("message"))
        encoded = json.dumps(message)
        records = getattr(self.services.journal, "records", None)
        names = self._calls()
        ok = (
            result.data.get("outcome") == "emitted"
            and message is not None
            and message.get("kind") == "vision.request"
            and "vision.decision" not in encoded
            and names == []
            and isinstance(records, list)
            and records == []
            and not any(name.startswith(("dog.", "drone.", "reasoner.")) for name in names)
        )
        return self._gate(
            ok,
            "scheduler touched a device, model, or journal",
            detail="no_motion",
            trace=("dog:0", "drone:0", "reasoner:0", "decision:0"),
        )

    async def _example_keys(self) -> FeatureResult:
        drone = _load_example("drone-vision-request.json")
        dog = _load_example("dog-vision-request.json")
        drone_result = await self._call(self._from_example(drone))
        self._advance(1)
        dog_result = await self._call(self._from_example(dog, settle=True))
        ok = _matches_example(drone_result, drone) and _matches_example(dog_result, dog)
        return self._gate(
            ok,
            "emitted vision request is missing an example key",
            detail="example_keys",
            trace=("envelope", "payload", "frame", "drone", "dog"),
        )

    async def _clock_uncertainty(self) -> FeatureResult:
        result = await self._call(self._payload("fresh", clock_error_ms=3001))
        error = result.error
        ok = (
            result.status == "blocked"
            and error is not None
            and error.code == "rejected"
            and result.data.get("message") is None
            and result.data.get("drop_reason") == "clock_uncertainty"
            and result.data.get("dropped_frame_count") == 1
        )
        return self._gate(
            ok,
            "clock uncertainty did not block the request",
            detail="clock_uncertainty",
            trace=("blocked", "no_request"),
        )

    async def _placeholder_model(self) -> FeatureResult:
        result = await self._call(self._payload("drone-downward-001"))
        message = _map(result.data.get("message"))
        payload = _map(None if message is None else message.get("payload"))
        model = None if payload is None else payload.get("model_id")
        ok = (
            model == PLACEHOLDER_MODEL
            and result.data.get("model_unresolved") is True
            and model != "grok-2-vision"
            and "grok-" not in str(model)
        )
        return self._gate(
            ok,
            "placeholder model id was rewritten",
            detail="placeholder_copied",
            trace=("model:CONFIGURE_VERIFIED_IMAGE_MODEL", "unresolved"),
        )

    async def _sample_interval(self) -> FeatureResult:
        first = await self._call(self._payload("first"))
        settled = await self._call(self._control(settle=True))
        self._advance(0.2)
        second = await self._call(self._payload("second"))
        self._advance(0.8)
        follow = await self._call(self._control(sample=True))
        follow_frame = _frame_of(follow)
        ok = (
            first.data.get("outcome") == "emitted"
            and settled.data.get("message") is None
            and second.data.get("outcome") == "held"
            and second.data.get("message") is None
            and follow.data.get("outcome") == "emitted"
            and follow_frame is not None
            and follow_frame.get("frame_id") == "second"
        )
        return self._gate(
            ok,
            "sampler emitted faster than the sample interval",
            detail="sample_interval",
            trace=("emitted:first", "held:second", "follow_up:second"),
        )

    async def _cancelled(self) -> FeatureResult:
        self.services.kernel.authority.latch_cancel("operator halt")
        result = await self._call(self._payload("drone-downward-001"))
        error = result.error
        ok = (
            result.status == "blocked"
            and error is not None
            and error.code == "cancelled"
            and result.data.get("message") is None
            and self._calls() == []
        )
        return self._gate(
            ok,
            "cancellation still scheduled vision",
            detail="cancellation",
            trace=("cancelled", "no_request", "dog:0"),
        )

    async def _call(self, payload: Mapping[str, object]) -> FeatureResult:
        return await self.execute(FeatureRequest("stage", "schedule", None, payload))

    def _payload(self, frame_id: str, **extra: object) -> dict[str, object]:
        camera = extra.pop("camera", "downward")
        track = extra.pop("track", None)
        captured = extra.pop("captured_at", None)
        if not isinstance(camera, str):
            raise fault("invalid_input", "camera must be a string")
        body: dict[str, object] = {
            "stage": "drone_search",
            "target_description": _TARGET,
            "frame": self._frame(
                frame_id,
                camera=camera,
                captured_at=captured if isinstance(captured, str) else None,
            ),
            "settings": self._settings(),
            "active_track_id": track,
        }
        body.update(extra)
        return body

    def _control(self, **flags: object) -> dict[str, object]:
        body: dict[str, object] = {"settings": self._settings()}
        body.update(flags)
        return body

    def _settings(self, overrides: Mapping[str, object] | None = None) -> dict[str, object]:
        settings: dict[str, object] = {
            "sample_ms": 1000,
            "timeout_ms": 5000,
            "evidence_age_ms": 3000,
            "max_in_flight": 1,
            "model_id": PLACEHOLDER_MODEL,
            "prompt_version": "patrol-demo-v2.0",
            "scene_context": {
                "staged_demo": True,
                "area_closed_by_operator": True,
            },
            "mission_id": "demo-20261104-001",
            "epoch": 1,
            "simulated": True,
        }
        if overrides:
            settings.update(overrides)
        return settings

    def _frame(
        self,
        frame_id: str,
        *,
        camera: str = "downward",
        captured_at: str | None = None,
    ) -> dict[str, object]:
        stamp = captured_at or format_utc(self.services.kernel.clock.utc_now())
        prefix = "dog" if camera == "front" else "drone"
        width = 1280 if camera == "front" else 320
        height = 720 if camera == "front" else 240
        return {
            "frame_id": frame_id,
            "image_ref": f"artifact://demo-20261104-001/{prefix}/{frame_id}.jpg",
            "sha256": _SHA,
            "captured_at": stamp,
            "camera_id": camera,
            "camera_epoch": 1,
            "width_px": width,
            "height_px": height,
            "camera_frame_id": f"{prefix}/camera_{camera}",
            "camera_to_body_calibration_id": "synthetic-calibration-v1",
            "simulated": True,
        }

    def _from_example(
        self,
        example: Mapping[str, object],
        *,
        settle: bool = False,
    ) -> dict[str, object]:
        payload = _map(example.get("payload"))
        if payload is None:
            raise fault("invalid_input", "example payload is missing")
        frame = dict(_require_map(payload.get("frame"), "frame"))
        frame["captured_at"] = format_utc(self.services.kernel.clock.utc_now())
        scene = _require_map(payload.get("scene_context"), "scene_context")
        body: dict[str, object] = {
            "stage": payload["stage"],
            "target_description": payload["target_description"],
            "frame": frame,
            "active_track_id": payload["active_track_id"],
            "settings": self._settings(
                {
                    "model_id": payload["model_id"],
                    "prompt_version": payload["prompt_version"],
                    "scene_context": {
                        "staged_demo": scene["staged_demo"],
                        "area_closed_by_operator": scene["area_closed_by_operator"],
                    },
                    "mission_id": example["mission_id"],
                    "epoch": example["epoch"],
                    "simulated": example["simulated"],
                }
            ),
        }
        if settle:
            body["settle"] = True
        return body

    def _advance(self, seconds: float) -> None:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("invalid_input", "simulation clock must be manual")
        clock.advance(seconds)

    def _calls(self) -> list[str]:
        devices = getattr(self.services.adapters, "devices", None)
        found = getattr(devices, "calls", None)
        if not isinstance(found, list):
            return ["missing-trace"]
        return [item for item in found if isinstance(item, str)]

    def _gate(
        self,
        ok: bool,
        reason: str,
        *,
        detail: str,
        trace: tuple[str, ...],
    ) -> FeatureResult:
        if not ok or self._calls():
            return self._failed("unsafe_state" if self._calls() else "rejected", reason)
        return self._foundation(detail=detail, trace=trace)

    def _failed(self, code: str, detail: str) -> FeatureResult:
        recovery = code in {"cancelled", "timeout", "unsafe_state", "io_fault"}
        return self._foundation(
            detail=detail,
            trace=("failed", code),
            status="failed",
            error=GroundError(code, detail, recovery),
        )

    def _foundation(
        self,
        *,
        detail: str,
        trace: tuple[str, ...],
        status: str = "ok",
        error: GroundError | None = None,
    ) -> FeatureResult:
        data = freeze_map(
            {
                "authorized": False,
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": len(self._calls()),
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": _SLOT,
                "schema_version": _SCHEMA,
            }
        )
        return FeatureResult(status, data, (), error)

    def _fault_result(self, exc: GroundFault) -> FeatureResult:
        code = exc.error.code
        failed = code in {"invalid_input", "internal", "validation_failed"}
        status = "failed" if failed else "blocked"
        return FeatureResult(status, _state_data(self._scheduler, outcome=status), (), exc.error)


def _from_decision(decision: Decision) -> FeatureResult:
    error = None
    if decision.status != "ok":
        error = GroundError(
            decision.error_code or "rejected",
            decision.error_detail or "vision request was not sent",
            False,
        )
    message: object = None
    if decision.message is not None:
        message = dict(decision.message)
    data = freeze_map(
        {
            "outcome": decision.outcome,
            "message": message,
            "dropped": decision.dropped_on_call > 0 or decision.outcome == "dropped",
            "drop_reason": decision.drop_reason,
            "dropped_frame_count": decision.dropped_frame_count,
            "dropped_on_call": decision.dropped_on_call,
            "request_id": decision.request_id,
            "frame_id": decision.frame_id,
            "model_id": decision.model_id,
            "model_unresolved": decision.model_unresolved,
            "in_flight": decision.in_flight,
            "held_frame_id": decision.held_frame_id,
            "expired_request_id": decision.expired_request_id,
            "unusable_request_ids": decision.unusable_request_ids,
            "live_call_count": 0,
        }
    )
    return FeatureResult(decision.status, data, (), error)


def _state_data(scheduler: VisionScheduler, *, outcome: str) -> Mapping[str, object]:
    model_id = None
    unresolved = False
    return freeze_map(
        {
            "outcome": outcome,
            "message": None,
            "dropped": False,
            "drop_reason": None,
            "dropped_frame_count": scheduler.dropped_frame_count,
            "dropped_on_call": 0,
            "request_id": None,
            "frame_id": None,
            "model_id": model_id,
            "model_unresolved": unresolved,
            "in_flight": False,
            "held_frame_id": None,
            "expired_request_id": None,
            "unusable_request_ids": scheduler.unusable_request_ids,
            "live_call_count": 0,
        }
    )


def _load_example(name: str) -> dict[str, object]:
    path = Path(repo_root() / "fixtures" / "ground" / "g15" / name)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return _require_map(loaded, name)


def _matches_example(result: FeatureResult, example: Mapping[str, object]) -> bool:
    message = _map(result.data.get("message"))
    if message is None or result.data.get("outcome") != "emitted":
        return False
    if set(message) != set(example):
        return False
    payload = _map(message.get("payload"))
    expected_payload = _map(example.get("payload"))
    if payload is None or expected_payload is None or set(payload) != set(expected_payload):
        return False
    frame = _map(payload.get("frame"))
    expected_frame = _map(expected_payload.get("frame"))
    scene = _map(payload.get("scene_context"))
    expected_scene = _map(expected_payload.get("scene_context"))
    if (
        frame is None
        or expected_frame is None
        or scene is None
        or expected_scene is None
        or set(frame) != set(expected_frame)
        or set(scene) != set(expected_scene)
    ):
        return False
    copied = (
        "frame_id",
        "image_ref",
        "sha256",
        "camera_id",
        "camera_epoch",
        "width_px",
        "height_px",
        "camera_frame_id",
        "camera_to_body_calibration_id",
        "simulated",
    )
    if any(frame.get(key) != expected_frame.get(key) for key in copied):
        return False
    return (
        message.get("protocol_version") == example.get("protocol_version")
        and message.get("mission_id") == example.get("mission_id")
        and message.get("epoch") == example.get("epoch")
        and message.get("source") == "ground"
        and message.get("destination") == "vision"
        and message.get("kind") == "vision.request"
        and message.get("correlation_id") is None
        and message.get("simulated") == example.get("simulated")
        and payload.get("provider") == "xai"
        and payload.get("model_id") == expected_payload.get("model_id")
        and payload.get("prompt_version") == expected_payload.get("prompt_version")
        and payload.get("stage") == expected_payload.get("stage")
        and payload.get("target_description") == expected_payload.get("target_description")
        and payload.get("active_track_id") == expected_payload.get("active_track_id")
        and payload.get("max_evidence_age_ms") == 3000
        and scene == expected_scene
    )


def _frame_of(result: FeatureResult) -> Mapping[str, object] | None:
    message = _map(result.data.get("message"))
    payload = _map(None if message is None else message.get("payload"))
    return _map(None if payload is None else payload.get("frame"))


def _map(value: object) -> Mapping[str, object] | None:
    if isinstance(value, (str, bytes)) or not isinstance(value, Mapping):
        return None
    return value


def _require_map(value: object, label: str) -> dict[str, object]:
    raw = _map(value)
    if raw is None:
        raise fault("invalid_input", f"{label} must be an object")
    return dict(raw)
