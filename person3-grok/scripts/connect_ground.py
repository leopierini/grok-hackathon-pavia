"""Send Person 3 presence traffic at Ground and record every distinct failure.

Run from ``person3-grok`` with this tree on ``PYTHONPATH`` and
``PATROL_TEAM_REPO`` pointing at the shared repo (see ``handoff/MERGE_GUIDE.md``).

No robot socket is opened. Secret values are not printed. Host, port, and auth
are read only to see whether they are set.
"""

from __future__ import annotations

import importlib
import inspect
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("PATROL_TEAM_REPO", ROOT.parent)).resolve()
OUT = ROOT / "handoff" / "integration_probe.md"

# Names we would need for a real /ws/robot/v2 session or an xAI call.
# Values are never written to the log.
_TRANSPORT_NAMES = (
    "ROBOT_HOST",
    "ROBOT_PORT",
    "ROBOT_AUTH",
    "ROBOT_WS_URL",
    "GROUND_HOST",
    "GROUND_PORT",
    "GROUND_WS_HOST",
    "GROUND_WS_PORT",
    "GROUND_WS_URL",
    "WS_ROBOT_HOST",
    "WS_ROBOT_PORT",
    "WS_ROBOT_AUTH",
    "UNITREE_ROBOT_IP",
    "XAI_API_KEY",
)


def main() -> int:
    if "--ground-native" in sys.argv:
        print(json.dumps(ground_native(), default=str))
        return 0
    if "--dog-native" in sys.argv:
        print(json.dumps(dog_native(), default=str))
        return 0
    if "--which-patrol" in sys.argv:
        print(json.dumps(which_patrol(), default=str))
        return 0
    report = run()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(report), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


