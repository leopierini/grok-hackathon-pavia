"""Run one simulated mission through the composed Ground providers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from patrol.contract import Frame, Incident
from patrol.ground.base import build_base_services
from patrol.ground.demo import MISSION, TARGET, Demo, _plain, _Stopped
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices
from patrol.ground.kernel.faults import GroundFault, fault
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.steps import SessionStopped, StepSession

Json = dict[str, Any]
Ready = Callable[[Demo, BaseServices, StepSession], None]

SCENARIO_TEXT: dict[str, str] = {
    "happy_path": "Readiness, scout, one drone primitive, beacon hold, RSSI, dog step, handoff, goal, then a separate landing.",
    "unknown_landing": "The goal can be reached while landing stays unknown and recovery stays required.",
    "blocked_planner": "The planner publishes no safe candidate, so the dog is not commanded.",
    "noisy_rssi": "A noisy RSSI window cannot guide a dog step.",
    "empty_rssi": "An empty RSSI window stays no-signal. Missing samples are not zero.",
    "stale_frame": "A stale drone frame is dropped and does not start vision.",
    "uncontrolled_motion": "Controlled drone motion is reported false.",
    "missing_pi_path": "The Pi data path is missing, so link readiness fails.",
    "halt": "The rehearsal itself requests halt before the dog step.",
    "link_loss": "Link loss latches safety without waiting for Grok.",
    "lease_expiry": "An expired lease does not grow a new move.",
    "slow_grok": "The Grok response is late. Halt during the wait is not cleared by the result.",
    "moving_beacon": "A moving beacon keeps the dog stopped.",
    "old_beacon_epoch": "An RSSI window from the previous beacon epoch is not comparable.",
    "ambiguous_target": "The dog camera reports a different track and cannot hand off.",
    "rejected_dog_command": "The dog rejects the completed step as expired. It is not repeated.",
    "missing_proximity": "Dog range is missing, so the goal stays unresolved.",
    "journal_fault": "The mission can finish while the journal writer fails. Unpublished is not saved.",
}
OPERATOR_SCENARIOS = tuple(SCENARIO_TEXT)


class OperatorDemo(Demo):
    def __init__(self, *args: Any, supervised: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.supervised = supervised
        self.late_model_withheld = False
        self._slow_once = False

    def prepare_message(self, message: Json) -> Json:
        payload = message.get("payload")
        if not isinstance(payload, dict):
            return message
        scenario = self.scenario
        kind = message.get("kind")
        if scenario == "moving_beacon" and message.get("message_id") == "msg-drone-held-after-step":
            beacon = payload.get("beacon")
            if isinstance(beacon, dict):
                beacon["hold_state"] = "moving"
        if scenario == "old_beacon_epoch" and kind == "rssi.window":
            payload["beacon_epoch"] = 3
        if scenario == "empty_rssi" and kind == "rssi.window":
            payload["samples"] = []
            payload["median_rssi_dbm"] = None
            payload["spread_db"] = None
            payload["quality"] = "unavailable"
        if scenario == "ambiguous_target" and kind == "vision.decision":
            frame_id = payload.get("frame_id")
            if isinstance(frame_id, str) and frame_id.startswith("dog-front"):
                detections = payload.get("detections")
                if isinstance(detections, list):
                    for item in detections:
                        if isinstance(item, dict):
                            item["track_id"] = "target-002"
                payload["reason"] = "Rehearsal injected a mismatched dog-camera track."
        if scenario == "rejected_dog_command" and kind == "command.ack" and message.get("source") == "dog":
            if payload.get("state") == "completed":
                payload["state"] = "rejected"
                payload["reason_code"] = "expired_command"
                payload["verified"] = False
                payload["detail"] = "Command expired before completion. No further move was issued."
        if scenario == "missing_proximity" and kind == "proximity.evidence":
            dog = payload.get("dog")
            if isinstance(dog, dict):
                dog["source"] = "lidar_associated"
                dog["association_valid"] = True
                dog["range_m"] = None
        return message

    async def message(self, raw: Mapping[str, object], *, restamp: bool = False) -> Json:
        if (
            self.scenario == "slow_grok"
            and not self._slow_once
            and isinstance(raw, Mapping)
            and raw.get("kind") == "vision.decision"
        ):
            self._slow_once = True
            self.waiting_for_model = True
            self.operator_notes.append({"kind": "vision_wait", "detail": "Grok response is still outstanding"})
            self._emit("vision_wait", {"detail": "Grok response is still outstanding"})
            try:
                for _ in range(20):
                    if self.should_halt is not None and self.should_halt():
                        self.late_model_withheld = True
                        break
                    await asyncio.sleep(0.05)
            finally:
                self.waiting_for_model = False
            if self.late_model_withheld:
                self._halt_skips = 3
                self.operator_notes.append(
                    {
                        "kind": "late_model",
                        "detail": "A model result arrived after halt and was not applied.",
                    }
                )
            else:
                self.advance(6)
                self.operator_notes.append(
                    {
                        "kind": "late_model",
                        "detail": "The manual clock passed the vision budget before the decision was stamped.",
                    }
                )
        return await super().message(raw, restamp=restamp)

    async def call(
        self,
        task: int,
        kind: str,
        name: str,
        payload: Json,
        *,
        require_ok: bool = True,
    ) -> Any:
        if self.late_model_withheld and task == 16 and name == "feature.v2_vision_decision":
            self.reason = "late model result did not clear halt"
            self.recovery_required = True
            self.phase = "ABORTED"
            self.late_model_withheld = False
            raise _Stopped(self.reason)
        proposal = payload.get("proposal") if isinstance(payload, Mapping) else None
        if self.supervised and task == 17 and name == "feature.v2_drone_command" and proposal is not None:
            self.reason = "supervised search; autonomous drone primitive withheld"
            self.operator_notes.append({"kind": "supervised", "detail": self.reason})
            await self.checkpoint("SCOUT", self.reason)
            raise _Stopped(self.reason)
        return await super().call(task, kind, name, payload, require_ok=require_ok)


def classify_phase(
    *,
    scenario: str,
    phase: str,
    reason: str,
    goal_reached: bool,
    landing_verified: bool,
    recovery_required: bool,
) -> str:
    if reason == "operator_halt" or scenario == "halt" or phase == "ABORTED":
        return "ABORTED"
    if scenario in {"link_loss", "lease_expiry"} or reason in {"link_loss", "expired_lease"}:
        return "FAULT"
    if goal_reached and not landing_verified:
        return "FAULT"
    if goal_reached and landing_verified and not recovery_required:
        return "DONE"
    if reason and phase == "IDLE":
        return "FAULT"
    return phase or "IDLE"


async def execute_simulation(
    output: Path,
    *,
    scenario: str,
    seed: int,
    transport: str,
    pace_s: float,
    supervised: bool,
    run_id: str,
    should_halt: Callable[[], bool],
    on_event: Callable[[str, Json], None],
    on_ready: Ready,
    dog_link: object | None = None,
    radio: Mapping[str, Any] | None = None,
) -> Json:
    if scenario not in OPERATOR_SCENARIOS or transport not in {"ethernet", "wifi"}:
        raise fault("invalid_input", "unknown rehearsal scenario or transport")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise fault("invalid_input", "seed must be an integer")
    output.mkdir(parents=True, exist_ok=False)
    services = await build_base_services(
        scenario="blocked_resolved",
        output_dir=output,
        journal_run_id=None,
    )
    clock = services.kernel.clock
    if not isinstance(clock, ManualClock):
        raise fault("unsafe_state", "operator rehearsal requires a manual clock")
    clock.advance(
        (datetime.fromisoformat("2026-11-04T13:00:10.210+00:00") - clock.utc_now()).total_seconds()
    )
    controls = StepSession([], session_id=run_id, clock=clock, mission_limit_s=600)
    services.kernel.authority.reset_generation("open simulated operator mission")
    services.state.open(
        Incident(
            MISSION,
            "display",
            TARGET,
            Frame(str(repo_root() / "fixtures/ground/g06/phone.jpg"), "phone", "display", None, True),
        ),
        make_settings(dog_transport=transport),
    )
    demo = OperatorDemo(
        services,
        output,
        scenario,
        seed,
        controls,
        supervised=supervised,
        dog_link=dog_link,
        radio=radio,
    )
    demo.pace_s = pace_s
    demo.should_halt = should_halt
    demo.on_event = on_event

    def request_safety(reason: str) -> None:
        services.safety.request(reason, demo.ticket)

    controls.bind_safety(lambda: services.kernel.authority.cancelled, request_safety)
    on_ready(demo, services, controls)
    cleanup_errors: list[str] = []
    report: Json | None = None
    try:
        if dog_link is not None:
            await dog_link.connect()  # type: ignore[attr-defined]
        try:
            await demo.run(transport)
        except _Stopped:
            pass
        except SessionStopped:
            demo.reason = demo.reason or "operator control halted"
            demo.recovery_required = True
            demo.phase = "ABORTED"
        except GroundFault as exc:
            demo.reason = exc.error.detail
            demo.recovery_required = True
            if demo.phase not in {"FAULT", "ABORTED"}:
                demo.phase = "FAULT"
        except Exception:
            demo.reason = demo.reason or "mission worker failed"
            demo.recovery_required = True
            demo.phase = "FAULT"
        demo.should_halt = None
        demo.phase = classify_phase(
            scenario=scenario,
            phase=demo.phase,
            reason=demo.reason,
            goal_reached=demo.goal_reached,
            landing_verified=demo.landing_verified,
            recovery_required=demo.recovery_required,
        )
        if scenario == "journal_fault":

            async def fail_flush() -> None:
                raise OSError("simulated journal writer failure")

            flush_name = "flush"
            setattr(services.journal, flush_name, fail_flush)
        flush = await demo.call(29, "stage", "flush", {}, require_ok=False)
        writer_failed = flush.status != "ok"
        published = False
        if writer_failed:
            demo.reason = (demo.reason + "; " if demo.reason else "") + "journal writer failed"
        elif scenario != "journal_fault":
            published_result = await demo.call(29, "stage", "publish", {}, require_ok=False)
            published = published_result.status == "ok"
        provider = demo.providers.get(29)
        provider_journal = _plain(getattr(provider, "records", []))
        metrics: Json = {}
        try:
            measured = await demo.call(
                31,
                "projection",
                "metrics",
                {
                    "journal": provider_journal,
                    "mission_start_monotonic": demo.mission_start * 1000,
                    "clock": {
                        "domain": "ground",
                        "quality": "manual_simulation",
                        "utc_pairs_allowed": False,
                    },
                    "run_id": MISSION,
                },
                require_ok=False,
            )
            metrics = _plain(measured.data)
        except (GroundFault, _Stopped, SessionStopped):
            metrics = {}
        outcome = "failed" if writer_failed or cleanup_errors else (
            "completed" if demo.goal_reached and demo.landing_verified and not demo.recovery_required else "unresolved"
        )
        report = {
            "schema_version": "ground-operator-rehearsal-v2",
            "run_id": run_id,
            "scenario": scenario,
            "seed": seed,
            "evidence": "simulated",
            "live_call_count": 0,
            "adapter_modes": {"dog": "fake", "drone": "fake", "grok": "fake"},
            "dog_transport": transport,
            "mission_id": MISSION,
            "mission_epoch": demo.ticket.epoch,
            "phase": demo.phase,
            "phase_history": demo.phase_history,
            "goal_reached": demo.goal_reached,
            "landing_verified": demo.landing_verified,
            "recovery_required": demo.recovery_required,
            "outcome": outcome,
            "reason": demo.reason,
            "provider_tasks": sorted(demo.providers),
            "trace": demo.trace,
            "commands": demo.commands,
            "messages": demo.messages,
            "notes": demo.operator_notes,
            "metrics": metrics,
            "writer_failed": writer_failed,
            "published": published,
            "provider_journal": provider_journal,
            "step_control": controls.get_snapshot(),
            "external_adapter_factories": "not supplied; v2 messages are simulated",
            "physical_acceptance": "not performed",
            "cleanup_errors": cleanup_errors,
        }
        if radio is not None:
            report["radio"] = radio
        if demo.dog_motion_log is not None:
            report["dog_ethernet"] = demo.dog_motion_log
            if demo.dog_motion_log.get("sent") is True:
                report["evidence"] = "dog-ethernet"
                report["adapter_modes"] = {"dog": "ethernet", "drone": "fake", "grok": "fake"}
        if not writer_failed:
            await services.journal.publish(
                {key: value for key, value in report.items() if key not in {"trace", "commands", "messages", "provider_journal"}}
            )
        return report
    finally:
        if dog_link is not None:
            try:
                await dog_link.close()  # type: ignore[attr-defined]
            except Exception:
                cleanup_errors.append("dog_close_failed")
        await controls.close()
        services.kernel.barriers.release_all()
        await services.kernel.tasks.collect(deadline=2)
        for closer in (services.adapters.close, services.console.close, services.journal.close):
            try:
                await closer()
            except Exception:
                cleanup_errors.append("close_failed")
        if report is not None:
            report["cleanup_errors"] = cleanup_errors
            if cleanup_errors:
                report["outcome"] = "failed"
            (output / "report.json").write_text(
                json.dumps(report, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
