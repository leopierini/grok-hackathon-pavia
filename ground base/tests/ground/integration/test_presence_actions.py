"""Presence actions from the vision side must be legal Ground messages.

The scripted rehearsal still uses reposition and switch_to_dog_vision.
These checks cover the actions issues 4 through 22 rejected.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path

from patrol.ground.extensions.g11.schema_check import load_schema, validate_message
from patrol.ground.extensions.g16.implementation import VisionDecisionFeature, create
from patrol.ground.extensions.g17.policy import decide
from patrol.ground.extensions.g17.samples import armed_context, payload_of
from patrol.ground.extensions.g18.messages import parse_command
from patrol.ground.extensions.g24.model import parse_command as parse_dog_command
from patrol.ground.kernel.paths import repo_root
from patrol.ground.testing.builders import build_test_services


def _load(folder: str, name: str) -> dict[str, object]:
    path = repo_root() / "fixtures" / "ground" / folder / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _example(name: str) -> dict[str, object]:
    path = repo_root() / "contracts" / "examples" / name
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise AssertionError(f"{name} is not an object")
    return {str(key): value for key, value in parsed.items()}


def _body(message: Mapping[str, object]) -> dict[str, object]:
    raw = message["payload"]
    if not isinstance(raw, dict):
        raise AssertionError("payload is missing")
    return raw


def _feature(tmp_path: Path) -> VisionDecisionFeature:
    created = create(build_test_services(output_dir=tmp_path))
    if not isinstance(created, VisionDecisionFeature):
        raise AssertionError("factory did not return the vision feature")
    return created


def test_schema_accepts_presence_fields_and_actions() -> None:
    schema = load_schema()
    warning = _example("ai-to-dog-proposal.json")
    warning_body = _body(warning)
    warning_body.update(
        {
            "action": "play_warning",
            "warning_id": "go-away",
            "text": "go away",
        }
    )
    validate_message(warning, schema)
    follow = copy.deepcopy(warning)
    follow_body = _body(follow)
    follow_body["action"] = "follow"
    follow_body.pop("warning_id", None)
    follow_body.pop("text", None)
    follow_body["standoff_m"] = 2.0
    validate_message(follow, schema)
    for action in ("return_home", "land_on_dog"):
        proposal = copy.deepcopy(warning)
        proposal_body = _body(proposal)
        proposal_body.pop("warning_id", None)
        proposal_body.pop("text", None)
        proposal_body["action"] = action
        if action == "land_on_dog":
            proposal_body["target_component"] = "drone"
        validate_message(proposal, schema)

    decision = _example("dog-vision-decision.json")
    for action in ("play_warning", "follow", "return_home", "land_on_dog"):
        cloned = copy.deepcopy(decision)
        _body(cloned)["suggested_action"] = action
        validate_message(cloned, schema)

    dog = _example("ground-to-dog-command.json")
    dog_body = _body(dog)
    dog_body["action"] = "play_warning"
    dog_body["motion"] = None
    dog_body["warning_id"] = "go-away"
    dog_body["text"] = "go away"
    validate_message(dog, schema)
    parse_dog_command(dog)
    for action in ("follow", "stop", "return_home"):
        command = copy.deepcopy(dog)
        command_body = _body(command)
        command_body.pop("warning_id", None)
        command_body.pop("text", None)
        command_body["action"] = action
        if action == "follow":
            command_body["standoff_m"] = 2.0
        validate_message(command, schema)
        parse_dog_command(command)

    drone = _example("ground-to-drone-land.json")
    drone_body = _body(drone)
    drone_body["action"] = "land_on_dog"
    drone_body["primitive_id"] = "land-on-dog-v1"
    drone_body["beacon_epoch"] = None
    validate_message(drone, schema)
    parsed, body = parse_command(drone)
    assert parsed.kind == "drone.command"
    assert body.action == "land_on_dog"
    assert body.beacon_epoch is None


def test_dog_approach_emits_the_presence_proposal(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    decision = _load("g16", "dog-vision-decision.json")
    request = _load("g16", "dog-vision-request.json")
    _body(decision)["suggested_action"] = "approach"
    _body(request)["stage"] = "dog_approach"
    assessed = feature.assess(decision, request, current_track_id="target-001")
    assert assessed.status == "ok"
    assert assessed.proposal is not None
    assert assessed.motion_authorized is True
    assert _body(assessed.proposal)["action"] == "approach"
    assert _body(assessed.proposal)["target_component"] == "dog"
    acquire = feature.assess(
        _load("g16", "dog-vision-decision.json"),
        _load("g16", "dog-vision-request.json"),
        current_track_id="target-001",
    )
    assert acquire.proposal is None
    assert acquire.motion_authorized is False


def test_gone_and_uncertain_honor_the_suggested_action(tmp_path: Path) -> None:
    feature = _feature(tmp_path)
    request = _load("g16", "dog-vision-request.json")
    _body(request)["stage"] = "dog_approach"
    decision = _load("g16", "dog-vision-decision.json")
    payload = _body(decision)
    payload["target_state"] = "not_visible"
    payload["detections"] = []
    payload["suggested_action"] = "stop"
    stopped = feature.assess(decision, request, current_track_id="target-001")
    assert stopped.proposal is not None
    assert _body(stopped.proposal)["action"] == "stop"
    assert _body(stopped.proposal)["target_component"] == "dog"
    assert stopped.motion_authorized is True

    uncertain = _load("g16", "dog-vision-decision.json")
    _body(uncertain)["target_state"] = "uncertain"
    _body(uncertain)["suggested_action"] = "review"
    reviewed = feature.assess(uncertain, request, current_track_id="target-001")
    assert reviewed.outcome == "review"
    assert reviewed.proposal is None
    assert reviewed.motion_authorized is False

    home = _load("g16", "dog-vision-decision.json")
    home_body = _body(home)
    home_body["target_state"] = "not_visible"
    home_body["detections"] = []
    home_body["suggested_action"] = "return_home"
    returned = feature.assess(home, request, current_track_id="target-001")
    assert returned.proposal is not None
    assert _body(returned.proposal)["action"] == "return_home"

    landing = _load("g16", "dog-vision-decision.json")
    landing_body = _body(landing)
    landing_body["target_state"] = "not_visible"
    landing_body["detections"] = []
    landing_body["suggested_action"] = "land_on_dog"
    landed = feature.assess(landing, request, current_track_id="target-001")
    assert landed.proposal is not None
    assert _body(landed.proposal)["action"] == "land_on_dog"
    assert _body(landed.proposal)["target_component"] == "drone"


def test_drone_stop_is_not_a_floor_land_and_dog_actions_are_not_rewritten() -> None:
    schema = load_schema()
    context = armed_context()
    proposal = context["proposal"]
    assert isinstance(proposal, dict)
    body = payload_of(proposal)
    body["action"] = "stop"
    stopped = decide(context)
    assert stopped.ok is False
    assert stopped.reason == "stop_is_not_land"
    assert stopped.draft is None

    body["action"] = "land_on_dog"
    body["beacon_epoch"] = None
    capabilities = context["capabilities"]
    assert isinstance(capabilities, dict)
    commands = payload_of(capabilities)["supported_commands"]
    assert isinstance(commands, list)
    commands.append("land_on_dog")
    landing = decide(context)
    assert landing.ok is True
    assert landing.draft is not None
    assert landing.draft.action == "land_on_dog"
    assert landing.draft.primitive_id == "land-on-dog-v1"
    assert landing.draft.primitive_id != "verified-floor-land-v1"
    assert landing.draft.beacon_epoch is None

    body["target_component"] = "dog"
    body["action"] = "approach"
    body["beacon_epoch"] = 4
    deferred = decide(context)
    assert deferred.ok is False
    assert deferred.code == "deferred"
    assert deferred.reason == "dog_policy"
    assert deferred.draft is None
    assert deferred.dog_command is None

    context["safety_snapshot_id"] = "safety-001"
    body["action"] = "play_warning"
    body["warning_id"] = "go-away"
    body["text"] = "go away"
    body["beacon_epoch"] = None
    warning = decide(context)
    assert warning.ok is True
    assert warning.draft is None
    assert warning.dog_command is not None
    validate_message(warning.dog_command, schema)
    warning_body = _body(warning.dog_command)
    assert warning_body["action"] == "play_warning"
    assert warning_body["warning_id"] == "go-away"
    assert warning_body["text"] == "go away"
    assert warning_body["motion"] is None
    parse_dog_command(warning.dog_command)

    body["action"] = "follow"
    body.pop("warning_id")
    body.pop("text")
    body["standoff_m"] = 2.0
    followed = decide(context)
    assert followed.dog_command is not None
    validate_message(followed.dog_command, schema)
    assert _body(followed.dog_command)["action"] == "follow"
    assert _body(followed.dog_command)["standoff_m"] == 2.0

    body["action"] = "return_home"
    body.pop("standoff_m")
    returned = decide(context)
    assert returned.dog_command is not None
    assert _body(returned.dog_command)["action"] == "return_home"
    assert "standoff_m" not in _body(returned.dog_command)
