#!/bin/bash
# Publish one goal in the map frame. The stack must already be running.
# Usage: robot/go2/goal.sh X Y
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "usage: $0 X Y" >&2
  exit 1
fi
stack=/Users/ares-pc/localrepo/grok-hackathon-pavia/robot
exec limactl shell go2 -- bash -lc "source $stack/go2/guest-env.sh && python3 $stack/go2/goal.py $1 $2"
