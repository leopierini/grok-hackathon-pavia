#!/bin/bash
# IMU calibration. Spins the dog in place for about 20 seconds. Needs a clear floor.
set -euo pipefail
if [ "${GO2_CALIB:-}" != 1 ]; then
  echo "This node drives the dog: a short settle, then a spin. Clear the floor, then re-run with GO2_CALIB=1." >&2
  exit 1
fi
stack=/Users/ares-pc/localrepo/grok-hackathon-pavia/robot
limactl shell go2 -- sudo bash "$stack/go2/guest-addr.sh"
exec limactl shell go2 -- bash -lc "source $stack/go2/guest-env.sh && ros2 run calibrate_imu calibrate_imu"
