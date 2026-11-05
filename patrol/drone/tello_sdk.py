"""Small Tello SDK client.

The drone replies to the UDP port that sent the command. This client binds
local port 9000. djitellopy binds 8889, and the Tello then ignores it.
Telemetry arrives on UDP 8890: height, floor distance (tof), battery, yaw,
and the mission pad id.
"""

from __future__ import annotations

import socket
import threading
import time

TELLO_IP = "192.168.10.1"
TELLO_PORT = 8889
LOCAL_PORT = 9000
STATE_PORT = 8890
STATE_KEYS = ("h", "tof", "bat", "mid", "x", "y", "z", "yaw")


def parse_state(packet: str) -> dict:
    """Pull height, battery and mission-pad fields out of one telemetry line."""
    found = {}
    for part in packet.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        if key not in STATE_KEYS:
            continue
        try:
            found[key] = int(float(value.strip()))
        except ValueError:
            continue
    return found


class TelloSDK:
    def __init__(self, listen_state: bool = True) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", LOCAL_PORT))
        self._state: dict = {}
        self._state_lock = threading.Lock()
        self._state_stop = threading.Event()
        self._state_sock: socket.socket | None = None
        self._state_thread: threading.Thread | None = None
        if listen_state:
            self._listen_state()

    def _listen_state(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("", STATE_PORT))
        except OSError as exc:
            print(f"state port {STATE_PORT} unavailable: {exc}")
            sock.close()
            return
        sock.settimeout(1.0)
        self._state_sock = sock
        self._state_thread = threading.Thread(target=self._read_state, daemon=True)
        self._state_thread.start()

    def _read_state(self) -> None:
        assert self._state_sock is not None
        while not self._state_stop.is_set():
            try:
                data, _addr = self._state_sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            parsed = parse_state(data.decode(errors="replace"))
            if not parsed:
                continue
            parsed["at"] = time.monotonic()
            with self._state_lock:
                self._state.update(parsed)

    def snapshot(self) -> dict:
        with self._state_lock:
            return dict(self._state)

    def send(self, command: str) -> None:
        """Send a command that does not reply. `rc` is one of these."""
        self.sock.sendto(command.encode(), (TELLO_IP, TELLO_PORT))

    def _discard_stale(self) -> None:
        """Drop replies left over from the previous command.

        `stop` can leave a second datagram (`forced stop`). The next
        `recv` would treat that as the answer to a new command, and every
        reply after that belongs to the command before it.
        """
        self.sock.setblocking(False)
        try:
            while True:
                self.sock.recvfrom(2048)
        except (BlockingIOError, InterruptedError):
            return
        finally:
            self.sock.setblocking(True)

    def query(self, command: str, timeout: float = 5) -> str:
        self._discard_stale()
        self.sock.settimeout(timeout)
        self.sock.sendto(command.encode(), (TELLO_IP, TELLO_PORT))
        data, _addr = self.sock.recvfrom(2048)
        return data.decode(errors="replace").strip()

    def close(self) -> None:
        self._state_stop.set()
        if self._state_sock is not None:
            self._state_sock.close()
        if self._state_thread is not None:
            self._state_thread.join(timeout=1.5)
        self.sock.close()
