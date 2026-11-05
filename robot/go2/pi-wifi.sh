#!/bin/bash
# The USB stick (TL-WN823N) is 2.4 GHz only and transmits at a crawl.
# The Pi's own radio joins hackathon on 5 GHz. The stick only scans the Tello.
# LTE stays the default route. shortcut: one SSID, password is the venue's.
set -u
printf '%s\n' '[keyfile]' 'unmanaged-devices=interface-name:wlan1' > /etc/NetworkManager/conf.d/unmanage-wlan1.conf
rm -f /etc/NetworkManager/conf.d/unmanage-wlan0.conf
nmcli general reload
sleep 1
nmcli dev set wlan1 managed no
nmcli dev set wlan0 managed yes
nmcli -t -f NAME con show | grep -qx facility && nmcli con delete facility
nmcli con add type wifi ifname wlan0 con-name facility ssid hackathon \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk hackathon \
  connection.autoconnect yes connection.interface-name wlan0 \
  802-11-wireless.band a \
  802-11-wireless.powersave 2 \
  ipv4.never-default yes ipv4.route-metric 200 ipv6.method ignore
nmcli con modify "Wired connection 2" ipv4.never-default no ipv4.route-metric 100
if ! nmcli --wait 25 con up facility; then
  nmcli con delete facility || true
  nmcli dev set wlan1 managed yes
  nmcli con add type wifi ifname wlan1 con-name facility ssid hackathon \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk hackathon \
    connection.autoconnect yes connection.interface-name wlan1 \
    802-11-wireless.powersave 2 \
    ipv4.never-default yes ipv6.method ignore
  nmcli --wait 25 con up facility || true
  echo '5 GHz join failed, stick restored' >&2
  exit 1
fi
ip link set wlan1 up
echo JOINED
iw dev wlan0 link
ip -4 -br addr show wlan0
ip route | awk '/^default/'
