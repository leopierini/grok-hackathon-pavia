#!/usr/bin/env python3
"""Bridge the Go2 DDS multicast both ways. Cable .161 <-> tunnel .101. No loop."""
import socket
import struct
import threading

GROUP = "239.255.0.1"
CABLE = "192.168.123.100"
TUNNEL = "192.168.123.102"
VM = "192.168.123.101"
DOG = "192.168.123.161"
PORTS = (7400, 7401)


def sender(iface):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)
    return sock


def relay(port):
    src = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    src.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    src.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    src.bind(("", port))
    for iface in (CABLE, TUNNEL):
        src.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            struct.pack("4s4s", socket.inet_aton(GROUP), socket.inet_aton(iface)),
        )
    to_vm = sender(TUNNEL)
    to_dog = sender(CABLE)
    seen = 0
    while True:
        data, addr = src.recvfrom(65535)
        if addr[0] == DOG:
            # wg0 rejects multicast (ENOKEY). The VM socket is already on this port.
            to_vm.sendto(data, (VM, port))
        elif addr[0] == VM:
            to_dog.sendto(data, (GROUP, port))
        else:
            continue
        seen += 1
        if seen == 1 or seen % 200 == 0:
            print(f"{addr[0]} {port} {seen}", flush=True)


for port in PORTS:
    threading.Thread(target=relay, args=(port,), daemon=True).start()
threading.Event().wait()
