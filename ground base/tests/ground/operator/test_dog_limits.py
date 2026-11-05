from __future__ import annotations

from patrol.ground.dog_limits import apply_limits, clamp_limits, default_limits, direction_steps


def test_defaults_are_forty_percent_under_the_dog_folder() -> None:
    limits = default_limits()
    assert limits["forward_m_s"] == 0.18
    assert limits["side_m_s"] == 0.12
    assert limits["yaw_rad_s"] == 0.36
    assert limits["step_s"] == 0.6


def test_slider_cannot_pass_the_dog_folder_recommendation() -> None:
    limits = clamp_limits(
        {"forward_m_s": 5, "side_m_s": 5, "yaw_rad_s": 5, "step_s": 30}
    )
    assert limits == {
        "forward_m_s": 0.3,
        "side_m_s": 0.2,
        "yaw_rad_s": 0.6,
        "step_s": 1.0,
    }


def test_direction_test_is_forward_back_right_left() -> None:
    steps = direction_steps(default_limits())
    assert [step["command_id"] for step in steps] == [
        "dog-test-forward",
        "dog-test-back",
        "dog-test-right",
        "dog-test-left",
    ]
    assert steps[0]["vx"] == 0.18
    assert steps[1]["vx"] == -0.18
    assert steps[2]["vy"] == -0.12
    assert steps[3]["vy"] == 0.12
    assert all(step["vyaw"] == 0.0 for step in steps)


def test_a_fast_command_is_clipped_before_it_reaches_the_dog() -> None:
    bounded = apply_limits(
        {"vx": 2, "vy": -2, "vyaw": 4, "duration_s": 8, "command_id": "too-fast"},
        default_limits(),
    )
    assert bounded["vx"] == 0.18
    assert bounded["vy"] == -0.12
    assert bounded["vyaw"] == 0.36
    assert bounded["duration_s"] == 0.6
