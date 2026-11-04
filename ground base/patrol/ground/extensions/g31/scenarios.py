"""Scripted timing cases. The harness calls the real metrics provider."""

from __future__ import annotations

from collections.abc import Mapping

from patrol.ground.extensions.g31.metrics import METRIC_NAMES
from patrol.ground.extensions.g31.samples import (
    ACTIVATION_MS,
    DOG_ACCEPT_MS,
    DOG_CAMERA_MS,
    DOG_COMPLETE_MS,
    DOG_ISSUE_MS,
    DOG_RUN_MS,
    DRONE_DECISION_MS,
    DRONE_FRAME_MS,
    DRONE_REQUEST_MS,
    GOAL_MS,
    HOLD_MS,
    LAND_ACCEPT_MS,
    LAND_ISSUE_MS,
    LAND_RUN_MS,
    LANDING_MS,
    PROXIMITY_MS,
    TARGET_MS,
    beacon_pair,
    empty_journal,
    full_journal,
    mismatched_clocks,
    request_payload,
    with_extra_drop,
    without_dog_camera,
    without_landing,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    SimulationCase,
)
from patrol.ground.kernel.validation import freeze_map

CASE_IDS = (
    "full_journal",
    "landing_unverified",
    "dog_acquisition_missing",
    "dropped_frames",
    "empty_journal",
    "mismatched_clocks",
    "recompute",
    "beacon_reset",
)

_FORBIDDEN = (
    "connect",
    "prepare",
    "run_route",
    "capture_frame",
    "inspect",
    "land",
    "halt",
    "assess_incident",
)


def cases(seed: int = 0) -> tuple[SimulationCase, ...]:
    traces = {
        "full_journal": METRIC_NAMES + ("filled",),
        "landing_unverified": ("landing_null", "landing_unverified", "detection_filled"),
        "dog_acquisition_missing": ("acquisition_null", "detection_filled"),
        "dropped_frames": ("dropped", "2"),
        "empty_journal": ("empty_journal", "nulls"),
        "mismatched_clocks": ("rejected", "ground", "drone_monotonic"),
        "recompute": ("identical",),
        "beacon_reset": ("resets", "1"),
    }
    built: list[SimulationCase] = []
    for case_id in CASE_IDS:
        built.append(
            SimulationCase(
                task_id="GROUND-31",
                case_id=case_id,
                seed=seed,
                setup=freeze_map({"journal": "fixture", "clock_domain": "ground"}),
                stimuli=(),
                barriers=(),
                faults=(),
                expected=freeze_map(_expected(case_id, traces[case_id])),
                forbidden_calls=_FORBIDDEN,
                teardown=("release_barriers", "collect_tasks", "remove_owned_temp"),
            )
        )
    return tuple(built)


async def run_case(services: BaseServices, case_id: str, seed: int) -> dict[str, object]:
    from patrol.ground.extensions.g31.implementation import create

    feature = create(services)
    failures: list[str] = []
    trace: tuple[str, ...] = ("check_failed", case_id)
    if not isinstance(seed, int):
        failures.append("seed must be an integer")
    try:
        if case_id == "full_journal":
            trace = METRIC_NAMES + ("filled",)
            failures.extend(await _expect_full(feature))
        elif case_id == "landing_unverified":
            trace = ("landing_null", "landing_unverified", "detection_filled")
            failures.extend(await _expect_landing(feature))
        elif case_id == "dog_acquisition_missing":
            trace = ("acquisition_null", "detection_filled")
            failures.extend(await _expect_camera(feature))
        elif case_id == "dropped_frames":
            trace = ("dropped", "2")
            failures.extend(await _expect_drops(feature))
        elif case_id == "empty_journal":
            trace = ("empty_journal", "nulls")
            failures.extend(await _expect_empty(feature))
        elif case_id == "mismatched_clocks":
            trace = ("rejected", "ground", "drone_monotonic")
            failures.extend(await _expect_clocks(feature))
        elif case_id == "recompute":
            trace = ("identical",)
            failures.extend(await _expect_recompute(feature))
        elif case_id == "beacon_reset":
            trace = ("resets", "1")
            failures.extend(await _expect_beacon(feature))
        else:
            failures.append(f"unknown case {case_id}")
    except Exception as exc:  # noqa: BLE001 — one case must record its own failure
        failures.append(f"exception {type(exc).__name__}: {exc}")
    calls = _calls(services)
    if calls:
        failures.append("device call " + ",".join(calls))
    return {"passed": not failures, "failures": failures, "trace": trace}


