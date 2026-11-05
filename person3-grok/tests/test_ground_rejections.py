"""Emit every presence action at Ground and record the rejection."""

from pathlib import Path

from patrol.bridge.probe import run_probe, write_log

_LOG = Path(__file__).resolve().parents[1] / "handoff" / "ground_rejection_log.md"


def test_presence_actions_are_rejected_and_logged() -> None:
    report = run_probe()
    write_log(report, _LOG)
    assert _LOG.is_file()
    text = _LOG.read_text(encoding="utf-8")
    assert "play_warning" in text
    assert "land-on-dog-v1" in text

    warning = report.actions["play_warning"]
    exact = warning[0]
    assert exact.schema_ok is False
    assert exact.schema_code == "payload_shape"
    assert exact.factory == "g17.policy.decide"
    assert exact.factory_ok is False
    shaped = warning[1]
    assert shaped.schema_ok is False
    assert "play_warning" not in report.schema_enums["motion.proposal"]
    command = warning[2]
    assert command.message["kind"] == "dog.command"
    assert command.schema_ok is False

    follow = report.actions["follow"]
    assert follow[0].schema_ok is False
    assert follow[1].schema_ok is False
    assert follow[2].schema_ok is False
    assert follow[2].message["payload"]["action"] == "follow"

    stop = report.actions["stop"]
    # Proposal action "stop" is a published label. The dog command is not.
    assert stop[0].schema_ok is True
    assert stop[0].factory_ok is False
    assert stop[0].factory_reason == "wrong_component"
    assert stop[1].message["kind"] == "dog.command"
    assert stop[1].schema_ok is False
    assert stop[1].schema_reason == "payload.action"

    home = report.actions["return_home"]
    assert home[0].schema_ok is False
    assert home[1].schema_ok is False
    assert "return_home" not in report.schema_enums["dog.command"]

    land = report.actions["land_on_dog"]
    assert land[0].schema_ok is False
    assert land[0].factory_ok is False
    assert land[0].factory_reason == "unsupported_action"
    assert land[1].schema_ok is False
    command_land = next(item for item in land if item.message and item.message["kind"] == "drone.command" and item.message["payload"]["action"] == "land_on_dog")
    assert command_land.schema_ok is False
    beacon = next(item for item in land if item.label.startswith("Beacon check"))
    assert beacon.schema_ok is False
    assert beacon.schema_reason == "payload.beacon_epoch"
    assert "land_on_dog" not in report.schema_enums["drone.command"]


def test_g16_drops_dog_approach_proposals() -> None:
    report = run_probe()
    by_label = {row.label: row for row in report.g16}
    visible = by_label["dog_approach person_visible suggested approach"]
    assert visible.schema_ok is True
    assert visible.status == "ok"
    assert visible.motion_authorized is False
    assert visible.proposal_action is None
    assert "no_proposal" in visible.trace
    assert "accepted" in visible.trace

    stopish = by_label["dog_approach person_visible suggested stop"]
    assert stopish.schema_ok is True
    assert stopish.proposal_action is None
    assert "no_proposal" in stopish.trace

    gone = by_label["dog_approach not_visible suggested stop"]
    assert gone.status == "ok"
    assert gone.proposal_action is None
    assert gone.trace[0] == "hold"
    assert "no_proposal" in gone.trace

    unsure = by_label["dog_approach uncertain suggested review"]
    assert unsure.status == "ok"
    assert unsure.proposal_action is None
    assert unsure.trace[0] == "review"
    assert "no_proposal" in unsure.trace

    drone = by_label["drone_track person_visible suggested hold (proposal is emitted)"]
    assert drone.schema_ok is True
    assert drone.status == "ok"
    assert drone.proposal_action == "hold"
    assert drone.motion_authorized is False
    assert any(item.startswith("proposal:") for item in drone.trace)
