"""One owner for the Tello: takeoff, patrol, hover, land.

The live page and the command line both call this. A worker thread runs
one action at a time. Land sets `abort` so a patrol stops and lands once.
"""

from __future__ import annotations

import json
import math
import queue
import threading
import time
from collections import deque
from pathlib import Path

from patrol.drone.marker_land import (
    LAND_CM,
    MarkerLander,
    downward_view,
    landing_move,
    marker_offset_cm,
)
from patrol.drone.recon import (
    height_commands,
    parse_height_cm,
    parse_pad_id,
)
from patrol.drone.tello_sdk import TelloSDK

ROOT_DEFAULT = Path("artifacts/drone/recon")
BRAINS = ("local", "jev", "reflex-only")
READ_TIMEOUT_S = 8.0
PAD_PHOTO_S = 1.0
SETTING_KEYS = (
    "height_cm",
    "stick",
    "speed_mps",
    "cruise_mps",
    "brake_m",
    "geofence_m",
    "brain",
    "explore_s",
    "pad",
    "pad_id",
    "down_photo",
    "stop_on_person",
)


def _blank(settings: dict) -> dict:
    blank = {
        "phase": "waiting",
        "scan": 0,
        "battery": None,
        "frames": [],
        "live": None,
        "person": None,
        "note": "",
        "airborne": False,
        "run_id": None,
        "reply": "",
        "height_cm_now": None,
        "mid": -1,
        "pad_x": None,
        "pad_y": None,
    }
    blank.update({key: settings[key] for key in SETTING_KEYS})
    return blank


class Board:
    """Flight record for one run. Also mirrors itself to the recon root."""

    def __init__(self, folder: Path, settings: dict, run_id: str) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.folder = folder
        self.path = folder / "state.json"
        self.mirror = folder.parent / "state.json"
        self.data = _blank(settings)
        self.data["run_id"] = run_id
        self.data["phase"] = "connecting"
        self._write()

    def set(self, **fields) -> None:
        self.data.update(fields)
        self._write()

    def add_frame(self, frame: dict) -> None:
        self.data["frames"].append(frame)
        self._write()

    def _write(self) -> None:
        body = json.dumps(self.data)
        for path in (self.path, self.mirror):
            tmp = path.with_suffix(".tmp")
            tmp.write_text(body)
            tmp.replace(path)


