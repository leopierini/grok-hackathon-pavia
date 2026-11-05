#!/usr/bin/env python3
"""WireGuard drops multicast, so hand the VM's own DDS multicast to the Pi as unicast."""
import socket
import struct
import threading

GROUP = "239.255.0.1"
LOCAL = "192.168.123.101"
PI = "192.168.123.102"
PORTS = (7400, 7401)


def relay(port):
    src = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    src.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    src.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    src.bind(("", port))
    src.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        struct.pack("4s4s", socket.inet_aton(GROUP), socket.inet_aton(LOCAL)),
    )
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    n = 0
    while True:
        data, addr = src.recvfrom(65535)
        if addr[0] != LOCAL:
            continue
        out.sendto(data, (PI, port))
        n += 1
        if n == 1 or n % 200 == 0:
            print(f"to-pi {port} {n}", flush=True)


for port in PORTS:
    threading.Thread(target=relay, args=(port,), daemon=True).start()
threading.Event().wait()
