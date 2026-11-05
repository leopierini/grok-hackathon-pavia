# Pi bridge: Raspberry Pi 5 on the dog

Status: **design, agreed with Leonardo on 2026-11-04. Nothing built or bought yet.**
Why it exists: so the laptop isn't tied to the dog by a cable during the demo, and so something on the dog can measure the drone's Wi-Fi signal. Used by [`docs/Lidar + SLAM.md`](Lidar%20+%20SLAM.md).

> ⛔ Same hard rules as `docs/dog.md`: no firmware/software changes on the dog, no network-mode or motion-mode switching, every STOP = StopMove + StandDown (never Damp). The staff controller stays the primary emergency stop.

## 1. Layout

```
 dog ──short Ethernet cable── Raspberry Pi 5 (on the dog, power bank)
                                 │ built-in Wi-Fi            │ USB Wi-Fi dongle
                                 ▼                           ▼
                     laptop (anywhere in the room)     Tello's own Wi-Fi
                     joystick page, Grok, dashboard     (signal strength)
```

- **Pi:** holds the one WebRTC connection to the dog (same cable and settings the laptop uses today: dog `192.168.123.161`, Pi static `192.168.123.222/24` on its Ethernet port, no router), runs `RealDog` + the joystick server, reads the LiDAR, measures the drone's RSSI, does the mapping and following (`Lidar + SLAM.md` stages 4–5).
- **Laptop:** runs all AI (Grok, intruder decision) and the dashboard, and opens the joystick page from the Pi in a browser. **In the demo it is connected to nothing by cable and stays out of the video.** Everything it does with the dog goes over Wi-Fi to the Pi.

**Why not connect the laptop to the dog over Wi-Fi instead?** It would need the dog's network mode switched (forbidden). Only if staff confirm the dog is already on a Wi-Fi network we can join.

## 2. Hardware

| Item | Notes |
|---|---|
| Raspberry Pi 5 | Have it (Leonardo). Built-in dual-band Wi-Fi, Gigabit Ethernet. 64-bit Raspberry Pi OS (Lite is enough). |
| Power bank | The Pi 5 wants 5 V / 5 A. A normal 5 V / 3 A bank runs it, but the Pi then limits its USB ports to 600 mA total, which should still cover one Wi-Fi dongle. Check the bank keeps up for a full session. |
| USB Wi-Fi dongle | 2.4 GHz (the Tello is 2.4 GHz). Prefer one that supports **monitor mode** (fallback in §4). |
| Short Ethernet cable | Dog port → Pi. |
| Mounting | Straps/velcro. Must not cover the drone's spot on the back or the LiDAR in the head, and must not snag the legs. Ask staff where (`Lidar + SLAM.md` §10). |

## 3. Software

- Python venv on the Pi with `requirements/dog.txt`. `unitree_webrtc_connect` installed **non-editable** (same as on the Mac). Check that `aiortc`, `av`, `opencv` (headless) and `wasmtime` install on the Pi's 64-bit ARM; the native LiDAR decoder only needs `lz4` + `numpy` if `wasmtime` is trouble.
- **Run the existing joystick server on the Pi.** Today it listens on `127.0.0.1` only and rejects other `Host`/`Origin` headers on purpose. Change needed: listen on the Pi's Wi-Fi address, allow that host, and require a **shared token** in the page URL (*my call*), so only our laptop can drive.
- Same rules as today: one controller, other tabs view-only, STOP always works.
- **Dog API for the laptop's AI process.** Grok's dog actions (dispatch the dog, take a photo, speak via the dog) call `RealDog` directly today, inside the laptop process. With the Pi holding the only dog connection, the laptop needs a **`RemoteDog`** that implements the same `DogPort` contract (`patrol/contract.py`) by calling the Pi over Wi-Fi, so the AI code doesn't change. The Pi side exposes those calls (same token as the page) next to the joystick server, which already owns the `RealDog`.
  - Camera frames and dog audio (speak / listen) also travel over Wi-Fi. Expect some extra lag; measure it.
  - `halt()` from the laptop maps to the Pi's STOP path.
  - **Contract change (agree with the team, the contract is shared):** add `follow_drone(ctx)` and `stop_follow()` to `DogPort`, plus a follow state in the status. The AI calls `follow_drone` when it decides "intruder" (`Lidar + SLAM.md` §8). `FakeDog` gets fake versions so the AI side can be tested without the dog.
