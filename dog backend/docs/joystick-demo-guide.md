# Joystick test demo: step-by-step guide

From plugging in the dog to switching off. Full details: [`docs/dog.md`](dog.md) §2 and §2c.

> ⛔ Never update, flash or reset the dog's firmware. No OTA, no re-bind, no mode switching.
> 🛑 **Staff must be present with their controller in hand.** The staff controller is the main stop. The joystick page is only a backup.
> ⚠️ This is the first time the joystick runs on the real dog, and the soft lie-down (STOP) has never been sent to it. Watch it closely the first time.

---

## 0. Before you start (one time only)

Skip this if `.venv` already works.

```bash
bash robot-docs/fetch-sdks.sh
brew install portaudio
python3.12 -m venv .venv
.venv/bin/pip install -r requirements/dog.txt
```

Check that `config/dog.local.json` exists (copy it from `config/dog.example.json` if it doesn't). It must contain `"interface": "192.168.123.161"`.

---

## 1. Dry run with the simulated dog (no robot, 2 min)

Do this first to check the page works on your laptop.

```bash
cd "<repo root>"
.venv/bin/python -m patrol.dog.joystick --fake
```

Open **http://127.0.0.1:8765/** in the browser. Press **Stand up**, drive a bit with `W A S D`, press **STOP**. Then press `Ctrl+C` in the terminal.

---

## 2. Connect the dog

1. Staff turns on the dog. Wait until it is standing or lying still.
2. **Close the Unitree phone app** (the dog accepts only one connection).
3. Plug the Ethernet cable from the dog into the USB LAN adapter on the Mac.
4. Set the Mac's address (only needed once per Mac, already done on Leonardo's):
   ```bash
   networksetup -setmanual "USB 10/100/1000 LAN" 192.168.123.222 255.255.255.0
   ```
5. Check the link:
   ```bash
   ping -c 3 192.168.123.161
   nc -vz -G 3 192.168.123.161 8081    # must say "succeeded"
   ```
   If the first ping says `No route to host`, wait a few seconds and try again.

---

## 3. Start the joystick

Run this in **your own Terminal window** (so the terminal stop keys work), from the repo root:

```bash
.venv/bin/python -m patrol.dog.joystick --config config/dog.local.json
```

The terminal prints `REAL dog (connecting, no motion on connect)`. Connecting never moves the dog.

Open **http://127.0.0.1:8765/** in the browser. Only one tab controls the dog; other tabs are view-only.

Check the status panel: connected, battery shown, live video running, safety shows **OK**.

---

## 4. Drive the demo

| Step | Do this |
|---|---|
| 1 | Clear about 3 m around the dog. Staff ready with the controller. |
| 2 | Press **Set home here** (centres the 3 m safety fence on the dog). |
| 3 | Press **Stand up**. Wait for "standing" in the status panel. |
| 4 | Leave the speed slider at 50 % (0.15 m/s) for the first run. |
| 5 | Walk forward a short distance: hold `W` (or push the left stick), then release. Releasing stops the dog, and it stays standing. |
| 6 | Try turning (`J` / `L` or the right stick) and sideways (`A` / `D`). |
| 7 | Press **Photo**. The file path appears on the page (saved in `evidence/dog/`). |
| 8 | Press **STOP** (or `Space` / `Q`). The dog stops and lies down softly. |

**Controls**

| Control | Action |
|---|---|
| `W` / `S` or left stick | Forward / back |
| `A` / `D` or left stick | Sideways |
| `J` / `L` / `←` `→` or right stick | Turn |
| Release keys or stick | Stop walking, stay standing |
| **STOP**, `Space`, `Q` | Stop + lie down softly |
| Terminal `Q` or `Enter` | Stop + lie down softly |
| Terminal `Ctrl+C` | Lie down, then exit |

Speed is capped at 0.3 m/s forward/back, 0.2 m/s sideways, 0.6 rad/s turning.

**To drive again after a STOP:** press **Re-arm (reconnect)**, then **Stand up**.

**If a safety trip happens** (red banner: fence, speed or tilt): the dog lies down by itself. Press **Re-arm**, then **Stand up**. If the dog is outside the fence, press **Set home here** first.

---

## 5. Finish

1. Press **STOP** so the dog lies down.
2. Press `Ctrl+C` in the terminal (lies down if needed, then exits).
3. Close the browser tab.
4. Staff switches off the dog. Unplug the Ethernet cable.
5. Logs and photos are in `evidence/dog/` (`joystick.jsonl` contains each stop and how long it took).

---

## If something goes wrong

| Problem | Fix |
|---|---|
| Dog does something unexpected | **Staff controller first**, then STOP on the page. |
| Cable pulled or link lost | The page can no longer stop the dog. Use the staff controller. |
| `RobotBusyError` | Phone app or another joystick is still connected. Close it. |
| `LocalSignalingPortError` | Wrong IP, cable out or dog off. Redo the checks in step 2. |
| `unitree_webrtc_connect is not installed` | You're not using `.venv/bin/python`. |
| `Cannot listen on 127.0.0.1:8765` | Another joystick is running. Close it or add `--port 8766`. |
| Page shows "view-only" | Another tab has control. Press **Take control** or close the other tab. |
