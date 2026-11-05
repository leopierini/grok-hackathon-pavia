"""Manual flight controller with a fake SDK. No socket, no drone, no server thread."""

import errno
import json
import threading
import time

import pytest

from patrol.drone import manual
from patrol.drone.manual import (
    AIRBORNE,
    GROUNDED,
    KEEPALIVE_S,
    LANDING,
    MAX_SPEED,
    STICK_LOCKOUT_S,
    TAKING_OFF,
    WATCHDOG_S,
    Controller,
    LinkBusy,
    map_sticks,
    open_sdk,
)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeSDK:
    """Records every send and query. Replies come from `replies`, default "ok"."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.sent: list[str] = []
        self.queried: list[str] = []
        self.replies = {"command": "ok", "battery?": "80", "takeoff": "ok", "land": "ok", "streamon": "ok", "height?": "0dm"}
        self.fail: set[str] = set()
        self.state = {"h": 0, "tof": 10, "bat": 80, "yaw": 0}
        self.telemetry_on = True
        self.frozen_at: float | None = None  # telemetry stops arriving after this time
        self.gate: threading.Event | None = None  # a query for `gate_cmd` blocks until set
        self.gate_cmd = ""
        self.entered = threading.Event()

    def send(self, command: str) -> None:
        self.sent.append(command)

    def query(self, command: str, timeout: float = 5) -> str:
        self.queried.append(command)
        if command == self.gate_cmd and self.gate is not None:
            self.entered.set()
            self.gate.wait(5)
        if command in self.fail:
            raise TimeoutError("timed out")
        return self.replies.get(command, "ok")

    def snapshot(self) -> dict:
        if not self.telemetry_on:
            return {}
        at = self.clock() if self.frozen_at is None else self.frozen_at
        return {**self.state, "at": at}

    def rcs(self) -> list[str]:
        return [c for c in self.sent if c.startswith("rc ")]


def make(clock=None, **kw):
    clock = clock or Clock()
    sdk = FakeSDK(clock)
    ctrl = Controller(sdk, grabber_factory=None, clock=clock, spawn=lambda fn: fn())
    return ctrl, sdk, clock


def connected(**kw):
    ctrl, sdk, clock = make(**kw)
    assert ctrl.connect() is True
    return ctrl, sdk, clock


def flying():
    """Connected, took off, past the post-takeoff stick lockout, nothing sent yet."""
    ctrl, sdk, clock = connected()
    assert ctrl.takeoff()["ok"]
    assert ctrl.state == AIRBORNE
    clock.advance(STICK_LOCKOUT_S + 0.1)
    return ctrl, sdk, clock


# ---- stick mapping, clamping, speed ----------------------------------------------------


def test_mapping_order_and_scale():
    # rc order is left/right, forward/back, up/down, yaw
    assert map_sticks((1, 0, 0, 0), 30) == (30, 0, 0, 0)
    assert map_sticks((0, 1, 0, 0), 30) == (0, 30, 0, 0)
    assert map_sticks((0, 0, -1, 0), 30) == (0, 0, -30, 0)
    assert map_sticks((0, 0, 0, 1), 30) == (0, 0, 0, 30)
    assert map_sticks((0.5, -0.5, 0, 0), 40) == (20, -20, 0, 0)


def test_mapping_clamps_axes_and_speed():
    assert map_sticks((5, -9, 99, -1e9), 30) == (30, -30, 30, -30)
    assert map_sticks((1, 1, 1, 1), 500) == (MAX_SPEED,) * 4
    assert map_sticks((1, 1, 1, 1), -5) == (0, 0, 0, 0)
    assert all(-100 <= v <= 100 for v in map_sticks((1, 1, 1, 1), 1e6))


@pytest.mark.parametrize("bad", [None, "1", float("nan"), float("inf"), True, [1], {}])
def test_garbage_axes_are_zero(bad):
    assert map_sticks((bad, bad, bad, bad), 50) == (0, 0, 0, 0)


def test_speed_default_low_and_capped():
    ctrl, _sdk, _clock = make()
    assert ctrl.speed == 30
    assert ctrl.set_speed(500)["speed"] == MAX_SPEED
    assert ctrl.set_speed(-3)["speed"] == manual.MIN_SPEED
    assert ctrl.set_speed(45)["speed"] == 45
    assert ctrl.set_speed("fast")["ok"] is False
    assert ctrl.set_speed(float("nan"))["ok"] is False
    assert ctrl.speed == 45


def test_speed_scales_what_is_sent():
    ctrl, sdk, clock = flying()
    ctrl.set_speed(50)
    ctrl.set_sticks(1, 0.5, 0, -1)
    assert ctrl.tick() == "rc 50 25 0 -50"
    assert sdk.sent[-1] == "rc 50 25 0 -50"


# ---- link and connect ------------------------------------------------------------------


def test_connect_sends_command_and_battery_only():
    ctrl, sdk, _clock = connected()
    assert sdk.queried == ["command", "battery?"]  # video disabled here; never a motion command
    assert ctrl.link == "up" and ctrl.battery == 80
    assert not sdk.sent


def test_connect_failure_leaves_link_down_and_flies_nothing():
    ctrl, sdk, _clock = make()
    sdk.fail.add("command")
    assert ctrl.connect() is False
    assert ctrl.link == "down"
    assert ctrl.takeoff() == {"ok": False, "error": "no drone link"}
    assert ctrl.errors


# ---- watchdog --------------------------------------------------------------------------


def test_watchdog_zeroes_sticks_after_silence():
    ctrl, sdk, clock = flying()
    ctrl.set_sticks(0, 1, 0, 0)
    assert ctrl.tick() == "rc 0 30 0 0"
    clock.advance(WATCHDOG_S - 0.05)
    assert ctrl.tick() == "rc 0 30 0 0"  # still inside the window
    clock.advance(0.1)  # now 300 ms+ since the last update
    assert ctrl.tick() == "rc 0 0 0 0"
    assert ctrl.watchdog_tripped is True
    assert ctrl.axes == (0.0, 0.0, 0.0, 0.0)
    clock.advance(0.06)
    assert ctrl.tick() == "rc 0 0 0 0"  # zero burst
    assert ctrl.status()["rc"] == [0, 0, 0, 0]


def test_fresh_updates_keep_the_sticks_alive():
    ctrl, sdk, clock = flying()
    for _ in range(20):
        ctrl.set_sticks(1, 0, 0, 0)
        clock.advance(0.06)
        assert ctrl.tick() == "rc 30 0 0 0"
    assert not ctrl.watchdog_tripped


def test_release_sends_zero_at_once_then_burst():
    ctrl, sdk, clock = flying()
    ctrl.set_sticks(0, 1, 0, 0)
    ctrl.tick()
    ctrl.set_sticks(0, 0, 0, 0)  # key up
    assert ctrl.tick() == "rc 0 0 0 0"  # same tick, no waiting for the rate limit
    zeros = 1
    for _ in range(10):
        clock.advance(0.06)
        if ctrl.tick() == "rc 0 0 0 0":
            zeros += 1
    assert zeros == manual.ZERO_BURST


# ---- rate limit, last writer wins ------------------------------------------------------


def test_rc_rate_limited_and_latest_wins():
    ctrl, sdk, clock = flying()
    sent = 0
    for i in range(200):  # a page hammering at 1 kHz for 0.2 s
        ctrl.set_sticks(1 if i % 2 else -1, 0, 0, 0)
        clock.advance(0.001)
        sent += ctrl.tick() is not None
    assert sent <= 5  # 20 Hz at most
    ctrl.set_sticks(0, 0, 1, 0)
    clock.advance(0.06)
    assert ctrl.tick() == "rc 0 0 30 0"  # only the newest value is ever sent: nothing queued


def test_out_of_order_packet_from_one_page_is_dropped():
    ctrl, sdk, clock = flying()
    ctrl.set_sticks(1, 0, 0, 0, sid="a", seq=5)
    assert ctrl.set_sticks(-1, 0, 0, 0, sid="a", seq=4)["stale"] is True
    assert ctrl.tick() == "rc 30 0 0 0"
    ctrl.set_sticks(0, 1, 0, 0, sid="b", seq=1)  # another page: last writer wins
    clock.advance(0.06)
    assert ctrl.tick() == "rc 0 30 0 0"


# ---- keep-alive ------------------------------------------------------------------------


def test_keepalive_timing_when_idle_airborne():
    ctrl, sdk, clock = flying()
    assert ctrl.tick() == "rc 0 0 0 0"  # first keep-alive at once after takeoff
    count = len(sdk.rcs())
    clock.advance(KEEPALIVE_S - 0.1)
    assert ctrl.tick() is None
    assert len(sdk.rcs()) == count
    clock.advance(0.2)
    assert ctrl.tick() == "rc 0 0 0 0"
    assert KEEPALIVE_S < 15  # the Tello lands itself after ~15 s of silence


def test_no_rc_while_grounded_or_before_link():
    ctrl, sdk, clock = make()
    clock.advance(10)
    assert ctrl.tick() is None  # not connected
    ctrl.connect()
    clock.advance(10)
    assert ctrl.tick() is None  # connected but grounded
    assert not sdk.sent


def test_sticks_ignored_while_grounded_and_during_takeoff_lockout():
    ctrl, sdk, clock = connected()
    assert ctrl.set_sticks(1, 1, 1, 1)["ignored"] is True
    assert ctrl.takeoff()["ok"]
    assert ctrl.set_sticks(1, 1, 1, 1)["ignored"] is True  # lockout
    assert ctrl.tick() == "rc 0 0 0 0"
    clock.advance(STICK_LOCKOUT_S + 0.01)
    assert "rc" in ctrl.set_sticks(1, 0, 0, 0)


def test_no_rc_while_takeoff_or_land_pending():
    ctrl, sdk, clock = connected()
    ctrl._spawn = lambda fn: None  # leave the command pending
    ctrl.takeoff()
    assert ctrl.state == TAKING_OFF
    clock.advance(5)
    assert ctrl.tick() is None
    ctrl.state = AIRBORNE
    ctrl.land()
    assert ctrl.state == LANDING
    clock.advance(5)
    assert ctrl.tick() is None
    assert not sdk.rcs()


# ---- takeoff / land rules --------------------------------------------------------------


def test_takeoff_only_when_grounded():
    ctrl, sdk, clock = connected()
    assert ctrl.takeoff()["ok"]
    assert ctrl.state == AIRBORNE
    again = ctrl.takeoff()
    assert again["ok"] is False and "airborne" in again["error"]
    assert sdk.queried.count("takeoff") == 1


def test_takeoff_refused_without_link_or_battery():
    ctrl, sdk, clock = connected()
    sdk.telemetry_on = False
    ctrl.battery = None
    assert "battery unknown" in ctrl.takeoff()["error"]
    ctrl.battery = 9
    assert "below 10%" in ctrl.takeoff()["error"]
    assert "takeoff" not in sdk.queried
    ctrl.battery = 10
    assert ctrl.takeoff()["ok"]


def test_takeoff_uses_fresh_telemetry_battery():
    ctrl, sdk, clock = connected()
    sdk.state["bat"] = 8
    assert "8%" in ctrl.takeoff()["error"]
    assert ctrl.state == GROUNDED


def test_takeoff_not_confirmed_leaves_us_grounded():
    ctrl, sdk, clock = connected()
    sdk.replies["takeoff"] = "error Motor stop"
    assert ctrl.takeoff()["ok"]
    assert ctrl.state == GROUNDED
    assert "takeoff refused" in ctrl.errors[-1][1]


def test_takeoff_without_reply_assumes_airborne_so_land_and_keepalive_work():
    ctrl, sdk, clock = connected()
    sdk.fail.add("takeoff")
    ctrl.takeoff()
    assert ctrl.state == AIRBORNE
    assert ctrl.tick() == "rc 0 0 0 0"


def test_low_battery_warning_flag():
    ctrl, sdk, clock = connected()
    sdk.state["bat"] = 19
    status = ctrl.status()
    assert status["battery"] == 19 and status["battery_low"] is True
    sdk.state["bat"] = 20
    assert ctrl.status()["battery_low"] is False


def test_land_always_allowed_and_returns_to_grounded():
    ctrl, sdk, clock = flying()
    ctrl.set_sticks(1, 0, 0, 0)
    assert ctrl.land()["ok"]
    assert ctrl.state == GROUNDED
    assert sdk.queried[-1] == "land"
    assert ctrl.axes == (0.0, 0.0, 0.0, 0.0)
    assert ctrl.takeoff()["ok"] is True  # may fly again


def test_land_allowed_from_every_state():
    for state in (GROUNDED, TAKING_OFF, AIRBORNE, LANDING):
        ctrl, sdk, clock = connected()
        ctrl.state = state
        assert ctrl.land()["ok"] is True, state


def test_land_not_confirmed_resumes_keepalive_and_can_retry():
    ctrl, sdk, clock = flying()
    sdk.replies["land"] = "error"
    sdk.replies["height?"] = "7dm"
    ctrl.land()
    assert ctrl.state == AIRBORNE
    assert "land not confirmed" in ctrl.errors[-1][1]
    assert ctrl.tick() == "rc 0 0 0 0"
    sdk.replies["land"] = "ok"
    ctrl.land()
    assert ctrl.state == GROUNDED


def test_land_on_height_zero_even_if_reply_is_an_error():
    ctrl, sdk, clock = flying()
    sdk.replies["land"] = "error Not joystick"
    sdk.replies["height?"] = "0dm"
    ctrl.land()
    assert ctrl.state == GROUNDED


def test_land_is_not_blocked_by_a_pending_takeoff():
    ctrl, sdk, clock = connected()
    sdk.gate, sdk.gate_cmd = threading.Event(), "takeoff"
    ctrl._spawn = ctrl._spawn_thread
    assert ctrl.takeoff()["ok"]
    assert sdk.entered.wait(2)  # the takeoff query holds the reply channel
    started = time.monotonic()
    assert ctrl.land()["ok"] is True
    assert time.monotonic() - started < 0.5  # returned at once
    assert "land" in sdk.sent  # raw land went out without waiting for the takeoff reply
    assert ctrl.state == LANDING
    sdk.gate.set()  # takeoff reply arrives
    deadline = time.monotonic() + 3
    while ctrl.state != GROUNDED and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ctrl.state == GROUNDED
    assert sdk.queried[-1] == "land"  # confirmed with a real land query


def test_adopts_a_drone_that_is_already_flying():
    ctrl, sdk, clock = connected()
    sdk.state["h"] = 120
    assert ctrl.tick() == "rc 0 0 0 0"
    assert ctrl.state == AIRBORNE
    assert "rc" in ctrl.set_sticks(1, 0, 0, 0)  # no lockout when taking over


def test_old_height_after_landing_is_not_adopted():
    ctrl, sdk, clock = flying()
    sdk.state["h"] = 120  # stale reading right after touchdown
    ctrl.land()
    assert ctrl.state == GROUNDED
    clock.advance(1)
    assert ctrl.tick() is None
    assert ctrl.state == GROUNDED
    sdk.state["h"] = 0
    clock.advance(10)
    assert ctrl.tick() is None


# ---- emergency -------------------------------------------------------------------------


def test_emergency_needs_arming_first():
    ctrl, sdk, clock = flying()
    res = ctrl.emergency()
    assert res["ok"] is False and "arm" in res["error"]
    assert "emergency" not in sdk.sent
    assert ctrl.state == AIRBORNE


def test_emergency_not_in_the_same_click():
    ctrl, sdk, clock = flying()
    ctrl.emergency_arm()
    assert ctrl.emergency()["ok"] is False  # same instant: a double-click is not deliberate
    assert "emergency" not in sdk.sent
    clock.advance(0.5)
    assert ctrl.emergency()["ok"] is True
    assert sdk.sent.count("emergency") == 2  # sent twice: one lost datagram must not matter
    assert ctrl.state == GROUNDED


def test_emergency_arming_times_out_and_is_single_use():
    ctrl, sdk, clock = flying()
    ctrl.emergency_arm()
    clock.advance(manual.EMERGENCY_WINDOW_S + 0.1)
    assert ctrl.emergency()["ok"] is False
    ctrl.emergency_arm()
    clock.advance(0.5)
    assert ctrl.emergency()["ok"] is True
    assert ctrl.emergency()["ok"] is False  # armed once, fired once


def test_land_cancels_emergency_arming():
    ctrl, sdk, clock = flying()
    ctrl.emergency_arm()
    assert ctrl.status()["emergency_armed"] is True
    ctrl.land()
    clock.advance(0.5)
    assert ctrl.emergency()["ok"] is False


def test_nothing_else_sends_emergency():
    ctrl, sdk, clock = flying()
    for body in ({"action": "land"}, {"action": "takeoff"}, {"action": "hover"}, {"action": "speed", "value": 40},
                 {"action": "emergency"}, {"action": "nonsense"}, {}):
        ctrl.command(body)
    ctrl.set_sticks(1, 1, 1, 1)
    ctrl.tick()
    assert "emergency" not in sdk.sent


# ---- bind failure ----------------------------------------------------------------------


def test_bind_failure_message_names_the_other_process():
    def busy():
        raise OSError(errno.EADDRINUSE, "Address already in use")

    with pytest.raises(LinkBusy) as err:
        open_sdk(busy)
    text = str(err.value)
    assert "9000" in text and "patrol.drone.live" in text and "stop" in text.lower()


def test_other_os_errors_are_not_disguised():
    def broken():
        raise OSError(errno.EACCES, "Permission denied")

    with pytest.raises(OSError) as err:
        open_sdk(broken)
    assert not isinstance(err.value, LinkBusy)


def test_main_prints_message_and_exits_without_serving(monkeypatch, capsys):
    import patrol.drone.tello_sdk as tello

    def busy():
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr(tello, "TelloSDK", busy)
    assert manual.main([]) == 2
    assert "patrol.drone.live" in capsys.readouterr().err


# ---- http layer (no server thread, no socket) -------------------------------------------


def test_host_check_blocks_foreign_hosts():
    assert manual.host_ok("127.0.0.1:8766")
    assert manual.host_ok("localhost:8766")
    assert not manual.host_ok("evil.example:8766")
    assert not manual.host_ok(None)


def test_status_is_json_and_complete():
    ctrl, sdk, clock = connected()
    status = json.loads(json.dumps(ctrl.status()))
    for key in ("state", "battery", "h", "tof", "yaw", "telemetry_age", "link_ok", "last_command",
                "last_reply", "errors", "video", "rc", "speed", "emergency_armed"):
        assert key in status
    sdk.frozen_at = clock()
    clock.advance(5)
    assert ctrl.status()["link_ok"] is False  # telemetry went quiet
    assert ctrl.status()["telemetry_age"] == 5.0


def test_video_failure_does_not_affect_flight():
    class BrokenGrabber:
        log = None

        def start(self):
            raise RuntimeError("no decoder")

    clock = Clock()
    sdk = FakeSDK(clock)
    ctrl = Controller(sdk, grabber_factory=BrokenGrabber, clock=clock, spawn=lambda fn: fn())
    assert ctrl.connect() is True
    assert ctrl.video == "down" and "no decoder" in ctrl.video_error
    assert ctrl.status()["video"] == "down"
    assert ctrl.takeoff()["ok"]
    clock.advance(STICK_LOCKOUT_S + 0.1)
    ctrl.set_sticks(0, 1, 0, 0)
    assert ctrl.tick() == "rc 0 30 0 0"
    assert ctrl.frame_jpeg() is None


def test_streamon_failure_marks_video_down_only():
    clock = Clock()
    sdk = FakeSDK(clock)
    sdk.fail.add("streamon")
    ctrl = Controller(sdk, grabber_factory=lambda: None, clock=clock, spawn=lambda fn: fn())
    assert ctrl.connect() is True
    assert ctrl.video == "down"
    assert ctrl.link == "up"