- Start on boot is optional; starting it by hand over SSH is fine for the hackathon.

## 4. Networks

- **Pi ⟷ laptop:** both join the same Wi-Fi network. *My suggestion:* a phone hotspot, because venue Wi-Fi often blocks devices from talking to each other, and the hotspot also keeps the laptop online for Grok. Open question for the team (§7).
- **Pi ⟷ Tello (signal strength):** the USB dongle joins the Tello's network and reads its signal (`iw dev <dongle> link` or `station dump`, about 5–10 Hz).
  - Unknown: whether the Tello is happy with a second device on its network while the drone team's laptop controls it. Test early with the drone team.
  - Fallback: the dongle listens passively to the Tello's beacons in monitor mode, without joining.
  - Bonus: if the Pi is on the Tello's network it could relay the drone video to the laptop. The drone team decides.

## 5. Safety (the extra rule)

With the laptop away from the dog, a STOP travels laptop → Wi-Fi → Pi → dog. So:

- **Lost contact with the laptop:** the existing joystick behaviour already sends StopMove (dog stays standing) when the WebSocket drops. **New:** if contact isn't back within **3 s** (*my call*), the Pi lies the dog down softly (StopMove + StandDown), logged. Following (stage 5) stops at once on contact loss.
- All existing safety thresholds (fence, speed, tilt, route overshoot) run on the Pi inside `RealDog`, unchanged.
- The staff controller stays the primary emergency stop. Pulling the Ethernet cable is still **not** a stop.
- Test the lost-contact rule with the dog lying down first (turn off the laptop's Wi-Fi and watch the log), then once standing with staff present.

## 6. Team message (WhatsApp draft, 2026-11-04)

> Hey! Proposed setup for the dog so we're not tethered to my laptop during the demo, does this sound good? 👇
>
> *Setup*
> 🐕 Dog ⟷ short Ethernet cable ⟷ *Raspberry Pi 5* riding on the dog (powered by a power bank)
> 📶 Pi ⟷ Wi-Fi ⟷ laptop (anywhere in the room)
>
> *What the Pi does*
> • Holds the connection to the dog (same as my laptop does now)
> • Reads the dog's LiDAR (obstacles)
> • Measures the drone's Wi-Fi signal strength with a USB Wi-Fi dongle joined to the Tello. The dog follows that signal to stay with the drone.
> • Passes commands from the laptop to the dog
>
> *What the laptop does*
> • Grok, the dashboard, the joystick page, no cable
>
> *Safety*
> • If the Pi loses contact with the laptop, it lies the dog down by itself
> • Staff controller stays the main emergency stop
> • No changes to the dog's firmware or settings
>
> *Questions*
> 1. Any objections, or a simpler way you'd do it?
> 2. Who has a USB Wi-Fi dongle + a power bank that can go on the dog?
> 3. Drone team: OK if the Pi joins the Tello's Wi-Fi to read its signal? It could also relay the drone video to the laptop.

## 7. Open questions

**Team:**
1. Who has a 2.4 GHz USB Wi-Fi dongle (ideally monitor-mode capable) and a power bank?
2. Which network do the Pi and laptop share (phone hotspot suggested)?
3. Drone team: OK for the Pi to join the Tello's network? Does the Tello still accept commands/video for the drone laptop with a second client joined?
4. Everyone: OK to add `follow_drone` / `stop_follow` to the shared `DogPort` contract?
5. Drone team: "drone follows the intruder" is new work compared with the agreed short hop. Who builds it?

**Staff:** mounting spot and the other questions in `Lidar + SLAM.md` §10.