def run() -> dict[str, object]:
    os.environ.setdefault("PATROL_TEAM_REPO", str(REPO))
    from patrol.bridge.ground import load_ground
    from patrol.bridge.messages import command_message, proposal_message
    from patrol.bridge.probe import run_probe
    from patrol.grok import create_reasoner
    from patrol.trigger.presence import PresenceSession
    from patrol.vision_v2.decision import build_decision, build_request

    ground = load_ground(REPO)
    schema = ground.schema_check.load_schema()
    probe = run_probe(REPO)
    rows: list[dict[str, object]] = []

    def add(area: str, item: str, **fields: object) -> None:
        row: dict[str, object] = {"area": area, "item": item}
        row.update(fields)
        rows.append(row)

    requests = {
        "dog_approach": build_request(
            stage="dog_approach",
            message_id="msg-req-dog-visible",
            request_id="vision-dog-visible",
            frame_id="dog-front-presence-001",
        ),
        "drone_track": build_request(
            stage="drone_track",
            message_id="msg-req-drone-hold",
            request_id="vision-drone-hold",
            frame_id="drone-down-presence-001",
        ),
    }
    for name, request in requests.items():
        code, reason, ok = _schema(ground, schema, request)
        add("vision.request", name, schema_ok=ok, schema_code=code, schema_reason=reason)

    for label, stage, state, action in (
        ("decision play_warning", "dog_approach", "person_visible", "play_warning"),
        ("decision follow", "dog_approach", "person_visible", "follow"),
        ("decision return_home", "dog_approach", "person_visible", "return_home"),
        ("decision land_on_dog", "drone_track", "person_visible", "land_on_dog"),
    ):
        request = requests["dog_approach" if stage == "dog_approach" else "drone_track"]
        decision = build_decision(request, state=state, message_id=f"msg-{label}", seq=20)
        decision["payload"]["suggested_action"] = action
        code, reason, ok = _schema(ground, schema, decision)
        assessment = _safe_assess(ground, decision, request)
        add(
            "vision.decision",
            label,
            schema_ok=ok,
            schema_code=code,
            schema_reason=reason,
            **assessment,
        )

    for row in probe.g16:
        add(
            "g16",
            row.label,
            schema_ok=row.schema_ok,
            schema_code=row.schema_code,
            schema_reason=row.schema_reason,
            status=row.status,
            outcome=row.outcome,
            proposal=row.proposal_action,
            motion_authorized=row.motion_authorized,
            trace=list(row.trace),
        )

    session = PresenceSession()
    intents = (
        session.on_presence("person_visible", "dog_approach")
        + session.on_presence("person_visible", "dog_approach")
        + session.on_presence("not_visible", "dog_approach")
    )
    by_action = {item.action: item for item in intents}
    common = dict(
        mission_id="demo-20261104-001",
        epoch=1,
        track_id="target-001",
        evidence_frame_id="dog-front-presence-001",
        correlation_id="msg-presence-decision",
        sent_at="2026-11-04T13:00:10.400Z",
        expires_at="2026-11-04T13:00:15.100Z",
        simulated=True,
    )
    for index, action in enumerate(("play_warning", "follow", "stop", "return_home", "land_on_dog"), start=1):
        intent = by_action[action]
        proposal = proposal_message(intent, seq=index, **common)
        command = command_message(intent, seq=index, **common)
        code, reason, ok = _schema(ground, schema, proposal)
        decision = _safe_g17(ground, proposal)
        payload = proposal["payload"]
        extras = [
            key
            for key in ("warning_id", "text", "standoff_m")
            if isinstance(payload, dict) and key in payload
        ]
        dropped = [
            key
            for key in ("warning_id", "text", "standoff_m")
            if getattr(intent, key if key != "standoff_m" else "standoff_m") is not None
            and isinstance(command.get("payload"), dict)
            and key not in command["payload"]
        ]
        add(
            "motion.proposal",
            action,
            schema_ok=ok,
            schema_code=code,
            schema_reason=reason,
            extras=extras,
            command_dropped_fields=dropped,
            **decision,
        )
        ccode, creason, cok = _schema(ground, schema, command)
        add(
            "command",
            f"{command['kind']} {action}",
            schema_ok=cok,
            schema_code=ccode,
            schema_reason=creason,
            kind=command["kind"],
            action=action,
        )

    halt = command_message(
        __import__("patrol.trigger.presence", fromlist=["Intent"]).Intent("halt", "dog"),
        seq=9,
        **common,
    )
    hcode, hreason, hok = _schema(ground, schema, halt)
    add("command", "dog.command halt", schema_ok=hok, schema_code=hcode, schema_reason=hreason, kind="dog.command", action="halt")

    # Published dog proposal (action approach) still hits g17 before any dog command exists.
    approach = json.loads((ground.ground_root / "fixtures" / "ground" / "g23" / "proposal.json").read_text(encoding="utf-8"))
    acode, areason, aok = _schema(ground, schema, approach)
    add("motion.proposal", "published approach", schema_ok=aok, schema_code=acode, schema_reason=areason, **_safe_g17(ground, approach))

    native = _spawn(REPO / "ground base", "--ground-native")
    add("ground-native", "g17-and-g23", **native)
    dog = _spawn(REPO / "dog backend", "--dog-native")
    add("dog-native", "create_dog", **dog)
    collision = {
        "person3_then_ground": _spawn_paths([ROOT, REPO / "ground base"], "--which-patrol"),
        "ground_then_person3": _spawn_paths([REPO / "ground base", ROOT], "--which-patrol"),
        "person3_then_dog": _spawn_paths([ROOT, REPO / "dog backend"], "--which-patrol"),
        "dog_then_person3": _spawn_paths([REPO / "dog backend", ROOT], "--which-patrol"),
    }
    add("import", "patrol package collision", paths=collision)

    reasoner_real = _call_reasoner(create_reasoner, "real")
    reasoner_fake = _call_reasoner(create_reasoner, "fake")
    add("reasoner", "create_reasoner real", **reasoner_real)
    add("reasoner", "create_reasoner fake keywords", **reasoner_fake)
    add(
        "reasoner",
        "signature",
        signature=str(inspect.signature(create_reasoner)),
        methods=sorted(
            name
            for name, value in inspect.getmembers(create_reasoner("fake", {}, "/tmp"), predicate=callable)
            if not name.startswith("_")
        ),
    )

    vision = subprocess.run(
        [sys.executable, "-m", "patrol.vision_v2"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    add(
        "transport",
        "python -m patrol.vision_v2",
        returncode=vision.returncode,
        stderr=vision.stderr.strip(),
        stdout=vision.stdout.strip(),
    )
    add("transport", "env", names={name: bool(os.environ.get(name)) for name in _TRANSPORT_NAMES})
    add(
        "transport",
        "ws/robot/v2",
        attempted=False,
        reason="host, port, and auth are unset; no connection was opened",
    )
    return {
        "ground_root": str(ground.ground_root),
        "dog_root": None if ground.dog_root is None else str(ground.dog_root),
        "presence_trace": list(probe.presence_trace),
        "schema_enums": probe.schema_enums,
        "rows": rows,
    }


def ground_native() -> dict[str, object]:
    """Imports that only resolve when ``ground base`` is the patrol package."""
    out: dict[str, object] = {}
    try:
        from patrol.ground.extensions.g17.policy import decide
        from patrol.ground.extensions.g17.samples import armed_context
    except Exception as exc:  # noqa: BLE001 — record the import failure itself
        out["g17_import"] = _exc(exc)
        return out

    def swap(action: str, target: str | None = None) -> dict[str, object]:
        context = armed_context()
        proposal = context["proposal"]
        assert isinstance(proposal, dict)
        payload = proposal["payload"]
        assert isinstance(payload, dict)
        payload["action"] = action
        if target is not None:
            payload["target_component"] = target
        try:
            decision = decide(context)
        except Exception as exc:  # noqa: BLE001
            return {"raised": _exc(exc)}
        draft = decision.draft
        return {
            "ok": decision.ok,
            "status": decision.status,
            "code": decision.code,
            "reason": decision.reason,
            "draft_action": None if draft is None else draft.action,
            "primitive_id": None if draft is None else draft.primitive_id,
            "beacon_epoch": None if draft is None else draft.beacon_epoch,
        }

    out["g17_armed"] = {
        "stop": swap("stop"),
        "land_on_dog": swap("land_on_dog"),
        "play_warning_on_drone": swap("play_warning"),
        "hold": swap("hold"),
        "approach_on_dog": swap("approach", "dog"),
    }

    try:
        from patrol.ground.extensions.g23.implementation import (
            _command_request,
            _load,
            _merged_action,
            _parse,
        )
    except Exception as exc:  # noqa: BLE001
        out["g23_import"] = _exc(exc)
        return out

    proposal = _load("proposal.json")
    readiness = _load("readiness.json")
    candidates = _load("candidates.json")

    def parse_action(action: str, target: str, *, null_candidate: bool) -> dict[str, object]:
        prop = json.loads(json.dumps(proposal))
        prop["payload"]["action"] = action
        prop["payload"]["target_component"] = target
        if null_candidate:
            prop["payload"]["candidate_id"] = None
            prop["payload"]["beacon_epoch"] = None
        payload = {
            "candidates": candidates,
            "readiness": readiness,
            "safety_snapshot_id": "safety-001",
            "halt_latched": False,
            "issue_halt": False,
            "simulated": True,
            "proposal": prop,
        }
        mapped = _merged_action(payload, None, prop)
        request = _command_request(payload)
        try:
            order = _parse(request, dict(request.payload))
        except Exception as exc:  # noqa: BLE001
            return {"merged_action": mapped, "parse_error": f"{type(exc).__name__}: {exc}"}
        return {
            "merged_action": mapped,
            "order_type": type(order).__name__,
            "order_action": getattr(order, "action", None),
        }

    cases = {}
    for action in ("approach", "stop", "play_warning", "follow", "return_home"):
        cases[action] = parse_action(action, "dog", null_candidate=False)
        cases[f"{action} bridge-shaped"] = parse_action(action, "dog", null_candidate=True)
    cases["land_on_dog"] = parse_action("land_on_dog", "drone", null_candidate=True)
    out["g23"] = cases

    try:
        from patrol.ground.extensions.g08.resolve import resolve_factories

        resolve_factories({"source": "public"})
        out["g08_public"] = {"ok": True}
    except Exception as exc:  # noqa: BLE001
        out["g08_public"] = {"ok": False, "error": _exc(exc)}

    for name in ("patrol.drone", "patrol.dog", "patrol.grok"):
        try:
            module = importlib.import_module(name)
            out[name] = {"ok": True, "file": getattr(module, "__file__", None)}
        except Exception as exc:  # noqa: BLE001
            out[name] = {"ok": False, "error": _exc(exc)}
    return out


def dog_native() -> dict[str, object]:
    out: dict[str, object] = {}
    try:
        import patrol

        out["patrol_file"] = getattr(patrol, "__file__", None)
        from patrol.dog import create_dog
    except Exception as exc:  # noqa: BLE001
        out["import_error"] = _exc(exc)
        for name in ("patrol.grok", "patrol.drone", "patrol.ground"):
            try:
                importlib.import_module(name)
                out[name] = "imported"
            except Exception as inner:  # noqa: BLE001
                out[name] = _exc(inner)
        return out
    out["signature"] = str(inspect.signature(create_dog))
    try:
        dog = create_dog(mode="fake", config={}, output_dir="/tmp/person3-dog-probe")
    except Exception as exc:  # noqa: BLE001
        out["create_error"] = _exc(exc)
        return out
    methods = sorted(name for name in dir(dog) if not name.startswith("_"))
    out["methods"] = methods
    out["has_execute"] = hasattr(dog, "execute")
    out["has_play_warning"] = hasattr(dog, "play_warning")
    out["has_play_audio_file"] = hasattr(dog, "play_audio_file")
    port_methods = []
    try:
        from patrol.contract import DogPort

        port_methods = sorted(name for name in dir(DogPort) if not name.startswith("_"))
    except Exception as exc:  # noqa: BLE001
        out["port_error"] = _exc(exc)
    out["port_methods"] = port_methods
    return out


def which_patrol() -> dict[str, object]:
    import patrol

    found: dict[str, object] = {"patrol_file": getattr(patrol, "__file__", None)}
    for name in ("patrol.grok", "patrol.ground", "patrol.dog", "patrol.drone", "patrol.bridge"):
        try:
            module = importlib.import_module(name)
            found[name] = getattr(module, "__file__", None)
        except Exception as exc:  # noqa: BLE001
            found[name] = _exc(exc)
    return found


def _spawn(path: Path, flag: str) -> dict[str, object]:
    return _spawn_paths([path], flag)


def _spawn_paths(paths: list[Path], flag: str) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in paths)
    env["PATROL_TEAM_REPO"] = str(REPO)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), flag],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "stdout": completed.stdout[-2000:],
        }
    try:
        loaded = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"returncode": 0, "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:]}
    if not isinstance(loaded, dict):
        return {"returncode": 0, "value": loaded}
    return loaded


