#!/bin/bash
# Pi side of the bridge. The SLAM stays on the Mac.
# shortcut: only the Tello whose SSID contains 62A593. Other Tellos in the room are ignored.
set -u
echo 1 > /proc/sys/net/ipv4/ip_forward
echo 0 > /proc/sys/net/ipv4/conf/all/rp_filter
if [ -e /proc/sys/net/ipv4/conf/wg0/rp_filter ]; then
  echo 0 > /proc/sys/net/ipv4/conf/wg0/rp_filter
  ip route replace 239.255.0.1/32 dev wg0 2>/dev/null || true
fi
tailscale set --advertise-routes=192.168.123.0/24 || true
if ! pgrep -f go2-dds-relay.py >/dev/null; then
  python3 /usr/local/sbin/go2-dds-relay.py >/var/log/go2-dds.log 2>&1 &
fi
while true; do
  if ip link show eth0 | grep -q LOWER_UP; then
    ip -4 addr show dev eth0 | grep -q '192\.168\.123\.100/' || ip addr add 192.168.123.100/24 dev eth0
    echo 1 > /proc/sys/net/ipv4/conf/eth0/proxy_arp
    echo 1 > /proc/sys/net/ipv4/conf/eth0/forwarding
    ip route del 192.168.123.101/32 via 100.111.41.98 dev tailscale0 2>/dev/null || true
    iptables -C FORWARD -i eth0 -o tailscale0 -j ACCEPT 2>/dev/null || iptables -A FORWARD -i eth0 -o tailscale0 -j ACCEPT
    iptables -C FORWARD -i tailscale0 -o eth0 -j ACCEPT 2>/dev/null || iptables -A FORWARD -i tailscale0 -o eth0 -j ACCEPT
  fi
  ip link set wlan0 up 2>/dev/null || true
  best=$(iw dev wlan0 scan 2>/dev/null | awk '
    /signal:/ {sig=$2}
    $1=="SSID:" && toupper($0) ~ /62A593/ {print sig}
  ' | sort -n | tail -1)
  if [ -n "${best:-}" ]; then
    echo "$best" > /run/go2-rssi
  fi
  sleep 5
done
