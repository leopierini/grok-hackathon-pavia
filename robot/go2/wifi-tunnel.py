#!/usr/bin/env python3
"""Carry the VM WireGuard socket to the Pi over the facility WiFi.

The VM's eth0 is Lima's 192.168.5.0/24, so the Pi's address never leaves the VM.
Replies must come back to the Mac's WiFi address.
shortcut: one Pi, one port. Both addresses are DHCP: pass them in.
"""
import socket
import sys
import threading

if len(sys.argv) != 3:
    sys.exit("usage: wifi-tunnel.py <mac-wifi-ip> <pi-wifi-ip>")

VM_SIDE = ("192.168.64.1", 51820)
WIFI = (sys.argv[1], 51820)
PI = (sys.argv[2], 51820)

vm_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
vm_sock.bind(VM_SIDE)
wifi_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
wifi_sock.bind(WIFI)
vm_addr = None


def from_vm():
    global vm_addr
    while True:
        data, addr = vm_sock.recvfrom(2048)
        vm_addr = addr
        wifi_sock.sendto(data, PI)


def from_pi():
    while True:
        data, addr = wifi_sock.recvfrom(2048)
        if vm_addr is not None:
            vm_sock.sendto(data, vm_addr)


threading.Thread(target=from_vm, daemon=True).start()
from_pi()
