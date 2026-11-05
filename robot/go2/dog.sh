#!/bin/bash
# findDrone and returnHome, on the stack in the VM.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
case "${1:-}" in
  findDrone) name=/find_drone ;;
  returnHome) name=/return_home ;;
  *) echo "use: dog.sh findDrone | returnHome" >&2; exit 2 ;;
esac
exec limactl shell go2 -- bash -lc "source $here/guest-env.sh && ros2 service call $name std_srvs/srv/Trigger"
