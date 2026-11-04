#!/usr/bin/env bash
# Re-download all robot SDKs (shallow clones) into robot-docs/sdks/ (git-ignored).
set -euo pipefail
cd "$(dirname "$0")" && mkdir -p sdks && cd sdks
clone() { [ -d "$2" ] && echo "skip $2" || git clone --depth 1 ${3:+-b $3} "$1" "$2"; }
# Dogs (Unitree)
clone https://github.com/legion1581/go2_webrtc_connect        go2_webrtc_connect
clone https://github.com/unitreerobotics/unitree_sdk2_python  unitree_sdk2_python
clone https://github.com/abizovnuralem/go2_ros2_sdk           go2_ros2_sdk
clone https://github.com/unitreerobotics/unitree_legged_sdk   unitree_legged_sdk go1
clone https://github.com/unitreerobotics/UnitreecameraSDK     UnitreecameraSDK
# Cobots
clone https://github.com/xArm-Developer/xArm-Python-SDK       xArm-Python-SDK
clone https://gitlab.com/sdurobotics/ur_rtde                  ur_rtde
clone https://github.com/Elite-Robots/Elite_Robots_CS_SDK     Elite_Robots_CS_SDK
