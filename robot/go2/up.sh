#!/bin/bash
# Connect only after the RViz button writes connect.request. Then calibrate, then start the stack.
set -u
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
pi=rpihack@100.110.8.74
stamp=/tmp/go2-mode
lock=/tmp/go2-up.dir
flag="$here/connect.request"

if [ ! -f "$flag" ]; then
  exit 0
fi
if ! mkdir "$lock" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$lock"' EXIT
rm -f "$flag"
log() { echo "$(date +%H:%M:%S) $*"; }
status() { printf '%s\n' "$*" > "$here/connect.status"; }

ssh_pi() {
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$pi" "$@"
}
in_vm() { limactl shell go2 -- bash -lc "$1"; }
seek_up() { in_vm 'ps -eo args= | grep -q "[p]ython3 /Users/ares-pc/localrepo/grok-hackathon-pavia/robot/go2/seek.py"'; }
start_seek() {
  seek_up && return 0
  in_vm "setsid --fork bash -c 'source $repo/robot/go2/guest-env.sh && exec python3 $repo/robot/go2/seek.py' >/tmp/go2-seek.log 2>&1"
}
admin() {
  osascript -e "do shell script \"$1\" with administrator privileges"
}

state=$(limactl list go2 --format '{{.Status}}' 2>/dev/null || true)
if [ "$state" != "Running" ]; then
  limactl start go2
fi

mode=wait
status "connessione..."
for _ in 1 2 3 4 5 6 7 8; do
  pi_ok=0
  ping -c 1 -W 2 100.110.8.74 >/dev/null 2>&1 && pi_ok=1
  if ifconfig en8 2>/dev/null | grep -q 'status: active' && ping -c 1 -W 1 192.168.123.161 >/dev/null 2>&1; then
    mode=usb
    break
  elif [ "$pi_ok" = 1 ] && ssh_pi 'ping -c 1 -W 1 192.168.123.161 >/dev/null'; then
    mode=bridge
    break
  fi
  if [ "$pi_ok" = 1 ]; then
    status "connessione rpi ok, connessione dog not ok"
  else
    status "connessione rpi not ok"
  fi
  log "cerco il cane"
  sleep 3
done
if [ "$mode" = wait ]; then
  log "cane non trovato"
  exit 0
fi
if [ "$mode" = usb ]; then
  status "connessione dog ok"
else
  status "connessione rpi ok, connessione dog ok"
fi
ssh_pi 'cat /run/go2-rssi 2>/dev/null || true' > "$here/rssi.dbm" || true

if [ "$mode" = usb ]; then
  in_vm "sudo bash $repo/robot/go2/guest-addr.sh"
  in_vm 'sudo rm -f /run/go2-peer /run/go2-addr'
  if ! ifconfig en8 | grep -q 'inet 192.168.123.101'; then
    admin "ifconfig en8 alias 192.168.123.101 netmask 255.255.255.0" || true
  fi
else
  if netstat -rn -f inet | awk '$1=="192.168.123" && $4=="en8"{found=1} END{exit !found}'; then
    admin "ifconfig en8 -alias 192.168.123.101" || { log "could not free 192.168.123 from en8"; exit 0; }
  fi
  tailscale set --accept-routes=true 2>/dev/null || admin "tailscale set --accept-routes=true" || true
  if ! ping -c 1 -W 3 192.168.123.161 >/dev/null 2>&1; then
    status "connessione rpi ok, connessione dog not ok"
    log "dog not reachable from the mac through the pi"
    exit 0
  fi
  admin "sysctl -w net.inet.ip.forwarding=1; route -n delete -host 192.168.123.101 2>/dev/null; route -n add -host 192.168.123.101 192.168.64.2" || { log "mac route failed"; exit 0; }
  in_vm 'sudo wg-quick up wg0 2>/dev/null || true; sudo sysctl -w net.ipv4.conf.all.rp_filter=0; sudo sysctl -w net.ipv4.conf.wg0.rp_filter=0; sudo ip route replace 192.168.123.161/32 dev wg0; sudo ip route replace 192.168.123.102/32 dev wg0; sudo ip route replace 192.168.123.100/32 dev wg0; sudo ip route replace 239.255.0.1/32 dev wg0; sudo ip addr del 192.168.123.101/32 dev lima0 2>/dev/null || true; echo wg0 | sudo tee /run/go2-iface >/dev/null; echo 192.168.123.101 | sudo tee /run/go2-addr >/dev/null; echo 192.168.123.161 | sudo tee /run/go2-peer >/dev/null'
  if ! in_vm 'ping -I 192.168.123.101 -c 1 -W 2 192.168.123.161 >/dev/null'; then
    status "connessione rpi ok, connessione dog not ok"
    log "vm cannot reach the dog"
    exit 0
  fi
fi

in_vm 'ps -eo pid,args | awk "/system_real_robot_with_route_planner.launch/ && !/awk/ {print \$1}" | while read -r p; do kill "$p" || true; done; ps -eo pid,args | awk "/python3/ && /seek.py/ && !/awk/ {print \$1}" | while read -r p; do kill "$p" || true; done' || true
if [ "$mode" = bridge ]; then
  in_vm "ps -eo args | awk '/go2-dds-inject.py/ && !/awk/' | grep -q . || setsid --fork python3 $repo/robot/go2/go2-dds-inject.py >/tmp/go2-dds-inject.log 2>&1"
  in_vm "source $repo/robot/go2/guest-env.sh && timeout 5 ros2 topic pub --once /utlidar/switch std_msgs/msg/String '{data: ON}'" || true
fi
sleep 2
if in_vm "source $repo/robot/go2/guest-env.sh && timeout 8 ros2 topic echo /utlidar/imu --once >/dev/null"; then
  status "calibrazione"
  log "calibrazione"
  in_vm "source $repo/robot/go2/guest-env.sh && timeout 50 ros2 run calibrate_imu calibrate_imu" || log "calibrazione interrotta"
else
  status "connessione rpi ok, connessione dog ok, nuvola non parte"
  log "niente imu, stack non avviato"
  exit 0
fi
in_vm "setsid --fork bash -c 'source $repo/robot/go2/guest-env.sh && exec ros2 launch vehicle_simulator system_real_robot_with_route_planner.launch' >/tmp/go2-stack.log 2>&1"
in_vm 'pgrep -x Xtigervnc >/dev/null || vncserver :1 -geometry 1440x900 -localhost yes -SecurityTypes None -xstartup "$HOME/.vnc/xstartup"'
in_vm 'ps -eo args= | grep -q "[w]ebsockify" || setsid --fork websockify --web=/usr/share/novnc 127.0.0.1:6080 127.0.0.1:5901 >/tmp/novnc.log 2>&1'
sleep 4
start_seek
echo "$mode" > "$stamp"
status "pronto"
log "started $mode"
