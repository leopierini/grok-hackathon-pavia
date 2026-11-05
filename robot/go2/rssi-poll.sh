#!/bin/bash
# Keep rssi.dbm in step with the Pi. Rewrite it only when the Pi file changes,
# so a stuck scan does not look like a fresh reading.
set -u
here=$(cd "$(dirname "$0")" && pwd)
pi=rpihack@100.110.8.74
stamp=""
while true; do
  got=$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$pi" 'stat -c %Y /run/go2-rssi 2>/dev/null; cat /run/go2-rssi' 2>/dev/null) || { sleep 2; continue; }
  if [ "$got" != "$stamp" ]; then
    stamp=$got
    printf '%s\n' "${got##*$'\n'}" > "$here/rssi.dbm"
  fi
  sleep 2
done
