"""Small Tello SDK client.

The drone replies to the UDP port that sent the command. This client binds
local port 9000. djitellopy binds 8889, and the Tello then ignores it.
"""

import socket

TELLO_IP = "192.168.10.1"
TELLO_PORT = 8889
LOCAL_PORT = 9000


class TelloSDK:
    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", LOCAL_PORT))

    def query(self, command: str, timeout: float = 5) -> str:
        self.sock.settimeout(timeout)
        self.sock.sendto(command.encode(), (TELLO_IP, TELLO_PORT))
        data, _addr = self.sock.recvfrom(2048)
        return data.decode(errors="replace").strip()

    def close(self) -> None:
        self.sock.close()