async def _expect_full(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(full_journal()))
    if result.status != "ok":
        return [_detail(result)]
    data = result.data
    failures: list[str] = []
    _expect_interval(failures, data, "mission_start_to_drone_target_s", 0, TARGET_MS)
    _expect_interval(failures, data, "detection_to_stable_hold_s", TARGET_MS, HOLD_MS)
    _expect_interval(failures, data, "stable_hold_to_dog_activation_s", HOLD_MS, ACTIVATION_MS)
    _expect_interval(failures, data, "dog_activation_to_dog_camera_s", ACTIVATION_MS, DOG_CAMERA_MS)
    _expect_interval(failures, data, "mission_start_to_proximity_s", 0, PROXIMITY_MS)
    _expect_interval(failures, data, "dog_activation_to_proximity_s", ACTIVATION_MS, PROXIMITY_MS)
    _expect_interval(failures, data, "goal_to_verified_landing_s", GOAL_MS, LANDING_MS)
    _expect_count(failures, data, "dropped_stale_frame_count", 1)
    _expect_count(failures, data, "beacon_epoch_resets", 1)
    _expect_count(failures, data, "no_progress_stops", 1)
    _expect_count(failures, data, "blocked_candidate_events", 1)
    _expect_pair(failures, data, "vision-drone-001", (DRONE_DECISION_MS - DRONE_REQUEST_MS) / 1000)
    _expect_age(failures, data, "vision-drone-001", (DRONE_DECISION_MS - DRONE_FRAME_MS) / 1000)
    _expect_command(
        failures,
        data,
        "cmd-dog-001",
        (DOG_ACCEPT_MS - DOG_ISSUE_MS) / 1000,
        (DOG_RUN_MS - DOG_ISSUE_MS) / 1000,
        (DOG_COMPLETE_MS - DOG_ISSUE_MS) / 1000,
    )
    _expect_command(
        failures,
        data,
        "cmd-drone-land-001",
        (LAND_ACCEPT_MS - LAND_ISSUE_MS) / 1000,
        (LAND_RUN_MS - LAND_ISSUE_MS) / 1000,
        (LANDING_MS - LAND_ISSUE_MS) / 1000,
    )
    accuracy = _nested(data, "metrics", "model_accuracy")
    if (
        not isinstance(accuracy, dict)
        or accuracy.get("unavailable_reason") != "no_labeled_evaluation"
    ):
        failures.append("accuracy was filled without a labeled manifest")
    if data.get("run_id") != "demo-20261104-001":
        failures.append("run id missing")
    if data.get("evidence") != "simulated":
        failures.append("evidence was not labeled simulated")
    names = data.get("metric_names")
    if list(names) != list(METRIC_NAMES) if isinstance(names, list) else True:
        failures.append("metric names missing")
    return failures


async def _expect_landing(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(without_landing()))
    if result.status != "ok":
        return [_detail(result)]
    failures: list[str] = []
    row = _nested(result.data, "metrics", "goal_to_verified_landing_s")
    if (
        not isinstance(row, dict)
        or row.get("seconds") is not None
        or row.get("unavailable_reason") != "landing_unverified"
    ):
        failures.append("landing latency was not null")
    _expect_interval(failures, result.data, "mission_start_to_drone_target_s", 0, TARGET_MS)
    return failures


async def _expect_camera(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(without_dog_camera()))
    if result.status != "ok":
        return [_detail(result)]
    failures: list[str] = []
    row = _nested(result.data, "metrics", "dog_activation_to_dog_camera_s")
    if not isinstance(row, dict) or row.get("seconds") is not None:
        failures.append("dog acquisition was not null")
    if isinstance(row, dict) and row.get("unavailable_reason") != "dog_camera_acquisition_missing":
        failures.append("dog acquisition reason missing")
    _expect_interval(failures, result.data, "mission_start_to_drone_target_s", 0, TARGET_MS)
    _expect_interval(failures, result.data, "detection_to_stable_hold_s", TARGET_MS, HOLD_MS)
    return failures


async def _expect_drops(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(with_extra_drop()))
    if result.status != "ok":
        return [_detail(result)]
    failures: list[str] = []
    _expect_count(failures, result.data, "dropped_stale_frame_count", 2)
    _expect_pair(
        failures, result.data, "vision-drone-001", (DRONE_DECISION_MS - DRONE_REQUEST_MS) / 1000
    )
    return failures


async def _expect_empty(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(empty_journal()))
    if result.status != "ok":
        return [_detail(result)]
    failures: list[str] = []
    metrics = result.data.get("metrics")
    if not isinstance(metrics, dict):
        return ["metrics missing"]
    if _contains_zero(metrics):
        failures.append("empty journal used a zero")
    for name in (
        "mission_start_to_drone_target_s",
        "goal_to_verified_landing_s",
        "dog_activation_to_dog_camera_s",
    ):
        row = metrics.get(name)
        if (
            not isinstance(row, dict)
            or row.get("seconds") is not None
            or row.get("unavailable_reason") != "empty_journal"
        ):
            failures.append(f"{name} was not an empty-journal null")
    return failures