def _schema(ground: object, schema: Mapping[str, object], message: Mapping[str, object]) -> tuple[str | None, str | None, bool]:
    try:
        ground.schema_check.validate_message(message, schema)  # type: ignore[attr-defined]
    except ground.schema_check.SchemaFault as fault:  # type: ignore[attr-defined]
        return fault.code, fault.reason, False
    return None, None, True


def _safe_assess(ground: object, decision: Mapping[str, object], request: Mapping[str, object]) -> dict[str, object]:
    try:
        assessment = ground.g16.assess(decision, request, current_track_id="target-001")  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        return {"assess_error": _exc(exc)}
    proposal = assessment.proposal
    action = None
    if isinstance(proposal, Mapping):
        payload = proposal.get("payload")
        if isinstance(payload, Mapping):
            action = payload.get("action")
    return {
        "assess_status": assessment.status,
        "assess_error": assessment.error_code,
        "assess_detail": assessment.error_detail,
        "outcome": assessment.outcome,
        "proposal": action,
        "motion_authorized": assessment.motion_authorized,
        "trace": list(assessment.trace),
    }


def _safe_g17(ground: object, proposal: Mapping[str, object]) -> dict[str, object]:
    try:
        decision = ground.g17.decide({"proposal": proposal})  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        return {"g17_error": _exc(exc)}
    return {
        "g17_ok": decision.ok,
        "g17_status": decision.status,
        "g17_code": decision.code,
        "g17_reason": decision.reason,
    }


