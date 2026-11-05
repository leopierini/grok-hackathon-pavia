"""Presence session: warn, follow, leave, halt, timeout."""

from patrol.grok.presence import (
    PRESENCE_PROMPT_VERSION,
    image_direction,
    presence_state,
    suggested_action,
)
from patrol.trigger.presence import PresenceSession


def test_prompt_and_mapping() -> None:
    assert PRESENCE_PROMPT_VERSION == "patrol-presence-v1"
    assert presence_state("still_there") == "person_visible"
    assert suggested_action("dog_approach", "person_visible") == "approach"
    assert suggested_action("drone_track", "person_visible") == "hold"
    assert suggested_action("dog_approach", "not_visible") == "stop"
    assert suggested_action("dog_approach", "uncertain") == "review"
    assert suggested_action("dog_approach", "timeout") == "review"


def test_image_direction_thirds() -> None:
    assert image_direction([0.0, 0.0, 0.2, 0.5]) == "left"
    assert image_direction([0.3, 0.2, 0.55, 0.8]) == "center"
    assert image_direction([0.7, 0.1, 0.95, 0.9]) == "right"
    assert image_direction(None) == "unknown"


def test_visible_then_follow_then_gone() -> None:
    session = PresenceSession()
    first = session.on_presence("person_visible", "dog_approach")
    second = session.on_presence("person_visible", "dog_approach")
    gone = session.on_presence("not_visible", "dog_approach")
    assert [item.action for item in first] == ["play_warning"]
    assert first[0].warning_id == "go-away"
    assert first[0].text == "go away"
    assert [item.action for item in second] == ["follow", "play_warning"]
    assert second[0].standoff_m == 2.0
    assert [item.action for item in gone] == ["stop", "land_on_dog", "return_home"]
    assert gone[1].target == "drone"
    assert session.on_presence("person_visible", "dog_approach") == []


def test_leaves_immediately() -> None:
    session = PresenceSession()
    gone = session.on_presence("not_visible", "dog_approach")
    assert [item.action for item in gone] == ["stop", "land_on_dog", "return_home"]
    assert session.warned is False


def test_unsure_and_timeout_move_nothing() -> None:
    session = PresenceSession()
    assert session.on_presence("uncertain", "dog_approach") == []
    assert session.on_presence("timeout", "dog_approach") == []
    assert session.on_presence("person_visible", "drone_track") == []


def test_halt_mid_follow_wins() -> None:
    session = PresenceSession()
    session.on_presence("person_visible", "dog_approach")
    session.on_presence("person_visible", "dog_approach")
    halted = session.halt()
    assert [item.action for item in halted] == ["halt"]
    assert session.halt() == []
    assert session.on_presence("person_visible", "dog_approach") == []
    assert session.on_presence("not_visible", "dog_approach") == []
