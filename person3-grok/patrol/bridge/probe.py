"""Run our emitters against Ground and record every rejection.

Usage (from ``person3-grok``, no network)::

    python -m patrol.bridge.probe

Writes ``handoff/ground_rejection_log.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from patrol.bridge.ground import GroundModules, load_ground
from patrol.bridge.messages import command_message, proposal_message, schema_shaped_proposal
from patrol.trigger.presence import Intent, PresenceSession
from patrol.vision_v2.decision import build_decision, build_request

_ACTIONS = ("play_warning", "follow", "stop", "return_home", "land_on_dog")
_SENT_AT = "2026-11-04T13:00:10.400Z"
_EXPIRES_AT = "2026-11-04T13:00:15.100Z"


@dataclass
class Check:
    label: str
    message: dict[str, object] | None
    schema_ok: bool
    schema_code: str | None
    schema_reason: str | None
    factory: str | None = None
    factory_ok: bool | None = None
    factory_status: str | None = None
    factory_code: str | None = None
    factory_reason: str | None = None
    note: str = ""


@dataclass
class G16Row:
    label: str
    decision: dict[str, object]
    request: dict[str, object]
    schema_ok: bool
    schema_code: str | None
    schema_reason: str | None
    status: str
    error_code: str | None
    error_detail: str | None
    outcome: str
    trace: tuple[str, ...]
    proposal_action: str | None
    motion_authorized: bool


@dataclass
class ProbeReport:
    ground_root: str
    dog_root: str | None
    actions: dict[str, list[Check]] = field(default_factory=dict)
    g16: list[G16Row] = field(default_factory=list)
    presence_trace: list[str] = field(default_factory=list)
    schema_enums: dict[str, list[str]] = field(default_factory=dict)


def run_probe(team_repo: str | Path | None = None) -> ProbeReport:
    ground = load_ground(team_repo)
    schema = ground.schema_check.load_schema()
    report = ProbeReport(
        ground_root=str(ground.ground_root),
        dog_root=None if ground.dog_root is None else str(ground.dog_root),
        schema_enums={
            "motion.proposal": list(schema["$defs"]["motion.proposal"]["properties"]["action"]["enum"]),
            "dog.command": list(schema["$defs"]["dog.command"]["properties"]["action"]["enum"]),
            "drone.command": list(schema["$defs"]["drone.command"]["properties"]["action"]["enum"]),
        },
    )
    session = PresenceSession()
    intents = (
        session.on_presence("person_visible", "dog_approach")
        + session.on_presence("person_visible", "dog_approach")
        + session.on_presence("not_visible", "dog_approach")
    )
    report.presence_trace = list(session.trace)
    by_action = {item.action: item for item in intents}
    for index, action in enumerate(_ACTIONS, start=1):
        intent = by_action[action]
        report.actions[action] = _action_checks(ground, schema, intent, seq=index)
    report.g16 = _g16_rows(ground, schema)
    return report


def write_log(report: ProbeReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: ProbeReport) -> str:
    lines: list[str] = [
        "# Ground rejection log",
        "",
        "Person 3 presence bridge, run against Ayush's Ground in this checkout.",
        "No dog socket, no drone socket, and no xAI call.",
        "",
        f"- Ground root: `{report.ground_root}`",
        f"- Dog root (not imported): `{report.dog_root}`",
        "- Checkers: `patrol/ground/extensions/g11/schema_check.py` (`validate_message`), "
        "`g16/decide.py` (`assess`), `g17/policy.py` (`decide`).",
        "- Presence session trace for still-there, still-there, gone: "
        + ", ".join(f"`{item}`" for item in report.presence_trace),
        "",
        "Published action enums loaded from Ground's schema:",
        "",
    ]
    for kind, values in report.schema_enums.items():
        lines.append(f"- `{kind}`: {', '.join(f'`{item}`' for item in values)}")
    lines.extend(
        [
            "",
            "Origin `hritvik-arora/robot-patrol` at `1f5b6c6` was not readable from this run "
            "(no Origin session). The messages below are the shapes this bridge sends, "
            "matching HAC-62 / HAC-58: `play_warning` (`warning_id` `go-away`, text `go away`), "
            "`follow` (standoff 2.0), `stop`, `return_home`, and `land_on_dog` "
            "(`primitive_id` `land-on-dog-v1`, `beacon_epoch` null).",
            "",
            "## Proposals and commands",
            "",
        ]
    )
    for action, checks in report.actions.items():
        lines.append(f"### {action}")
        lines.append("")
        for check in checks:
            lines.append(f"#### {check.label}")
            lines.append("")
            if check.note:
                lines.append(check.note)
                lines.append("")
            if check.message is not None:
                lines.append("Message:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(check.message, indent=2, sort_keys=True))
                lines.append("```")
                lines.append("")
            if check.schema_ok:
                lines.append("- Schema: accepted (`validate_message` returned without error).")
            else:
                lines.append(
                    f"- Schema: rejected `{check.schema_code}: {check.schema_reason}`."
                )
            if check.factory is not None:
                if check.factory_ok:
                    lines.append(f"- Factory `{check.factory}`: accepted.")
                else:
                    lines.append(
                        f"- Factory `{check.factory}`: rejected "
                        f"status `{check.factory_status}`, code `{check.factory_code}`, "
                        f"reason `{check.factory_reason}`."
                    )
            lines.append("")
    lines.extend(["## g16 vision.decision on dog_approach", ""])
    lines.append(
        "g16 keeps `motion_authorized` false. Dog stages (`dog_acquire`, `dog_approach`) "
        "drop the proposal even when the decision is accepted. "
        "`not_visible` and `uncertain` never consult `suggested_action`."
    )
    lines.append("")
    for row in report.g16:
        lines.append(f"### {row.label}")
        lines.append("")
        lines.append("Decision sent:")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(row.decision, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
        if row.schema_ok:
            lines.append("- Schema: accepted.")
        else:
            lines.append(f"- Schema: rejected `{row.schema_code}: {row.schema_reason}`.")
        proposal = "none" if row.proposal_action is None else row.proposal_action
        lines.append(
            f"- g16 `assess`: status `{row.status}`, outcome `{row.outcome}`, "
            f"error `{row.error_code}`, detail `{row.error_detail}`, "
            f"proposal `{proposal}`, motion_authorized `{str(row.motion_authorized).lower()}`."
        )
        lines.append("- Trace: " + ", ".join(f"`{item}`" for item in row.trace))
        lines.append("")
    lines.append(
        "A `drone_track` row is included so the log shows a stage where g16 does emit a proposal. "
        "That proposal is `hold` for the drone, not one of the five presence actions."
    )
    lines.append("")
    return "\n".join(lines)


def _action_checks(
    ground: GroundModules,
    schema: Mapping[str, object],
    intent: Intent,
    *,
    seq: int,
) -> list[Check]:
    common = dict(
        mission_id="demo-20261104-001",
        epoch=1,
        seq=seq,
        track_id="target-001",
        evidence_frame_id="dog-front-presence-001",
        correlation_id="msg-presence-decision",
        sent_at=_SENT_AT,
        expires_at=_EXPIRES_AT,
        simulated=True,
    )
    proposal = proposal_message(intent, **common)
    command = command_message(intent, **common)
    payload = proposal["payload"]
    extras = [key for key in ("warning_id", "text", "standoff_m") if isinstance(payload, dict) and key in payload]
    exact_label = "Exact proposal"
    if extras:
        exact_label = "Exact proposal (extra fields: " + ", ".join(extras) + ")"
    checks = [
        _schema_and_factory(
            ground,
            schema,
            exact_label,
            proposal,
            run_g17=True,
        )
    ]
    shaped = schema_shaped_proposal(proposal)
    if shaped["payload"] != proposal["payload"]:
        checks.append(
            _schema_and_factory(
                ground,
                schema,
                "Schema-shaped proposal (extras removed so the action enum is reached)",
                shaped,
                run_g17=True,
                note="Same action and routing as the exact proposal. Extra keys are omitted only for this check.",
            )
        )
    checks.append(
        _schema_and_factory(
            ground,
            schema,
            "Command shape asked of Ground (not sent to a robot)",
            command,
            run_g17=False,
        )
    )
    if intent.action == "land_on_dog":
        landed = json.loads(json.dumps(command))
        landed["payload"]["action"] = "land"
        checks.append(
            _schema_and_factory(
                ground,
                schema,
                "Beacon check: same drone command with action set to land",
                landed,
                run_g17=False,
                note=(
                    "Not a message the bridge sends. Action is replaced so Ground's schema "
                    "can report `beacon_epoch: null` on its own. The published drone.command "
                    "beacon_epoch is an integer, not null."
                ),
            )
        )
    return checks


def _schema_and_factory(
    ground: GroundModules,
    schema: Mapping[str, object],
    label: str,
    message: dict[str, object],
    *,
    run_g17: bool,
    note: str = "",
) -> Check:
    code, reason, ok = _schema(ground, schema, message)
    check = Check(
        label=label,
        message=message,
        schema_ok=ok,
        schema_code=code,
        schema_reason=reason,
        note=note,
    )
    if run_g17 and message.get("kind") == "motion.proposal":
        decision = ground.g17.decide({"proposal": message})
        check.factory = "g17.policy.decide"
        check.factory_ok = bool(decision.ok)
        check.factory_status = decision.status
        check.factory_code = decision.code or None
        check.factory_reason = decision.reason
    return check


def _schema(
    ground: GroundModules,
    schema: Mapping[str, object],
    message: Mapping[str, object],
) -> tuple[str | None, str | None, bool]:
    try:
        ground.schema_check.validate_message(message, schema)
    except ground.schema_check.SchemaFault as fault:
        return fault.code, fault.reason, False
    return None, None, True


def _g16_rows(ground: GroundModules, schema: Mapping[str, object]) -> list[G16Row]:
    specs = [
        (
            "dog_approach person_visible suggested approach",
            "dog_approach",
            "person_visible",
            "msg-req-dog-visible",
            "vision-dog-visible",
            "dog-front-presence-001",
            "target-001",
        ),
        (
            "dog_approach person_visible suggested stop",
            "dog_approach",
            "person_visible",
            "msg-req-dog-stop",
            "vision-dog-stop",
            "dog-front-presence-002",
            "target-001",
        ),
        (
            "dog_approach not_visible suggested stop",
            "dog_approach",
            "not_visible",
            "msg-req-dog-gone",
            "vision-dog-gone",
            "dog-front-presence-003",
            "target-001",
        ),
        (
            "dog_approach uncertain suggested review",
            "dog_approach",
            "uncertain",
            "msg-req-dog-unsure",
            "vision-dog-unsure",
            "dog-front-presence-004",
            "target-001",
        ),
        (
            "drone_track person_visible suggested hold (proposal is emitted)",
            "drone_track",
            "person_visible",
            "msg-req-drone-hold",
            "vision-drone-hold",
            "drone-down-presence-001",
            "target-001",
        ),
    ]
    rows: list[G16Row] = []
    for index, (label, stage, state, message_id, request_id, frame_id, track) in enumerate(specs, start=10):
        request = build_request(
            stage=stage,
            message_id=message_id,
            request_id=request_id,
            frame_id=frame_id,
            seq=index,
            active_track_id=track,
        )
        if label.startswith("dog_approach person_visible suggested stop"):
            decision = build_decision(request, state=state, message_id=f"msg-dec-{index}", seq=index + 1)
            decision["payload"]["suggested_action"] = "stop"
            decision["payload"]["reason"] = "Stop in place. This is not an operator halt."
        else:
            decision = build_decision(request, state=state, message_id=f"msg-dec-{index}", seq=index + 1)
        code, reason, ok = _schema(ground, schema, decision)
        assessment = ground.g16.assess(
            decision,
            request,
            current_track_id=track,
        )
        proposal_action = None
        proposal = assessment.proposal
        if isinstance(proposal, Mapping):
            payload = proposal.get("payload")
            if isinstance(payload, Mapping) and isinstance(payload.get("action"), str):
                proposal_action = payload["action"]
        rows.append(
            G16Row(
                label=label,
                decision=decision,
                request=request,
                schema_ok=ok,
                schema_code=code,
                schema_reason=reason,
                status=assessment.status,
                error_code=assessment.error_code,
                error_detail=assessment.error_detail,
                outcome=assessment.outcome,
                trace=tuple(assessment.trace),
                proposal_action=proposal_action,
                motion_authorized=bool(assessment.motion_authorized),
            )
        )
    return rows


def main() -> int:
    report = run_probe()
    path = Path(__file__).resolve().parents[2] / "handoff" / "ground_rejection_log.md"
    write_log(report, path)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
