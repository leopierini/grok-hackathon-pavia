# Ground station — research and implementation guide

Research date: **4 November 2026**. The demo in this file was revised the same day after the team meeting. Intended reader: the teammate implementing the ground station.

**Active demo:** the drone scouts first. xAI Grok classifies a staged person from the drone camera. The dog stays still while the drone is moving. A Raspberry Pi on the dog measures the Tello's Wi-Fi signal, and Ground uses that only to choose a collision-checked step the dog app already marked safe. When the dog camera sees the same person, the dog finishes on its own vision. The demo goal is a current dog-to-person range plus a current drone horizontal offset. Landing is a separate recovery step.

The assignable work is Tasks 11–32 in [ground task.md](<ground task.md>). Tasks 01–10 stay the foundation. Message shapes are in [contracts/README.md](contracts/README.md). The demo itself is the next section of this file. [demo-v2.md](demo-v2.md) is only a pointer here.

The phone-photo, fixed-route, carried-drone flow in [plan.md](plan.md) is not this demo. Do not build `run_route` or `inspect` as the success path.

**Recommendation:** build a small Python application that runs one demonstration at a time, validates the v2 JSON messages, approves one bounded command at a time, keeps operator halt responsive, and records what actually happened. Start on fixtures from `contracts/examples/`. Connect hardware only after the same workflow passes its failure tests.

This document still holds the equipment research for the photographed **Unitree Go2 PRO** and **Tello EDU**. That research describes documented interfaces. It does not mean the firmware, the Pi radio path, directional Tello control, or the downward camera has passed a physical test. No robot was connected or commanded while preparing this guide.

**Current setup, confirmed by the user:** the back enclosure is a router, but its networking is not currently working. The available dog connection is a wired Ethernet cable to the command laptop, and that cable must remain attached throughout the run. The robot has its own onboard power and needs no separate external power cable for this setup; the precise battery/power arrangement is unconfirmed. Wireless operation is a possible future capability, not a dependency of the current demo.

**Connection support required by the user:** implement both **Ethernet and Wi-Fi connection options for the dog**, and **Wi-Fi for the drone**. Ethernet is the dog's current default and verified-setup target; dog Wi-Fi remains an alternate configuration to enable after the physical connection is working and tested. In Ethernet mode the tether stays attached for the whole run. Select one dog connection before starting a mission; keep the same DogPort interface for both options.

**Confirmed drone library:** the team will use **DJITelloPy**, with the exact import `from djitellopy import Tello`. This is a user-confirmed implementation choice, not an open library-selection question. The installed version and successful physical connection still need recording. Future user-provided setup details should update this guide, distinguishing confirmed choices from tested behavior and remaining unknowns.

## Demo specification and which JSON file goes to whom

Status: the active demo, 4 November 2026. Nothing in this section certifies that a physical flight, a Pi measurement, or directional Tello control has been tested.

### Confirmed meeting decisions

- The drone scouts first, observes a staged person, and helps direct the dog toward that person.
- Vision uses **xAI Grok**. Groq is a different service and is not selected.
- A **Raspberry Pi is mounted on top of the dog** and measures Wi-Fi RSSI from the dog's location.
- The dog is Go2 PRO. Ethernet is the connection available now and stays plugged in for an Ethernet run. Wi-Fi is a separate profile.
- The broken router in the back enclosure is not the Pi, and the Pi does not repair that router.
- The drone is Tello EDU, `from djitellopy import Tello`. Directional control is currently unreliable in the teammate's build. Treat that as an open fault. The SDK documents bounded moves, so the demo does not depend on uncontrolled random flight.
- The dog teammate owns the control app, LiDAR, SLAM or reactive avoidance, obstacle checks, and translating JSON into motion.
- "LAM" from the meeting means SLAM until that teammate names the real stack.
- Ground owns orchestration, message checks, command approval, deadlines, and logs.
- The team has not yet sent the final log list. The JSON files below are the proposed contract.

### What changed from the earlier demo

The old flow was a phone photo, a fixed dog route, then a carried drone if the dog's view was blocked. That is not the demo. The demo starts with the drone already in the air. Carrying the drone on the dog is not required. A phone image or a fixed route can exist only as a labeled fallback test. It does not prove RSSI guidance.

Tasks 01–10 stay as they are. They do not implement this loop. Tasks 11–32 do.

### Sequence

1. Operator selects the area, the staged-person target, the flight profile, dog transport, thresholds, and a clear landing patch. Connect the dog, the drone, the Pi, and xAI at the same time.
2. Exchange capability messages. Arm a camera, a radio, a map, or a movement mode only when that peer reports it.
3. Take off only with permission. Use a verified search profile, or a supervised flight, while Ground records observations. **4 m** is allowed only in a measured space with an approved profile. It is not the default.
4. Sample the latest usable drone image, initially once a second in simulation, with one Grok request in flight. Drop older images. The drone keeps its own flight watchdog while that request runs.
5. Vision returns a person box, a confidence, the frame id, and a semantic proposal. Ground keeps the track. It checks freshness and calibration before any reposition.
6. Move the drone only with one approved primitive. Then hold it still and start a new beacon epoch. The dog stays stopped while the drone is moving or the hold is uncertain.
7. The Pi sends RSSI windows for the exact drone BSSID, with time and dog pose. Ground may choose a short step toward a stronger signal only from candidates the dog planner marked safe.
8. The dog app checks LiDAR again and runs one leased command. After it stops, take the next window. Stay inside the Ethernet cable. Stop if blocked, noisy, lost, stale, or out of search budget.
9. Also sample the dog camera. When the same person is visible there, switch the dog to its own vision. RSSI stays in the log. It does not mean the dog has arrived.
10. The goal needs a current dog-to-person range and a current drone horizontal offset, for the same person. Stop the dog and hold the aircraft. Record the goal separately from landing.
11. Land with the drone owner's procedure and verify the aircraft. An unknown landing is still a fault after the goal.

### Feasibility checks

**Controlled movement.** Tello SDK 2.0 documents translations and yaw. DJITelloPy exposes those calls. The current failure needs diagnosis. Do not build pursuit out of uncontrolled drift. A search may pick among verified short primitives, with a seed, a region, a step cap, and local supervision. If that control is unavailable, use a supervised search and label it, or stay in simulation. [Manufacturer SDK](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)

