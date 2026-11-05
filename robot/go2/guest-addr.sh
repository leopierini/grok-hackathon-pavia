#!/bin/bash
# Give the bridged NIC the address the Go2 expects. Does not touch the NAT NIC.
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo "run with sudo" >&2
  exit 1
fi
found=$(ip -4 -o addr show | awk '/192.168.123.100\//{print $2; exit}')
if [ -z "$found" ]; then
  for path in /sys/class/net/*; do
    iface=$(basename "$path")
    [ "$iface" = lo ] && continue
    ip -4 addr show dev "$iface" | grep -q 'inet ' && continue
    ip addr add 192.168.123.100/24 dev "$iface"
    found=$iface
    break
  done
fi
if [ -z "$found" ]; then
  echo "no NIC without an IPv4 address" >&2
  exit 1
fi
echo "$found" > /run/go2-iface
echo "$found"
