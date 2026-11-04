#!/bin/bash
# Go2 joystick launcher. Double-click in Finder (opens Terminal), or run: scripts/dog_joystick.command
#   - starts the joystick server for the REAL dog and opens the page in your browser
#   - if the dog isn't reachable yet, the server connects by itself once it answers
#   - if a joystick is already running, it only opens the page
# Keep this Terminal window open: Q / Enter = STOP (lie down softly), Ctrl+C = lie down + exit.
# Extra arguments go to the server, e.g.  scripts/dog_joystick.command --fake

cd "$(dirname "$0")/.." || exit 1
URL="http://127.0.0.1:8765/"

pause_exit() { echo; read -r -p "Press Enter to close this window." _; exit "${1:-0}"; }

if curl -s -o /dev/null --max-time 1 "$URL"; then
  echo "Joystick already running: opening $URL"
  open "$URL"
  exit 0
fi
if [ ! -x .venv/bin/python ]; then
  echo "No .venv found. Set it up first (handoff/dog.md, section 2)."
  pause_exit 1
fi
if [ ! -f config/dog.local.json ] && [[ " $* " != *" --fake "* ]]; then
  echo "config/dog.local.json is missing. Copy config/dog.example.json and set the dog's IP."
  pause_exit 1
fi

if [[ " $* " != *" --fake "* ]]; then
  IP=$(.venv/bin/python -c 'import json; print(json.load(open("config/dog.local.json")).get("interface", ""))' 2>/dev/null)
  if [ -n "$IP" ] && ! ping -c 1 -t 1 "$IP" >/dev/null 2>&1; then
    echo "Dog ($IP) not reachable yet: plug in the Ethernet cable / turn the dog on."
    echo "The server connects by itself as soon as the dog answers."
    echo
  fi
fi

.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json --open "$@"
echo
echo "Joystick server stopped."
pause_exit 0