async def _expect_clocks(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(mismatched_clocks()))
    if result.status != "failed" or result.error is None:
        return ["mismatched clocks were not rejected"]
    if result.error.code != "rejected":
        return [result.error.code]
    detail = result.error.detail
    if "ground" not in detail or "drone_monotonic" not in detail:
        return [detail]
    if "metrics" in result.data:
        return ["rejected clocks still returned a duration"]
    return []


async def _expect_recompute(feature: object) -> list[str]:
    payload = request_payload(full_journal())
    first = await _measure(feature, payload)
    second = await _measure(feature, payload)
    if first.status != "ok" or second.status != "ok":
        return ["recompute did not succeed"]
    if dict(first.data) != dict(second.data):
        return ["recompute changed the metrics"]
    return []


async def _expect_beacon(feature: object) -> list[str]:
    result = await _measure(feature, request_payload(beacon_pair()))
    if result.status != "ok":
        return [_detail(result)]
    failures: list[str] = []
    _expect_count(failures, result.data, "beacon_epoch_resets", 1)
    return failures


async def _measure(feature: object, payload: dict[str, object]) -> FeatureResult:
    execute = getattr(feature, "execute", None)
    if not callable(execute):
        raise RuntimeError("provider has no execute method")
    result: object = await execute(
        FeatureRequest("projection", "feature.v2_metrics", None, freeze_map(payload))
    )
    if not isinstance(result, FeatureResult):
        raise RuntimeError("provider did not return a FeatureResult")
    return result


def _expected(case_id: str, trace: tuple[str, ...]) -> dict[str, object]:
    return {
        "status": "ok",
        "simulated": True,
        "live_call_count": 0,
        "device_calls": 0,
        "authorized": False,
        "retained": False,
        "within_limit": True,
        "measurement_clock": "manual",
        "slot": "feature.v2_metrics",
        "schema_version": "ground-task-v2",
        "detail": case_id,
        "trace": trace,
    }


def _expect_interval(
    failures: list[str],
    data: Mapping[str, object],
    name: str,
    start_ms: int,
    end_ms: int,
) -> None:
    row = _nested(data, "metrics", name)
    expected = (end_ms - start_ms) / 1000
    if (
        not isinstance(row, dict)
        or row.get("seconds") != expected
        or row.get("unavailable_reason") is not None
    ):
        failures.append(f"{name} expected {expected} got {row!r}")


def _expect_count(failures: list[str], data: Mapping[str, object], name: str, count: int) -> None:
    row = _nested(data, "metrics", name)
    if not isinstance(row, dict) or row.get("count") != count:
        failures.append(f"{name} expected {count} got {row!r}")


def _expect_pair(
    failures: list[str], data: Mapping[str, object], request_id: str, seconds: float
) -> None:
    found = _row_by_id(_nested(data, "metrics", "vision_latency_s"), "pairs", request_id)
    if (
        not isinstance(found, dict)
        or found.get("seconds") != seconds
        or found.get("unavailable_reason") is not None
    ):
        failures.append(f"vision {request_id} expected {seconds} got {found!r}")


def _expect_age(
    failures: list[str], data: Mapping[str, object], request_id: str, seconds: float
) -> None:
    found = _row_by_id(_nested(data, "metrics", "evidence_age_at_use_s"), "samples", request_id)
    if not isinstance(found, dict) or found.get("seconds") != seconds:
        failures.append(f"age {request_id} expected {seconds} got {found!r}")


def _expect_command(
    failures: list[str],
    data: Mapping[str, object],
    command_id: str,
    accept_s: float,
    run_s: float,
    complete_s: float,
) -> None:
    found = _row_by_id(
        _nested(data, "metrics", "command_latency_s"), "commands", command_id, "command_id"
    )
    if not isinstance(found, dict):
        failures.append(f"command {command_id} missing")
        return
    if (
        found.get("accept_s") != accept_s
        or found.get("run_s") != run_s
        or found.get("complete_s") != complete_s
    ):
        failures.append(f"command {command_id} got {found!r}")


def _row_by_id(
    block: object,
    key: str,
    identity: str,
    field: str = "request_id",
) -> object:
    if not isinstance(block, dict):
        return None
    rows = block.get(key)
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get(field) == identity:
            return row
    return None


def _nested(data: Mapping[str, object], *keys: str) -> object:
    current: object = data
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _contains_zero(value: object) -> bool:
    if value == 0:
        return True
    if isinstance(value, dict):
        return any(_contains_zero(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_zero(item) for item in value)
    return False


def _calls(services: BaseServices) -> list[str]:
    devices = getattr(services.adapters, "devices", None)
    found = getattr(devices, "calls", None)
    if isinstance(found, list):
        return [str(item) for item in found]
    return []


def _detail(result: FeatureResult) -> str:
    if result.error is not None:
        return result.error.detail
    return result.status
