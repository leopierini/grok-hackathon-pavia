"""Scripted RSSI homing cases. The harness runs the real provider against these."""

from __future__ import annotations

from patrol.ground.extensions.g22.policy import SCHEMA, SLOT
from patrol.ground.kernel.contracts import SimulationCase
from patrol.ground.kernel.validation import freeze_map

_MOTION = ("dog.run_route", "drone.inspect", "dog.capture_frame", "reasoner.assess_incident")
_TEARDOWN = (
    "release_barriers",
    "collect_tasks",
    "remove_owned_temp",
    "assert_no_socket",
)
_SAMPLES = "rssi-0,rssi-1,rssi-2,rssi-3,rssi-4,rssi-5"
_WINDOWS = "msg-pi-rssi-window,msg-pi-rssi-window-later"
_ONE = "rssi-0,rssi-1,rssi-2"
_ONE_WINDOW = "msg-pi-rssi-window"


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    def make(case_id: str, expected: dict[str, object]) -> SimulationCase:
        merged: dict[str, object] = {
            "status": "ok",
            "simulated": True,
            "live_call_count": 0,
            "device_calls": 0,
            "authorized": False,
            "slot": SLOT,
            "schema_version": SCHEMA,
            "measurement_clock": "manual",
            "within_limit": True,
        }
        merged.update(expected)
        return SimulationCase(
            task_id="GROUND-22",
            case_id=case_id,
            seed=seed,
            setup=freeze_map({"seed": seed}),
            stimuli=(),
            barriers=(),
            faults=(),
            expected=freeze_map(merged),
            forbidden_calls=_MOTION,
            teardown=_TEARDOWN,
        )

    return (
        make("select_forward", {"detail": "select:candidate-forward-01", "trace": _seen(
            "select", "aligned_improvement", "candidate-forward-01", "valid", _SAMPLES, _WINDOWS
        )}),
        make("empty_candidates", {"detail": "stop:no_safe_candidate", "trace": _seen(
            "stop", "no_safe_candidate", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("beacon_moving", {"detail": "stop:beacon_not_stable", "trace": _early(
            "stop", "beacon_not_stable"
        )}),
        make("quality_noisy", {"detail": "stop:noisy", "trace": _seen(
            "stop", "noisy", "", "noisy", _SAMPLES, _WINDOWS
        )}),
        make("single_window", {"detail": "hold:single_window", "trace": _seen(
            "hold", "single_window", "", "valid", _ONE, _ONE_WINDOW
        )}),
        make("active_command", {"detail": "stop:command_active", "trace": _early(
            "stop", "command_active"
        )}),
        make("strong_no_candidate", {"detail": "stop:no_safe_candidate", "trace": _seen(
            "stop",
            "no_safe_candidate",
            "",
            "valid",
            "rssi-s0,rssi-s1,rssi-s2,rssi-s3,rssi-s4,rssi-s5",
            "msg-pi-rssi-strong-a,msg-pi-rssi-strong-b",
        )}),
        make("budget_exhausted", {"detail": "stop:budget_exhausted", "trace": _early(
            "stop", "budget_exhausted"
        )}),
        make("motion_denied", {"detail": "stop:motion_not_allowed", "trace": _early(
            "stop", "motion_not_allowed"
        )}),
        make("flat_trend", {"detail": "stop:flat_trend", "trace": _seen(
            "stop", "flat_trend", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("hysteresis_hold", {"detail": "hold:hysteresis", "trace": _seen(
            "hold", "hysteresis", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("handoff_vision", {"detail": "handoff:dog_vision", "trace": _early(
            "handoff", "dog_vision"
        )}),
        make("quality_stale", {"detail": "stop:stale", "trace": _seen(
            "stop", "stale", "", "stale", _SAMPLES, _WINDOWS
        )}),
        make("quality_unavailable", {"detail": "stop:unavailable", "trace": _seen(
            "stop",
            "unavailable",
            "",
            "unavailable",
            _ONE,
            "msg-pi-rssi-window,msg-pi-rssi-window-none",
        )}),
        make("planner_blocked", {"detail": "stop:planner_blocked", "trace": _early(
            "stop", "planner_blocked", blocked=True
        )}),
        make("beacon_epoch", {"detail": "stop:beacon_epoch_mismatch", "trace": _seen(
            "stop", "beacon_epoch_mismatch", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("no_spatial_gradient", {"detail": "stop:no_spatial_gradient", "trace": _seen(
            "stop", "no_spatial_gradient", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("unaligned_candidate", {"detail": "stop:no_aligned_candidate", "trace": _seen(
            "stop", "no_aligned_candidate", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("range_field_rejected", {"detail": "stop:no_safe_candidate", "trace": _seen(
            "stop", "no_safe_candidate", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("select_reverse", {"detail": "select:candidate-back", "trace": _seen(
            "select", "aligned_improvement", "candidate-back", "valid", _SAMPLES, _WINDOWS
        )}),
        make("map_epoch", {"detail": "stop:map_epoch_mismatch", "trace": _seen(
            "stop", "map_epoch_mismatch", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("bssid_mismatch", {"detail": "stop:bssid_mismatch", "trace": _seen(
            "stop", "bssid_mismatch", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("vision_ambiguous", {"detail": "review:vision_ambiguous", "trace": _early(
            "review", "vision_ambiguous"
        )}),
        make("expired_candidate", {"detail": "stop:no_safe_candidate", "trace": _seen(
            "stop", "no_safe_candidate", "", "valid", _SAMPLES, _WINDOWS
        )}),
        make("sentinel_rejected", {
            "status": "failed",
            "error_code": "invalid_input",
            "error_detail": "rssi median 0 is not a no-signal value",
            "detail": "invalid:rssi_sentinel",
            "trace": ("no_range_m", "no_dog_command"),
        }),
        make("string_motion", {
            "status": "failed",
            "error_code": "invalid_input",
            "error_detail": "dog_motion_allowed must be a boolean",
            "detail": "invalid:dog_motion_allowed",
            "trace": ("no_range_m", "no_dog_command"),
        }),
    )


def _seen(
    action: str,
    reason: str,
    candidate_id: str,
    quality: str,
    sample_ids: str,
    window_ids: str,
) -> tuple[str, ...]:
    return _row(action, reason, candidate_id, "3", "1", quality, sample_ids, window_ids, False)


def _early(action: str, reason: str, *, blocked: bool = False) -> tuple[str, ...]:
    return _row(action, reason, "", "3", "1", "", "", "", blocked)


def _row(
    action: str,
    reason: str,
    candidate_id: str,
    beacon_epoch: str,
    map_epoch: str,
    quality: str,
    sample_ids: str,
    window_ids: str,
    blocked: bool,
) -> tuple[str, ...]:
    flag = "true" if blocked else "false"
    return (
        f"action:{action}",
        f"reason:{reason}",
        f"candidate_id:{candidate_id}",
        f"beacon_epoch:{beacon_epoch}",
        f"map_epoch:{map_epoch}",
        f"quality:{quality}",
        f"sample_ids:{sample_ids}",
        f"window_ids:{window_ids}",
        f"blocked:{flag}",
        "no_range_m",
        "no_dog_command",
    )
