# Robot Patrol

Four people, four blocks. Take one block and do its tasks in order. The only shared surface is `patrol/contract.py`. The ground station is the only process that calls the dog, the drone, and Grok.

Track D. A camera spots an anomaly. A Tello EDU goes there and hovers. The Go2 does not receive a coordinate. It hears the drone's Wi-Fi, walks toward the stronger signal, and stops only when the drone's camera sees the dog underneath. Grok decides whether to send the dog, reads both cameras, and writes the alert.

Thursday 16:00: one video of a full pass, and a log line with two numbers (time from anomaly to arrival, and Grok's dispatches against "always send the dog").

The dog in this file is a **Unitree Go2** (AIR, PRO, or EDU — not confirmed on the museum unit). The drone is a **Tello EDU**.

## One run

1. Someone sets a target in plain language. Example: "a person or an abandoned object in a closed area".
2. The Tello searches. There are no mission pads and no map. It yaws a full turn in 45° steps, grabs a frame at each step, and Grok says whether the target is in that frame. If not, it flies forward about 40 cm and turns again. It stops at the first yes.
3. On yes, the Tello hovers there and stays a Wi-Fi beacon. It does not know where the dog is, and it does not steer the dog. If the whole search is a no, it flies its own moves backwards and lands next to the dog, which has been waiting at the launch point.
4. The dog turns, samples signal strength, and steps toward the louder heading. Obstacle avoidance on the Go2 stays on, so a step does not require a map of the room.
5. When the signal stops rising, the drone looks for the dog. Grok says whether the dog is in that frame. If yes, the dog has arrived. If no, the dog is not under the drone yet and takes another step.
6. Grok describes the dog's camera and an alert goes out.

A phone photo can start the same run when the Tello is on the ground. In that case there is no beacon, so the dog walks a short path the team taught by hand instead of following the signal.

The search uses the forward color camera: a spin plus a short step. Arrival uses the other sensor. The Tello EDU exposes a downward camera with `downvision 1` (in `djitellopy`, `set_video_direction(Tello.CAMERA_DOWNWARD)`). It is a low-resolution grayscale infrared image, one stream at a time, so the drone switches to it only to confirm the dog is underneath, then can switch back.

## RSSI

RSSI is the received power of a radio signal, in dBm. A stronger reading (a number closer to zero, such as −40 instead of −80) means the receiver is closer to the source, if the room is not bouncing the signal off metal and walls. It is not a distance in meters. The dog compares readings. It never converts them into a range.

The source is the Tello. Every Tello EDU is its own Wi-Fi access point, so it is already broadcasting while it hovers.

The Go2, in the vanilla Unitree API we have (`go2_webrtc_connect`, `unitree_sdk2_python`), exposes sport mode, cameras, LiDAR, and obstacle avoidance. It does not expose "signal strength of some other Wi-Fi network" or a computed distance to that network. The Go2's own Wi-Fi is the control link. Scanning a second network on that same radio, while the link stays up, is not a documented call.

The Raspberry Pi 5 on the dog (`rpihack`, Tailscale `100.110.8.74`, Debian 13, 4 GB) is a bridge. The SLAM stays in the VM on the Mac.

- Ethernet to the Go2's rear port. The Pi holds `192.168.123.100` and the dog is `192.168.123.161`. The Pi advertises that subnet over Tailscale, so the VM reaches the dog after the USB cable is gone.
- The dog discovers peers by multicast on that short cable only. The Pi relays that discovery and the DDS traffic. The dog's OS stays as it is.
- The Pi's own Wi-Fi scans `TELLO-62A593` and does not join it. Other Tellos in the room are ignored. `read_rssi()` reads that scan and the reading comes back to the VM across the same bridge.
- A USB LTE modem is the Pi's default route. Tailscale rides on it. Lidar and IMU cross that link, so a slow uplink delays the scan.

The Mac runs the stack and never joins the Tello.

## Arrival

The signal is how the dog travels. The camera is how the run decides it has arrived.

The flying Tello cannot point the dog left or right. It has no fix on the dog until the dog enters the camera. The dog only has the signal, so it keeps sweeping until the readings peak.

Then the drone switches to the downward camera and takes a frame. Grok answers one question: is the dog in this image? 

- Yes: arrival. Describe the scene and send the alert.
- No: the dog is not under the drone. Do not treat the peak as success. Step again.

The camera will miss a dog that is close but outside the frame. That miss means "not confirmed", not "the camera now chooses the heading". The signal stays the guide.

## Drone carried on the dog

The Tello can sit on the dog and lift off when a higher view is needed. The pair is then one robot: the dog walks, and it deploys the drone to see past its own head height. A Tello EDU is about 80 g. The Go2 can carry that. Weight is not the problem.

Use the launch when the question needs a view the dog cannot get: over a fence, onto a roof, into a courtyard, or past the point where a drone launched from the door would run out of range. The dog walks there with obstacle avoidance on, stops, and the Tello takes off from a plate on its back. The drone searches, hovers on the find, and becomes the beacon. The dog then homes on the signal the same way as above. Landing is on the ground. Landing back on the dog is a different project.

The dog does not need a scan of the whole building before that walk. Obstacle avoidance is already on the Go2: `obstacles_avoid` in `go2_webrtc_connect` and in `unitree_sdk2_python`. Turn it on and send a short move. It keeps the body off furniture. It does not pick which corner to investigate. That choice is the drone's search plus Grok, not a map made in advance.

Two corners and no prior route: the drone looks, Grok picks the corner, the Tello hovers there, the dog follows the signal. A top-down survey of the house is not a step in this run.

What is actually fiddly about the mount:

- The Go2's LiDAR sits on the top of the body. The plate has to clear the dome and the prop arc. Prop guards stay on.
- Takeoff needs the dog still. A flat plate, dog stopped or lying down, then launch. A moving back is not a runway.
- The command laptop must not join the Tello's access point. The VM reaches the dog through the Pi at `100.110.8.74`. The dog link, the beacon, and the LTE uplink are three networks the whole time.

Thursday's software is the same whether the Tello starts on the plate or on the floor. The floor start is the fallback if the plate is not ready in the slot.

## What Grok does

Grok never opens a socket to the Go2 or the Tello. It sees frames and text, and it returns text. The ground station is the only thing that turns those returns into motion.

| Call | Input | Output | Effect |
|---|---|---|---|
| `assess` | Drone frame + the target sentence | `send`, `reason` | Send the dog, or log a false alarm and stay on patrol |
| `sees_dog` | Downward infrared frame | yes or no | Confirm arrival. A no sends the dog one more step |
| `describe` | Dog's front camera | two or three sentences | What is at the spot |
| `compose_alert` | Assessment + description | a short message | The alert that goes out |
| Voice | English speech | function calls into the ground station only | Set the target, start patrol, halt, "what do you see", "go toward the signal" |

There is no zone name. The model does not invent a place. Halt is immediate and does not ask for confirmation. Any move goes through the ground station, which checks that the dog is standing and that obstacle avoidance is on.

One extra `assess` with a second sentence ("side gate is open") shows that a new order is the same function. The labeled photos for the score are the museum target only.

## Search and return

The Tello has no GPS and no pads, so a search is a list of body moves. Each move is stored. The inverse of that list is the way home.

1. Dog stopped at the launch point. It stays there for the whole search.
2. Take off. Yaw 45°, save a frame, ask Grok. Repeat eight times.
3. If every frame is no, move forward 40 cm and yaw again. Cap the forward steps at three.
4. First yes: stop, hover, return that frame. Do not fly home yet. The dog leaves the launch point and follows the signal.
5. All no: pop the move list and fly it backwards (`cw` becomes `ccw`, forward becomes back), then land. The dog is still standing where the drone took off, so the landing is next to the dog.

Reversing the moves is dead reckoning. On a shiny floor the hover drifts, so the landing is near the dog, not on its back. A person keeps the land key. The drone cannot chase the dog if the dog has walked off.

## Before you split

```python
# patrol/contract.py  — ground station writes this first; everyone else imports it

class Survey(TypedDict):
    frame_path: str
    source: str          # "tello" | "phone" | "fake"
    target: str
    found: bool

class Assessment(TypedDict):
    send: bool
    reason: str
    target: str

class Arrival(TypedDict):
    frame_path: str      # drone frame used for sees_dog
    rssi_dbm: float
    confirmed: bool      # True only after sees_dog says yes
```

| Folder | Who writes it |
|---|---|
| `patrol/contract.py` | Ground |
| `patrol/dog/` | Dog |
| `patrol/drone/` | Drone |
| `patrol/grok/` | Grok |
| `patrol/ground/` | Ground |
| `fixtures/dog/` `fixtures/drone/` `fixtures/rssi/` `fixtures/labels/` | The person who captured them |
| `eval/results.md` | Grok |
| `demo/script.md` | Ground |

Wi-Fi: the Tello stays its own access point. `read_rssi()` runs on the Pi's Wi-Fi and reaches the VM over the bridge. The command laptop never joins the Tello.

Walker: a clean RSSI slope uses `home()`. A jagged scan, or a start from a phone photo, uses a short walk the team taught by hand. There is no pad to fly to. Ground holds that choice in one flag.

Ask staff, once: Go2 firmware and AIR / PRO / EDU, and the Unitree account for the AES key (firmware ≥ 1.1.15, `fetch_aes_key.py`). The Pi 5 on the back (`100.110.8.74`) is the bridge to the dog. The SLAM stays on the laptop.

---

## 1 — Dog

You own `patrol/dog/`. You send stand, turn, a short move, stop. Sport mode stays on the robot. Turn `obstacles_avoid` on before any step. You do not build avoidance, and you do not build a map.

You implement:

```python
class Dog:
    def stand(self) -> None: ...
    def halt(self) -> None: ...                 # immediate, from anywhere
    def read_rssi(self) -> float: ...           # Pi Wi-Fi scan of TELLO-62A593
    def home(self) -> Arrival: ...              # heading sweep; confirmed stays False
    def walk_taught(self) -> Arrival: ...      # fallback when there is no beacon
```

`FakeDog` implements the same methods first. `home()` on the fake replays `fixtures/rssi/scan.csv`. `confirmed` is always false here. Ground sets it after `sees_dog`.

**1. Connect and stand.** WebRTC (`go2_webrtc_connect`). Stand, balance, `halt()` from the keyboard. A dropped link stops the dog. Switch obstacle avoidance on and walk one short step to show it is active.

**2. Read the signal on the Pi.** `wlan0` scans `TELLO-62A593` without joining it. Other Tellos are ignored. The Ethernet command link stays up. Write `place, heading, rssi` to `fixtures/rssi/scan.csv` with the Tello powered on the floor, motors off. Louder toward the Tello means `home()` on Thursday. Jagged means `walk_taught`.

**3. Heading sweep.** Replay the CSV on a laptop and check that stepping toward the loudest sample reaches the beacon. Then `home()` on the dog: 8 headings, `read_rssi()`, one short step on the max, stop. Return when the signal stops rising or a step cap hits. Do not set `confirmed`. `halt` cuts the loop.

**4. Taught walk and the fake.** `walk_taught` is one stored heading plus a timed move, used when there is no beacon. In the dog slot, save one photo under `fixtures/dog/`.

Done when `home()` walks the real dog toward a Tello on the floor and returns an `Arrival` with an RSSI, or `scan.csv` shows why Thursday uses `walk_taught`.

Leave the drone, the prompt, and the state machine alone.

---

## 2 — Drone

You own `patrol/drone/`. One Tello EDU. It finds the anomaly, hovers as the beacon, and supplies the downward frame that confirms the dog. Fly only in the staff slot, with a person on the kill command.

You implement:

```python
class Spotter:
    def survey(self, target: str) -> Survey: ...   # yaw + short steps, stop on first find
    def hover(self) -> None: ...
    def look_for_dog(self) -> str: ...             # switch to the downward camera, return a frame
    def return_home(self) -> None: ...             # replay the search moves backwards, then land
    def land(self) -> None: ...
```

`FakeSpotter` returns a phone photo from `fixtures/drone/` so ground can run today.

**1. Connect, fly, land.** SDK over UDP. Take off, hold, land, and land again on a key or a timeout. Save one JPEG (`streamon`).

**2. Search.** `survey` yaws eight times by 45°, writes each JPEG under `fixtures/drone/`, and returns on the first frame Grok marks `found`. Otherwise it moves forward 40 cm, up to three times, and yaws again. Every move is appended to a list.

**3. Hover or go home.** On a find, `hover()` until the dog arrives or the slot timer fires, then `look_for_dog()`. On no find, `return_home()` replays that list backwards and lands. The dog must still be at the launch point for that landing to be next to it. Check the battery before takeoff. For the RSSI scan, the Tello only has to sit on the floor, powered on.

The plate on the dog's back is a flat plate that clears the LiDAR dome, with prop guards on, used only while the dog is stopped. If it is not mounted for the slot, launch from the floor beside the dog. Same search, same return.

Done when one flight either hovers on a find and saves a frame of the dog, or flies the search backwards and lands beside the launch point.

Leave the dog's walker, the prompt, and the log alone.

---

## 3 — Ground station

You own `patrol/contract.py`, `patrol/ground/`, and `demo/script.md`. You are the only caller. Publish the contract first. Until then the others copy the types from this file.

```text
spotter.survey(target)
    → grok.assess(survey)
        → if not send: log false alarm, return to patrol
        → if not survey.found: spotter.return_home(); log; stop
        → spotter.hover()                 # skipped for source "phone"
        → dog.home() or dog.walk_taught()
        → frame = spotter.look_for_dog()  # skipped for walk_taught
        → if not grok.sees_dog(frame): dog takes one more home step, look again
        → grok.describe(dog frame)
        → grok.compose_alert(...)
        → log, then spotter.land()       # beside the dog, which walked to the hover
```

`halt()` in every state calls `dog.halt()` then `spotter.land()`.

**1. Contract and rehearsal.** Write `patrol/contract.py`. Runner on `FakeSpotter`, a fake `assess` with `send: true`, a fake `sees_dog` that returns true, and `FakeDog`. One command, one log line.

**2. State machine.** `patrol → anomaly → assess → beacon → home → confirm → describe → alert → patrol`. `send: false` skips beacon, home, and confirm. `sees_dog` false returns to home for one more step, up to the step cap, then logs "not confirmed".

**3. Safety, phone, walker flag.** No motion unless the dog is standing. Cap sweep steps and cap the drone's forward steps at three. `PhoneSpotter.survey` sets `source: "phone"` and the runner calls `walk_taught`, never `hover`. Flag `walker=home|walk_taught`.

**4. Log and script.** One JSON line per event: time, source, target, send, reason, walker, steps, rssi, confirmed, arrival time, alert text. Print time-to-arrival, and how many sends "always send the dog" would have made against Grok's flag. Write `demo/script.md` for the two-minute pass.

Done when one command runs the chain on fakes, the same command runs it on the real dog, and the log shows both numbers.

Leave flight code, sport-mode commands, and prompt wording alone.

---

## 4 — Grok

You own `patrol/grok/` and `eval/results.md`. You read frames and return text. You never open a socket to the dog or the Tello. Voice calls the ground station, not the robots.

```python
def assess(survey: Survey) -> Assessment: ...
def sees_dog(frame_path: str) -> bool: ...
def describe(frame_path: str) -> str: ...
def compose_alert(assessment: Assessment, description: str) -> str: ...
```

**1. `assess`.** Call the API with `frame_path` and `target`. Return only `send`, `reason`, and `target`. Museum target: "a person or an abandoned object in a closed area". About ten labeled images in `fixtures/labels/`: person in a closed zone, abandoned object, empty room, ordinary visitor. Score `send` against those labels. One extra call with "side gate is open" shows a new sentence on the same function. `survey` calls this once per yaw step and stops on the first yes.

**2. `sees_dog` and the alert.** `sees_dog` is yes or no on the downward infrared frame. `describe` is two or three sentences on the dog's front camera. `compose_alert` is what was seen and why it was sent, short enough to read aloud.

**3. Voice.** English. Function calls into the ground station only: set target, start patrol, halt, "what do you see", "go toward the signal". Halt is immediate.

**4. Eval.** Freeze the prompt. Write `eval/results.md`: correct sends, missed anomalies, false alarms, against "always send". Tell ground the prompt version so the video and the number match.

Done when a new photo in `fixtures/` comes back as a valid `Assessment`, and the eval beats "always send" on false alarms.

Leave motion and the state machine alone.

---

## Who is free when

| When | Dog | Drone | Ground | Grok |
|---|---|---|---|---|
| Now | `FakeDog` | `FakeSpotter` from a phone photo | Contract, runner on fakes | `assess` and `sees_dog` on saved images |
| On the robot | Find the scanner: back board or phone. Write `scan.csv` | Tello powered, motors off, for that scan | — | — |
| Dog slot | Avoidance on, `home()` or `walk_taught`, one photo | — | Point the runner at the real dog | — |
| Drone slot | Dog stays at the launch point | One search: hover on a find, or fly the moves backwards and land | — | `assess` each frame during that flight |
| Last slot | Sweep while it hovers | Hover, look for the dog, land beside it | Record the pass, log on screen | Halt once by voice, read the alert |

If the scan is jagged or the Tello does not fly, the video is the phone spotter plus `walk_taught`. Same log. The plate on the dog's back is optional for that video.