**Downward camera.** DJITelloPy exposes `set_video_direction(Tello.CAMERA_DOWNWARD)` and describes a 320×240 grayscale downward stream. Test it on this drone at the proposed height. There is no rear camera. Switching cameras must flush old frames and increment the camera epoch. A front camera can see a person from far enough away. A nearby front view at 4 m can be a wall. [Camera API](https://djitellopy.readthedocs.io/en/latest/tello/#djitellopy.tello.Tello.set_video_direction)

**RSSI.** RSSI is received power at the Pi, not meters and not a bearing. The Pi must sit on the dog, name the drone BSSID, and include timestamps and dog poses. Laptop RSSI is not a substitute. Tello `wifi?` reports SNR, not dog-mounted RSSI. A stronger signal is a more negative number closer to zero. No signal is an empty sample list and a null median, never 0 dBm. Every drone move increments the beacon epoch and invalidates the old comparison. [SDK read commands](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)

**LiDAR, SLAM, and planning.** LiDAR observes. SLAM estimates pose and map. The local planner proposes a collision-checked step. Ground receives health, map identity, and safe candidate ids. Enabling Go2 avoidance does not create a building map. If only reactive avoidance exists, say so and limit the demo. [Driver](https://github.com/legion1581/unitree_webrtc_connect), [avoidance example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/data_channel/obstacles_avoid/obstacles_avoid.py)

**Proximity.** At about 4 m altitude the aircraft cannot also be within 1 m of a standing person's center in full 3D. Dog range and drone horizontal offset are different numbers. Obstacle clearance is a third number. A close obstacle is not the person. Missing range, calibration, track match, or a current operator confirmation stays unresolved. Do not invent the distance.

**Authority.** Grok receives real image bytes, not a path that exists only on one laptop. Vision returns a decision or a proposal. Ground writes the device command. The dog and drone apps enforce their own leases and stops. Model JSON never goes to the motors. Halt, an obstacle stop, an expired command, and link loss do not wait for another model call.

Simulation budgets to measure and then tune: image sample 1000 ms, one inference in flight, vision timeout 5000 ms, evidence age 3000 ms, ordinary command lease at most 500 ms. These are not certified safe values. Slow vision means hold or review.

Still untested, and each one blocks only its own real feature: directional drone moves, the downward camera, Pi model and data path, dog-app endpoint, navigation mode, proximity thresholds, venue height, and the team's final log list.

### Which JSON file to send to whom

Every example is synthetic (`simulated: true`). Hand the file so the teammate can see the exact fields. Do not fly or walk a robot by opening it.

The folder for all of them is:

`C:\Users\Ayush\Desktop\ground\contracts\examples\`

The human explanation that goes with each set is in `C:\Users\Ayush\Desktop\ground\contracts\`.

#### Drone teammate

Also send `C:\Users\Ayush\Desktop\ground\contracts\drone-to-ai.md` and `C:\Users\Ayush\Desktop\ground\contracts\ai-to-drone.md`.

| They send Ground this shape | File |
| --- | --- |
| What the aircraft can actually do | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-capabilities.json` |
| Flight state, height, beacon, and the current frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-observation.json` |
| Command accepted, not finished | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-accepted.json` |
| Command running | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-running.json` |
| Command finished | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-ack-completed.json` |
| Landing not verified | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-landing-unknown.json` |

| Ground sends them this shape | File |
| --- | --- |
| One approved move | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-command.json` |
| Hover | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-hover.json` |
| Land | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-drone-land.json` |

`C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-drone-proposal.json` is Grok's proposal to Ground. Do not give it to the drone as a command.

#### Dog-app teammate

Also send `C:\Users\Ayush\Desktop\ground\contracts\dog-to-ai.md` and `C:\Users\Ayush\Desktop\ground\contracts\ai-to-dog.md`.

| They send Ground this shape | File |
| --- | --- |
| What the dog can do | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-capabilities.json` |
| Pose, LiDAR, and navigation mode | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-observation.json` |
| Safe steps Ground is allowed to choose from | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-navigation-candidates.json` |
| Command accepted | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-accepted.json` |
| Command running | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-running.json` |
| Command finished and the dog stopped | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-ack-completed.json` |
| Command rejected, dog did not move | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-command-rejected.json` |

| Ground sends them this shape | File |
| --- | --- |
| One approved step | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-dog-command.json` |
| Halt | `C:\Users\Ayush\Desktop\ground\contracts\examples\ground-to-dog-halt.json` |

`C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-dog-proposal.json` is Grok's proposal to Ground. The dog app does not execute that file.

#### Vision teammate

Also send `C:\Users\Ayush\Desktop\ground\contracts\vision.md`.

| Ground sends them this shape | File |
| --- | --- |
| Drone frame to classify | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-vision-request.json` |
| Dog frame to classify | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-vision-request.json` |

| They send Ground this shape | File |
| --- | --- |
| Decision on the drone frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\drone-vision-decision.json` |
| Decision on the dog frame | `C:\Users\Ayush\Desktop\ground\contracts\examples\dog-vision-decision.json` |
| Proposal for the drone, still not a motor command | `C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-drone-proposal.json` |
| Proposal for the dog, still not a motor command | `C:\Users\Ayush\Desktop\ground\contracts\examples\ai-to-dog-proposal.json` |

The request JSON does not contain the image bytes. The `artifact://` reference has to be resolved to the real JPEG before the xAI call. The hash in the example is a placeholder.

#### Pi teammate

The Pi is on the dog. Also send `C:\Users\Ayush\Desktop\ground\contracts\rssi-and-navigation.md`.

| They send Ground this shape | File |
| --- | --- |
| What the Pi can measure | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-capabilities.json` |
| One RSSI window at the dog | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-rssi-window.json` |
| Pi is alive and the clock error | `C:\Users\Ayush\Desktop\ground\contracts\examples\pi-heartbeat.json` |

Ground does not send the Pi a motion command.

#### Logs Ground keeps

Also send everyone `C:\Users\Ayush\Desktop\ground\contracts\events-and-logs.md`. These are Ground's own records, not packets for a robot to execute.

| Record | File |
| --- | --- |
| Person first seen from the drone | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-drone_target_acquired.json` |
| Dog allowed to start homing | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-dog_dispatched.json` |
| Demo goal reached | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-demo_goal_reached.json` |
| Landing not verified | `C:\Users\Ayush\Desktop\ground\contracts\examples\event-landing_unverified.json` |
| Dog range and drone horizontal offset | `C:\Users\Ayush\Desktop\ground\contracts\examples\proximity-evidence.json` |
| Index of every example | `C:\Users\Ayush\Desktop\ground\contracts\examples-index.json` |
| All examples as separate lines, not one mission | `C:\Users\Ayush\Desktop\ground\contracts\example-events.jsonl` |

`example-events.jsonl` mixes success and failure examples. Do not replay it as a single flight.

## Reading route

- To understand the demo: the section above, then sections 1 and 8 of this file.
- To understand the messages: [contracts/README.md](contracts/README.md) and section 6.
- To understand the equipment: sections 2–4. The Pi on the dog is new relative to the photographs.
- To start coding: sections 7–11 and 17, plus Tasks 11–32 in [ground task.md](<ground task.md>).
- To integrate and rehearse: sections 12–16 and 18.
- To examine similar systems and original sources: sections 4 and 19.

## 1. Your responsibility

You own the application that makes these steps happen in the right order:

```text
connect dog, drone, Pi, and xAI; arm only reported capabilities
→ operator approves the venue and the flight profile
→ drone takes off or is flown in a supervised search
→ sample the latest drone frame; one Grok request at a time
→ if a staged person is visible, approve one bounded drone step
→ hold the drone still and start a new beacon epoch
→ read Pi RSSI at the dog and pick one safe dog step
→ when the dog camera sees the same person, switch off RSSI guidance
→ record dog range and drone horizontal offset separately
→ land and verify the aircraft; unknown landing stays a fault
```

You also own halt, deadlines, message validation, local logs, and integration. Those are part of the demo, not finishing touches.

| You implement | Another teammate implements |
| --- | --- |
| When a `drone.command` or `dog.command` is approved | DJITelloPy calls, the Go2 app, LiDAR, and local stops |
| Whether the beacon is stable enough for the dog to move | How the Pi reads RSSI and how the dog planner marks a step safe |
| Which frame is fresh enough to send to xAI | The xAI request, the model name, and the structured decision |
| Correlation of every JSON message into the journal | The bytes of the image and the motor conversion |
| Timing, operator halt, and the split between goal and landing | Vendor retries, command expiry on the device, and physical recovery |

The dog app parses Ground's JSON. It does not parse Grok's reply. The drone adapter does the same. A direction such as "left" from the model is image direction until a calibrated, allowlisted primitive exists.

The proposed flight height is 4 m, in a room tall enough for it. The hackathon room is not that room. 4 m is a profile value, not a default takeoff argument.

The first working version needs a terminal. A graphical dashboard, web API, ROS graph, fleet scheduler, and database are unnecessary.

## 2. What the photographs establish

### 2.1 Observations, inferences, and unknowns

| Item | Evidence from the supplied photographs | Consequence for Ground |
| --- | --- | --- |
| Dog edition | The close-up manufacturer's label explicitly reads **Unitree Go2 PRO**. | Configure and test the PRO integration path; stop treating the unit as an unknown AIR/PRO/EDU. |
| Drone edition | The airframe and packaging explicitly read **Tello EDU**. | Use the EDU SDK path, subject to actual firmware testing. |
| Drone camera | A forward-facing lens is visible. Underside positioning components are also visible. | The demo camera is the **downward** camera, not a rear camera. There is no rear camera. At about 4 m a nearby front view can be a wall; a front view from farther away can still see a person. Downward video is a capability to test, not a fact established by the photo. |
| Guards | Propeller guards are fitted in the photos. | Measure the guarded footprint for the carrier and flight area. |
| Back enclosure | The user confirms it is a router whose networking is currently not working. Its exact model is unknown. | Do not rely on it for wireless robot access or internet. Account for it physically when considering a launch pad. |
| Required tether in current Ethernet mode | The user confirms the currently available dog link is Ethernet, connected continuously throughout the run. Software must also support a future tested Wi-Fi option. | Apply cable checks to Ethernet runs; use connection-specific acceptance before enabling Wi-Fi runs. |
| External power | The user confirms no separate external power cable is needed; the robot has its own power. Battery details remain unknown. | Do not add a laptop-power or PoE requirement. Still check the robot's operational charge/readiness. |
| Launch mount | The photos show the antenna enclosure, not a demonstrated drone carrier/release mechanism. | Default the real launch tier to `floor` until a separate mount acceptance passes. |
| Firmware and API access | Not visible in a reliable software-version screen. | Still need the actual firmware, authorized account/key arrangement, and connection test. |

The enclosure's router identity and current networking failure are user-confirmed facts. Its future wireless availability remains unknown. This does not establish a general-purpose onboard computer, usable second Wi-Fi radio, or drone-control API. Do not add an SSH dependency or assume the router can control the drone or supply internet. The exact Ethernet endpoint, IP settings, and software service still need documenting and testing.

Do not search using the robot's full serial number or publish it in demo logs. The edition label is sufficient for public model research. Keep device-specific identifiers and any AES key in private configuration.

Useful original photo references on this PC:

- [Go2 PRO label](<C:/Users/Ayush/Downloads/WhatsApp Image 2026-11-04 at 13.00.15 (1).jpeg>).
- [Back enclosure and cabling](<C:/Users/Ayush/Downloads/WhatsApp Image 2026-11-04 at 13.00.14.jpeg>).
- [Tello EDU packaging](<C:/Users/Ayush/Downloads/WhatsApp Image 2026-11-04 at 13.00.04 (1).jpeg>).
- [Tello forward camera and guards](<C:/Users/Ayush/Downloads/WhatsApp Image 2026-11-04 at 12.59.58.jpeg>).

These paths are local research references, not portable project fixtures. Copy only appropriate images into a project evidence folder if the team actually needs them; retain provenance and avoid unnecessary personal information.

### 2.2 Corrections to carry into implementation

1. **Go2 PRO is confirmed; developer capabilities are not.** Do not select EDU-only SDK examples merely because the robot is a Go2.
2. **There is already hardware on the back.** The mounting plan must account for antennas, cables, vents, sensors, and retention. The old flat-plate sketch is not an installation plan.
3. **Use the EDU's actual specifications.** Ryze lists 87 g including propellers and battery, 2.4 GHz Wi-Fi, and a 720p live view. The earlier approximate 80 g should not be the payload specification. Guards and carrier add weight. A saved video frame should not be described as a full-resolution 5 MP still just because the product supports that photo mode. [Ryze specifications](https://www.ryzerobotics.com/tello-edu/specs)
4. **Keep the AP network as the baseline.** Current DJITelloPy source mentions EDU station-mode video through SDK 3. Treat that as firmware-dependent, not universally unavailable. Retain the dedicated AP link until an alternative passes testing. [Streaming implementation](https://github.com/damiafuentes/DJITelloPy/blob/master/djitellopy/tello.py)

## 3. Exact-model connection and instruction research

### 3.1 Go2 PRO: which integration to use

Unitree's official comparison distinguishes PRO from EDU for secondary development. A PRO label does not establish access to the official EDU development stack. The sensible first route for this project is the community `unitree_webrtc_connect` driver, which explicitly lists Go2 PRO support. This is an upstream support claim that still needs verification on this unit. [Official comparison](https://www.unitree.com/go2/), [driver README](https://github.com/legion1581/unitree_webrtc_connect/blob/master/README.md)

The driver uses WebRTC, the communication path used by the consumer app. Your dog teammate should test it locally, without firmware modification. Ground imports only the agreed `create_dog()` factory.

| Connection mode | How it works | Recommendation |
| --- | --- | --- |
| `LocalSTA` | Driver's LAN/IP connection path; use the actual reachable dog IP or supported discovery. | Test the current Ethernet path first; also configure this path for a shared Wi-Fi LAN if supported and tested later. The mode name does not prove service availability over either interface. |
| `LocalAP` | Laptop joins the dog's own access point. The inspected driver assigns robot address `192.168.12.1` in this mode. | Support as an alternate dog Wi-Fi configuration, but do not enable a real run until this unit's wireless connection passes testing. |
| `Remote` | Uses cloud-mediated signaling/relay and account setup. | Avoid for the first indoor demo; adds dependencies without solving local coordination. |

Those mode names and the AP address come from the [driver implementation](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/webrtc_driver.py). `LocalSTA` addresses in example code are examples, not the museum dog's address. Do not copy `192.168.123.18` or another sample IP blindly.

The current README documents a per-device AES requirement for Go2 firmware 1.1.15 and later. The dog owner must record the actual firmware and arrange authorized key retrieval with staff if needed. Ground should receive a configured adapter, not implement cloud authentication. [Firmware/authentication documentation](https://github.com/legion1581/unitree_webrtc_connect/blob/master/README.md)

Connection-only example for understanding the dog adapter; it performs no posture or walking command:

```python
import os
from unitree_webrtc_connect import (
    UnitreeWebRTCConnection,
    WebRTCConnectionMethod,
)

async def open_local_dog_link():
    options = {"ip": os.environ["UNITREE_ROBOT_IP"]}
    device_key = os.environ.get("UNITREE_AES_128_KEY")
    if device_key:
        options["aes_128_key"] = device_key
    link = UnitreeWebRTCConnection(WebRTCConnectionMethod.LocalSTA, **options)
    await link.connect()
    return link
```

This belongs inside `patrol/dog`, not inside Ground. The environment variable names above are a proposed local configuration convention; the dog adapter must document its final names in its handoff. Connection creation is not equivalent to successful camera, state, avoidance, or stop verification.

For the current Ethernet setup, first establish the laptop interface, dog-side endpoint, compatible IP/subnet settings, and reachable service with the dog owner/staff. Then test the configured adapter's connection, telemetry, camera, and halt over that same cable. Ethernet is a physical transport; it does not automatically imply WebRTC availability, EDU SDK access, SSH, internet access, or a particular default IP. If the LAN WebRTC path is unavailable, document the blocker and keep Ground on stubs while the dog owner verifies an alternative behind DogPort.

### 3.2 Go2 PRO: how instructions reach it

The inspected upstream constants identify the sport request topic and commands below. Use imported constants in device code; Ground must not hardcode numeric IDs. Firmware/control mode still determines whether the command works. [Upstream constants](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/constants.py)

| Device-level concept | Upstream name / identifier | Ground-level operation |
| --- | --- | --- |
| Sport request channel | `RTC_TOPIC["SPORT_MOD"]`, `rt/api/sport/request` | Hidden inside DogPort |
| Stand | `SPORT_CMD["StandUp"]`, 1004 | Dog app, before a leased step |
| Balanced stand | `SPORT_CMD["BalanceStand"]`, 1002 | Dog app, if that stance is the tested one |
| Stop walking | `SPORT_CMD["StopMove"]`, 1003 | One ingredient of the app's halt |
| Motion request | `SPORT_CMD["Move"]`, 1008 | Inside the dog app. Ground sends `dog.command`, not this id |
| Avoidance service | `RTC_TOPIC["OBSTACLES_AVOID"]` | The app's local check. Ground only sees the safe-candidate list |

The upstream avoidance example enables and queries the service, then drives through simulated wireless-controller messages. This is important: do not assume every sport movement command passes through avoidance merely because avoidance is enabled. The dog owner should use the demonstrated path and prove its effect with staff. [Avoidance example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/data_channel/obstacles_avoid/obstacles_avoid.py)

The example's joystick values are normalized control inputs, not meters or a safe speed prescription. Its terminal input uses Unix-specific modules. Borrow the message/control pattern, not its keyboard loop or movement magnitudes for your Windows application.

The driver's video class exposes video-channel switching and a track callback. Dog's adapter should receive and timestamp frames, decode/save JPEGs, and return the frozen `Frame` object. Ground should never manage an aiortc track or decode the stream itself. [Video implementation](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/webrtc_video.py)

A useful command-readiness checklist for the dog handoff is:

- Can the actual PRO connect in the chosen mode and stay connected?
- Can it supply a newly captured camera frame?
- What telemetry establishes standing and stationary state?
- Does the selected motion path still respect the tested avoidance behavior?
- What exactly does halt send, and how long does stopping take?
- What happens if command traffic stops or the connection drops?
- Does a timed-out command leave the physical state uncertain?

There is no researched `go_to` for a room name on this unit. The demo does not use one. The dog app accepts a short `dog.command` in `dog/base_link` and rechecks LiDAR before it moves. Ground does not send a building route.

### 3.3 Tello EDU: connection and SDK path

Use the team's confirmed library, **DJITelloPy** (`from djitellopy import Tello`), inside the drone teammate's adapter. Ground sends `drone.command` and does not create a second Tello client. The drone owner records the tested `djitellopy` version. Choosing the library does not establish that connection, video, directional motion, downward video, or landing have passed.

The SDK 2.0 guide specifies the aircraft AP address `192.168.10.1`; commands/replies use UDP 8889, state uses 8890, and video uses 11111. Enter SDK mode with `command`; start video with `streamon`. Network and video setup belong to the drone adapter. [Manufacturer SDK guide](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)

Connection-only diagnostic example, to be run by the drone owner in isolation:

```python
from djitellopy import Tello

def inspect_tello_connection():
    aircraft = Tello(host="192.168.10.1", retry_count=1)
    aircraft.connect()
    return aircraft, aircraft.get_battery()
```

This synchronous diagnostic does not take off. Run it outside Ground's event loop and only when the production adapter is disconnected. Verify `retry_count=1` against the pinned library.

| SDK instruction | Typical library operation | Meaning / project use |
| --- | --- | --- |
| `command` | `connect()` | Enter SDK mode; no takeoff. |
| `battery?` | `get_battery()` | Battery read; flight reserve remains a tested profile setting. |
| `streamon` | `streamon()` / frame reader | Video for a fresh inspection JPEG. |
| `takeoff` | `takeoff()` | Starts real flight; adapter/profile only. |
| `forward`, `up`, other translations | Corresponding movement methods | Relative centimeters, not a building coordinate or absolute floor height. |
| `cw` / `ccw` | Rotation methods | Relative degrees. |
| `stop` | Profile's hover operation | Hover, not land. |
| `land` | `land()` | Descend at current position; profile must first clear the dog. |
| `emergency` | `emergency()` | Motor cut; not the normal Ground halt path. |

SDK 2.0 translations have a 20–500 cm range; it also documents automatic landing after 15 seconds without commands. The drone owner must implement compatible command supervision during flight. Ground must not send its own competing keepalives. [Command definitions and timeout behavior](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)

### 3.4 Two SDK traps your integration tests must catch

**Hidden retries.** DJITelloPy's control-command loop uses `retry_count`, default 3, with a separate takeoff timeout. Test that an ambiguous takeoff causes one wire attempt, including SDK behavior. Counting Ground calls alone is insufficient. [Command implementation](https://github.com/damiafuentes/DJITelloPy/blob/master/djitellopy/tello.py)

**Software flight flags.** `is_flying` changes after successful takeoff/land calls; it is not independent physical evidence. A lost reply can leave actual flight uncertain. Require documented evidence for every reported flight state. [Flight methods](https://github.com/damiafuentes/DJITelloPy/blob/master/djitellopy/tello.py)

If the installed SDK cannot satisfy the profile's bounded abort behavior, keep real flight disabled and use the fake. Ground cannot fix an uninterruptible aircraft driver by wrapping it in another task.

### 3.5 What to do with the existing back enclosure

The router is currently unusable for networking, and Ethernet to the laptop must stay connected. Record these facts now. Ask staff only for the remaining details needed for the wired setup, recorded in `handoff/ground.md`:

| Needed fact | Why it matters |
| --- | --- |
| Exact Ethernet endpoint and laptop adapter | Identify the port/cable path actually used for dog control. |
| Dog IP, subnet, and any required laptop IP settings | Establish a reproducible wired connection without guessing example addresses. |
| Cable length, attachment/strain relief, and approved routing | Bound the route and keep the tether clear of legs, furniture, propellers, and landing area. |
| Router model and repair status, if already known | Record future options without making repair a prerequisite for Ground development. |
| Separate laptop internet connection | Grok needs a working uplink; do not count on the broken router or dog Ethernet to provide it. |
| Whether any accessible computer already runs a robot service | Avoid a second simultaneous control owner. |
| Whether removal/extra attachment is permitted | Determine whether pad/carried launch is even available for this event. |

Use the answers as configuration. Do not make Ground depend on shell access to this unknown device. The broken router is not the RSSI receiver.

The RSSI receiver is a **Raspberry Pi mounted on the dog**. It measures the Tello beacon from the dog's position and sends `rssi.window` messages to Ground. The Pi's model, radio, power, clock sync, and the path that carries those messages back to the laptop are still unrecorded. A Pi joined to the Tello access point does not automatically have a route to the laptop. Record that path as wired, USB, or a second radio before arming RSSI homing. See [contracts/rssi-and-navigation.md](contracts/rssi-and-navigation.md).

## 4. Similar projects: what to learn and what to leave out

These are primary project repositories or author/manufacturer documentation. They were inspected as design references, not executed against this hardware. Similarity does not prove compatibility.

| Project / original source | Relevant observed pattern | How we should use it |
| --- | --- | --- |
| [Unitree WebRTC UI](https://github.com/legion1581/unitree_ui) | Go2 connection modes, camera, operator controls, and explicit robot/error status. | Useful reference for connection diagnostics and status presentation. Keep our terminal small; do not build its full web/3D interface. |
| [Go2 API, current monorepo](https://github.com/carlosvts/go2/tree/main/api) | A central WebRTC owner exposes bounded operations; application health and robot connection state are separate. Its README distinguishes sent commands from completion. | Keep one robot-link owner and validate returned evidence. We can implement this boundary with Python calls; an HTTP service is not required. The old `go2-api` repo is archived/moved. |
| [Go2 Agentic Robotics Control](https://github.com/jrcichra/agentic_unitree_go2) | Combines a terminal, model integration, and an offline mock mode. | Build a convincing mock workflow early. Do not adopt its broad model toolset or assume its claimed behaviors were tested on this PRO. |
| [Open-RMF fleet adapter template](https://github.com/open-rmf/fleet_adapter_template) and [demos](https://github.com/open-rmf/rmf_demos) | Robot-specific API wrappers sit below coordination; heterogeneous robots can participate through explicit integration boundaries. | Preserve DogPort/DronePort. Leave fleet bidding, maps, traffic scheduling, ROS, and simulation installation out of this deadline. |
| [Spot Mission Service](https://dev.bostondynamics.com/docs/concepts/autonomy/missions_service.html) | High-level actions, state conditions, and operator prompts are separate mission components. | Implement explicit stages and confirmations. These concepts transfer; Spot RPCs and GraphNav capabilities do not transfer to Go2. |
| [Spot Lease Service](https://dev.bostondynamics.com/docs/concepts/lease_service) and [Keepalive](https://dev.bostondynamics.com/docs/concepts/keepalive_service.html) | Control ownership and communications-loss policy are distinct mechanisms. | Use a single local command owner and require tested device-side stop behavior. Our local flag is not a hardware-enforced Spot lease. |
| [QGroundControl flight toolbar](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/fly_view/fly_view_toolbar.html) | Readiness, armed, flying, landing, and communications loss are distinct operator states. | Show mission state and physical state separately. A green “connected” indicator must not imply flight readiness. QGC is a UI reference, not a Tello driver. |
| [BehaviorTree.CPP asynchronous actions](https://www.behaviortree.dev/docs/tutorial-basics/tutorial_04_sequence/) | Long-running actions must yield and support halt; request completion is a separate condition. | Use responsive async stages with explicit results. A plain finite-state workflow is sufficient here; a behavior-tree engine is optional future work. |
| [MAVSDK Python example](https://github.com/mavlink/MAVSDK-Python/blob/main/examples/takeoff_and_land.py) and [MAVLink command protocol](https://mavlink.io/en/services/command.html) | Connection/health checks precede action, while acknowledgements and completion are distinguished. | Learn the lifecycle. Do not use MAVSDK for Tello: this project's aircraft uses its own text/UDP SDK. Do not copy MAVLink's resend policy into non-idempotent Tello motion. |
| [SayCan research project](https://say-can.github.io/) | Language-level proposals are grounded in available robot skills. | Offer Grok a tiny decision vocabulary and let deterministic checks decide whether a requested skill can run. We are not reproducing SayCan's learned affordance models. |

My design inference from these projects: the most valuable work in Ground is a dependable boundary between **requested behavior**, **permitted behavior**, **command execution**, and **observed outcome**. A larger interface or more model tools would not remove that requirement.

### 4.1 Example of the distinction

```text
Grok: “inspect”                  A recommendation
Ground: all interlocks pass     Permission for one specific profile
Drone: takeoff command sent     An execution attempt
Drone: image captured           An evidence event
Drone: floor landing verified   A physical completion claim
Ground: report saved            A mission outcome
```

Do not compress these into `success=True` after the first acknowledgement. MAVLink explicitly documents that accepted does not necessarily mean completed; the same distinction is useful as a design rule here, without assuming identical protocol semantics. [Command lifecycle](https://mavlink.io/en/services/command.html)

## 5. Recommended application structure

### 5.1 Runtime layout

```text
                         terminal input
                               |
                         StationController
                          /      |       \
             normal mission   safety     status snapshots
                coroutine    supervisor
                  |             |
          DogPort / DronePort / ReasonerPort
                  |
             event journal → local files
```

Use one `asyncio` event loop and one active mission coroutine. Keep separate tasks for terminal input, the safety/recovery path, journal writing, and a modest status monitor. The other teammates' adapters own their transport workers and video processing.

The normal mission coroutine can be readable sequential code with branches. You do not need a message broker or a fully generic workflow engine. Concurrency is required for operator control, vision timing, and supervision. The dog does not walk while the drone is repositioning. One approved device command is in flight at a time.

### 5.2 Files to create

All paths below are in the future Robot Patrol source root. They describe your owned implementation, not files already generated by this research.

```text
patrol/ground/
  __init__.py
  __main__.py           parse arguments, load config, select adapters, run app
  app.py                StationController; one mission and lifecycle ownership
  mission.py            drone-first demo workflow
  state.py              internal enums, session state, command validation
  safety.py             halt latch, stop/abort task, recovery decisions
  console.py            prompt_toolkit input and operator messages
  config.py             JSON loading, path resolution, validation
  evidence.py           frame/file/metadata validation
  journal.py            events.jsonl writer and summary publication
  metrics.py            timing and saved-evaluation presentation
  selftest.py           independent stub-run entry point
  testing/
    __init__.py
    stubs.py            private implementations of the frozen Protocols
tests/ground/
  test_messages.py
  test_vision_schedule.py
  test_commands.py
  test_rssi.py
  test_proximity.py
  test_halt.py
  test_logging.py
fixtures/ground/
  contracts/          copies of the synthetic JSON examples
  scenarios.json
config/ground.example.json
requirements/ground.txt
handoff/ground.md
demo/script.md
```

Begin with `state.py`, `mission.py`, private stubs, and a tiny selftest. Split additional files when their responsibilities exist. This tree is a guide, not a requirement to create fifteen empty modules on day one.

### 5.3 Dependencies

| Need | Choice | Reason |
| --- | --- | --- |
| CLI flags | Standard-library `argparse` | Adequate for the agreed command. |
| Async execution | Python 3.11 `asyncio` | Matches the contract and asynchronous dog/reasoner paths. |
| Interactive input | `prompt_toolkit` 3.x, pinned after testing | Awaitable prompts and terminal-friendly output. |
| Config/types | `json`, `dataclasses`, explicit validators | Avoid a second schema system for frozen contract objects. |
| JPEG sanity checks | Pillow, pinned after testing | Validate that an alleged JPEG can actually be decoded. |
| Testing | `pytest`; optionally `pytest-asyncio` | Tests run without hardware or keys. |
| Storage | Local JSON Lines and JSON | Simple, inspectable artifacts for this demo. |

Ground must not require `djitellopy`, aiortc, `unitree_webrtc_connect`, or `xai-sdk` in its private-stub selftest. The combined real installation will aggregate the owners' tested dependency pins later.

Use normal CPython on Windows for your offline development. Choose the actual real-run OS jointly with the dog/drone owners after installation tests; the Go2 driver's dependencies include native audio/video components and its documented install path is Linux-oriented. “Python package installed” is not proof that the real adapter works on this Windows laptop. [Driver dependency manifest](https://github.com/legion1581/unitree_webrtc_connect/blob/master/pyproject.toml)

## 6. How you consume the interfaces

The demo wire contract is protocol **2.0-draft** in [contracts/message.schema.json](contracts/message.schema.json). Tasks 01–10 may still materialize the older plan.md section 6 types for the foundation. Do not treat those v1 methods as the demo. A v2 mission does not call `run_route` or `inspect`.

Factory creation has no network or motion side effect. Private fixtures implement the same message envelopes, so early testing needs nobody else's package and no API key.

| Peer | Ground accepts | Ground sends |
| --- | --- | --- |
| Drone | `capabilities.report`, `drone.observation`, `command.ack` | `drone.command` for one allowlisted primitive: takeoff, search step, track step, hover, or land |
| Dog app | `capabilities.report`, `dog.observation`, `navigation.candidates`, `command.ack` | `dog.command` for stand, a leased `move_local` or `turn`, or halt |
| Pi | `rssi.window`, `heartbeat` | The beacon id and epoch to measure. Ground does not scan Wi-Fi itself |
| Vision | `vision.decision` | `vision.request` plus the resolved image bytes |

Grok returns a scene decision and, at most, a `motion.proposal`. Ground writes the device command. The examples to share are listed in [contracts/README.md](contracts/README.md). `contracts/examples/ai-to-dog-proposal.json` is not the packet the dog executes. `contracts/examples/ground-to-dog-command.json` is.

### 6.1 What the messages still cannot prove

An observation timestamp is the sender's clock. Ground also records local arrival time. Clock error beyond the evidence budget blocks ordinary motion.

`accepted` on a command acknowledgement means accepted, not finished. A finished track step can leave the aircraft airborne. `flight_state` unknown, or the landing example in `contracts/examples/drone-landing-unknown.json`, keeps a recovery fault.

There is no public proof that `close()` has stopped every vendor worker. If the adapter handoff cannot show that, keep the device faulted instead of opening a second client.

Directional Tello control is currently unreliable in the teammate's build. The SDK documents bounded translations, so record that as an open control fault. Arm `controlled_motion` only when their capability report says it is true and validated. Until then the search is supervised, or it stays in simulation. Do not replace that fault with unbounded random motion.

If downward video, SLAM, or the Pi path is absent from the capability report, leave that feature disarmed. A missing report is not a hidden success.

## 7. State and lifecycle design

### 7.1 Keep three kinds of state separate

| Kind | Example | Source of truth |
| --- | --- | --- |
| Mission phase | `SCOUT`, `HOLD`, `HOME`, `LAND` | Ground workflow |
| Physical state | dog stationary; drone grounded, airborne, or unknown; beacon stable or moving | Device messages and physical acceptance |
| Demo result | goal reached, unresolved, aborted, failed, recovery required | Current proximity evidence and landing evidence, stored separately |

The goal can be reached while the landing is still unknown. The terminal keeps the recovery lock until the aircraft is verified. A goal event is not permission to start another run.

Use these phase names for the v2 demo:

`IDLE`, `CONNECT`, `SCOUT`, `TRACK`, `HOLD`, `HOME`, `DOG_VISION`, `PROXIMITY`, `LAND`, `DONE`, `ABORTED`, `FAULT`.

### 7.2 Transition table

| Phase | Operation / accepted event | Successful next step | Other outcome |
| --- | --- | --- | --- |
| `IDLE` | Select profile, transport, and area; arm | `CONNECT` | Missing profile or real-mode without arm stays idle. |
| `CONNECT` | Capability reports for dog, drone, and Pi | `SCOUT` | A required feature reported false stays disarmed. |
| `SCOUT` | Fresh drone frame and a Grok decision | Person visible → `TRACK` | Not visible keeps searching inside the budget; uncertain → review. |
| `TRACK` | One approved drone primitive and its acknowledgements | Stable hold → `HOLD` | Control unavailable → supervised search or stop. Unknown execution → `FAULT`. |
| `HOLD` | New beacon epoch, drone still, dog still | Comparable Pi window → `HOME` | Moving or expired hold keeps the dog stopped. |
| `HOME` | One safe candidate and one leased dog step | Dog camera acquires the same person → `DOG_VISION` | Blocked, noisy, or no progress → stop and review. |
| `DOG_VISION` | Dog frame and a matching track | Approach on vision → `PROXIMITY` | Wrong track or multiple people → review. |
| `PROXIMITY` | Dog range and drone horizontal offset, both current | `LAND` | Either side missing → unresolved. RSSI strength is not arrival. |
| `LAND` | Land command and a grounded acknowledgement | `DONE` | Unknown landing stays `FAULT` even if the goal was reached. |
| Any phase | Halt, link loss, stale evidence, or lease expiry | Safety commands only | `ABORTED` or `FAULT`. A late Grok reply cannot clear it. |

Unknown hardware state has priority over the next ordinary phase. A late callback cannot overwrite `FAULT` with `DONE`.

### 7.3 Internal session fields

These are Ground internals; they do not add fields to the shared dataclasses:

| Field | Purpose |
| --- | --- |
| `mission_id` | One id for this demonstration. |
| `epoch` | Generation number invalidated on halt/reset. Old commands die with it. |
| `beacon_epoch` | Advances when the drone moves. Old RSSI windows cannot be compared after that. |
| `camera_epoch` | Advances when the camera, resolution, or calibration changes. |
| `track_id` | Ground's id for the staged person. The model does not assign a durable identity. |
| `state` | Current phase name from the table above. |
| `armed_features` | Only the flags the capability reports marked true and validated. |
| `halt_latched` | Blocks ordinary actions immediately, without waiting for Grok. |
| `recovery_required` | Stays true while landing or another physical state is unknown. |
| `goal_reached` | True only from Task 26's proximity checks. Independent of landing. |
| `active_command_id` | The one dog or drone command waiting for acknowledgements. |
| monotonic start/deadline fields | Duration measurement and evidence budgets. |

Every transition checks that the session is still current, its epoch matches, cancellation is not latched, and the expected prior phase still applies. No normal transition clears a recovery lock.

## 8. Mission algorithm

### 8.1 Drone-first pseudocode

This is design pseudocode, not a complete drop-in implementation. `stage()` is the guarded, deadline-aware runner in section 9. Message names match `contracts/`.

```text
run_demo(session):
    admit capability reports; arm only validated features
    require operator arm before any real motion
    require the selected dog transport and an explicit Pi data path

    drone observes; if controlled_motion is false, stay supervised or simulated
    loop SCOUT until budget, halt, or a fresh person_visible on the drone camera:
        keep the newest frame; drop frames older than the evidence budget
        one vision.request in flight; ignore a late decision
        a proposal is stored, not sent to the aircraft

    if a calibrated primitive exists:
        send one drone.command and wait for its own acknowledgements
        a timeout queries that command id; it does not send a second takeoff
    else:
        record supervised search and do not invent a random move

    require flight_state airborne and beacon hold_state stable
    advance beacon_epoch after any drone reposition
    dog stays stopped until that new hold is valid

    loop HOME until dog vision, stop, or budget:
        accept an rssi.window only for this BSSID and beacon_epoch
        choose one candidate_id from the dog's current safe list
        send one dog.command with lease_ms at most 500
        wait until the dog ack says verified and stationary
        a blocked list, noisy window, or flat signal stops the loop

    when two fresh dog frames show the same track_id, switch to DOG_VISION
    RSSI remains in the log as supporting evidence

    goal_reached only if dog range and drone horizontal offset are both current
    a 4 m altitude does not also count as a 1 m 3D distance to the person
    then send land as its own command
    unknown landing sets recovery_required and does not erase the goal
```

Every early finish still runs lifecycle cleanup. A cancellation or a bad message must not fall through into the next move. Do not catch every exception and continue with a default distance of zero.

### 8.2 Sequence

```mermaid
sequenceDiagram
    participant O as Operator
    participant S as Ground
    participant V as xAI vision
    participant T as Drone
    participant P as Pi on dog
    participant D as Dog app
    O->>S: Arm profile, transport, and area
    T-->>S: Observation, beacon, frame
    S->>V: vision.request with image bytes
    V-->>S: person_visible and a proposal
    S->>T: one drone.command primitive
    T-->>S: accepted, running, completed
    Note over S: New beacon epoch; dog still stopped
    P-->>S: rssi.window for that epoch
    D-->>S: safe navigation.candidates
    S->>D: one dog.command
    D-->>S: verified stationary ack
    D-->>S: Dog frame
    S->>V: dog_acquire request
    V-->>S: same track visible
    S-->>O: Goal only if range and horizontal offset are current
    S->>T: land
    T-->>S: grounded, or unknown with recovery still required
```

## 9. Async execution, halt, and deadlines

### 9.1 The execution model to use

Keep the normal workflow in one coroutine so its ordering is easy to inspect. Run input and safety supervision separately. Device adapters must yield while awaiting I/O, and any synchronous vendor calls must be handled in their own bounded worker path.

Python task cancellation is cooperative, and `wait_for()` can wait beyond its nominal timeout while cancellation completes. Keep references to tasks and explicitly account for late/pending work. A TaskGroup also waits for its tasks to end; it is not a hardware stop mechanism. [Python 3.11 task/cancellation semantics](https://docs.python.org/3.11/library/asyncio-task.html)

Do not put a route or flight behind a shared application lock that `halt()` must acquire. Use short synchronous state/permission checks; never hold a normal-operation lock across an SDK await.

### 9.2 Stage runner: required behavior

For every stage:

1. Validate the current session/epoch and ordinary-action permission before constructing its operation.
2. Allocate a unique stage token; record monotonic and UTC start times.
3. Create a stage-specific RunContext sharing the mission's cancellation event.
4. Create/register the operation task. Give it a descriptive name.
5. Wait for operation completion, halt, or the stage deadline without blocking the console.
6. After completion, recheck session/epoch/cancel before accepting the result or advancing state.
7. Validate the returned contract object and record completion or error.
8. On timeout/halt, latch cancellation, request physical stop/abort, and keep track of unfinished work. Do not start another ordinary stage.

Use `asyncio.wait()` with task references and a timeout when you need to observe pending work without automatically waiting for cancellation to finish. Dispose of your own unused timer/waiter tasks. A pending vendor worker stays a recovery condition even if the outer coroutine was cancelled.

### 9.3 Deadline construction

The shared contract's deadline uses `time.monotonic()`. Use that clock consistently for RunContext and elapsed measurements. For asyncio wait durations, calculate remaining seconds from that same clock; do not assume an arbitrary injected clock and the event loop clock share a numeric origin.

This helper is ordinary Python 3.11 code after the frozen contract is materialized:

```python
import time
from threading import Event
from patrol.contract import RunContext

def context_for_stage(
    mission_id: str,
    mission_deadline: float,
    stage_limit_s: float,
    cancellation: Event,
) -> RunContext:
    return RunContext(
        mission_id=mission_id,
        deadline_monotonic=min(
            mission_deadline, time.monotonic() + stage_limit_s
        ),
        cancel=cancellation,
    )
```

Initial demo budgets are in section 11.4: 1000 ms sampling, 5000 ms vision timeout, 3000 ms evidence age, and at most 500 ms for an ordinary command lease. Takeoff and land keep their own deadlines. The whole run needs a configured cap. These are development defaults, not physical safety limits.

The aircraft's normal flight budget and its abort budget are separate. A takeoff response timeout can consume much of a 30-second flight allocation; this must be reconciled with the drone owner's tested SDK settings before enabling real flight. Extending the whole mission timeout does not make an unbounded aircraft command safe.

### 9.4 Halt path

Implement one synchronous `request_halt(reason)` entry point on StationController that does the following without awaiting disk or device I/O:

1. Set `halt_latched=True` and the mission's thread-safe cancellation Event.
2. Invalidate the active epoch and outstanding operator confirmations.
3. Block all new ordinary actions and preserve/set the flight lock as needed.
4. Create one retained safety-supervisor task if none already exists.
5. Display that halt has been requested; actual completion remains pending.

The supervisor promptly **starts both** `dog.halt()` and `drone.land()` as separate operations. It does not await the dog before requesting the aircraft abort. It collects both results/errors, reads status where possible, and decides whether recovery remains required.

Do not use a fail-fast TaskGroup that lets one stop error cancel the other stop attempt. Each attempt must have independent error handling. A bounded observation wait can report pending stop work while keeping the supervisor and task references alive.

Repeated halt joins/reports the same safety operation; it must not create competing landing sequences. The drone adapter arbitrates abort and the pending `inspect()` cleanup internally.

The no-new-step rule applies to normal mission steps. Approved clearance, controlled landing, and stop cleanup can still execute after cancellation under separate safety limits. Do not reuse an expired RunContext for recovery.

### 9.5 What cancelling a thread does not do

A synchronous SDK method already running in a thread does not stop merely because its Future is cancelled. Python's executor documentation distinguishes cancelling queued work from running work. The device adapter must check its cancellation token between bounded calls and stop producing later commands. [Executor cancellation behavior](https://docs.python.org/3.11/library/concurrent.futures.html)

If the adapter remains stuck, show `FAULT`, keep the controls locked, and use the documented operator recovery procedure. Do not create a second adapter to “try again” while the first may still issue commands.

### 9.6 Status supervision

Take modest periodic status snapshots, such as one per second initially, only through the adapters. They must serialize access to their transport safely. Polling must not starve their abort channel.

- Before a dog step: standing, stationary, and avoidance are true, the beacon hold is stable, and the candidate is still in the current safe list.
- During a dog step: one command id is active. Loss of connection, avoidance, or the beacon hold requests halt.
- While the drone is moving: the dog stays stopped. A new beacon epoch is required before the next RSSI comparison.
- Before land: the goal record and the landing record are updated separately.
- A snapshot that is older than the evidence budget is not current, even if its numbers look good.

Blocking work and network logging can stall an event loop. Use debug mode during development to expose slow callbacks and unhandled task errors. [Asyncio development guidance](https://docs.python.org/3.11/library/asyncio-dev.html)

## 10. Operator console and permissions

### 10.1 Commands and scope

| Command | Valid context | Effect |
| --- | --- | --- |
| `status` | Any time | Show phase, armed features, beacon epoch, active command, goal, and landing. |
| `arm` | Idle, capabilities loaded, no fault | Permit this run. Does not move anything. Real motion requires arm. |
| `start` | Armed, not already running | Begin scout. Reject a second start. |
| `supervised` | Scout, and only when controlled motion is disarmed | Label the search as operator-flown. Does not enable autonomous steps. |
| `halt` | Any time | Latch immediately. Dog halt and drone hover or land follow the profile, without waiting for Grok. |
| `reset` | Goal and landing both resolved, or the operator supplies a recovery token after a fault | New epoch, disarmed. |
| `quit` / EOF | Any time | Halt and cleanup, then exit. |

Do not queue a confirmation for a later phase. Halt and reset invalidate old command ids. Ethernet stays connected for an Ethernet run; no console command disconnects it so the dog can walk farther.

### 10.2 Windows-compatible input

Use `PromptSession.prompt_async()` and `patch_stdout()` so operator input can coexist with status output. Catch prompt `KeyboardInterrupt` and `EOFError` and send them into the same halt/quit lifecycle. [Prompt toolkit async input](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html)

Do not rely on Unix `termios`, `tty`, `loop.add_reader(stdin)`, or `loop.add_signal_handler()` for this Windows app. Windows asyncio has platform-specific restrictions, including no `add_signal_handler()` support. Test Ctrl+C in the actual terminal used for the demo. [Python platform documentation](https://docs.python.org/3.11/library/asyncio-platforms.html)

Avoid `asyncio.to_thread(input)` as the main console design: a blocked input thread complicates shutdown. Keep a noninteractive stub/selftest path for redirected input and CI.

At application level, catch unexpected main-task cancellation and initiate/retain the cleanup supervisor before propagating it. A hard process kill, laptop power loss, or repeated forced interruption can still bypass cleanup; device-side behavior and the independent staff controller are necessary.

### 10.3 Suggested terminal display

```text
Robot Patrol  |  protocol 2.0-draft  |  mission <short-id>
DOG ethernet / Go2 PRO    DRONE Tello EDU    PI on dog    xAI Grok
Phase: HOLD     Beacon epoch: 4     Dog motion: STOPPED
Drone: airborne / hold stable / height 4 m floor_agl / controlled motion armed
Track: target-001 on downward camera
Next: accept a Pi window, then one safe dog step
Goal: unresolved     Landing: not attempted
Commands: status | halt | quit
```

Unknown height stays unknown. A missing Pi path is shown as RSSI disarmed. Model text is logged and is not parsed as a command.

## 11. Preconditions, evidence, and result validation

### 11.1 Guards before a dog step

Require all of the following:

- Current mission and epoch, halt clear, and the command not already expired.
- The dog capability report armed the motion being requested.
- Standing, stationary, and avoidance are exactly true. Null is not true.
- The beacon hold is stable, unexpired, and on the current beacon epoch.
- `candidate_id` is in the latest safe list, on `dog/base_link`, and still inside `valid_until`.
- No other dog or drone motion command is active.
- Ethernet runs stay inside the tether budget. Wi-Fi runs use the Wi-Fi profile that was armed, with no mid-run switch.
- The Pi window, if this step is RSSI guidance, matches the drone BSSID and beacon epoch.

Use explicit `is True` checks. A string `"false"` must not become permission.

### 11.2 Guards before a drone step

- Operator arm is consumed for this run, and the aircraft state is known.
- `controlled_motion` is true for an autonomous search or track step. Otherwise only hover, land, or a labeled supervised action is available.
- The primitive id is on the local allowlist. The model does not supply SDK text or a "move five meters" command.
- A track step that depends on image direction has a calibration id. A null calibration blocks that step.
- Height is stored with its reference. A 4 m figure labeled `unknown` or `takeoff_relative` is not an approved floor height.
- The dog is stopped before the drone moves, and it stays stopped until the new beacon epoch is stable.
- The cable, when Ethernet is selected, stays clear of the landing area.

The drone teammate still applies the local failsafe. Ground does not send a second takeoff when the first reply is missing. After landing, recovery stays latched until the grounded state is verified.

### 11.3 Frame validation

For every returned frame:

1. Check it is the expected contract type, source, and exact current zone.
2. Require an absolute path to an existing, nonempty regular file under the adapter's assigned output directory for live outputs.
3. Decode/verify JPEG format with a bounded file-size limit. An extension or header alone does not prove a readable image.
4. Validate the capture timestamp and camera epoch. A missing timestamp stays missing. File modification time is not capture time.
5. For live capture, require capture after the corresponding operation began and within its recorded capture interval. The adapter is responsible for rejecting an old stream buffer when selecting it.
6. For aerial evidence, allow transit/landing time after capture; log image age rather than requiring it to remain under five seconds at operation return.
7. Reject simulated frames returned by a real adapter. Preserve expected simulation flags in mixed runs.
8. Record file identity, operation ID, path, source, timestamp, and validation outcome.

Ground can verify metadata consistency and file integrity, not prove that a dishonest timestamp is correct. Adapter acceptance must demonstrate fresh-stream behavior. A whole-mission replay file is not live evidence even if saved under a new name.

Use UTC for capture records and monotonic time for durations. Record both operation clocks. If system UTC jumps enough to invalidate capture comparisons, fail the evidence check rather than rewriting its timestamp.

### 11.4 Model response checks

The vision teammate validates the xAI payload. Ground still checks `vision.decision` against the request id, frame id, and camera epoch before using it. A box must be four normalized numbers in order. `person_visible` can open a track. It cannot create a distance.

`uncertain`, a late reply, or two people without a matching track id become review. The reason string is not a command. A decision that arrives after halt does not clear the latch.

Initial simulation budgets, to be measured and then changed: sample the latest frame every 1000 ms, one request in flight, request timeout 5000 ms, evidence age 3000 ms, ordinary command lease at most 500 ms. Takeoff and land use their own deadlines. The 500 ms lease is not a motor-cut timer.

## 12. Configuration and simultaneous networking

### 12.1 Ground configuration

Use the plan's config envelope and relative-path rule: each relative path resolves against the JSON file containing that path. Convert adapter file paths to absolute before passing them on. Secrets are environment/local configuration only.

```json
{
  "dog_transport": "ethernet",
  "pi_data_path": "usb",
  "dog_config_path": "dog.local.json",
  "drone_config_path": "drone.local.json",
  "pi_config_path": "pi.local.json",
  "vision_config_path": "vision.local.json",
  "flight_profile": "proposed_4m_floor_agl",
  "image_sample_ms": 1000,
  "vision_timeout_ms": 5000,
  "evidence_age_ms": 3000,
  "command_lease_ms": 500,
  "dog_range_max_m": null,
  "drone_horizontal_max_m": null,
  "output_root": "../artifacts"
}
```

Leave the two range thresholds null until the team agrees them for the real space. The 1.5 m numbers in `contracts/examples/proximity-evidence.json` are an illustration.

Keep the dog IP and key in the dog config, the Tello interface in the drone config, the Pi path in the Pi config, and the xAI model id in the vision config. The example model string `CONFIGURE_VERIFIED_IMAGE_MODEL` is a placeholder. A missing profile, a missing Pi path, or an unvalidated capability disables that real feature.

Maintain separate dog connection profiles, for example `dog.ethernet.local.json` and `dog.wifi.local.json`. Ground selects one through `dog_config_path`; both instantiate `RealDog` through the same frozen factory. The dog owner maps the chosen interface/IP profile to the tested driver connection mode. Keep the profile's transport identity (`ethernet` or `wifi`) in Ground's run metadata so cable-specific checks and logs match the actual setup. These are proposed profile filenames, not already implemented files. No new public adapter methods are needed, and two active dog-control clients must not be created to provide the two options.

Configuration checks should reject nonpositive/nonfinite timeouts, unknown zones/modes/tiers, malformed paths, and unsupported real-pad/fake-dog combinations before movement. Do not silently fall back from a requested real adapter to a fake one.

### 12.2 Baseline topology

```text
Go2 PRO ==== Ethernet tether ==== command laptop ---- Wi-Fi ---- Tello EDU AP
            stays connected            |                         (beacon)
Pi on the dog ---- usb / wire / second radio ---- laptop        |
                             separate verified internet uplink  |
                                       |                        |
                                  xAI Grok                      |
```

The dog link, the Tello link, the Pi telemetry path, and the internet uplink are four facts. The broken router in the back enclosure is none of them. If the laptop's only Ethernet port is on the dog and its only Wi-Fi radio is on the Tello, internet and the Pi path need their own verified interfaces. Do not assume the Tello access point routes to the Pi and the laptop at the same time.

The alternate supported configuration replaces the dog's Ethernet link with a tested dog Wi-Fi link while leaving the Tello on Wi-Fi. If dog and drone require different access points, provide independent Wi-Fi interfaces or another explicitly tested simultaneous topology; do not switch one radio between them during a mission. Wi-Fi support in software does not mean the currently broken router has been repaired.

The current Ethernet demonstration is tethered. Each dog step must fit the cable's approved reach, slack, and strain relief. A tether snag is not an obstacle the software can reliably detect. Keep the cable out of the propellers and the landing patch. No stage disconnects the cable so the dog can walk farther. A separately accepted Wi-Fi profile does not use these cable checks, and it does not turn itself on after an Ethernet fault.

Test all links simultaneously. A laptop reaching each device separately after switching networks does not establish an integrated setup. Ground must not discover this during takeoff.

### 12.3 Windows route checks

These are read-only diagnostics to run on the actual command laptop:

```powershell
Get-NetIPConfiguration
Get-NetRoute -AddressFamily IPv4
Find-NetRoute -RemoteIPAddress 192.168.10.1
```

Run the last command again using the actual dog address. Microsoft documents `Find-NetRoute` as selecting the best local address and route for a remote address. It is useful for checking which interface Windows will use. [Microsoft reference](https://learn.microsoft.com/powershell/module/nettcpip/find-netroute)

Record the chosen interfaces, IP prefixes, gateway, and successful adapter-level video/control checks. Ping alone is neither proof nor a necessary condition for successful UDP SDK operation. A failed ICMP response does not establish that Tello's command/video ports are unavailable.

Verify that the route to the actual dog IP selects the intended wired interface. Verify Grok internet access while the dog Ethernet and Tello Wi-Fi are both active; an isolated dog link must not accidentally become the internet route. Record any required network settings in the handoff rather than making unreviewed automatic OS network changes in Ground.

Check for overlapping subnets. In particular, a venue/box network using `192.168.10.0/24` can conflict with the Tello network. Have staff resolve the topology rather than adding guessed routes. Do not disable the entire firewall as a troubleshooting shortcut; allow the tested application/ports on the intended link if needed.

Verify outbound Grok access only after the local robot links are active. Laptop internet access does not imply that an onboard computer, if one exists, also has internet; this build puts Grok on the laptop.

### 12.4 Connection lifecycle

Connecting can run before arm because it is non-motion. A missing Pi path blocks RSSI homing and stays visible. It does not authorize a fake signal.

A loss of connection during a dog step or a flight is different from a feature that was never armed. Active uncertainty triggers recovery. Reconnecting never resumes motion or replays a command id.

Ethernet loss latches halt and blocks new actions. Request dog halt and the profile's drone hover or land on any path that is still up. If the dog link is gone, do not claim the halt was delivered. The local lease and the operator's own controller still apply. There is no automatic switch to Wi-Fi, and the broken router is not a backup.

Change dog transport only between runs, after recovery and after the previous client is closed. A Wi-Fi loss uses the same fault policy. Neither profile replays a step on the other transport.

## 13. Event journal, evidence folders, and metrics

### 13.1 Per-mission layout

```text
artifacts/<mission_id>/
  events.jsonl
  summary.json
  config.redacted.json
  dog/
  drone/
  pi/
  vision/
```

Create the run directory uniquely before motion. Image bytes stay in the artifact store. The journal line stores the artifact reference and hash, not the image. The field list is the proposal in [contracts/events-and-logs.md](contracts/events-and-logs.md). The team's final log list has not arrived. Add later fields with a schema revision. Do not drop `message_id`, `mission_id`, `epoch`, `command_id`, `frame_id`, `track_id`, or `beacon_epoch`.

### 13.2 Event shape

Use a sequence counter assigned by Ground when an event is enqueued. It gives ordering even if wall-clock timestamps coincide. Every line is one complete JSON object.

```json
{
  "seq": 17,
  "timestamp_utc": "2026-11-04T13:00:00Z",
  "elapsed_s": 12.7,
  "mission_id": "illustrative-only",
  "protocol_version": "2.0-draft",
  "state": "HOLD",
  "event": "command_approved",
  "kind": "drone.command",
  "message_id": "illustrative-only",
  "command_id": "illustrative-only",
  "beacon_epoch": 4,
  "modes": {"dog": "fake", "drone": "fake", "pi": "fake", "vision": "fake"},
  "data": {"primitive_id": "verified-hold-v1"}
}
```

These are example values, not a flight. Record capability flags, frames, vision requests and decisions, approvals, command acknowledgements, RSSI quality, proximity, halt, and landing. `demo_goal_reached` and `landing_unverified` are different events. Exact samples live in `contracts/examples/`. `contracts/example-events.jsonl` is a catalog of separate examples, not one mission.

Do not log API keys, tokens, or raw authorization headers. A missing measurement is null with a reason, not zero.

### 13.3 Writing without blocking halt

Use one journal writer, with ordered small event records passed through a queue. A dedicated writer thread can handle file I/O; the main loop should not wait for a slow filesystem before latching halt. Python provides QueueHandler/QueueListener for threaded logging, though a structured JSON Lines writer may be simpler for your event schema. [Logging queue facilities](https://docs.python.org/3.11/library/logging.handlers.html)

Keep file-writer exceptions observable. If a write fails, stop authorizing new ordinary actions, invoke necessary stop/recovery, display the storage failure, and retain whatever diagnostics remain available. Do not say the log was saved when it was not.

Use a temporary summary file in the same directory and publish it with `os.replace()` after writing/flushing. Replacement reduces exposure to partial summaries; it is not a guarantee of power-loss durability. Keep temporary/final files on the same filesystem and test the behavior on the real OS. [Python file replacement](https://docs.python.org/3.11/library/os.html#os.replace)

For live motion, enqueue the operation-intent event before scheduling the command. If stronger durability is later needed, add a bounded writer acknowledgement before motion; halt must always bypass that wait. For this demo, document whether events are queued, flushed, or synced instead of claiming a transactional robotics system.

### 13.4 Demo timings

Compute these from one clock domain. Leave the value null, with a reason, when either endpoint is missing.

- Mission start to the first valid drone detection.
- Detection to a stable beacon hold, then to the first dog step.
- First dog step to the same person in the dog camera.
- Start, and dog activation, to the joint proximity check.
- Goal time to verified landing. Unknown landing does not become a latency of zero.
- Vision latency, evidence age, and how many stale frames were dropped.
- Per-command accept, running, and completed times.
- RSSI windows by quality, beacon-epoch changes, blocked candidate lists, and no-progress stops.

A successful orchestration log is not a classification-accuracy result. The summary names which peers were real, which features were disarmed, the thresholds actually used, and whether recovery is still required.

## 14. Failure and restart policy

| Situation | Ground response | Continue automatically? |
| --- | --- | --- |
| Capability missing or `validated` false | Leave that feature disarmed. | No invented capability. |
| Controlled motion false | Supervised search, or simulation. | No random flight. |
| Downward video unusable | Use an approved front-camera case or stop. | No relabeling a front frame as downward. |
| Stale or late vision result | Drop it. Hold or review. | No more aggressive motion. |
| Drone command reply missing | Query that command id. | No second takeoff. |
| Beacon moving or hold expired | Dog stays stopped. Old RSSI is incomparable. | No. |
| Empty safe-candidate list | Stop and review. | No invented detour. |
| RSSI noisy, flat, or no signal | Stop. No-signal is empty samples and a null median. | No. A 0 dBm sentinel is rejected. |
| Dog command expired or rejected | Record no motion. | No replacement step. |
| Dog sees a different person | Review. | No track switch. |
| Range or horizontal offset missing | Goal stays unresolved. | No fabricated distance. |
| Goal reached, landing unknown | Keep the goal. Set recovery required. | No. |
| Operator halt or link loss | Latch immediately. Do not wait for Grok. | No. |
| Writer failure | Stop new actions and show the persistence fault. | No claim that the log was saved. |
| Process restarts after a fault | Reconnect disarmed. | Never resume the old command. |
| Ethernet lost | Halt where the path still exists. | No silent Wi-Fi handover. |

### 14.1 Reset procedure

1. Verify the dog is stopped and the aircraft is recovered. Unknown landing means stay faulted. The operator recovers the drone by hand.
2. Ensure the old normal mission, stop/landing operations, and adapter workers have quiesced. Unknown/pending means remain faulted.
3. Close all adapters idempotently; preserve original and cleanup errors separately.
4. Recreate adapters through their factories and reconnect without motion.
5. Allocate a new cancellation Event and session epoch. Clear old confirmation futures and evidence references.
6. Return to disarmed IDLE with a new incident ID when new input is accepted.

Backend operator step controls now distinguish a soft observation timeout from a physical fault. A soft timeout can wait for the same attempt, or retry a verified retryable step while preserving completed checkpoints. They do not resume a route from an unknown pose or clear a halt. After a physical fault, the reset procedure above still applies. See [the backend API and frontend handoff](docs/ground/step-controls.md) for exact functions, budgets, and JSON commands.

### 14.2 What Ground cannot guarantee

Ground can gate calls and request stops while it is running and connected. It cannot force a disconnected device to receive a stop, guarantee stopping after laptop power loss, or prove a safe pad takeoff from a photograph. Record measured device-side command expiry and keep the staff's independent controls available.

These are concrete acceptance limits of this equipment/software setup. They should be visible in the handoff, not hidden behind a generic `try/finally` claim.

## 15. Test strategy before any real hardware

### 15.1 Three testing levels

| Level | Dependencies | What it establishes |
| --- | --- | --- |
| Private Ground stubs | Frozen contract + your files | Your workflow, input, state checks, safety requests, and logs work independently. |
| Merged module fakes | Actual public factories from all three teammates | Names, signatures, dataclasses, scenarios, and packaging integrate. |
| One real adapter at a time, then full setup | Equipment/API access | Actual connection, command, freshness, and recovery behavior. |

Passing private stubs does not establish factory integration. Passing fakes does not establish a physical stop/landing guarantee.

### 15.2 Private stub requirements

- Implement the v2 message handlers with vendor imports kept out of the stub run.
- Use the synthetic JSON in `contracts/examples/` plus small JPEG fixtures whose hashes match.
- Record a trace of approved command ids. A duplicate command id must not appear as a second move or a second takeoff.
- Hold a vision call or a command acknowledgement on a barrier so halt can win. Avoid long sleeps.
- Cover the drone-first cases in section 15.3. Do not require the retired phone-incident scenario names.
- Label every fixture `simulated=true`. A stub must not return those hashes with `simulated=false`.

### 15.3 Scenario acceptance matrix

| Scenario / test | Assertion that matters |
| --- | --- |
| Happy path | One drone step, a new beacon epoch, one dog step, dog-camera handoff, then goal and landing as separate records. |
| `controlled_motion` false | Supervised or stopped. No random move is chosen. |
| Stale drone frame | Dropped. No vision request and no track step. |
| Late Grok reply | Ignored. Does not clear a halt. |
| Takeoff reply missing | One command id is queried. No second takeoff. |
| Beacon moving | Dog command count stays zero. |
| Old beacon epoch on a Pi window | Window rejected as incomparable. |
| Blocked candidate list | Stop. No synthetic forward step. |
| Noisy or empty RSSI | Stop. Empty signal is null dBm, not 0. |
| Dog ack expired | No motion flag and no replacement command. |
| Two people or the wrong track | Review. RSSI handoff does not occur. |
| Missing range or offset | Goal unresolved. |
| Goal plus unknown landing | Goal stays true. Recovery stays required. |
| Halt during vision | Dog halt and drone hover or land, with no model wait. |
| Repeated halt | One latch. |
| Double start | One mission. |
| Writer failure | Halt still works. The log is not marked published. |
| Ctrl+C / EOF | Same path as typed halt. |
| Restart after a fault | Disarmed. The old command is not resumed. |
| Ethernet loss | No Wi-Fi handover. |
| Pi path missing | RSSI disarmed. Dog and drone can still be identified. |
| Ethernet tether overrun | Dog step rejected. |

### 15.4 Test assertions and tools

Use `tmp_path` for artifacts, fake adapters for failure control, and event/barrier synchronization to inject halt at a known point. Assert call order, result fields, and forbidden actions rather than exact terminal colors or screen coordinates.

If using pytest-asyncio, keep test/fixture event-loop scopes consistent and clean up every retained task. Its documentation explains loop isolation and test discovery modes. [pytest-asyncio concepts](https://pytest-asyncio.readthedocs.io/en/stable/concepts.html)

For console tests, prompt_toolkit supports pipe input and dummy output. Feed commands and verify controller effects; do not snapshot its entire renderer output. [Prompt toolkit testing guide](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/unit_testing.html)

Test the race where the model result and halt arrive almost together. The epoch and halt check must block the command even when the decision itself is valid. Test the same race for a late dog acknowledgement and for reset.

Record fake halt recognition latency separately from physical stop/landing time. The 0.5 s target tests application responsiveness, not aircraft descent speed.

## 16. Commands you should deliver

### 16.1 Independent first milestone

```powershell
python -m patrol.ground.selftest --stubs --scenario drone_first
```

This must work from the v2 fixtures, Ground's own files, and Ground's dependencies. It must not import a missing dog app, DJITelloPy, or the xAI SDK.

### 16.2 Merged all-fake workflow

```powershell
python -m patrol.ground --dog fake --drone fake --pi fake --vision fake --scenario drone_first
```

This path uses the teammates' factories when those factories exist. It does not silently replace a missing factory with a private stub. The rehearsal in Task 32 is allowed to use its own fixtures because it is an independent card. The integrated command is not.

### 16.3 Real run

```powershell
python -m patrol.ground --dog real --drone real --pi real --vision real --config config/ground.local.json
```

That path starts disarmed. The operator then uses:

```text
status
arm
start
status
halt
```

`start` is legal only after arm, and only with the features the capability reports actually armed. `halt` is available throughout. Recovery comes before `reset`. A 4 m profile is selected in config for a venue that allows it. It is not implied by `start`.

### 16.4 Development setup

Work from a clean Robot Patrol project root, not the parent Resume Changer application. A proposed Windows setup after you have created your dependency file is:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/ground.txt
.\.venv\Scripts\python.exe -m pytest tests/ground
```

Pin the versions actually tested. The commands above require Python 3.11 to be installed; this guide has not installed it. Keep hardware dependencies in optional/combined installation paths so your private-stub workflow stays lightweight.

## 17. Build order for your first 30 hours

This is a proposed schedule, not a claim that every hardware capability fits inside it. Hardware slots can move independently from offline development.

| Time | Your concrete deliverable | Verification |
| --- | --- | --- |
| 0–2 h | Parse v2 envelopes and reject bad ones. Session opens disarmed. | The example observation and dog command parse. A bad epoch does not. |
| 2–5 h | Capability arming, drone observations, frame hash, and the vision schedule. | Stale frames drop. One request is in flight. |
| 5–9 h | Decision checks, drone command approval, acknowledgements, and beacon epoch. | No SDK string reaches the drone. A missing reply does not retakeoff. |
| 9–12 h | Pi windows, safe candidates, one dog command, and dog acknowledgements. | A blocked list or a moving beacon produces no step. |
| 12–15 h | Dog-camera handoff, proximity, landing split, halt, and the journal. | Goal and unknown landing can both be true. Halt does not wait on xAI. |
| 15–18 h | Offline rehearsal and the operator script. | `drone_first` passes on fixtures. The catalog JSONL is not replayed as one mission. |
| 18–23 h | Dog Ethernet, Tello, Pi path, and internet up together. | Record the real interfaces. RSSI stays disarmed if the Pi path is missing. |
| 23–26 h | Supervised or bounded flight, then one dog step, in the approved venue. | 4 m only where the ceiling and the profile allow it. |
| 26–30 h | One recorded run with artifacts, timings, and the handoff. | Disarmed features stay labeled. Recovery is separate from the goal. |

The first useful day is a fake run that can halt during a pending vision call. A script that prints the happy path and cannot stop is not ready for hardware.

If time is short, keep one supervised scout, one dog step, and an honest unresolved goal. Cut display polish before cutting halt, the beacon epoch, or the landing fault.

## 18. Hardware session and final handoff

### 18.1 First combined connection session — motors and flight inactive

1. Record Go2 PRO firmware, the Ethernet port, and the router's current failure. The robot uses its own power. No extra power cable is part of this setup.
2. Record the Pi model, how it is mounted, and whether its messages reach the laptop by USB, wire, or a second radio.
3. Connect the dog over the Ethernet cable that will stay attached. Read state and one still frame. Do not walk.
4. Connect the Tello. Read battery and one frame from the camera you intend to use. Do not take off. Try the downward camera here and record whether it actually streams.
5. Confirm xAI with one still image while the dog and Tello links stay up.
6. Stop one-off diagnostic clients before Ground owns the links.
7. Exchange capability reports. Leave controlled motion, downward video, SLAM, and RSSI disarmed where the report does not validate them.
8. Write down every unknown. An unknown is not a pass.

### 18.2 First motion session

1. Show dog halt from Ground and from the operator's own control.
2. Show one leased dog step inside the cable reach, then a verified stop. The dog app must reject a candidate it no longer considers safe.
3. Show one bounded drone step, or a supervised search if directional control is still unreliable. Then show a stable hover and the beacon epoch advancing after the move.
4. During that hover, read one Pi window and confirm it names the Tello BSSID. The dog stays still until the hold is stable.
5. Treat landing as its own check. A picture from the air does not prove the aircraft is down.
6. Use the venue that fits the height profile. Do not fly the 4 m profile under the low hackathon-room ceiling.
7. Keep the artifacts, the modes, the disarmed features, and both the goal result and the landing result.

### 18.3 Handoff contents

`handoff/ground.md` should give the next person:

- Source root, Python, OS, install command, and the pins that were actually tested.
- The stub command and the all-fake command, with results.
- Redacted config and the four paths: dog, Tello, Pi, and internet.
- Which dog transport works. Wi-Fi stays unverified until it is tested. The router stays recorded as failed.
- Go2 firmware, Tello library version, whether directional motion worked, and whether downward video worked.
- Pi model, mount, data path, and clock error.
- The xAI model id and prompt version. The placeholder string is not a model id.
- Cable reach, landing area, operator halt, and how to reset after an unknown landing.
- One artifacts folder. Goal and landing must both be visible in it.
- The contract files each teammate was given, and any log field the team added later.

You are ready to hand this over when another teammate can run the fake demo, see which features were real, and explain a failed run from the files alone.

## 19. Source map and research limits

All links below are primary manufacturer, library-author, project-author, or language/runtime documentation. Mutable repositories may change after this research date; pin tested versions in the actual implementation.

| Source | What it supports in this guide |
| --- | --- |
| [Unitree Go2 product comparison](https://www.unitree.com/go2/) | Edition differences; do not assume PRO equals EDU development support. |
| [Unitree WebRTC driver README](https://github.com/legion1581/unitree_webrtc_connect/blob/master/README.md) | Claimed PRO support, connection modes, firmware/AES setup. |
| [Driver connection implementation](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/webrtc_driver.py) | Local AP address and actual connection API. |
| [Driver constants](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/constants.py) | Topics and command-name/ID mappings. |
| [Avoidance example](https://github.com/legion1581/unitree_webrtc_connect/blob/master/examples/go2/data_channel/obstacles_avoid/obstacles_avoid.py) | Avoidance query/toggle and demonstrated controller command path. |
| [Video channel](https://github.com/legion1581/unitree_webrtc_connect/blob/master/unitree_webrtc_connect/webrtc_video.py) | Video switching and callback API. |
| [Ryze EDU specifications](https://www.ryzerobotics.com/tello-edu/specs) | Weight, wireless/video and camera specifications. |
| [Ryze SDK 2.0](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf) | Network ports, text commands, units, and timeout behavior. |
| [DJITelloPy implementation](https://github.com/damiafuentes/DJITelloPy/blob/master/djitellopy/tello.py) | Library retries, local flight flags, command methods, firmware-specific video notes. |
| [Unitree UI](https://github.com/legion1581/unitree_ui), [Go2 API](https://github.com/carlosvts/go2/tree/main/api), [agentic Go2](https://github.com/jrcichra/agentic_unitree_go2) | Closely related connection/coordination/mock-interface designs. |
| [Open-RMF template](https://github.com/open-rmf/fleet_adapter_template), [demos](https://github.com/open-rmf/rmf_demos) | Device integration boundaries and heterogeneous coordination. |
| [Spot missions](https://dev.bostondynamics.com/docs/concepts/autonomy/missions_service.html), [leases](https://dev.bostondynamics.com/docs/concepts/lease_service), [keepalive](https://dev.bostondynamics.com/docs/concepts/keepalive_service.html) | Mission, operator-prompt, ownership, and communications-loss concepts. |
| [QGC toolbar](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/fly_view/fly_view_toolbar.html) | Distinct readiness and flight-status presentation. |
| [BehaviorTree.CPP async tutorial](https://www.behaviortree.dev/docs/tutorial-basics/tutorial_04_sequence/) | Nonblocking, interruptible long-running action pattern. |
| [MAVSDK example](https://github.com/mavlink/MAVSDK-Python/blob/main/examples/takeoff_and_land.py), [MAVLink command protocol](https://mavlink.io/en/services/command.html) | Health/action lifecycle and acknowledgement-versus-completion distinction. |
| [SayCan](https://say-can.github.io/) | Grounding language proposals in available skills; conceptual comparison only. |
| [Python tasks](https://docs.python.org/3.11/library/asyncio-task.html), [development](https://docs.python.org/3.11/library/asyncio-dev.html), [platforms](https://docs.python.org/3.11/library/asyncio-platforms.html), [executors](https://docs.python.org/3.11/library/concurrent.futures.html) | Async implementation and cancellation/platform limits. |
| [Prompt toolkit input](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html), [testing](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/unit_testing.html) | Async terminal and programmable input tests. |
| [Microsoft Find-NetRoute](https://learn.microsoft.com/powershell/module/nettcpip/find-netroute) | Read-only Windows route diagnostics. |

The architecture, build schedule, guards, file layout, and acceptance tests are recommendations tailored to this project. They are not claimed features of those reference systems. The photographs identify the hardware edition and visible installation; they cannot establish firmware access, network reachability, positioning quality, flight reliability, or safe stopping latency.
