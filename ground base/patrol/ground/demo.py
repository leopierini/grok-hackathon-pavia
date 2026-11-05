"""Gate C: compose the real Ground policies over explicitly simulated v2 peers.

This is a behavioral rehearsal, not a robot transport or a flight simulator.
Every policy is discovered from its owned manifest. No stage-policy double is
registered. Device messages, link probes, images, and geometry are synthetic.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

from patrol.contract import Frame, Incident
from patrol.ground.base import build_base_services
from patrol.ground.kernel.clock import ManualClock
from patrol.ground.kernel.contracts import BaseServices, FeaturePort, FeatureRequest, FeatureResult
from patrol.ground.kernel.faults import fault
from patrol.ground.kernel.features import FeatureMap
from patrol.ground.kernel.loader import discover, load_callable
from patrol.ground.kernel.paths import repo_root
from patrol.ground.kernel.settings import make_settings
from patrol.ground.steps import (
    SessionStopped,
    StepAttempt,
    StepRejected,
    StepSession,
    StepSpec,
)

SCENARIOS = (
    "happy_path",
    "unknown_landing",
    "blocked_planner",
    "noisy_rssi",
    "stale_frame",
    "uncontrolled_motion",
    "missing_pi_path",
    "halt",
    "link_loss",
    "lease_expiry",
)
MISSION = "demo-20261104-001"
TARGET = "A person in the operator-marked closed demo area."
Json = dict[str, Any]


def _load(relative: str) -> Json:
    value: object = json.loads((repo_root() / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise fault("invalid_input", "rehearsal input must be an object")
    return value


def _plain(value: object) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


class _Stopped(Exception):
    pass


class Demo:
    def __init__(
        self,
        services: BaseServices,
        output: Path,
        scenario: str,
        seed: int,
        controls: StepSession | None = None,
        budgets: Mapping[int, tuple[float, float]] | None = None,
        dog_link: object | None = None,
        radio: Mapping[str, Json] | None = None,
        grok: str = "fake",
    ) -> None:
        if grok not in {"fake", "real"}:
            raise fault("invalid_input", "grok mode must be fake or real")
        self.services = services
        self.output = output
        self.scenario = scenario
        self.seed = seed
        self.grok = grok
        self.live_calls = 0
        self._vision_busy = False
        self.providers: dict[int, FeaturePort] = {}
        self.trace: list[Json] = []
        self.messages: list[Json] = []
        self.sequences: dict[str, int] = {}
        self.goal_reached = False
        self.landing_verified = False
        self.recovery_required = False
        self.reason = ""
        self.commands: list[Json] = []
        self.mission_start = services.kernel.clock.monotonic()
        self.context = _load("fixtures/ground/integration/context.json")
        self.ticket = services.kernel.authority.issue(MISSION, "v2-demo")
        self.controls = controls
        self.budgets = budgets or {}
        self.call_counts: dict[int, int] = {}
        self.pace_s = 0.0
        self.should_halt: Callable[[], bool] | None = None
        self.on_event: Callable[[str, Json], None] | None = None
        self.phase = "IDLE"
        self.phase_history: list[Json] = []
        self.operator_notes: list[Json] = []
        self.waiting_for_model = False
        self._halt_skips = 0
        self.dog_link = dog_link
        self.radio = dict(radio) if radio is not None else None
        self.dog_motion_log: Json | None = None

    @property
    def now(self) -> str:
        return self.services.kernel.clock.utc_now().isoformat().replace("+00:00", "Z")

    def advance(self, seconds: float) -> None:
        clock = self.services.kernel.clock
        if not isinstance(clock, ManualClock):
            raise fault("unsafe_state", "rehearsal requires a manual clock")
        clock.advance(seconds)

    def prepare_message(self, message: Json) -> Json:
        return message

    def _emit(self, kind: str, payload: Json) -> None:
        if self.on_event is not None:
            self.on_event(kind, payload)

    async def _halt_gate(self) -> None:
        if self._halt_skips > 0:
            self._halt_skips -= 1
            return
        if self.should_halt is not None and self.should_halt():
            self.reason = "operator_halt"
            self.recovery_required = True
            self.phase = "ABORTED"
            self._emit("halt", {"accepted": True, "delivered": None, "phase": "ABORTED"})
            raise _Stopped("operator_halt")

    async def _pace(self) -> None:
        remaining = self.pace_s
        if remaining <= 0:
            return
        while remaining > 0:
            await self._halt_gate()
            step = min(0.05, remaining)
            await asyncio.sleep(step)
            remaining -= step

    async def checkpoint(self, phase: str, reason: str) -> None:
        await self._halt_gate()
        if phase != self.phase:
            self.phase = phase
            entry: Json = {"phase": phase, "reason": reason, "at": self.now}
            self.phase_history.append(entry)
            self._emit("phase", entry)
        await self._pace()

    async def call(
        self,
        task: int,
        kind: str,
        name: str,
        payload: Json,
        *,
        require_ok: bool = True,
    ) -> FeatureResult:
        await self._halt_gate()
        if task not in {11, 27, 28, 29, 31, 32}:
            self.services.kernel.authority.require_current(self.ticket)
        request = FeatureRequest(
            kind,
            name,
            None if task in {28, 29, 31, 32} else self.ticket,
            payload,
        )
        if self.controls is not None and task not in {28, 29, 31, 32}:
            self.call_counts[task] = self.call_counts.get(task, 0) + 1
            key = f"g{task}.{self.call_counts[task]:03}"
            wait, hard = self.budgets.get(task, (3.0, 30.0))
            # Only read-only link checks and navigation planning may be replayed.
            # Wire ingestion, approvals, trackers and evidence stores have side effects.
            self.controls.add_step(
                StepSpec(
                    key,
                    f"G{task}: {name}",
                    wait,
                    hard,
                    "idempotent" if task in {20, 30} else "never",
                )
            )

            async def operation(_: StepAttempt) -> FeatureResult:
                value = await self.providers[task].execute(request)
                if require_ok and value.status != "ok":
                    self.reason = (
                        f"task {task}: {value.error.detail if value.error else value.status}"
                    )
                    raise StepRejected(self.reason)
                return value

            try:
                result = cast(FeatureResult, await self.controls.run_step(key, operation))
            except StepRejected as exc:
                raise _Stopped(self.reason) from exc
        else:
            result = await self.providers[task].execute(request)
        self.trace.append(
            {
                "task": task,
                "name": name,
                "status": result.status,
                "error": None if result.error is None else result.error.detail,
                "monotonic_s": self.services.kernel.clock.monotonic(),
                "data": _plain(result.data),
            }
        )
        if require_ok and result.status != "ok":
            self.reason = f"task {task}: {result.error.detail if result.error else result.status}"
            self._emit(
                "provider",
                {
                    "task": task,
                    "name": name,
                    "status": result.status,
                    "error": self.reason,
                },
            )
            raise _Stopped(self.reason)
        self._emit(
            "provider",
            {
                "task": task,
                "name": name,
                "status": result.status,
                "error": None if result.error is None else result.error.detail,
            },
        )
        return result

    async def message(self, raw: Mapping[str, object], *, restamp: bool = False) -> Json:
        await self._halt_gate()
        message: Json = self.prepare_message(_plain(raw))
        if message.get("simulated") is not True:
            raise fault("unsafe_state", "rehearsal refuses live evidence")
        source = str(message["source"])
        self.sequences[source] = self.sequences.get(source, 0) + 1
        message["seq"] = self.sequences[source]
        if restamp:
            message["sent_at"] = self.now
        await self.call(
            11,
            "guard",
            "v2_envelope",
            {
                "message": json.dumps(message),
                "expected_source": source,
                "expected_destination": message["destination"],
                "epoch": self.ticket.epoch,
            },
        )
        await self.call(29, "stage", "accept", {"envelope": message})
        self.messages.append(message)
        self._emit(
            "message",
            {
                "message_id": message.get("message_id"),
                "kind": message.get("kind"),
                "source": message.get("source"),
            },
        )
        await self._pace()
        return message

    async def wire(self, name: str, *, restamp: bool = False) -> Json:
        return await self.message(_load(f"contracts/examples/{name}.json"), restamp=restamp)

    async def run(self, transport: str) -> None:
        manifests = discover(repo_root() / "patrol/ground/extensions")
        for manifest in manifests[10:]:
            provider = cast(FeaturePort, load_callable(manifest, "factory")(self.services))
            self.providers[int(manifest.task_id[-2:])] = provider
            registry = self.services.kernel.features
            if not isinstance(registry, FeatureMap):
                raise fault("unsafe_state", "rehearsal requires the concrete feature registry")
            registry.register(manifest.slot, provider)
        await self.call(29, "stage", "open", {"run_id": "mission", "output_root": str(self.output)})
        probe = _load(f"fixtures/ground/g30/probe-{transport}.json")
        if self.scenario == "missing_pi_path":
            probe["pi_path"] = None
        # Acceptance is synthetic, and never upgrades to physical acceptance.
        probe["tether_accepted"] = _load("fixtures/ground/g30/tether-acceptance.json")["accepted"]
        probe["wifi_accepted"] = _load("fixtures/ground/g30/wifi-acceptance.json")["accepted"]
        probe["messages"] = {
            "dog": _load("contracts/examples/dog-capabilities.json"),
            "drone": _load("contracts/examples/drone-capabilities.json"),
            "pi": _load("contracts/examples/pi-heartbeat.json"),
        }
        await self.checkpoint("CONNECT", "checking dog, drone, and Pi links")
        await self.call(30, "guard", "check", {"probe": probe})
        reports = [await self.wire(f"{role}-capabilities") for role in ("drone", "dog", "pi")]
        if self.scenario == "uncontrolled_motion":
            reports[0]["payload"]["features"]["controlled_motion"] = False
        settings = make_settings(
            dog_transport=transport,
            profile_identity=f"dog.{transport}",
            adapter_configs={
                "dog": {"device_id": "dog-01", "transport": transport},
                "drone": {"device_id": "drone-01", "flight_intent": "autonomous_search"},
                "pi": {"device_id": "pi-01", "required": True},
                "router": {"device_id": "router-back", "networking": "failed"},
            },
        )
        capabilities = await self.call(
            12,
            "stage",
            "admit",
            {
                "reports": tuple(reports),
                "settings": settings,
                "snapshot": self.services.state.snapshot(),
            },
        )
        self.context["drone_approval"]["capabilities"] = reports[0]
        observation = _load("contracts/examples/drone-observation.json")
        frame = _load("fixtures/ground/g14/accepted/downward.json")
        observation["payload"]["frame"] = frame
        observation = await self.message(observation)
        await self.call(
            13,
            "stage",
            "drone.observation",
            {
                "envelope": observation,
                "capability": reports[0],
                "mission_epoch": self.ticket.epoch,
            },
        )
        checked = await self.call(
            14,
            "stage",
            "feature.v2_frame",
            {
                "frame": frame,
                "zone": "display",
                "mission_id": MISSION,
                "epoch": 1,
                "store_root": str(repo_root() / "fixtures/ground/g14/store"),
            },
        )
        if self.scenario == "stale_frame":
            self.advance(4)
        await self.checkpoint("SCOUT", "scheduling a drone vision request")
        schedule = await self.call(
            15,
            "stage",
            "schedule",
            {
                "frame": frame,
                "stage": "drone_search",
                "target_description": TARGET,
                "settings": self._schedule_settings(),
                "active_track_id": None,
                "clock_error_ms": 0,
            },
        )
        request = schedule.data.get("message")
        if not isinstance(request, Mapping):
            self.reason = "stale frame dropped; no vision request"
            raise _Stopped(self.reason)
        request = await self.message(request)
        self.advance(random.Random(self.seed).uniform(0.01, 0.02))
        decision = await self._drone_vision_decision(request, frame)
        decision = await self.message(decision, restamp=True)
        accepted = await self.call(
            16,
            "stage",
            "feature.v2_vision_decision",
            {
                "decision": decision,
                "request": request,
                "current_camera_epoch": 1,
            },
        )
        if accepted.data.get("track_id") != "target-001":
            raise fault("validation_failed", "vision did not bind the staged track")
        await self.wire("event-drone_target_acquired", restamp=True)
        proposal = accepted.data.get("proposal")
        if not isinstance(proposal, Mapping):
            self.reason = "vision withheld a calibrated proposal"
            raise _Stopped(self.reason)
        proposal = await self.message(proposal)
        context = self.context["drone_approval"]
        context.update(
            {
                "proposal": proposal,
                "observation": observation,
                "evaluated_at": self.now,
                "calibration": checked.data["uncalibrated"] is False,
                "armed": capabilities.data["autonomous_search"] == "armed",
                "seed": self.seed,
            }
        )
        await self.checkpoint("TRACK", "approving one drone primitive")
        approved = await self.call(17, "stage", "feature.v2_drone_command", context)
        command = await self.message(cast(Mapping[str, object], approved.data["command"]))
        self.commands.append(command)
        await self.call(
            18,
            "command",
            "register",
            {
                "command": command,
                "reply_deadline_monotonic": self.services.kernel.clock.monotonic() + 1,
            },
        )
        moving = await self.call(
            19,
            "guard",
            "feature.v2_beacon",
            {
                "armed_bssid": "02:00:00:00:00:01",
                "observation": observation,
                "drone_command": command,
                "drone_command_running": True,
                "drone_command_status": "running",
                "previous_beacon_epoch": 3,
            },
        )
        if moving.data["dog_motion_allowed"] is not False:
            raise fault("unsafe_state", "dog was allowed to move during a drone step")
        for state in ("accepted", "running", "completed"):
            ack = _load(f"contracts/examples/drone-ack-{state}.json")
            ack["correlation_id"] = command["message_id"]
            ack["payload"]["command_id"] = command["payload"]["command_id"]
            ack = await self.message(ack, restamp=True)
            await self.call(18, "command", "apply_ack", {"command": command, "ack": ack})
        await self.checkpoint("HOLD", "requiring a new stable beacon hold")
        observation["message_id"] = "msg-drone-held-after-step"
        observation["payload"]["beacon"]["beacon_epoch"] = 4
        observation["payload"]["beacon"]["verified_at"] = self.now
        observation = await self.message(observation, restamp=True)
        hold = await self.call(
            19,
            "guard",
            "feature.v2_beacon",
            {
                "armed_bssid": "02:00:00:00:00:01",
                "observation": observation,
                "drone_command": command,
                "drone_command_running": False,
                "drone_command_status": "completed",
                "previous_beacon_epoch": 3,
            },
        )
        await self.approach(transport, reports[1], hold)

    async def approach(self, transport: str, dog_capability: Json, hold: FeatureResult) -> None:
        await self.checkpoint("HOME", "comparing RSSI only for the current beacon epoch")
        homing = self.context["homing"]
        homing["beacon"]["beacon_epoch"] = hold.data["beacon_epoch"]
        homing["dog_motion_allowed"] = hold.data["dog_motion_allowed"]
        homing["now"] = self.now
        rssi = self.context["rssi"]
        rssi["beacon"].update(
            {
                "beacon_epoch": hold.data["beacon_epoch"],
                "epoch": hold.data["beacon_epoch"],
            }
        )
        windows = []
        for window in homing["windows"]:
            window["payload"]["beacon_epoch"] = hold.data["beacon_epoch"]
            if self.scenario == "noisy_rssi":
                window["payload"]["quality"] = "noisy"
            window = await self.message(window)
            windows.append(window)
            rssi.update({"window": window})
            result = await self.call(21, "guard", "validate", rssi)
            if result.data.get("follow") is not True:
                self.reason = "RSSI evidence cannot guide a step"
                raise _Stopped(self.reason)
        homing["windows"] = windows
        dog = _load("contracts/examples/dog-observation.json")
        dog["payload"]["transport"] = transport
        dog = await self.message(dog)
        candidates = homing["candidates"]
        if self.scenario == "blocked_planner":
            candidates["payload"].update({"candidates": [], "blocked": True})
        candidates = await self.message(candidates)
        navigation = await self.call(
            20,
            "guard",
            "feature.v2_dog_navigation",
            {
                "observation": dog,
                "candidates": candidates,
                "capabilities": dog_capability,
                "map_epoch": 1,
                "profile": {"dog_transport": transport, "profile_identity": transport},
            },
        )
        # Downstream policies receive only the candidates the actual navigation gate retained.
        safe_ids = navigation.data.get("usable_candidate_ids", ())
        if not safe_ids:
            safe_ids = navigation.data.get("candidate_ids", ())
        allowed = set(cast(tuple[str, ...], safe_ids))
        candidates["payload"]["candidates"] = [
            c for c in candidates["payload"]["candidates"] if c["candidate_id"] in allowed
        ]
        homing["candidates"] = candidates
        selected = await self.call(22, "stage", "homing", {"homing": homing})
        selection = dict(selected.events[0].payload)
        if selection.get("action") != "select":
            self.reason = f"homing stopped: {selection.get('reason')}"
            raise _Stopped(self.reason)
        if self.scenario in {"halt", "link_loss", "lease_expiry"}:
            stimulus = {
                "halt": "operator_halt",
                "link_loss": "link_loss",
                "lease_expiry": "expired_lease",
            }[self.scenario]
            payload: Json = {"stimulus": stimulus, "profile": "land"}
            if stimulus == "expired_lease":
                payload.update({"command": self.commands[-1], "started": False})
            await self.call(28, "guard", stimulus, payload, require_ok=False)
            self.recovery_required = True
            self.reason = stimulus
            raise _Stopped(stimulus)
        await self.wire("event-dog_dispatched", restamp=True)
        readiness = _load("fixtures/ground/g23/readiness.json")
        readiness["transport"] = transport
        approved = await self.call(
            23,
            "command",
            "approve",
            {
                "selection": {
                    "selection_id": "homing-001",
                    "candidate_id": selection["candidate_id"],
                    "guidance": "rssi",
                    "track_id": "target-001",
                    "beacon_epoch": 4,
                },
                "candidates": candidates,
                "readiness": readiness,
                "safety_snapshot_id": "safety-001",
                "halt_latched": False,
                "simulated": True,
            },
        )
        command = await self.message(cast(Mapping[str, object], approved.data["command"]))
        self.commands.append(command)
        if self.dog_link is not None:
            live = await self.dog_link.execute(command)  # type: ignore[attr-defined]
            self.dog_motion_log = live
            self._emit("dog_ethernet", live)
            if getattr(self.dog_link, "armed", False) and live.get("sent") is not True:
                self.reason = str(live.get("detail") or "dog ethernet motion was not sent")
                raise _Stopped(self.reason)
        for state in ("accepted", "running", "completed"):
            ack = _load(f"contracts/examples/dog-ack-{state}.json")
            ack["correlation_id"] = command["message_id"]
            ack["payload"]["command_id"] = command["payload"]["command_id"]
            ack = await self.message(ack, restamp=True)
            stopped = await self.call(24, "stage", "track", {"command": command, "ack": ack})
        if stopped.data["stopped"] is not True:
            raise fault("unsafe_state", "dog did not verify its stopped acknowledgement")
        self.advance(1.25)
        await self.checkpoint("DOG_VISION", "acquiring the same target on the dog camera")
        history = await self.dog_views()
        acquired = await self.call(25, "stage", "dog_acquire", history)
        if acquired.data["mode"] != "visual":
            self.reason = "dog camera has not acquired the same track"
            raise _Stopped(self.reason)
        await self.checkpoint("PROXIMITY", "checking dog range and drone horizontal offset")
        refreshed = _load("contracts/examples/drone-observation.json")
        refreshed["message_id"] = "msg-drone-hold-at-goal"
        refreshed["payload"]["beacon"].update(
            {
                "beacon_epoch": 4,
                "verified_at": self.now,
                "hold_valid_until": (self.services.kernel.clock.utc_now() + timedelta(seconds=2))
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
        refreshed = await self.message(refreshed, restamp=True)
        hold = await self.call(
            19,
            "guard",
            "feature.v2_beacon",
            {
                "observation": refreshed,
                "armed_bssid": "02:00:00:00:00:01",
            },
        )
        evidence = _load("contracts/examples/proximity-evidence.json")
        evidence["payload"]["dog"]["observed_at"] = self.now
        evidence["payload"]["drone"]["observed_at"] = self.now
        evidence = await self.message(evidence, restamp=True)
        goal = await self.call(
            26,
            "stage",
            "evaluate",
            {
                "message": evidence,
                "track_id": "target-001",
                "dog_stopped": stopped.data["stopped"],
                "hold_state": hold.data["hold_state"],
                "evaluated_at": self.now,
                "profile": _load("fixtures/ground/g26/profile-open.json"),
            },
        )
        if not goal.events:
            raise fault("validation_failed", "proximity gate produced no goal")
        goal_message = await self.message(goal.events[0].payload)
        self.goal_reached = True
        context = self.context["drone_approval"]
        context.update(
            {
                "proposal": None,
                "evaluated_at": self.now,
                "observation": refreshed,
                "operator_request": {
                    "request_id": "operator-land-001",
                    "action": "land",
                    "track_id": "target-001",
                    "camera_id": "downward",
                    "mission_id": MISSION,
                    "epoch": 1,
                    "simulated": True,
                    "reason": "Simulated operator recovery request.",
                },
            }
        )
        await self.checkpoint("LAND", "landing is a separate command from the goal")
        land_result = await self.call(17, "command", "feature.v2_drone_command", context)
        land = await self.message(cast(Mapping[str, object], land_result.data["command"]))
        self.commands.append(land)
        name = (
            "drone-landing-unknown" if self.scenario == "unknown_landing" else "drone-ack-completed"
        )
        ack = _load(f"contracts/examples/{name}.json")
        ack["message_id"] = "msg-final-land-ack"
        ack["correlation_id"] = land["message_id"]
        ack["payload"]["command_id"] = land["payload"]["command_id"]
        ack["payload"]["observed_motion"] = (
            "unknown" if self.scenario == "unknown_landing" else "grounded"
        )
        ack = await self.message(ack, restamp=True)
        observation = _load("contracts/examples/drone-observation.json")
        observation["payload"]["flight_state"] = (
            "unknown" if self.scenario == "unknown_landing" else "grounded"
        )
        recovery = await self.call(
            27,
            "stage",
            "evaluate",
            {
                "goal_event": goal_message,
                "land_command": land,
                "land_ack": ack,
                "observation": observation,
            },
            require_ok=False,
        )
        self.landing_verified = recovery.data.get("landing_verified") is True
        self.recovery_required = recovery.data.get("recovery_required") is True
        if not self.landing_verified:
            self.landing_verified = recovery.data.get("landing_status") == "verified"
        if self.recovery_required:
            self.reason = "goal reached; landing unverified"
            await self.checkpoint("FAULT", self.reason)
        elif self.goal_reached and self.landing_verified:
            await self.checkpoint("DONE", "goal reached and landing verified")

    async def dog_views(self) -> Json:
        history: Json = {
            "track_id": "target-001",
            "camera_epoch": 1,
            "evidence_budget_ms": 3000,
            "consecutive_hit_threshold": 2,
            "homing_allowed": True,
            "frames": [],
            "decisions": [],
            "requests": [],
        }
        for index in range(2):
            if index:
                self.advance(1.01)
            frame = _load("fixtures/ground/g14/accepted/front.json")
            frame["frame_id"] = f"dog-front-{index + 1:03}"
            frame["captured_at"] = self.now
            await self.call(
                14,
                "stage",
                "feature.v2_frame",
                {
                    "frame": frame,
                    "zone": "display",
                    "source": "dog",
                    "mission_id": MISSION,
                    "epoch": 1,
                    "store_root": str(repo_root() / "fixtures/ground/g14/store"),
                },
            )
            scheduled = await self.call(
                15,
                "stage",
                "schedule",
                {
                    "frame": frame,
                    "stage": "dog_acquire",
                    "active_track_id": "target-001",
                    "target_description": TARGET,
                    "settings": self._schedule_settings(),
                    "settle": True,
                    "clock_error_ms": 0,
                },
            )
            request = await self.message(cast(Mapping[str, object], scheduled.data["message"]))
            decision = await self._dog_vision_decision(request, index)
            decision = await self.message(decision, restamp=True)
            await self.call(
                16,
                "stage",
                "feature.v2_vision_decision",
                {
                    "decision": decision,
                    "request": request,
                    "current_track_id": "target-001",
                    "current_camera_epoch": 1,
                },
            )
            history["frames"].append(frame)
            history["decisions"].append(decision)
            history["requests"].append(request)
        history["observed_at"] = self.now
        history["rssi_records"] = self.context["homing"]["windows"]
        return history

    def _schedule_settings(self) -> Mapping[str, object]:
        """Keep the placeholder model on the fake path.

        Task 16 requires the decision's model id to match the request. A real
        image call cannot send ``CONFIGURE_VERIFIED_IMAGE_MODEL``, so the real
        path names the model on the request the connector will call.
        """

        settings = self.context["schedule_settings"]
        if not isinstance(settings, Mapping):
            raise fault("invalid_input", "schedule settings must be an object")
        if self.grok != "real":
            return settings
        from patrol.ground.signal.client import DEFAULT_IMAGE_MODEL

        named = dict(settings)
        named["model_id"] = DEFAULT_IMAGE_MODEL
        return named

    async def _drone_vision_decision(
        self,
        request: Mapping[str, object],
        frame: Mapping[str, object],
    ) -> Json:
        if self.grok == "real":
            return await self._real_decision_async(request)
        decision = _load("contracts/examples/drone-vision-decision.json")
        decision["correlation_id"] = request["message_id"]
        payload = decision["payload"]
        if not isinstance(payload, dict):
            raise fault("invalid_input", "scripted vision decision payload must be an object")
        request_payload = request["payload"]
        if not isinstance(request_payload, Mapping):
            raise fault("invalid_input", "vision request payload must be an object")
        payload.update(
            {
                "request_id": request_payload["request_id"],
                "frame_id": frame["frame_id"],
                "frame_captured_at": frame["captured_at"],
                "model_id": request_payload["model_id"],
                "prompt_version": request_payload["prompt_version"],
                "suggested_action": "reposition",
                "image_direction": "left",
            }
        )
        return decision

    async def _dog_vision_decision(self, request: Mapping[str, object], index: int) -> Json:
        if self.grok == "real":
            decision = await self._real_decision_async(request)
        else:
            decision = _load("contracts/examples/dog-vision-decision.json")
            decision["correlation_id"] = request["message_id"]
            payload = decision["payload"]
            if not isinstance(payload, dict):
                raise fault("invalid_input", "scripted vision decision payload must be an object")
            request_payload = request["payload"]
            if not isinstance(request_payload, Mapping):
                raise fault("invalid_input", "vision request payload must be an object")
            frame = request_payload["frame"]
            if not isinstance(frame, Mapping):
                raise fault("invalid_input", "vision request frame must be an object")
            payload.update(
                {
                    "request_id": request_payload["request_id"],
                    "frame_id": frame["frame_id"],
                    "frame_captured_at": frame["captured_at"],
                    "model_id": request_payload["model_id"],
                    "prompt_version": request_payload["prompt_version"],
                }
            )
        decision["message_id"] = f"msg-dog-decision-{index + 1}"
        return decision

    def _release_vision(self) -> None:
        self._vision_busy = False

    async def _real_decision_async(self, request: Mapping[str, object]) -> Json:
        if self._vision_busy:
            raise fault("rejected", "a vision request is already in flight")
        self._vision_busy = True
        loop = asyncio.get_running_loop()
        payload = dict(request)

        def work() -> Json:
            try:
                return self._real_decision(payload)
            finally:
                loop.call_soon_threadsafe(self._release_vision)

        decision = await asyncio.to_thread(work)
        if self.should_halt is not None and self.should_halt():
            raise _Stopped("vision result arrived after halt")
        return decision

    def _real_decision(self, request: Mapping[str, object]) -> Json:
        from patrol.ground.signal import SignalError, assess_frame

        try:
            decision = assess_frame(request)
        except SignalError as exc:
            self.reason = f"{exc.code}: {exc.detail}"
            raise
        self.live_calls += 1
        return cast(Json, decision)


async def run_demo(
    output: Path,
    *,
    scenario: str = "happy_path",
    seed: int = 0,
    transport: str = "ethernet",
    controls: StepSession | None = None,
    budgets: Mapping[int, tuple[float, float]] | None = None,
    dog_link: object | None = None,
    radio: Mapping[str, Json] | None = None,
    grok: str = "fake",
) -> Json:
    if scenario not in SCENARIOS or transport not in {"ethernet", "wifi"}:
        raise fault("invalid_input", "unknown rehearsal scenario or transport")
    if grok not in {"fake", "real"}:
        raise fault("invalid_input", "grok mode must be fake or real")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise fault("invalid_input", "seed must be an integer")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    services = await build_base_services(
        scenario="blocked_resolved",
        output_dir=output,
        journal_run_id=None,
    )
    clock = services.kernel.clock
    assert isinstance(clock, ManualClock)
    clock.advance(
        (datetime.fromisoformat("2026-11-04T13:00:10.210+00:00") - clock.utc_now()).total_seconds()
    )
    settings = make_settings(dog_transport=transport)
    services.kernel.authority.reset_generation("open simulated v2 mission")
    services.state.open(
        Incident(
            MISSION,
            "display",
            TARGET,
            Frame(
                str(repo_root() / "fixtures/ground/g06/phone.jpg"), "phone", "display", None, True
            ),
        ),
        settings,
    )
    demo = Demo(services, output, scenario, seed, controls, budgets, dog_link, radio, grok)
    if controls is not None:

        def request_safety(reason: str) -> None:
            services.safety.request(reason, demo.ticket)

        controls.bind_safety(
            lambda: services.kernel.authority.cancelled,
            request_safety,
        )
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
            demo.reason = "operator control halted or reached its mission deadline"
        if services.kernel.authority.cancelled and not demo.landing_verified:
            demo.recovery_required = True
        if demo.commands and not demo.landing_verified and not services.kernel.authority.cancelled:
            await demo.call(
                28,
                "guard",
                "operator_halt",
                {
                    "stimulus": "operator_halt",
                    "profile": "land",
                    "active_commands": demo.commands,
                },
                require_ok=False,
            )
            demo.recovery_required = True
        await demo.call(29, "stage", "flush", {})
        journal = cast(Any, demo.providers[29]).records
        metrics = await demo.call(
            31,
            "projection",
            "metrics",
            {
                "journal": _plain(journal),
                "mission_start_monotonic": demo.mission_start * 1000,
                "clock": {
                    "domain": "ground",
                    "quality": "manual_simulation",
                    "utc_pairs_allowed": False,
                },
                "run_id": MISSION,
            },
        )
        report = {
            "schema_version": "ground-composed-rehearsal-v2",
            "scenario": scenario,
            "seed": seed,
            "evidence": "simulated",
            "live_call_count": demo.live_calls,
            "adapter_modes": {"dog": "fake", "drone": "fake", "grok": demo.grok},
            "dog_transport": transport,
            "goal_reached": demo.goal_reached,
            "landing_verified": demo.landing_verified,
            "recovery_required": demo.recovery_required,
            "outcome": "completed" if demo.goal_reached and demo.landing_verified else "unresolved",
            "reason": demo.reason,
            "provider_tasks": sorted(demo.providers),
            "trace": demo.trace,
            "commands": demo.commands,
            "metrics": _plain(metrics.data),
            "external_adapter_factories": (
                "grok signal connector; dog, drone, and Pi messages stay simulated"
                if demo.grok == "real"
                else "not supplied; v2 messages are simulated"
            ),
            "physical_acceptance": "not performed",
            "cleanup_errors": cleanup_errors,
        }
        if demo.radio is not None:
            report["radio"] = demo.radio
        if demo.dog_motion_log is not None:
            report["dog_ethernet"] = demo.dog_motion_log
        if controls is not None:
            report["step_control"] = controls.get_snapshot()
        await services.journal.publish(
            {key: value for key, value in report.items() if key not in {"trace", "commands"}}
        )
        return report
    finally:
        if dog_link is not None:
            try:
                await dog_link.close()  # type: ignore[attr-defined]
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if controls is not None:
            # Stop the supervisor before closing device/journal services.
            await controls.close()
        services.kernel.barriers.release_all()
        await services.kernel.tasks.collect(deadline=2)
        for closer in (services.adapters.close, services.console.close, services.journal.close):
            try:
                await closer()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if report is not None:
            if controls is not None:
                report["step_control"] = controls.get_snapshot()
                try:
                    (output / "step-events.json").write_text(
                        json.dumps(controls.events(), indent=2) + "\n", encoding="utf-8"
                    )
                except OSError as exc:
                    cleanup_errors.append(type(exc).__name__)
            if cleanup_errors:
                report["outcome"] = "failed"
            (output / "report.json").write_text(
                json.dumps(report, indent=2) + "\n",
                encoding="utf-8",
            )
