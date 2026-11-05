# Manual Tello controller (fallback)

Fly the Tello by hand from the laptop when the autonomous flow misbehaves.

    .venv/bin/python -m patrol.drone.manual            # real drone
    .venv/bin/python -m patrol.drone.manual --fake     # simulated drone and camera, sends nothing

Open http://127.0.0.1:8766 yourself. Starting it never moves the drone: it only sends `command`, asks the battery and turns the camera on.

It owns the Tello link (local UDP 9000), so stop `patrol.drone.live` first. If port 9000 is taken it prints which process to stop and exits.

## Keys

| Key | Action |
| --- | --- |
| W / S | forward / back (arrows Up / Down too) |
| A / D | left / right (arrows Left / Right too) |
| Q / E | turn left / right |
| R / F | up / down (PageUp / PageDown too) |
| Space | hover: sticks to zero |
| T | takeoff, press twice within 3 s |
| L or Esc | LAND, instant, never confirmed |
| X | emergency, press twice: cuts the motors and drops the drone |

Gamepad (standard mapping): left stick moves, right stick turns and goes up/down, Start takeoff (twice), B or Back land, A hover. The LAND bar at the bottom of the page is always visible.

## Safety

- Deadman: the page sends sticks at ~20 Hz only while a key or stick is active. The server zeroes the sticks after 300 ms without an update (tab closed, blur, stuck key). The page also zeroes on keyup, window blur, tab switch and Cmd/Ctrl/Alt.
- Speed slider: default 30, max 70. All rc values are clamped to the slider and to -100..100.
- The server sends at most 20 rc/s and only the newest stick state (no queue). Releasing sends `rc 0 0 0 0` at once, repeated 4 times.
- Idle hover: `rc 0 0 0 0` every 2 s while airborne (the Tello lands itself after ~15 s of silence). No rc is sent while grounded or while a takeoff or land is pending.
- Takeoff only when grounded, battery known and >= 10 %. Sticks are ignored for 1 s after takeoff. Battery < 20 % shows a red warning.
- Land is always allowed in every state. During a pending takeoff it is sent raw at once, then confirmed with a normal `land` query. If land is not confirmed the state returns to airborne so keep-alive resumes and you can press Land again.
- Emergency needs arm then confirm (0.3 s to 4 s apart), enforced by the server. Land cancels the arming.
- If the controller starts while the drone is already flying (telemetry h >= 30 cm) it takes over as airborne. Start it within ~10 s of stopping `patrol.drone.live`, because the Tello lands itself after ~15 s without commands.
- Ctrl+C on the server while the drone may be airborne sends `land`.
- Video is polled JPEGs on its own path. If it fails the page says "VIDEO DOWN" and flying still works.
- The server answers only Host 127.0.0.1 / localhost and only JSON POSTs, so other web pages cannot drive it.
