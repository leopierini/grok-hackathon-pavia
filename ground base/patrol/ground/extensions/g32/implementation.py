"""Rehearsal feature. The harness validates foundation keys; the report file holds the mission."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g32.rehearsal import (
    SCHEMA,
    SLOT,
    Outcome,
    RehearsalError,
    distinct_ids,
    evaluate,
    load_case,
    overwrite_id,
    play,
)
from patrol.ground.kernel.contracts import (
    BaseServices,
    FeatureRequest,
    FeatureResult,
    GroundError,
    GroundEvent,
)
from patrol.ground.kernel.faults import GroundFault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.validation import freeze_map

_PLAYED = frozenset(
    {
        "happy_path",
        "unknown_landing",
        "blocked_planner",
        "noisy_rssi",
        "stale_frame",
        "uncontrolled_motion",
        "catalog_mission",
        "second_takeoff",
    }
)


class RehearsalFeature:
    def __init__(self, services: BaseServices) -> None:
        self.services = services
        self.observations: dict[str, object] = {}
        self.cleanup_paths: tuple[str, ...] = ()

    async def execute(self, request: FeatureRequest) -> FeatureResult:
        payload = request.payload
        name = request.name
        if name not in {"barrier_release", "barrier_cancelled"}:
            selected = payload.get("scenario")
            if isinstance(selected, str) and selected.strip():
                name = selected.strip()
        mode = payload.get("simulation_mode", "simulation")
        if request.name == "real_mode":
            name = "real_mode"
        if name == "barrier_release":
            return await self._barrier(cancel=False)
        if name == "barrier_cancelled":
            return await self._barrier(cancel=True)
        if _real_mode(name, mode, payload):
            return self._reject("invalid_input", "real_mode_rejected")
        if name == "string_simulated" or _bad_simulated(payload):
            return self._reject("invalid_input", "simulated_flag_rejected")
        seed = payload.get("seed", self.services.kernel.seed)
        if isinstance(seed, bool) or not isinstance(seed, int):
            return self._reject("invalid_input", "seed must be an integer")
        try:
            output = _output_root(self.services, payload)
            script = self.services.kernel.io.read_text(repo_root() / "demo" / "script.md").encode(
                "utf-8"
            )
            if name == "distinct_runs":
                return self._distinct(seed, output, script)
            if name == "overwrite_rejected":
                return self._overwrite(seed, output, script)
            if name not in _PLAYED:
                return self._reject("invalid_input", "unknown rehearsal case")
            outcome = evaluate(name, seed, play(load_case(self.services.kernel.io, name)))
            run = output / f"rehearsal-{name}-seed{seed}"
            self._publish(run, outcome, script)
            self.cleanup_paths = (str(run),)
            return self._from_outcome(outcome)
        except RehearsalError as exc:
            return self._reject(exc.code, exc.detail, recovery=exc.recovery)
        except GroundFault as exc:
            return self._reject(
                exc.error.code,
                exc.error.detail,
                recovery=exc.error.recovery_required,
            )

    def _distinct(self, seed: int, output: Path, script: bytes) -> FeatureResult:
        outcome = evaluate(
            "happy_path",
            seed,
            play(load_case(self.services.kernel.io, "happy_path")),
        )
        if outcome.status != "ok":
            return self._from_outcome(outcome)
        left, right = distinct_ids(seed)
        runs = (output / left, output / right)
        for run in runs:
            self._publish(run, outcome, script)
        self.cleanup_paths = tuple(str(run) for run in runs)
        trace = (f"directory:{left}", f"directory:{right}")
        return self._finish("ok", "two_directories", trace, code=None)

    def _overwrite(self, seed: int, output: Path, script: bytes) -> FeatureResult:
        outcome = evaluate(
            "happy_path",
            seed,
            play(load_case(self.services.kernel.io, "happy_path")),
        )
        if outcome.status != "ok":
            return self._from_outcome(outcome)
        run = output / overwrite_id(seed)
        self._publish(run, outcome, script)
        self.cleanup_paths = (str(run),)
        try:
            self._publish(run, outcome, script)
        except RehearsalError as exc:
            if exc.detail != "overwrite_rejected":
                return self._finish("failed", exc.detail, (), code=exc.code, recovery=exc.recovery)
            return self._finish(
                "failed",
                "overwrite_rejected",
                ("run_created", "overwrite_rejected"),
                code="rejected",
            )
        return self._finish("failed", "overwrite_accepted", (), code="validation_failed")

    def _publish(self, run: Path, outcome: Outcome, script: bytes) -> None:
        if run.exists():
            raise RehearsalError("rejected", "overwrite_rejected")
        io = self.services.kernel.io
        report = json.dumps(dict(outcome.report), indent=2) + "\n"
        io.write_bytes(run / "report.json", report.encode("utf-8"))
        lines = "".join(json.dumps(dict(item)) + "\n" for item in outcome.journal)
        io.write_bytes(run / "events.jsonl", lines.encode("utf-8"))
        io.write_bytes(run / "script.md", script)

    async def _barrier(self, *, cancel: bool) -> FeatureResult:
        flag = {"released": False, "cancelled": False}
        self.observations["released"] = flag
        barriers = self.services.kernel.barriers
        barriers.arm("rehearsal-hold")
        path = _output_root(self.services, {}) / "barrier-hold.txt"
        self.services.kernel.io.write_bytes(path, b"held\n")
        self.cleanup_paths = (str(path),)

        async def worker() -> None:
            try:
                await barriers.wait("rehearsal-hold")
                flag["released"] = True
            except asyncio.CancelledError:
                flag["cancelled"] = True
                raise

        task = asyncio.create_task(worker(), name="rehearsal-hold")
        self.services.kernel.tasks.retain("rehearsal-hold", task)
        await _park(self.services, "rehearsal-hold")
        if cancel:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return self._finish("ok", "barrier_cancelled", ("barrier_cancelled",), code=None)
        return self._finish(
            "ok",
            "barrier_released",
            ("barrier_held",),
            code=None,
            retained=True,
        )

    def _from_outcome(self, outcome: Outcome) -> FeatureResult:
        return self._finish(
            outcome.status,
            outcome.detail,
            outcome.trace,
            code=outcome.error_code,
            recovery=outcome.recovery,
        )

    def _reject(
        self,
        code: str,
        detail: str,
        *,
        recovery: bool = False,
        trace: tuple[str, ...] = (),
    ) -> FeatureResult:
        return self._finish("failed", detail, trace, code=code, recovery=recovery)

    def _finish(
        self,
        status: str,
        detail: str,
        trace: tuple[str, ...],
        *,
        code: str | None,
        recovery: bool = False,
        retained: bool = False,
    ) -> FeatureResult:
        error = None if status == "ok" or code is None else GroundError(code, detail, recovery)
        if status != "ok" and error is None:
            error = GroundError("validation_failed", detail, recovery)
        data = {
            "live_call_count": 0,
            "simulated": True,
            "trace": trace,
            "within_limit": True,
            "device_calls": _device_calls(self.services),
            "cleanup": self.cleanup_paths,
            "retained": retained,
            "measurement_clock": "manual",
            "slot": SLOT,
            "schema_version": SCHEMA,
            "authorized": False,
            "detail": detail,
        }
        event = GroundEvent(
            "simulation_completed",
            None,
            {"scenario": detail, "status": status},
        )
        return FeatureResult(status, freeze_map(data), (event,), error)


def create(services: BaseServices) -> RehearsalFeature:
    return RehearsalFeature(services)


def command_exit(result: FeatureResult) -> int:
    return 0 if result.status == "ok" else 1


def _real_mode(name: str, mode: object, payload: Mapping[str, object]) -> bool:
    return name == "real_mode" or mode == "real" or payload.get("simulated") is False


def _bad_simulated(payload: Mapping[str, object]) -> bool:
    if "simulated" not in payload:
        return False
    return not isinstance(payload["simulated"], bool)


def _output_root(services: BaseServices, payload: Mapping[str, object]) -> Path:
    raw = payload.get("output_root")
    if isinstance(raw, str) and raw.strip():
        return Path(raw)
    devices = getattr(services.adapters, "devices", None)
    output = getattr(devices, "output_dir", None)
    if isinstance(output, Path):
        return output
    raise RehearsalError("invalid_input", "output root is required")


def _device_calls(services: BaseServices) -> int:
    devices = getattr(services.adapters, "devices", None)
    calls = getattr(devices, "calls", None)
    if isinstance(calls, list):
        return len(calls)
    return 0


async def _park(services: BaseServices, name: str) -> None:
    for _ in range(5):
        await asyncio.sleep(0)
        if name in services.kernel.tasks.pending():
            return
    raise RehearsalError("internal", "barrier worker did not park", recovery=True)
