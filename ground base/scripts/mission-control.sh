#!/usr/bin/env bash
# Mission Control (Next.js, http://127.0.0.1:3000) + Ground API + drone flight server, on macOS/Linux.
# The Live patrol screen (/live) drives the real peers. Rehearsal screens are unchanged.
#
#   scripts/mission-control.sh sim        fake drone, simulated dog, scripted Grok (no hardware, no key)
#   scripts/mission-control.sh sim-grok   fake drone, simulated dog, REAL Grok
#   TELLO_IP=192.168.5.137 scripts/mission-control.sh real        real Tello + dog on Ethernet + Grok
#   TELLO_IP=192.168.5.137 scripts/mission-control.sh real-nodog  real Tello + Grok, no dog
#
# Who to look for: GROUND_LIVE_TARGET="a person wearing a red cap" scripts/mission-control.sh real
# Pilot page (takeoff / land, always available): http://127.0.0.1:8766  (sim: 8799)
# Ctrl+C stops everything; the drone server lands the aircraft on exit.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TEAM="$(cd "$HERE/.." && pwd)"
MODE="${1:-sim}"

case "$MODE" in
  sim)        DRONE_ARGS=(--fake --port 8799); export GROUND_LIVE_DRONE=http://127.0.0.1:8799 GROUND_LIVE_DOG=sim GROUND_LIVE_GROK=fake GROUND_LIVE_ARM_DOG=1 GROUND_LIVE_TAKEOFF=1 ;;
  sim-grok)   DRONE_ARGS=(--fake --port 8799); export GROUND_LIVE_DRONE=http://127.0.0.1:8799 GROUND_LIVE_DOG=sim GROUND_LIVE_GROK=real GROUND_LIVE_ARM_DOG=1 GROUND_LIVE_TAKEOFF=1 ;;
  real)       DRONE_ARGS=(--port 8766); export GROUND_LIVE_DRONE=http://127.0.0.1:8766 GROUND_LIVE_DOG=ethernet GROUND_LIVE_GROK=real GROUND_LIVE_ARM_DOG=1 GROUND_LIVE_TAKEOFF=1 ;;
  real-nodog) DRONE_ARGS=(--port 8766); export GROUND_LIVE_DRONE=http://127.0.0.1:8766 GROUND_LIVE_DOG=none GROUND_LIVE_GROK=real GROUND_LIVE_TAKEOFF=1 ;;
  *) echo "usage: $0 sim|sim-grok|real|real-nodog" >&2; exit 2 ;;
esac

export GROUND_OPERATOR_TOKEN="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
export GROUND_API_ORIGIN=http://127.0.0.1:8765
PIDS=()
cleanup() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

cd "$TEAM" && "$TEAM/.venv/bin/python" -m patrol.drone.manual "${DRONE_ARGS[@]}" & PIDS+=($!)
cd "$HERE" && "$HERE/.venv/bin/python" -m patrol.ground.operator --host 127.0.0.1 --port 8765 & PIDS+=($!)
cd "$HERE/ui/mission-control" && npm run dev & PIDS+=($!)

echo "Mission Control  http://127.0.0.1:3000/live   (mode $MODE)"
echo "Pilot page       ${GROUND_LIVE_DRONE}"
wait
