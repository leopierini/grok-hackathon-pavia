"""Capability admission feature. create(services) does not connect or move hardware."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from patrol.ground.extensions.g12.admit import (
    SCHEMA,
    SLOT,
    Ledger,
    demo_settings,
    demo_snapshot,
    load_envelopes,
    with_features,
    with_payload,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundSettings,
    SessionSnapshot,
)
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.validation import freeze_map

_PAYLOAD_KEYS = frozenset({"reports", "settings", "snapshot"})


def create(services: BaseServices) -> CapabilityFeature:
    if not isinstance(services, BaseServices):
        raise fault("invalid_input", "capabilities create expects base services")
    return CapabilityFeature(services)


class CapabilityFeature:
    """Arm a feature only when the matching peer report validates it."""

    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.ledger = Ledger()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        if not isinstance(request, FeatureRequest):
            return _failed("invalid_input", "expected a FeatureRequest")
        try:
            if request.kind == "diagnostic":
                return self._diagnostic(request)
            if request.kind not in {"stage", "guard"}:
                return _failed("invalid_input", "unsupported request kind")
            return self._from_request(request)
        except GroundFault as exc:
            return _failed(exc.error.code, exc.error.detail)

    def _from_request(self, request: FeatureRequest) -> FeatureResult:
        unknown = [key for key in request.payload if key not in _PAYLOAD_KEYS]
        if unknown:
            return _failed("invalid_input", "unknown capability payload")
        missing = _PAYLOAD_KEYS - set(request.payload)
        if missing:
            return _failed("invalid_input", "capability payload is incomplete")
        reports = request.payload.get("reports")
        settings = request.payload.get("settings")
        snapshot = request.payload.get("snapshot")
        if isinstance(reports, (str, bytes)) or not isinstance(reports, tuple):
            return _failed("invalid_input", "reports must be a tuple of envelopes")
        envelopes: list[Mapping[str, object]] = []
        for item in reports:
            if isinstance(item, (str, bytes)) or not isinstance(item, Mapping):
                return _failed("invalid_input", "each report must be an object")
            envelopes.append(item)
        if not isinstance(settings, GroundSettings) or not isinstance(snapshot, SessionSnapshot):
            return _failed("invalid_input", "settings and snapshot are required")
        return self.ledger.apply(
            tuple(envelopes),
            settings,
            snapshot,
            request.ticket,
            cancelled=self.services.kernel.authority.cancelled,
        )

    def _diagnostic(self, request: FeatureRequest) -> FeatureResult:
        handlers: dict[str, Callable[[], FeatureResult]] = {
            "admit_examples": self._admit_examples,
            "autonomous_search_blocked": self._autonomous_search_blocked,
            "pi_report_missing": self._pi_report_missing,
            "slam_unresolved": self._slam_unresolved,
            "unvalidated_dog": self._unvalidated_dog,
            "replay_one_report": self._replay_one_report,
            "downward_camera_missing": self._downward_camera_missing,
            "honest_control_fault": self._honest_control_fault,
            "role_device_mismatch": self._role_device_mismatch,
        }
        handler = handlers.get(request.name)
        if handler is None:
            return self._done(
                False,
                f"unknown case {request.name}",
                status="failed",
                code="invalid_input",
                detail=f"unknown case {request.name}",
                trace=("failed", "invalid_input"),
            )
        return handler()

    def _admit_examples(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        result = self._run((drone, dog, pi))
        features = _map(result, "features")
        router = _map(result, "router")
        peers = _map(result, "peers")
        ok = (
            result.status == "ok"
            and result.error is None
            and features.get("controlled_motion") is True
            and features.get("downward_video") is True
            and features.get("rssi_receiver") is True
            and features.get("lidar") is True
            and features.get("slam") is True
            and features.get("target_range") is True
            and result.data.get("dog_controlled_motion") is True
            and result.data.get("navigation_mode") == "slam_eligible"
            and result.data.get("autonomous_search") == "armed"
            and result.data.get("motion_permission") is False
            and result.data.get("session_armed") is False
            and result.data.get("armed_record_count") == 3
            and router.get("device_id") == "router-back"
            and router.get("peer") is False
            and router.get("networking") == "failed"
            and "pi" in peers
            and _map_at(peers, "pi").get("device_id") == "pi-01"
            and len(result.events) == 3
            and self._device_calls() == 0
            and _no_secret(result)
        )
        return self._done(
            ok,
            "examples were not admitted",
            detail="three_peers_admitted",
            trace=(
                "peer:drone:admitted",
                "peer:dog:admitted",
                "peer:pi:admitted",
                "controlled_motion:true",
                "downward_video:true",
                "rssi_receiver:true",
                "lidar:true",
                "slam:true",
                "target_range:true",
                "dog_controlled_motion:true",
                "navigation_mode:slam_eligible",
                "autonomous_search:armed",
                "router:router-back",
                "router_peer:false",
                "motion_permission:false",
                "armed_records:3",
            ),
        )

    def _autonomous_search_blocked(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        drone = with_features(drone, controlled_motion=False)
        result = self._run((drone, dog, pi))
        features = _map(result, "features")
        ok = (
            result.status == "blocked"
            and result.error is not None
            and result.error.code == "rejected"
            and result.error.detail == "controlled_motion_reported_false"
            and features.get("controlled_motion") is False
            and result.data.get("autonomous_search") == "blocked"
            and result.data.get("motion_permission") is False
            and "motion_plan" not in result.data
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "autonomous search was not blocked",
            status="blocked",
            code="rejected",
            detail="controlled_motion_reported_false",
            trace=(
                "controlled_motion:false",
                "autonomous_search:blocked",
                "motion_plan:none",
                "motion_permission:false",
            ),
        )

    def _pi_report_missing(self) -> FeatureResult:
        drone, dog, _pi = load_envelopes()
        result = self._run((drone, dog))
        features = _map(result, "features")
        peers = _map(result, "peers")
        ok = (
            result.status == "blocked"
            and result.error is not None
            and result.error.code == "unavailable"
            and result.error.detail == "pi_report_missing"
            and features.get("rssi_receiver") is False
            and result.data.get("vision_only_dog_approach") == "available"
            and "pi" not in peers
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "missing pi report still armed rssi",
            status="blocked",
            code="unavailable",
            detail="pi_report_missing",
            trace=(
                "rssi_receiver:false",
                "reason:pi_report_missing",
                "vision_only_dog_approach:available",
                "motion_permission:false",
            ),
        )

    def _slam_unresolved(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        dog = with_features(dog, slam=False)
        result = self._run((drone, dog, pi))
        features = _map(result, "features")
        ok = (
            result.status == "ok"
            and features.get("lidar") is True
            and features.get("slam") is False
            and result.data.get("reactive_avoidance_eligible") is True
            and result.data.get("slam_eligible") is False
            and result.data.get("navigation_mode") == "unresolved"
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "slam false did not leave navigation unresolved",
            detail="navigation_mode:unresolved",
            trace=(
                "lidar:true",
                "slam:false",
                "reactive_avoidance_eligible:true",
                "navigation_mode:unresolved",
            ),
        )

    def _unvalidated_dog(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        dog = with_payload(dog, validated=False)
        result = self._run((drone, dog, pi))
        dog_peer = _map_at(_map(result, "peers"), "dog")
        reported = dog_peer.get("reported_features")
        armed = dog_peer.get("features")
        reported_motion = (
            isinstance(reported, Mapping) and reported.get("controlled_motion") is True
        )
        armed_motion = isinstance(armed, Mapping) and armed.get("controlled_motion") is True
        ok = (
            result.status == "ok"
            and result.data.get("dog_controlled_motion") is False
            and reported_motion
            and not armed_motion
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "unvalidated dog motion was armed",
            detail="dog_motion_disarmed",
            trace=(
                "validated:false",
                "dog_controlled_motion:false",
                "reported_dog_controlled_motion:true",
                "motion_armed:false",
            ),
        )

    def _replay_one_report(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        first = self._run((drone, dog, pi))
        second = self._run((drone,))
        replayed = second.data.get("replayed")
        ok = (
            first.status == "ok"
            and second.status == "ok"
            and first.data.get("armed_record_count") == 3
            and second.data.get("armed_record_count") == 3
            and replayed == ("msg-drone-capabilities",)
            and second.events == ()
            and len(first.events) == 3
            and second.data.get("motion_permission") is False
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "replay created another armed record",
            detail="single_armed_record",
            trace=(
                "replayed:msg-drone-capabilities",
                "armed_records:3",
                "motion_permission:false",
            ),
        )

    def _downward_camera_missing(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        drone = with_payload(drone, camera_ids=["front"])
        result = self._run((drone, dog, pi))
        features = _map(result, "features")
        reported = _map_at(_map(result, "peers"), "drone").get("reported_features")
        reasons = _map_at(_map(result, "peers"), "drone").get("disarm_reasons")
        reported_video = isinstance(reported, Mapping) and reported.get("downward_video") is True
        ok = (
            result.status == "ok"
            and features.get("downward_video") is False
            and features.get("controlled_motion") is True
            and reported_video
            and isinstance(reasons, tuple)
            and "downward_camera_id_missing" in reasons
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "downward video was armed without a downward camera",
            detail="downward_video_disarmed",
            trace=(
                "downward_video:false",
                "reported_downward_video:true",
                "reason:downward_camera_id_missing",
                "controlled_motion:true",
            ),
        )

    def _honest_control_fault(self) -> FeatureResult:
        drone, dog, pi = load_envelopes()
        drone = with_features(drone, controlled_motion=False, downward_video=False)
        settings = demo_settings(flight_intent="supervised")
        result = self._run((drone, dog, pi), settings)
        features = _map(result, "features")
        reported = _map_at(_map(result, "peers"), "drone").get("reported_features")
        reported_motion = (
            isinstance(reported, Mapping) and reported.get("controlled_motion") is False
        )
        ok = (
            result.status == "ok"
            and features.get("controlled_motion") is False
            and features.get("downward_video") is False
            and reported_motion
            and result.data.get("autonomous_search") == "not_requested"
            and result.data.get("continuation") == "supervised"
            and "motion_plan" not in result.data
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "reported control fault was changed",
            detail="controlled_motion_stays_false",
            trace=(
                "controlled_motion:false",
                "reported_controlled_motion:false",
                "downward_video:false",
                "autonomous_search:not_requested",
            ),
        )

    def _role_device_mismatch(self) -> FeatureResult:
        drone, _dog, _pi = load_envelopes()
        drone = with_payload(drone, device_id="dog-01")
        result = self._run((drone,))
        ok = (
            result.status == "failed"
            and result.error is not None
            and result.error.code == "rejected"
            and result.error.detail == "role_device_mismatch"
            and result.data.get("armed_record_count") == 0
            and result.data.get("motion_permission") is False
            and result.events == ()
            and self._device_calls() == 0
        )
        return self._done(
            ok,
            "mismatched role was admitted",
            status="failed",
            code="rejected",
            detail="role_device_mismatch",
            trace=(
                "rejected:role_device_mismatch",
                "armed_records:0",
                "motion_permission:false",
            ),
        )

    def _run(
        self,
        reports: tuple[Mapping[str, object], ...],
        settings: GroundSettings | None = None,
    ) -> FeatureResult:
        chosen = demo_settings() if settings is None else settings
        return self.ledger.apply(
            reports,
            chosen,
            demo_snapshot(chosen),
            None,
            cancelled=self.services.kernel.authority.cancelled,
        )

    def _device_calls(self) -> int:
        devices = getattr(self.services.adapters, "devices", None)
        calls = getattr(devices, "calls", ())
        if isinstance(calls, list):
            return len(calls)
        return 0

    def _done(
        self,
        ok: bool,
        failure: str,
        *,
        detail: str,
        trace: tuple[str, ...],
        status: str = "ok",
        code: str = "",
    ) -> FeatureResult:
        if self._device_calls() != 0:
            ok = False
            failure = "adapter call during capability admission"
        if not ok:
            return FeatureResult(
                "failed",
                self._foundation(detail=failure, trace=("check_failed", failure)),
                (),
                GroundError("validation_failed", failure, False),
            )
        error = None if status == "ok" else GroundError(code, detail, False)
        return FeatureResult(status, self._foundation(detail=detail, trace=trace), (), error)

    def _foundation(self, *, detail: str, trace: tuple[str, ...]) -> Mapping[str, object]:
        return freeze_map(
            {
                "authorized": False,
                "retained": False,
                "detail": detail,
                "trace": trace,
                "device_calls": self._device_calls(),
                "cleanup": (),
                "measurement_clock": "manual",
                "within_limit": True,
                "simulated": True,
                "live_call_count": 0,
                "slot": SLOT,
                "schema_version": SCHEMA,
            }
        )


def _failed(code: str, detail: str) -> FeatureResult:
    return FeatureResult(
        "failed",
        freeze_map(
            {
                "slot": SLOT,
                "schema_version": SCHEMA,
                "decision": "rejected",
                "continuation": "unresolved",
                "motion_permission": False,
                "session_armed": False,
                "reason": detail,
            }
        ),
        (),
        GroundError(code, detail, code == "cancelled"),
    )


def _map(result: FeatureResult, key: str) -> Mapping[str, object]:
    value = result.data.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def _map_at(mapping: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = mapping.get(key)
    if isinstance(value, Mapping):
        return value
    return {}


def _no_secret(result: FeatureResult) -> bool:
    text = repr(result.data) + repr(result.events) + repr(result.error)
    return "password" not in text.lower() and "super-secret" not in text.lower()
