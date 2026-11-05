"""How the laptop reaches the dog and the drone with one Wi-Fi radio.

A Wi-Fi radio holds one association. The ground laptop has one radio. The dog
is on its own Ethernet subnet and must not be switched onto Wi-Fi. The Tello
is an access point of its own and will not join another network. Those three
facts are the whole routing plan.

Today the laptop's Ethernet adapter is the dog's only WebRTC client. The
laptop Wi-Fi is not used for either robot, so it can stay on the internet.
The drone is a script.

When the Pi 4 is mounted, the laptop Wi-Fi joins one network, called the
ground AP here (a phone hotspot or a small router). The Pi's built-in radio
joins that same network. The dog cable moves to the Pi. A USB 2.4 GHz radio
on the Pi, and only that radio, joins the Tello. Ground opens one TCP session
to the Pi and sends dog messages and drone messages on that session. It never
opens a second Wi-Fi association.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

DOG_IP = "192.168.123.161"
DOG_PORT = 8081
DOG_SUBNET_HOST = "192.168.123.222"
DOG_PREFIX = "192.168.123."
PI_RELAY_PORT = 8766
GROUND_AP = "ground-ap"
TELLO_AP = "tello-ap"

DogHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class LinkError(RuntimeError):
    pass


def ethernet_now() -> dict[str, Any]:
    """Dog on the laptop Ethernet cable. Drone stays a script. Wi-Fi is idle."""
    plan: dict[str, Any] = {
        "profile": "ethernet-now",
        "laptop_wifi": [],
        "dog": {
            "radio": "laptop-ethernet",
            "address": DOG_IP,
            "port": DOG_PORT,
            "laptop_address": DOG_SUBNET_HOST,
            "prefix": 24,
            "protocol": "unitree-webrtc-localsta",
        },
        "drone": {"radio": "simulated-script", "live": False},
        "pi": None,
    }
    check(plan)
    return plan


def pi4(*, dongle_up: bool = False) -> dict[str, Any]:
    """Pi 4 carries both robots. The laptop Wi-Fi joins only the ground AP."""
    plan: dict[str, Any] = {
        "profile": "pi4",
        "board": "raspberry-pi-4",
        "laptop_wifi": [{"radio": "laptop-wifi", "network": GROUND_AP}],
        "dog": {
            "radio": "pi-ethernet",
            "address": DOG_IP,
            "port": DOG_PORT,
            "pi_address": DOG_SUBNET_HOST,
            "prefix": 24,
            "protocol": "unitree-webrtc-localsta",
            "ground_hop": "tcp on the ground AP to the Pi, then Ethernet",
        },
        "drone": {
            "radio": "pi-wlan1" if dongle_up else "simulated-script",
            "network": TELLO_AP,
            "live": False,
            "reason": (
                "Pi USB radio is associated; drone bytes still stay scripted until a live "
                "aircraft bridge is accepted"
                if dongle_up
                else "the Pi's second radio is absent, so the drone stays the script"
            ),
        },
        "pi": {
            "board": "raspberry-pi-4",
            "wlan0": GROUND_AP,
            "wlan1": TELLO_AP,
            "eth0": DOG_SUBNET_HOST,
            "relay_port": PI_RELAY_PORT,
            "dongle_up": dongle_up,
        },
    }
    check(plan)
    return plan


def check(plan: dict[str, Any]) -> None:
    """Reject any plan that would associate the laptop Wi-Fi twice."""
    wifi = plan["laptop_wifi"]
    if not isinstance(wifi, list):
        raise LinkError("laptop_wifi must be a list of associations")
    if len(wifi) > 1:
        raise LinkError("the laptop has one Wi-Fi radio and cannot join two networks")
    networks = {row.get("network") for row in wifi}
    if TELLO_AP in networks:
        raise LinkError(
            "the laptop Wi-Fi must not join the Tello; the Pi's USB radio is the only Tello client"
        )
    dog_radio = plan["dog"]["radio"]
    if plan["profile"] == "ethernet-now":
        if wifi:
            raise LinkError("ethernet-now does not put either robot on the laptop Wi-Fi")
        if dog_radio != "laptop-ethernet":
            raise LinkError("ethernet-now reaches the dog on the laptop Ethernet adapter")
    elif plan["profile"] == "pi4":
        if networks != {GROUND_AP}:
            raise LinkError("the laptop Wi-Fi joins only the ground AP")
        if dog_radio != "pi-ethernet":
            raise LinkError("with the Pi mounted the dog cable is on the Pi, not the laptop")
        if plan["drone"]["radio"] not in {"pi-wlan1", "simulated-script"}:
            raise LinkError("the drone is reached from the Pi's second radio, or it stays a script")
    else:
        raise LinkError(f"unknown link profile {plan['profile']!r}")


def dongle_associated(iface: str = "wlan1") -> bool:
    """True only when a second radio exists and its operstate is up.

    The laptop does not have this interface. On the Pi it is the USB dongle.
    """
    state = Path(f"/sys/class/net/{iface}/operstate")
    if not state.is_file():
        return False
    return state.read_text(encoding="utf-8").strip() == "up"


def probe_dog_ethernet(timeout: float = 2.0) -> dict[str, Any]:
    """See whether port 8081 on the dog answers from this machine.

    A TCP connect is the same check as `nc` in the dog notes. It does not send
    a WebRTC offer and it does not send motion.
    """
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((DOG_IP, DOG_PORT))
        local = sock.getsockname()[0]
    except OSError as exc:
        return {
            "reachable": False,
            "dog": DOG_IP,
            "port": DOG_PORT,
            "detail": f"{type(exc).__name__}: {exc}",
        }
    finally:
        sock.close()
    on_subnet = local.startswith(DOG_PREFIX) and local != DOG_IP
    return {
        "reachable": True,
        "dog": DOG_IP,
        "port": DOG_PORT,
        "local_address": local,
        "laptop_on_dog_subnet": on_subnet,
        "expected_laptop_address": DOG_SUBNET_HOST,
    }


class Relay:
    """One TCP session from Ground. Dog bytes go to Ethernet. Drone bytes stay a script.

    This is the process that will run on the Pi 4. Binding it on the ground-AP
    address is the only way the laptop talks to either robot. A second laptop
    association is not opened here.
    """

    def __init__(self, dog_handler: DogHandler | None = None, *, dongle_up: bool = False) -> None:
        self.dog_handler = dog_handler
        self.dongle_up = dongle_up
        self.clients = 0
        self.dog_messages: list[dict[str, Any]] = []
        self.drone_messages: list[dict[str, Any]] = []
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self._server = await asyncio.start_server(self._handle, host, port)
        sockets: list[Any] = list(self._server.sockets or [])
        self.port = sockets[0].getsockname()[1]

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients += 1
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    reply = {"ok": False, "detail": "command must be one JSON object per line"}
                else:
                    reply = await self.dispatch(msg if isinstance(msg, dict) else {})
                writer.write(json.dumps(reply).encode() + b"\n")
                await writer.drain()
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def dispatch(self, msg: dict[str, Any]) -> dict[str, Any]:
        channel = msg.get("channel")
        body = msg.get("body")
        if channel == "dog":
            if not isinstance(body, dict):
                return {"ok": False, "channel": "dog", "detail": "dog body must be an object"}
            self.dog_messages.append(body)
            reply: dict[str, Any] = {
                "ok": True,
                "channel": "dog",
                "path": ["ground-ap", "pi-wlan0", "pi-ethernet", DOG_IP],
                "live_radio": "ethernet",
            }
            if self.dog_handler is not None:
                reply.update(await self.dog_handler(body))
            return reply
        if channel == "drone":
            if not isinstance(body, dict):
                return {"ok": False, "channel": "drone", "detail": "drone body must be an object"}
            self.drone_messages.append(body)
            radio = "pi-wlan1" if self.dongle_up else "simulated-script"
            return {
                "ok": True,
                "channel": "drone",
                "path": ["ground-ap", "pi-wlan0", radio],
                "live": False,
                "simulated": True,
                "reason": pi4(dongle_up=self.dongle_up)["drone"]["reason"],
            }
        return {"ok": False, "detail": "channel must be dog or drone"}


async def exchange(
    port: int,
    messages: list[dict[str, Any]],
    host: str = "127.0.0.1",
) -> list[dict[str, Any]]:
    """Send every message on one connection and collect one reply each."""
    reader, writer = await asyncio.open_connection(host, port)
    replies = []
    try:
        for msg in messages:
            writer.write(json.dumps(msg).encode() + b"\n")
            await writer.drain()
            line = await reader.readline()
            replies.append(json.loads(line))
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
    return replies
