#!/bin/bash
# Start the CMU Go2 stack inside the Lima VM. Does not modify the dog.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
stack=/Users/ares-pc/localrepo/grok-hackathon-pavia/robot
limactl start --name=go2 --tty=false "$here/lima.yaml"
limactl shell go2 -- sudo bash "$stack/go2/guest-addr.sh"
# The VM owns 192.168.123.100 on the cable. Drop the same address on the Mac.
if ifconfig en8 2>/dev/null | grep -q 'inet 192.168.123.100'; then
  osascript -e 'do shell script "ifconfig en8 -alias 192.168.123.100" with administrator privileges'
fi
exec limactl shell go2 -- bash -lc "source $stack/go2/guest-env.sh && cd \"\$HOME/autonomy_stack_go2\" && ros2 launch vehicle_simulator system_real_robot_with_route_planner.launch"
