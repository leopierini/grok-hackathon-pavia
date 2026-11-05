"""Continuous recon flight: perception and Jev on side threads, rc at 10 Hz here.

The reflex thread measures every new video frame. The Jev thread sends the
newest frame, waits for the answer, and sends the next one. The control
loop never waits on either: it reads whatever is newest, asks the
navigator, and sends one `rc` per tick. Whatever goes wrong, the last thing
sent is `rc 0 0 0 0`, because the Tello keeps flying the last stick it got.

A scan is a turn in place at about 60°/s that stops every 90°: sticks to
zero, a short settle, then the first frame decoded after the settle. The
Tello stream runs 200 to 400 ms late, so a frame grabbed while turning shows
a heading 12 to 24° back and is smeared. Then one Jev call on all four, and
a yaw-stick turn toward the pick.
`cw` and `ccw` are refused while the sticks are active, so every turn
goes through `rc`.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import asdict

from patrol.drone import jev
from patrol.drone.navigator import Limits, Navigator, Seen, View, choose_heading

TICK_S = 0.1
PUBLISH_S = 0.25
REFLEX_HZ = 15
SCAN_DPS = 60
SCAN_STOPS = 4
SCAN_SETTLE_S = 0.3
SCAN_FRAME_TIMEOUT_S = 1.0
YAW_STICK_PER_DPS = 1.0
CAMERA_FOV_DEG = 56.0
CENTER_TOLERANCE_DEG = 5
FAILED_SCANS_TO_LAND = 3
LOW_BATTERY = 25
VETOES_KEPT = 2
VIDEO_RETRY_S = 1.5
VIDEO_LOST_S = 10.0
YAW_TOLERANCE_DEG = 8.0


def stick(value: float, per_unit: float) -> int:
    return max(-100, min(100, int(round(value * per_unit))))


def nearest(headings: list[int], target: float) -> int:
    return min(headings, key=lambda h: abs((h - target + 180) % 360 - 180))


class Explorer:
    def __init__(self, pilot, grabber, reflex, client, limits: Limits, brain: str, duration_s: float) -> None:
        self.pilot = pilot
        self.grabber = grabber
        self.reflex = reflex
        self.client = client
        self.limits = limits
        self.brain = brain
        self.duration_s = duration_s
        self.nav = Navigator(limits, brain, started_at=time.monotonic())
        self.fb_per_mps = float(pilot.settings["stick"]) / float(pilot.settings["speed_mps"])
        self._lock = threading.Lock()
        self._reading = None
        self._seen: Seen | None = None
        self._jev_error = ""
        self._jev_ms: float | None = None
        self._running = threading.Event()
        self._guide_on = threading.Event()
        self._threads: list[threading.Thread] = []
        self._yaw0: int | None = None
        self._scan_count = 0
        self._travel: float | None = None
        self._vetoes: list[float] = []
        self.people: list[dict] = []
        self._video_revived_at = 0.0

    # side threads

    def _perceive(self) -> None:
        last = 0.0
        period = 1.0 / REFLEX_HZ
        while self._running.is_set():
            started = time.monotonic()
            image, at = self.grabber.latest()
            if image is not None and at > last:
                last = at
                try:
                    reading = self.reflex.measure(image, at=at)
                except Exception as exc:
                    self.pilot._say(f"  reflex failed: {exc}")
                    reading = None
                with self._lock:
                    self._reading = reading
            time.sleep(max(0.0, period - (time.monotonic() - started)))

    def _guide(self) -> None:
        last = 0.0
        while self._running.is_set():
            if not self._guide_on.wait(timeout=0.1):
                continue
            image, at = self.grabber.latest()
            if image is None or at <= last:
                time.sleep(0.02)
                continue
            last = at
            try:
                guide = self.client.guide(jev.encode_frame(image), self.pilot._camera_height_cm())
            except jev.JevError as exc:
                with self._lock:
                    self._jev_error = str(exc)
                time.sleep(0.2)
                continue
            seen = Seen(guide.blocked, guide.steer, guide.steer_confidence, guide.person, at)
            with self._lock:
                self._seen = seen
                self._jev_error = ""
                self._jev_ms = guide.latency_s * 1000
                self.nav.note(seen)

    def _start_threads(self) -> None:
        self._running.set()
        targets = [self._perceive]
        if self.client is not None:
            targets.append(self._guide)
            self._guide_on.set()
        for target in targets:
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)

    def _stop_threads(self) -> None:
        self._running.clear()
        self._guide_on.clear()
        for thread in self._threads:
            thread.join(timeout=5)
        self._threads = []

    # control

    def _rc(self, fb_mps: float = 0.0, yaw_dps: float = 0.0) -> None:
        self.pilot.sdk.send(f"rc 0 {stick(fb_mps, self.fb_per_mps)} 0 {stick(yaw_dps, YAW_STICK_PER_DPS)}")

    def _halt(self) -> None:
        self.pilot.sdk.send("rc 0 0 0 0")

    def _telemetry_heading(self) -> float | None:
        yaw = self.pilot.sdk.snapshot().get("yaw")
        if yaw is None:
            return None
        if self._yaw0 is None:
            self._yaw0 = yaw
        return (yaw - self._yaw0) % 360

    def _battery(self) -> int | None:
        return self.pilot.sdk.snapshot().get("bat")

    def run(self) -> str:
        self._telemetry_heading()
        self._start_threads()
        failed_scans = 0
        last_publish = 0.0
        last_tick = time.monotonic()
        end = last_tick + self.duration_s
        outcome = "done"
        try:
            while True:
                now = time.monotonic()
                dt = now - last_tick
                last_tick = now
                if self.pilot._stop_requested():
                    outcome = "stopped"
                    break
                if now >= end:
                    outcome = "done"
                    break
                battery = self._battery()
                if battery is not None and battery < LOW_BATTERY:
                    self.pilot._say(f"battery {battery}%; landing")
                    outcome = "battery"
                    break
                heading = self._telemetry_heading()
                if heading is not None:
                    self.nav.pose.turn_to(heading)
                with self._lock:
                    reading, seen = self._reading, self._seen
                self.nav.stop_on_person = bool(self.pilot.settings.get("stop_on_person", True))
                command = self.nav.step(now, reading, seen)
                _frame, frame_at = self.grabber.latest()
                quiet = now - max(frame_at, self.nav.started_at)
                if quiet > VIDEO_RETRY_S and now - self._video_revived_at > VIDEO_RETRY_S:
                    self._video_revived_at = now
                    self.pilot._say("video stalled; asking for the stream again")
                    try:
                        self.pilot.sdk.query("streamon", timeout=1)
                    except Exception as exc:
                        self.pilot._say(f"  streamon failed: {exc}")
                if command.mode == "cruise":
                    self._rc(command.fb_mps, command.yaw_dps)
                    self.nav.pose.advance(command.fb_mps, dt)
                    if heading is None:
                        self.nav.pose.turn_to(self.nav.pose.heading + command.yaw_dps * dt)
                    if command.fb_mps > 0:
                        self._travel = self.nav.pose.heading
                    failed_scans = 0
                elif command.mode == "hold":
                    self._halt()
                    if quiet > VIDEO_LOST_S:
                        self.pilot._say(f"no video for {VIDEO_LOST_S:.0f} s; landing")
                        outcome = "video"
                        break
                elif command.mode == "scan":
                    self._halt()
                    self.pilot._say(f"scan: {command.reason}")
                    if command.reason.startswith("jev blocked"):
                        self._vetoes = (self._vetoes + [self.nav.pose.heading])[-VETOES_KEPT:]
                    scanned = self._scan()
                    if scanned:
                        failed_scans = 0
                    else:
                        failed_scans += 1
                        if failed_scans >= FAILED_SCANS_TO_LAND:
                            self.pilot._say(f"{failed_scans} scans in a row found no way; hovering")
                            outcome = "stuck"
                            break
                    last_tick = time.monotonic()
                elif command.mode == "person":
                    self._halt()
                    self._person(seen)
                    outcome = "person"
                    break
                if now - last_publish >= PUBLISH_S:
                    last_publish = now
                    self._publish(command, reading, seen)
                time.sleep(max(0.0, TICK_S - (time.monotonic() - now)))
        finally:
            try:
                self._halt()
            finally:
                self._stop_threads()
        return outcome

    def _publish(self, command, reading, seen) -> None:
        pose = self.nav.pose
        with self._lock:
            jev_ms = self._jev_ms
            jev_error = self._jev_error
        now = time.monotonic()
        self.pilot._publish(
            live={
                "mode": command.mode,
                "reason": command.reason,
                "fb_mps": round(command.fb_mps, 2),
                "yaw_dps": round(command.yaw_dps, 1),
                "ahead_m": None if reading is None else round(reading.center_m, 2),
                "near_m": None if reading is None or reading.near_m is None else round(reading.near_m, 2),
                "left_m": None if reading is None else round(reading.left_m, 2),
                "right_m": None if reading is None else round(reading.right_m, 2),
                "reflex_ms": None if reading is None else round(reading.seconds * 1000),
                "reflex_age_s": None if reading is None else round(now - reading.at, 2),
                "blocked": None if seen is None else round(seen.blocked, 2),
                "steer": None if seen is None else seen.steer,
                "person": None if seen is None else round(seen.person, 2),
                "jev_ms": None if jev_ms is None else round(jev_ms),
                "jev_age_s": None if seen is None else round(now - seen.at, 2),
                "jev_error": jev_error,
                "brain": self.brain,
                "x": round(pose.x, 2),
                "y": round(pose.y, 2),
                "heading": round(pose.heading),
                "scans": self._scan_count,
            },
            phase="exploring" if command.mode == "cruise" else command.mode,
        )

    # scan

    def _scan(self) -> bool | None:
        board = self.pilot.board
        self._guide_on.clear()
        index = self._scan_count
        self._scan_count += 1
        self.pilot._publish(phase="scanning", scan=index + 1)
        time.sleep(0.3)
        previous = self._telemetry_heading()
        base = self.nav.pose.heading if previous is None else previous
        turned = 0.0
        shots: list[tuple[int, object, float]] = []
        for stop in range(SCAN_STOPS):
            segment_start = time.monotonic()
            segment_turned = turned
            deadline = segment_start + 1.6 * 90 / SCAN_DPS + 0.5
            while turned < 90 * stop - 3:
                if self.pilot._stop_requested():
                    self._halt()
                    return False
                if time.monotonic() > deadline:
                    break
                self._rc(0.0, SCAN_DPS)
                time.sleep(TICK_S / 2)
                heading = self._telemetry_heading()
                if heading is not None and previous is not None:
                    step = (heading - previous + 180) % 360 - 180
                    if step > 0:
                        turned += step
                    previous = heading
                else:
                    turned = segment_turned + (time.monotonic() - segment_start) * SCAN_DPS
            self._halt()
            time.sleep(SCAN_SETTLE_S)
            image, at = self.grabber.frame_after(time.monotonic(), timeout=SCAN_FRAME_TIMEOUT_S)
            settled = self._telemetry_heading()
            if settled is not None and previous is not None:
                step = (settled - previous + 180) % 360 - 180
                if step > 0:
                    turned += step
                previous = settled
            absolute = int(round(base + turned)) % 360
            if image is None:
                self.pilot._say(f"  no fresh frame at {absolute}°; skipped")
                continue
            shots.append((absolute, image, at))
        self._halt()
        if not shots:
            self.pilot._say("  scan got no frames")
            return False
        views: dict[int, View] = {}
        frames_b64: list[tuple[int, str]] = []
        files: dict[int, str] = {}
        for absolute, image, at in shots:
            reading = self.reflex.measure(image, at=at)
            views[absolute] = View(reading.center_m)
            name = f"scan{index}-h{absolute:03d}.jpg"
            if board is not None:
                image.save(board.folder / name)
            files[absolute] = name
            if self.client is not None:
                frames_b64.append((absolute, jev.encode_frame(image)))
        headings = list(views)
        back = None if self._travel is None else nearest(headings, self._travel + 180)
        choice = None
        if self.client is not None:
            scan = self.client.scan(frames_b64, back, self.pilot._camera_height_cm())
            choice = scan.choice
            for heading, judgment in scan.judgments.items():
                views[heading] = View(views[heading].reflex_m, judgment.blocked, judgment.room_m, judgment.person)
        chosen, why = choose_heading(views, choice, self.nav.pose, self.limits, back, self._vetoes)
        for heading, view in views.items():
            reason = why.get(heading)
            line = f"  {heading:3d}°  reflex {view.reflex_m:.2f} m"
            if view.blocked is not None:
                line += f"  jev blocked {view.blocked:.2f} room {view.room_m:.1f} m person {view.person:.2f}"
            line += "  ok" if reason is None else f"  no: {reason}"
            self.pilot._say(line)
            if board is not None:
                frame = {"step": index, "heading": heading, "file": files[heading], "height_cm": self.pilot._camera_height_cm()}
                frame.update({key: (round(value, 2) if isinstance(value, float) else value) for key, value in asdict(view).items()})
                frame["why"] = reason
                frame["picked"] = heading == chosen
                frame["jev_pick"] = heading == choice
                board.add_frame(frame)
        if chosen is None:
            self.pilot._say("  no safe heading")
            self._guide_on.set()
            return False
        reached = self._yaw_to(chosen)
        self.nav.reset_person()
        with self._lock:
            self._seen = None
        self.nav.started_at = time.monotonic()
        note = "" if abs((reached - chosen + 180) % 360 - 180) <= YAW_TOLERANCE_DEG else f" (wanted {chosen}°)"
        self.pilot._say(f"  -> {reached:.0f}°{note}" + (" (jev pick)" if chosen == choice else ""))
        self._guide_on.set()
        return True

    def _yaw_to(self, target: float) -> float:
        """Turn in place with the yaw stick until the telemetry heading is there.

        The Tello refuses `cw` and `ccw` while it is flying on `rc`.
        """
        deadline = time.monotonic() + 360 / SCAN_DPS + 2.0
        while not self.pilot._stop_requested() and time.monotonic() < deadline:
            current = self._telemetry_heading()
            if current is None:
                current = self.nav.pose.heading
            delta = (target - current + 180) % 360 - 180
            if abs(delta) <= YAW_TOLERANCE_DEG:
                break
            rate = math.copysign(min(SCAN_DPS, max(20.0, abs(delta))), delta)
            self._rc(0.0, rate)
            time.sleep(TICK_S / 2)
            if self._telemetry_heading() is None:
                self.nav.pose.turn_to((current + rate * TICK_S / 2) % 360)
        self._halt()
        reached = self._telemetry_heading()
        if reached is None:
            reached = self.nav.pose.heading
        self.nav.pose.turn_to(reached)
        return reached

    # person

    def _person(self, seen: Seen | None) -> None:
        self.pilot._publish(phase="person")
        image, _at = self.grabber.latest()
        box = None
        if image is not None and self.client is not None:
            try:
                box = self.client.box(jev.encode_frame(image))
            except jev.JevError as exc:
                self.pilot._say(f"  person box failed: {exc}")
        if box is not None and box.person >= self.limits.person_limit:
            offset = (box.center_x - 0.5) * CAMERA_FOV_DEG
            if abs(offset) > CENTER_TOLERANCE_DEG and not self.pilot._stop_requested():
                self._yaw_to(self.nav.pose.heading + offset)
            image, _at = self.grabber.latest()
        pose = self.nav.pose
        name = f"person{len(self.people)}.jpg"
        if image is not None and self.pilot.board is not None:
            image.save(self.pilot.board.folder / name)
        found = {
            "x": round(pose.x, 2),
            "y": round(pose.y, 2),
            "heading": round(pose.heading),
            "file": name if image is not None else None,
            "person": None if seen is None else round(seen.person, 2),
            "box": None if box is None else asdict(box),
        }
        self.people.append(found)
        self.pilot._say(f"person in view at x {pose.x:.1f} m, y {pose.y:.1f} m, heading {pose.heading:.0f}°")
        self.pilot._publish(phase="person", person=found, note="going to the person")
        self.pilot.follow_person(self.grabber, self._spot_person)

    def _spot_person(self, image):
        """The person's box in this frame, or None when the detector does not see one."""
        if image is None or self.client is None:
            return None
        try:
            return self.client.box(jev.encode_frame(image))
        except Exception:
            return None
