#!/bin/bash
set +u
source /opt/ros/humble/setup.bash
source "$HOME/autonomy_stack_go2/install/setup.bash"
set -u
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
iface=$(cat /run/go2-iface)
if [ -s /run/go2-addr ]; then
  nic="address=\"$(cat /run/go2-addr)\""
else
  nic="name=\"${iface}\""
fi
discovery=""
if [ -s /run/go2-peer ]; then
  discovery="<Discovery><Peers><Peer address=\"$(cat /run/go2-peer)\"/></Peers></Discovery>"
fi
export CYCLONEDDS_URI="<CycloneDDS><Domain>${discovery}<General><Interfaces><NetworkInterface ${nic} priority=\"default\" multicast=\"true\"/></Interfaces><AllowMulticast>true</AllowMulticast></General></Domain></CycloneDDS>"
unset ROS_DOMAIN_ID || true
export ROS_LOCALHOST_ONLY=0