def _call_reasoner(factory: object, mode: str) -> dict[str, object]:
    try:
        value = factory(mode=mode, config={}, output_dir="/tmp/person3-reasoner-probe")  # type: ignore[operator]
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": _exc(exc)}
    return {"ok": True, "type": type(value).__name__}


def _exc(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    if os.environ.get("PROBE_TRACE") == "1":
        text = "".join(traceback.format_exception(exc))
    return text


def render(report: Mapping[str, object]) -> str:
    lines = [
        "# Integration probe — Person 3 against Ground",
        "",
        "Ran from `person3-grok` with `PYTHONPATH=person3-grok` and `PATROL_TEAM_REPO` at the repo root.",
        "Ground checkers were loaded by file path. Dog and drone sockets were not opened.",
        "Environment values for host, port, auth, and `XAI_API_KEY` are recorded only as set or unset.",
        "",
        f"- Ground root: `{report['ground_root']}`",
        f"- Dog root (not imported on this path): `{report['dog_root']}`",
        "- Presence trace: " + ", ".join(f"`{item}`" for item in report["presence_trace"]),
        "",
        "Published action enums:",
        "",
    ]
    enums = report["schema_enums"]
    assert isinstance(enums, dict)
    for kind, values in enums.items():
        lines.append(f"- `{kind}`: " + ", ".join(f"`{item}`" for item in values))
    lines.append("")
    rows = report["rows"]
    assert isinstance(rows, list)
    current = ""
    for row in rows:
        assert isinstance(row, dict)
        area = str(row["area"])
        if area != current:
            current = area
            lines.extend(["", f"## {area}", ""])
        lines.append(f"### {row['item']}")
        lines.append("")
        lines.append("```json")
        shown = {key: value for key, value in row.items() if key not in {"area", "item"}}
        lines.append(json.dumps(shown, indent=2, sort_keys=True, default=str))
        lines.append("```")
        lines.append("")
    lines.append("Schema rejections for the five presence proposals are also in `handoff/ground_rejection_log.md`.")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
