#!/usr/bin/env bash
# Start the live museum demo: the drone flight server and the Ground live console.
#
#   scripts/live-demo.sh sim                 # no hardware, no key: fake drone, simulated dog, scripted Grok
#   scripts/live-demo.sh sim-grok            # fake drone + simulated dog, REAL Grok (needs the key file)
#   TELLO_IP=192.168.5.137 scripts/live-demo.sh real        # real Tello (station mode), real dog on Ethernet, real Grok
#   TELLO_IP=... scripts/live-demo.sh real-nodog            # real Tello + Grok, no dog
#
# Pages:  Ground console http://127.0.0.1:8770   Drone pilot page http://127.0.0.1:8766 (sim: 8799)
# Halt:   red button or Q in the console. Land: L / button in the pilot page. Staff keep the dog controller.
# Ctrl+C stops both processes. The drone server lands the aircraft on exit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"          # ground base
TEAM="$(cd "$HERE/.." && pwd)"                     # repo root (drone tree + root .venv)
MODE="${1:-sim}"
DRONE_PY="$TEAM/.venv/bin/python"
GROUND_PY="$HERE/.venv/bin/python"
read -r -a EXTRA <<< "${LIVE_EXTRA:-}"

case "$MODE" in
  sim)       DRONE_ARGS=(--fake --port 8799); DRONE_URL=http://127.0.0.1:8799; LIVE=(--dog sim --arm-dog --grok fake --allow-takeoff) ;;
  sim-grok)  DRONE_ARGS=(--fake --port 8799); DRONE_URL=http://127.0.0.1:8799; LIVE=(--dog sim --arm-dog --grok real --allow-takeoff) ;;
  real)      DRONE_ARGS=(--port 8766); DRONE_URL=http://127.0.0.1:8766; LIVE=(--dog ethernet --arm-dog --grok real) ;;
  real-nodog) DRONE_ARGS=(--port 8766); DRONE_URL=http://127.0.0.1:8766; LIVE=(--dog none --grok real) ;;
  *) echo "usage: $0 sim|sim-grok|real|real-nodog" >&2; exit 2 ;;
esac

if [[ "$MODE" == real* && -z "${TELLO_IP:-}" ]]; then
  echo "TELLO_IP is unset: the drone server will use AP mode 192.168.10.1" >&2
fi

cd "$TEAM"
"$DRONE_PY" -m patrol.drone.manual "${DRONE_ARGS[@]}" &
DRONE_PID=$!
trap 'kill $DRONE_PID 2>/dev/null; wait 2>/dev/null' EXIT INT TERM
sleep 2
cd "$HERE"
"$GROUND_PY" -m patrol.ground.live --drone "$DRONE_URL" "${LIVE[@]}" ${EXTRA[@]+"${EXTRA[@]}"}
