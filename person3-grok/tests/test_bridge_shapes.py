"""Bridge messages carry the presence fields and do not open a socket."""

from patrol.bridge.messages import command_message, proposal_message, schema_shaped_proposal
from patrol.trigger.presence import Intent


def _common() -> dict[str, object]:
    return dict(
        mission_id="demo-20261104-001",
        epoch=1,
        seq=1,
        track_id="target-001",
        evidence_frame_id="dog-front-presence-001",
        correlation_id="msg-dec",
        sent_at="2026-11-04T13:00:10.400Z",
        expires_at="2026-11-04T13:00:15.100Z",
    )


def test_warning_proposal_fields() -> None:
    intent = Intent("play_warning", "dog", warning_id="go-away", text="go away")
    message = proposal_message(intent, **_common())
    assert message["source"] == "vision"
    assert message["destination"] == "ground"
    assert message["kind"] == "motion.proposal"
    payload = message["payload"]
    assert payload["action"] == "play_warning"
    assert payload["target_component"] == "dog"
    assert payload["warning_id"] == "go-away"
    assert payload["text"] == "go away"
    shaped = schema_shaped_proposal(message)
    assert "warning_id" not in shaped["payload"]
    assert shaped["payload"]["action"] == "play_warning"


def test_follow_and_land_commands() -> None:
    follow = command_message(Intent("follow", "dog", standoff_m=2.0), **_common())
    assert follow["kind"] == "dog.command"
    assert follow["source"] == "ground"
    assert follow["destination"] == "dog"
    assert follow["payload"]["action"] == "follow"
    assert follow["payload"]["standoff_m"] == 2.0
    warning = command_message(
        Intent("play_warning", "dog", warning_id="go-away", text="go away"),
        **_common(),
    )
    assert warning["payload"]["warning_id"] == "go-away"
    assert warning["payload"]["text"] == "go away"
    land = command_message(Intent("land_on_dog", "drone"), **_common())
    assert land["kind"] == "drone.command"
    assert land["destination"] == "drone"
    assert land["payload"]["action"] == "land_on_dog"
    assert land["payload"]["primitive_id"] == "land-on-dog-v1"
    assert land["payload"]["beacon_epoch"] is None
