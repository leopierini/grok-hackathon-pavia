# Dog station setup

You are setting up the dog ground station on a Mac, from this repo. This Mac runs the Go2 SLAM stack and talks to the Raspberry Pi on the dog. It does not fly the drone and it does not join the Tello.

The Pi is already configured. Do not reconfigure its Wi-Fi, LTE, or WireGuard keys.

## What you are building

- Host: a Mac on the facility Wi-Fi, with Tailscale in the same tailnet as the Pi.
- Guest: a Lima VM named `go2`, Ubuntu 22.04, ROS 2 Humble, the autonomy stack already described in this repo.
- The Pi (`rpihack`, Tailscale `100.110.8.74`) bridges Ethernet to the dog (`192.168.123.161`). The VM reaches the dog through WireGuard (`wg0`), not through the facility subnet.
- Leave the Tello alone. The Pi's USB stick scans it. This Mac must stay on `hackathon`.

## Requirements

- macOS, Apple Silicon or Intel.
- At least 16 GB of RAM and 40 GB of free disk. The VM asks for 8 CPUs, 12 GB, and a 40 GB disk. Stop if the Mac is smaller.
- Lima 2.0 or newer (`brew install lima`).
- Tailscale (`brew install tailscale`), logged into the tailnet that already contains `100.110.8.74`. Then `tailscale set --accept-routes=true`.
- The file `/etc/wireguard/wg0.conf` from the existing dog VM. Copy it from the operator out of band. Do not generate a new key pair, and do not commit the file. Only one machine may run this tunnel at a time. The original Mac must have `wg0` down before you bring it up here.

## 1. Clone and rewrite the absolute paths

Clone the repo. Every path below is hard-coded to the original Mac. Set `ROOT` to your clone and rewrite them before starting the VM:

```bash
ROOT="$(cd /path/to/grok-hackathon-pavia && pwd)"
OLD=/Users/ares-pc/localrepo/grok-hackathon-pavia
grep -Rl "$OLD" "$ROOT/robot/go2" | while read -r f; do
  sed -i '' "s|$OLD|$ROOT|g" "$f"
done
```

Files that contain the prefix: `lima.yaml`, `provision.sh`, `up.sh`, `seek.py`, `run.sh`, `calib.sh`, `goal.sh`.

In `robot/go2/lima.yaml`, delete the `go2lan` network entry. That network is a USB Ethernet bridge (`en8`) on the original Mac. This station has no dog cable. Leave only:

```yaml
networks:
- vzNAT: true
```

## 2. Start the VM and build

```bash
limactl start --name=go2 --tty=false "$ROOT/robot/go2/lima.yaml"
limactl shell go2 -- bash "$ROOT/robot/go2/provision.sh"
```

`provision.sh` must print `PROVISION_OK`. The colcon build is long and uses one worker on purpose. If `netplan apply` complains that `lima1` is missing, continue. That interface exists only when the USB bridge is attached.

Check the build from outside:

```bash
limactl shell go2 -- test -d "$HOME/autonomy_stack_go2/install" && echo BUILT
```

## 3. Install the existing WireGuard config

Copy the operator's `wg0.conf` into the VM. Do not print the file.

```bash
limactl shell go2 -- sudo install -m 600 /dev/stdin /etc/wireguard/wg0.conf < /path/to/wg0.conf
```

The VM address inside that file is `192.168.123.101`. The Pi is `192.168.123.102`. The dog is `192.168.123.161`.

## 4. Reach the Pi before starting the stack

Join Wi-Fi SSID `hackathon` and stay there. The PSK is the same string, also written in `robot/go2/pi-wifi.sh`.

```bash
ping -c 3 100.110.8.74
ssh -o BatchMode=yes rpihack@100.110.8.74 'ip -4 -br addr; echo ---; ping -c 1 -W 1 192.168.123.161 >/dev/null && echo DOG_UP || echo DOG_DOWN'
```

`DOG_DOWN` is acceptable while the other team has the robot. `DOG_UP` means the Ethernet cable between the Pi and the dog is plugged in. Do not continue to step 5 until it is `DOG_UP`.

The Pi's facility address is `192.168.5.230` on `wlan0` (5 GHz). DHCP can change it. Read it from the `ip` line above rather than trusting this number.

## 5. Bring the stack up

`up.sh` exits immediately unless a flag file exists. Create it, then run the script. The script asks for an administrator password through a macOS dialog. That dialog has to be approved by the person at the keyboard.

```bash
touch "$ROOT/robot/go2/connect.request"
bash "$ROOT/robot/go2/up.sh"
cat "$ROOT/robot/go2/connect.status"
```

Success is the single word `pronto` in `connect.status`. RViz is at `http://127.0.0.1:6080/vnc.html?autoconnect=true` on this Mac.

What `up.sh` does, in order: start Lima, reach the dog through the Pi, bring `wg0` up inside the VM, calibrate the IMU, launch `system_real_robot_with_route_planner.launch`, then start `seek.py`. If the IMU topic does not arrive it stops and writes `nuvola non parte`. Do not launch the stack by hand after that. Fix the tunnel first.

A direct check, after `pronto`:

```bash
limactl shell go2 -- bash -lc "source $ROOT/robot/go2/guest-env.sh && timeout 8 ros2 topic echo /utlidar/imu --once"
```

## 6. Move the lidar off LTE only if the Wi-Fi is actually fast

LTE is the working tunnel. The facility Wi-Fi is faster only when a quiet ping stays low. From this Mac, with no extra traffic:

```bash
ping -c 20 -i 0.2 192.168.5.230
```

Stop here if any packet is lost or the median is above 30 ms. The lidar stays on LTE.

If the ping is clean, the VM still cannot send to `192.168.5.230`: Lima's own NAT inside the guest is also `192.168.5.0/24`. Run the forwarder on the Mac, not inside the VM. `192.168.64.1` is the Lima gateway on the host. No sudo.

```bash
MAC=$(ipconfig getifaddr en0)
python3 "$ROOT/robot/go2/wifi-tunnel.py" "$MAC" 192.168.5.230
```

Leave that process running. In another terminal, point the VM's WireGuard peer at the forwarder:

```bash
limactl shell go2 -- sudo bash -lc 'key=$(wg show wg0 peers | head -1); wg set wg0 peer "$key" endpoint 192.168.64.1:51820 persistent-keepalive 5; wg show wg0'
```

A handshake newer than a few seconds, then this ping, means the fast path is up:

```bash
limactl shell go2 -- ping -I 192.168.123.101 -c 3 -W 2 192.168.123.161
```

If the handshake does not complete, put the endpoint back on the LTE path and leave it there:

```bash
limactl shell go2 -- sudo bash -lc 'key=$(wg show wg0 peers | head -1); wg set wg0 peer "$key" endpoint 100.110.8.74:51820 persistent-keepalive 15'
```

## Commands this station owns

After `pronto`:

```bash
bash "$ROOT/robot/go2/dog.sh" findDrone
bash "$ROOT/robot/go2/dog.sh" returnHome
```

The red Stop button in RViz is the halt. Do not send motion any other way.

## Do not

- Do not join `TELLO-62A593` from this Mac. That drops `hackathon` and the lidar path.
- Do not run `patrol.drone`. The drone station is the other computer.
- Do not change the Pi's `wlan0` (facility, 5 GHz, never the default route) or `wlan1` (Tello scan only).
- Do not add iptables rules on UDP 51820.
- Do not start a second copy of `wifi-tunnel.py`.