class FrameGrabber:
    """Decode the video stream on a side thread and keep only the newest frame.

    A capture waits for a frame decoded after a deadline, so a photo taken
    just after a turn is not a frame that was still sitting in the buffer.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._image = None
        self._at = 0.0
        self.log = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import av
        except ImportError:
            self._error = "video decoder missing"
            return
        while not self._stop.is_set():
            container = None
            try:
                # A short read timeout aborts the demuxer with "Immediate exit
                # requested" and drops the stream. Eight seconds rides out a WiFi
                # gap; close() still unblocks because of the same timeout.
                container = av.open(
                    "udp://0.0.0.0:11111",
                    timeout=(8, READ_TIMEOUT_S),
                    options={"overrun_nonfatal": "1", "fifo_size": "50000", "reuse": "1"},
                )
                for frame in container.decode(video=0):
                    if self._stop.is_set():
                        break
                    picture = frame.to_image()
                    if picture.size[0] < 16:
                        continue
                    with self._lock:
                        self._image = picture
                        self._at = time.monotonic()
                        self._error = None
            except Exception as exc:
                if self._stop.is_set():
                    break
                text = f"  capture failed: {exc}"
                print(text)
                if self.log:
                    self.log(text)
                time.sleep(0.2)
            finally:
                if container is not None:
                    container.close()

    def ready(self) -> bool:
        with self._lock:
            return self._image is not None

    def latest(self):
        """Newest decoded frame and when it was decoded, or (None, 0.0)."""
        with self._lock:
            return self._image, self._at

    def frame_after(self, not_before: float, timeout: float = 2.5):
        """First frame decoded at or after `not_before`, or (None, 0.0) if none comes in time."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                image, at, error = self._image, self._at, self._error
            if image is not None and at >= not_before:
                return image, at
            if error == "video decoder missing":
                break
            time.sleep(0.02)
        return None, 0.0

    def capture(self, dest: Path, not_before: float, timeout: float = 2.5) -> bool:
        image, _at = self.frame_after(not_before, timeout)
        if image is None:
            return False
        image.save(dest)
        return True

    def close(self) -> None:
        """Waits for the decoder to let go of port 11111, or the next stream cannot bind."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=READ_TIMEOUT_S + 2.0)


class Pilot:
    def __init__(
        self,
        output_root: Path | None = None,
        sdk_factory=TelloSDK,
        grabber_factory=FrameGrabber,
        reflex_factory=None,
        jev_factory=None,
    ) -> None:
        self.output_root = Path(output_root) if output_root else ROOT_DEFAULT
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._sdk_factory = sdk_factory
        self._grabber_factory = grabber_factory
        self.settings = {
            "height_cm": 100,
            "stick": 25,
            "speed_mps": 0.4,
            "cruise_mps": 0.2,
            "brake_m": 1.0,
            "geofence_m": 4.0,
            "brain": "local",
            "explore_s": 60,
            "pad": False,
            "pad_id": "any",
            "down_photo": False,
            "stop_on_person": True,
        }
        self.abort = threading.Event()
        self.hold = threading.Event()
        self.sdk = None
        self.board: Board | None = None
        self.airborne = False
        self._landed = True
        self._blocked = False
        self._run_open = False
        self._busy = False
        self._grabber: FrameGrabber | None = None
        self._reflex_factory = reflex_factory
        self._jev_factory = jev_factory
        self._local = None
        self._reflex = None
        self._keep_hover = False
        self._pad_detect_on = False
        self._pad_watching = False
        self._kept_at = 0.0
        self._height_applied: int | None = None
        self._lines: deque[str] = deque(maxlen=80)
        self._lock = threading.Lock()
        self._queue: queue.Queue[str] = queue.Queue()
        self._worker: threading.Thread | None = None
        self.status = _blank(self.settings)

    def start(self) -> None:
        self._worker = threading.Thread(target=self._loop, daemon=True)
        self._worker.start()
        threading.Thread(target=self._air_loop, daemon=True).start()

    def update_settings(self, raw: dict) -> str | None:
        cleaned: dict = {}
        previous_height = self.settings["height_cm"]
        if "height_cm" in raw and raw["height_cm"] is not None:
            value = int(raw["height_cm"])
            if not 40 <= value <= 300:
                return "height must be 40 to 300 cm"
            cleaned["height_cm"] = value
        if "stick" in raw and raw["stick"] is not None:
            value = int(raw["stick"])
            if not 10 <= value <= 50:
                return "stick must be 10 to 50"
            cleaned["stick"] = value
        if "speed_mps" in raw and raw["speed_mps"] is not None:
            value = float(raw["speed_mps"])
            if not 0.1 <= value <= 1.5:
                return "speed must be 0.1 to 1.5 m/s"
            cleaned["speed_mps"] = value
        if "cruise_mps" in raw and raw["cruise_mps"] is not None:
            value = float(raw["cruise_mps"])
            if not 0.1 <= value <= 0.8:
                return "cruise must be 0.1 to 0.8 m/s"
            cleaned["cruise_mps"] = value
        if "brake_m" in raw and raw["brake_m"] is not None:
            value = float(raw["brake_m"])
            if not 0.6 <= value <= 2.5:
                return "brake distance must be 0.6 to 2.5 m"
            cleaned["brake_m"] = value
        if "geofence_m" in raw and raw["geofence_m"] is not None:
            value = float(raw["geofence_m"])
            if not 1 <= value <= 15:
                return "geofence must be 1 to 15 m"
            cleaned["geofence_m"] = value
        if "brain" in raw and raw["brain"] is not None:
            if raw["brain"] not in BRAINS:
                return "brain must be local, jev or reflex-only"
            cleaned["brain"] = raw["brain"]
        if "explore_s" in raw and raw["explore_s"] is not None:
            value = int(raw["explore_s"])
            if not 10 <= value <= 300:
                return "flight time must be 10 to 300 s"
            cleaned["explore_s"] = value
        if "pad" in raw and raw["pad"] is not None:
            cleaned["pad"] = bool(raw["pad"])
            if not cleaned["pad"]:
                self._pad_detect_on = False
        if "down_photo" in raw and raw["down_photo"] is not None:
            cleaned["down_photo"] = bool(raw["down_photo"])
        if "stop_on_person" in raw and raw["stop_on_person"] is not None:
            cleaned["stop_on_person"] = bool(raw["stop_on_person"])
        if "pad_id" in raw and raw["pad_id"] is not None:
            try:
                parse_pad_id(str(raw["pad_id"]))
            except ValueError:
                return "pad id must be any or m1 through m8"
            cleaned["pad_id"] = str(raw["pad_id"]).lower()
        with self._lock:
            self.settings.update(cleaned)
            self.status.update({key: self.settings[key] for key in SETTING_KEYS})
        if self.board is not None and cleaned:
            self.board.set(**cleaned)
        if "height_cm" in cleaned and cleaned["height_cm"] != previous_height and self.airborne:
            self._request_height()
        if cleaned.get("pad"):
            self._request_pad()
        return None

    def submit(self, body: dict) -> dict:
        action = body.get("action")
        if action == "set":
            error = self.update_settings(body)
            return {"ok": error is None, "error": error}
        if action == "land":
            self.abort.set()
            with self._lock:
                if self.airborne or self._blocked:
                    self._landed = False
                if not self._busy:
                    self._busy = True
                self._queue.put("land")
            return {"ok": True}
        if action == "hover":
            self.hold.set()
            with self._lock:
                if not self._busy and self.airborne:
                    self._busy = True
                    self._queue.put("hover")
            return {"ok": True}
        if action == "patrol" and body.get("explore_s") is not None:
            error = self.update_settings({"explore_s": body.get("explore_s")})
            if error:
                return {"ok": False, "error": error}
        if action in ("takeoff", "patrol"):
            with self._lock:
                if self._busy:
                    return {"ok": False, "error": "busy"}
                if action == "takeoff" and self.airborne and not self._blocked:
                    return {"ok": False, "error": "already flying"}
                self.abort.clear()
                self.hold.clear()
                self._busy = True
                self._queue.put(action)
            return {"ok": True}
        return {"ok": False, "error": "unknown action"}

    def snapshot(self) -> dict | None:
        with self._lock:
            if self.board is not None:
                data = json.loads(json.dumps(self.board.data))
            elif self.status.get("phase") != "waiting" or self.status.get("note") or self._lines:
                data = json.loads(json.dumps(self.status))
            else:
                return None
            data["log"] = list(self._lines)
            return data

    def _say(self, text: str) -> None:
        print(text)
        self._lines.append(text)

    def run_patrol(self) -> int:
        with self._lock:
            self._busy = True
        try:
            return 0 if self._patrol_body() else 1
        finally:
            with self._lock:
                self._busy = False

    def _loop(self) -> None:
        while True:
            action = self._queue.get()
            try:
                if action == "takeoff":
                    self._takeoff_body()
                elif action == "patrol":
                    self._patrol_body()
                elif action == "land":
                    self._ensure_sdk()
                    self._land_once()
                elif action == "hover":
                    self._finish_motion()
                    self._publish(phase="hovering", note="hover", airborne=True)
                elif action == "height":
                    self._go_height()
                    if self.abort.is_set() and self.airborne:
                        self._land_once()
                elif action == "pad":
                    self._watch_pad()
            except Exception as exc:
                print(f"pilot failed: {exc}")
                self._publish(phase="failed", note=str(exc))
                if self.airborne:
                    self._land_once(precise=False)
            finally:
                with self._lock:
                    self._busy = False

    def _publish(self, **fields) -> None:
        fields["airborne"] = self.airborne
        self.status.update(fields)
        if self.board is not None:
            self.board.set(**fields)
        else:
            mirror = self.output_root / "state.json"
            tmp = mirror.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.status))
            tmp.replace(mirror)

    def _stop_requested(self) -> bool:
        return self.abort.is_set() or self.hold.is_set()

    def _ensure_sdk(self) -> None:
        if self.sdk is None:
            self.sdk = self._sdk_factory()

    def _ensure_model(self) -> bool:
        if self._reflex is not None:
            return True
        self._publish(phase="loading model")
        try:
            if self._reflex_factory is not None:
                self._reflex = self._reflex_factory()
            else:
                from patrol.drone.reflex import Reflex

                self._reflex = Reflex()
        except FileNotFoundError as exc:
            self._publish(phase="failed", note=str(exc))
            return False
        print(f"reflex depth model on {getattr(self._reflex, 'device', '?')}")
        return True

    def _jev_client(self):
        """A Jev client, local or remote, or None with the reason published when it cannot run."""
        if self._jev_factory is not None:
            return self._jev_factory()
        if self.settings["brain"] == "local":
            return self._local_brain()
        from patrol.drone.jev import JevClient, api_key

        key = api_key()
        if not key:
            self._publish(phase="refused", note="no OPENROUTER_API_KEY; set it or pick reflex-only")
            return None
        return JevClient(key)

    def _local_brain(self):
        """Loaded once and kept: the models take several seconds to load."""
        if self._local is None:
            from patrol.drone.local import LocalBrain

            self._publish(phase="loading model", note="local brain")
            try:
                self._local = LocalBrain()
            except (FileNotFoundError, ValueError, OSError) as exc:
                self._publish(phase="failed", note=f"local brain: {exc}")
                return None
            print(f"local brain {self._local.judge.name} on {self._local.device}")
        return self._local

    def _begin_run(self) -> None:
        if self._run_open and self.board is not None:
            return
        run_id = time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())
        self.board = Board(self.output_root / run_id, self.settings, run_id)
        self._run_open = True

    def _query(self, command: str, timeout: float = 5) -> str:
        assert self.sdk is not None
        try:
            reply = self.sdk.query(command, timeout=timeout)
        except Exception as exc:
            self._say(f"{command} failed: {exc}; retrying")
            reply = self.sdk.query(command, timeout=timeout)
        self._say(f"{command} -> {reply}")
        self._kept_at = time.monotonic()
        self._publish(reply=reply)
        self._note_pad()
        return reply

    def _note_pad(self) -> None:
        if self.sdk is None:
            return
        snap = self.sdk.snapshot()
        if not snap:
            return
        self._publish(
            mid=snap.get("mid", -1),
            pad_x=snap.get("x"),
            pad_y=snap.get("y"),
        )

    def _connect(self) -> bool:
        self._ensure_sdk()
        self._publish(phase="connecting")
        try:
            if self._query("command") != "ok":
                self._publish(phase="failed", note="no sdk link")
                return False
            battery = int(self._query("battery?"))
        except Exception as exc:
            self._publish(phase="failed", note=str(exc))
            return False
        print(f"battery {battery}%")
        self._publish(battery=battery)
        if battery < 20:
            print("refusing to fly below 20%")
            self._publish(phase="refused", note="battery below 20%")
            return False
        return True

    def _ready_to_arm(self) -> bool:
        """A dropped link locks takeoff until the drone reads as on the ground."""
        if not self._blocked:
            return True
        self._ensure_sdk()
        try:
            self._query("command", timeout=3)
            height = self._query("height?", timeout=3)
        except Exception as exc:
            self._say(f"cannot confirm it is down: {exc}")
            self._publish(phase="failed", note="flight state unknown; do not take off again")
            return False
        now = parse_height_cm(height)
        self._publish(height_cm_now=now)
        if now != 0:
            self._say(f"still at {height}; land before another takeoff")
            self.airborne = True
            self._publish(phase="hovering", note="still in the air", airborne=True)
            return False
        self._blocked = False
        self.airborne = False
        self._landed = True
        self._publish(phase="landed", note="on the ground", airborne=False, height_cm_now=0)
        return True

    def _arm(self) -> bool:
        if not self._ready_to_arm():
            return False
        if self.airborne:
            return True
        if not self._connect():
            return False
        try:
            self._query("downvision 0", timeout=3)
        except Exception as exc:
            print(f"downvision reset skipped: {exc}")
        self._pad_detect_on = False
        self._landed = False
        self._publish(phase="taking off")
        try:
            reply = self._query("takeoff", timeout=20)
        except Exception as exc:
            self._publish(phase="failed", note="takeoff not confirmed")
            print(f"takeoff failed: {exc}")
            self._land_once(precise=False)
            return False
        if reply != "ok":
            print("takeoff was not confirmed; no second attempt")
            self._publish(phase="failed", note="takeoff not confirmed")
            self._land_once(precise=False)
            return False
        self.airborne = True
        self._publish(phase="settling", airborne=True)
        self._settle(2.0)
        self._go_height()
        return True

    def _takeoff_body(self) -> bool:
        self._begin_run()
        if not self._arm():
            return False
        self._publish(phase="hovering", note="hover", airborne=True)
        return True

    def _patrol_body(self) -> bool:
        outcome = False
        try:
            outcome = self._patrol_inner()
        except Exception as exc:
            self._say(f"recon failed: {exc}")
            self._publish(phase="failed", note=str(exc))
            outcome = False
        finally:
            if self.sdk is not None and self.airborne:
                self.sdk.send("rc 0 0 0 0")
            if self.airborne and not self._landed:
                # Time running out leaves it up. Land is the button, low battery, or no video.
                if self.abort.is_set() or not outcome:
                    self._land_once(precise=self.abort.is_set())
                else:
                    self._finish_motion()
                    if not self._keep_hover:
                        note = self.board.data.get("note") if self.board is not None else ""
                        self._publish(phase="hovering", note=note or "patrol done; hovering")
        return outcome

    def _patrol_inner(self) -> bool:
        from patrol.drone.explore import Explorer
        from patrol.drone.navigator import Limits

        self._keep_hover = False
        if not self._ensure_model():
            return False
        if self.abort.is_set() or (self.hold.is_set() and not self.airborne):
            return False
        brain = self.settings["brain"]
        client = None
        if brain != "reflex-only":
            client = self._jev_client()
            if client is None:
                return False
        if not self._ready_to_arm():
            return False
        self._begin_run()
        if not self.airborne:
            if not self._arm():
                return False
        else:
            self._go_height()
        grabber = self._open_video()
        try:
            if not grabber.ready():
                self._say("no video; landing instead of flying blind")
                self._publish(phase="failed", note="no video")
                return False
            if self.settings["down_photo"] and self.board is not None:
                _got, front = self._grab_down(grabber, self.board.folder / "down.jpg")
                if not front:
                    grabber = self._restart_video(grabber)
            limits = Limits(
                cruise_mps=float(self.settings["cruise_mps"]),
                brake_m=float(self.settings["brake_m"]),
                slow_m=float(self.settings["brake_m"]) + 1.0,
                geofence_m=float(self.settings["geofence_m"]),
            )
            seconds = int(self.settings["explore_s"])
            self._say(f"explore {seconds}s, brain {brain}, cruise {limits.cruise_mps} m/s, brake {limits.brake_m} m")
            explorer = Explorer(self, grabber, self._reflex, client, limits, brain, seconds)
            outcome = explorer.run()
            self._say(f"explore ended: {outcome}")
            if outcome == "person":
                self._keep_hover = True
                return True
            if outcome == "stuck":
                self._publish(note="no safe heading after 3 scans")
                return True
            elif outcome == "battery":
                self._publish(note="battery low")
            elif outcome == "video":
                self._publish(note="video lost; landed instead of flying blind")
            return outcome in ("done", "stopped")
        finally:
            if client is not None:
                client.close()
            self._stop_stream()

    def _request_height(self) -> None:
        with self._lock:
            if self._busy or not self.airborne:
                return
            self._busy = True
            self._queue.put("height")

    def _go_height(self) -> None:
        if self.sdk is None or not self.airborne or self._stop_requested():
            return
        target = int(self.settings["height_cm"])
        if self._height_applied == target:
            return
        try:
            reply = self._query("height?", timeout=3)
        except Exception as exc:
            print(f"height unread: {exc}")
            return
        current = parse_height_cm(reply)
        self._publish(height_cm_now=current)
        for command in height_commands(current, target):
            if self._stop_requested():
                return
            print(command)
            reply = self._query(command, timeout=12)
            if reply != "ok":
                return
        self._height_applied = target

    def _settle(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self._stop_requested():
                return
            try:
                reply = self._query("height?", timeout=3)
                print(f"settling, height {reply}")
                self._publish(height_cm_now=parse_height_cm(reply))
            except Exception as exc:
                print(f"settling unread: {exc}")
            time.sleep(min(0.4, max(0.0, end - time.monotonic())))

    def _wait_for_video(self, grabber) -> None:
        if grabber.ready():
            return
        try:
            self._query("command", timeout=2)
        except Exception as exc:
            self._say(f"video not ready: {exc}")
            return
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self._stop_requested() or grabber.ready():
                return
            time.sleep(0.1)

    def _camera_height_cm(self) -> int | None:
        """Height above the floor right now: tof, else takeoff-relative h, else the last height? reply."""
        snap = self.sdk.snapshot() if self.sdk is not None else {}
        tof = snap.get("tof")
        if tof is not None and 15 <= tof <= 400:
            return int(tof)
        h = snap.get("h")
        if h is not None and 15 <= h <= 400:
            return int(h)
        last = self.status.get("height_cm_now")
        if last:
            return int(last)
        return None

    def _open_video(self):
        reply = self._query("streamon")
        if reply != "ok":
            self._query("streamon")
        time.sleep(0.8)
        grabber = self._grabber_factory()
        grabber.log = self._say
        grabber.start()
        self._grabber = grabber
        self._wait_for_video(grabber)
        return grabber

    def _restart_video(self, grabber):
        grabber.close()
        self._grabber = None
        try:
            self._query("downvision 0", timeout=3)
        except Exception as exc:
            self._say(f"  downvision 0 still failing: {exc}")
        try:
            self._query("streamoff", timeout=3)
        except Exception as exc:
            self._say(f"  streamoff failed: {exc}")
        time.sleep(0.5)
        return self._open_video()

    def _grab_down(self, grabber: FrameGrabber, dest: Path) -> tuple[bool, bool]:
        """Floor photo, then back to the front camera. Returns (photo taken, front camera back)."""
        try:
            print("  downvision", self._query("downvision 1", timeout=3))
        except Exception as exc:
            print(f"  down camera skipped: {exc}")
            return False, True
        ok = grabber.capture(dest, time.monotonic() + 0.3, timeout=2.0)
        front = False
        for _attempt in range(3):
            try:
                if self._query("downvision 0", timeout=3) == "ok":
                    front = True
                    break
            except Exception as exc:
                print(f"  downvision reset failed: {exc}")
            time.sleep(0.5)
        if ok:
            print(f"  down {dest.name}")
        return ok, front

    def _finish_motion(self) -> None:
        if self.sdk is None:
            return
        try:
            self._query("stop", timeout=5)
        except Exception as exc:
            print(f"stop failed: {exc}")

    def _stop_stream(self) -> None:
        if self._grabber is not None:
            self._grabber.close()
            self._grabber = None
        if self.sdk is None:
            return
        try:
            self.sdk.query("streamoff", timeout=2)
        except Exception:
            pass

    def follow_person(self, grabber, spot, already_down: bool = False) -> None:
        """Fly to a person seen ahead, then hold station over them with the downward camera.

        `spot(image)` returns a box (fractions of the frame) or None. A person already
        in the downward picture skips the approach. This does not land.
        """
        overhead = already_down
        lost_since = None
        note = "staying above the person" if already_down else "going to the person"
        self._say(note)
        self._publish(phase="person", note=note)
        lander = MarkerLander(self.sdk, grabber, say=self._say)
        lander.forward = (1.0, 0.0)
        lander.right = (0.0, 1.0)
        try:
            while self.airborne and not self._landed and not self.abort.is_set() and self.settings.get("stop_on_person", True):
                image = None
                if grabber is not None:
                    image, _at = grabber.latest()
                box = spot(image) if image is not None else None
                now = time.monotonic()
                if box is None:
                    self.sdk.send("rc 0 0 0 0")
                    self._kept_at = now
                    lost_since = lost_since or now
                    if now - lost_since >= 1.0:
                        self._say("person left the picture; hovering")
                        self._publish(phase="person", note="person left the picture; hovering")
                        return
                    time.sleep(0.2)
                    continue
                lost_since = None
                cx = float(box.center_x)
                cy = (float(box.top) + float(box.bottom)) / 2
                wide = max(0.0, float(box.right) - float(box.left))
                tall = max(0.0, float(box.bottom) - float(box.top))
                if not overhead:
                    close = wide * tall >= 0.12 or (cy >= 0.62 and wide * tall >= 0.05)
                    if close:
                        self.sdk.send("rc 0 0 0 0")
                        self._climb_over()
                        grabber = self._switch_down(grabber)
                        lander.grabber = grabber
                        overhead = True
                        self._say("above the person")
                        self._publish(phase="person", note="above the person")
                        continue
                    yaw = 0 if abs(cx - 0.5) < 0.08 else int(math.copysign(25, cx - 0.5))
                    forward = 18 if abs(cx - 0.5) < 0.18 else 8
                    self.sdk.send(f"rc 0 {forward} 0 {yaw}")
                    self._kept_at = time.monotonic()
                else:
                    lr, fb = lander.steer((cx - 0.5) * 40.0, (cy - 0.5) * 40.0, rest_cm=4.0)
                    self.sdk.send(f"rc {lr} {fb} 0 0")
                    self._kept_at = time.monotonic()
                    line = f"above the person, rc {lr} {fb}"
                    self._publish(phase="person", note=line)
                time.sleep(0.2)
            if self.sdk is not None:
                self.sdk.send("rc 0 0 0 0")
        finally:
            if overhead and self.sdk is not None and self.airborne and not self._landed:
                try:
                    self._query("downvision 0", timeout=3)
                except Exception as exc:
                    self._say(f"downvision 0 failed: {exc}")

    def _climb_over(self) -> None:
        self._say("climbing over the person")
        try:
            self._query("up 80", timeout=12)
        except Exception as exc:
            self._say(f"climb failed: {exc}")

    def _switch_down(self, grabber):
        """Point the stream at the floor and return the grabber that reads it."""
        try:
            self._query("moff", timeout=3)
        except Exception as exc:
            self._say(f"moff failed: {exc}")
        try:
            self._query("streamoff", timeout=3)
        except Exception as exc:
            self._say(f"streamoff failed: {exc}")
        if grabber is not None:
            grabber.close()
            if self._grabber is grabber:
                self._grabber = None
        time.sleep(0.4)
        reply = self._query("downvision 1", timeout=3)
        if reply != "ok":
            self._say(f"down camera refused: {reply}")
            return grabber
        opened = self._open_video()
        deadline = time.monotonic() + 8
        while not opened.ready() and time.monotonic() < deadline and not self.abort.is_set():
            self.sdk.send("rc 0 0 0 0")
            time.sleep(0.2)
        return opened

    def _watch_pad(self) -> None:
        """Center on the marker, descend the cone, then drop into the funnel and land.

        Descent starts inside 25 cm, with the sideways sticks still correcting.
        They rest only inside 6 cm. From 40 cm down, anything inside 15 cm is in
        the 35 cm mouth, so it sinks hard. Turning the checkbox off leaves it hovering.
        """
        self._begin_run()
        self._say("looking down; a photo every second")
        self._publish(phase="hovering", note="looking down")
        grabber = None
        try:
            try:
                self._query("moff", timeout=3)
            except Exception as exc:
                self._say(f"moff failed: {exc}")
            self._pad_detect_on = False
            try:
                self._query("streamoff", timeout=3)
            except Exception as exc:
                self._say(f"streamoff failed: {exc}")
            time.sleep(0.4)
            reply = self._query("downvision 1", timeout=3)
            if reply != "ok":
                self._say(f"down camera refused: {reply}")
                return
            grabber = self._open_video()
            deadline = time.monotonic() + 8
            while not grabber.ready() and time.monotonic() < deadline and not self.abort.is_set():
                self.sdk.send("rc 0 0 0 0")
                time.sleep(0.2)
            if not grabber.ready():
                self._say(f"down camera sent no video ({grabber._error or 'no frame'})")
                return
            count = 0
            last_photo = 0.0
            spoken = None
            held = 0.0
            commit = False
            lander = MarkerLander(self.sdk, grabber, say=self._say)
            lander.calibrate()
            while self.airborne and not self._landed and self.settings["pad"] and not self.abort.is_set():
                image, _at = grabber.frame_after(time.monotonic() - 0.2, timeout=1.0)
                if image is None:
                    self.sdk.send("rc 0 0 0 0")
                    held = 0.0
                    line = "down camera sent no frame"
                else:
                    picture = downward_view(image)
                    now = time.monotonic()
                    height = self._camera_height_cm()
                    if now - last_photo >= PAD_PHOTO_S:
                        name = f"pad-{count:03d}.jpg"
                        picture.save(self.board.folder / name)
                        count += 1
                        last_photo = now
                        self.board.add_frame(
                            {"step": 0, "heading": count, "file": name, "height_cm": height, "why": "down"}
                        )
                    offset = marker_offset_cm(picture)
                    if offset is None:
                        lr, fb, ud = 0, 0, 0
                        held = 0.0
                        line = "marker not in the picture"
                    else:
                        if math.hypot(*offset) <= LAND_CM:
                            held += 0.2
                        else:
                            held = 0.0
                        lr, fb = lander.steer(*offset)
                        ud, level, commit = landing_move(*offset, height, held)
                        if level:
                            lr, fb = 0, 0
                        line = f"marker {offset[0]:+.0f}, {offset[1]:+.0f} cm, rc {lr} {fb} {ud}"
                    self.sdk.send(f"rc {lr} {fb} {ud} 0")
                    self._kept_at = time.monotonic()
                    self._publish(phase="hovering", note=line)
                if line != spoken:
                    self._say(line)
                    spoken = line
                if commit:
                    self._say("marker centered and low; landing")
                    break
                time.sleep(0.2)
            if commit and self.airborne and not self._landed and not self.abort.is_set():
                self._land_once()
        except Exception as exc:
            self._say(f"down photos failed: {exc}")
        finally:
            if self.sdk is not None:
                self.sdk.send("rc 0 0 0 0")
            if grabber is not None:
                self._stop_stream()
            if self.sdk is not None and self.airborne and not self._landed:
                try:
                    self._query("downvision 0", timeout=3)
                except Exception as exc:
                    self._say(f"downvision 0 failed: {exc}")
            self._pad_watching = False
            if self.abort.is_set() and self.airborne and not self._landed:
                self._land_once()
            elif self.airborne and not self._landed:
                self._publish(phase="hovering", note="pad camera off")

    def _land_once(self, precise: bool = True) -> None:
        if self._landed:
            return
        prior = None
        prior_note = ""
        if self.board is not None and self.board.data.get("phase") in ("failed", "refused"):
            prior = self.board.data["phase"]
            prior_note = self.board.data.get("note") or ""
        self._stop_stream()
        if self.sdk is None:
            self._landed = True
            self.airborne = False
            self._blocked = False
            self._run_open = False
            self._publish(phase="landed", airborne=False)
            return
        del precise
        note = ""
        self._publish(phase="landing")
        try:
            try:
                reply = self._query("land", timeout=15)
            except Exception as exc:
                self._say(f"land failed: {exc}; retrying")
                reply = self._query("land", timeout=15)
            height = self._query("height?", timeout=3)
            self._say(f"land {reply}, height {height}")
            now = parse_height_cm(height)
            self._publish(height_cm_now=now)
            if now == 0:
                self._blocked = False
        except Exception as exc:
            self._say(f"land failed: {exc}")
            self._say("flight state unknown; do not take off again")
            self._blocked = True
            self._landed = False
            self.airborne = True
            self._run_open = False
            self._publish(
                phase="failed",
                note="flight state unknown; do not take off again",
                airborne=True,
            )
            return
        self._landed = True
        self.airborne = False
        self._pad_detect_on = False
        self._height_applied = None
        self._run_open = False
        self._publish(phase=prior or "landed", note=prior_note or note)

    def _request_pad(self) -> None:
        """Queue the downward camera once. The checkbox and the hover loop both call this."""
        with self._lock:
            if self.abort.is_set() or self._busy or self._pad_watching:
                return
            if not self.airborne or self._landed or not self.settings["pad"]:
                return
            self._busy = True
            self._pad_watching = True
            self._queue.put("pad")

    def _air_loop(self) -> None:
        """Hold a hover, and photograph downward while the pad switch is on.

        The Tello lands itself after about 15 s with no command, so a hover
        sends `rc 0 0 0 0` well inside that. `rc` has no reply, so this does
        not race the worker's queries. One dropped packet must not kill the
        loop: after that the checkbox does nothing and the drone lands itself.
        """
        while True:
            time.sleep(0.25)
            try:
                if self.sdk is None or not self.airborne or self._landed:
                    continue
                with self._lock:
                    busy = self._busy
                if not busy:
                    now = time.monotonic()
                    if now - self._kept_at >= 5:
                        self.sdk.send("rc 0 0 0 0")
                        self._kept_at = now
                    self._request_pad()
            except Exception as exc:
                self._say(f"hover keep failed: {exc}")
                time.sleep(1.0)
