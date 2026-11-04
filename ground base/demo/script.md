# Drone-first demo — two-minute operator brief

This page is the operator script for one offline rehearsal. The evidence label is **software simulation**. This rehearsal is not physical acceptance of the Go2, the Tello, the Raspberry Pi, or xAI.

Live Ground logs are written on the ground laptop at `artifacts/<mission_id>/events.jsonl`, with `summary.json` in the same directory. Those files are Ground records. They are not packets for a robot to execute. Send `contracts/events-and-logs.md` to every teammate. `contracts/example-events.jsonl` is a catalog of separate examples. Replay that catalog as one flight and the causal-order check fails.

## Site check

Confirm the room is closed, the landing patch is empty and marked, and the dog Ethernet cable can stay plugged in for the whole Ethernet run. The laptop must keep the dog link, Tello Wi-Fi, and Grok internet up together. There is no automatic radio handover.

The **4 m** profile is available only when the venue has been measured and the drone teammate has accepted that profile for this room. The hackathon ceiling is too low for that profile. Arm a lower supervised profile there. A 4 m number in an example file is a profile value. It is not an enabled default, and the sample command leaves `requested_height_m` empty.

## Arm

Start disarmed. Arm a camera, a radio, a map, or a movement mode only after that peer's `capabilities.report` says it is present and validated. This rehearsal forces `simulated: true` on every device message and rejects a real-mode flag before any scenario step. A real adapter that returns synthetic evidence is rejected.

## What the drone teammate must have verified

The aircraft is a Tello EDU behind `from djitellopy import Tello`. Directional motion is an open control fault until they show one verified bounded primitive. Uncontrolled drift is a stop or a supervised hold. It is not a search, and a timed-out takeoff does not get a second takeoff.

They must have checked the front camera and the downward camera as separate gates. There is no rear camera. Hover and land stay available without a Grok round trip.

Send them `contracts/drone-to-ai.md`, `contracts/ai-to-drone.md`, and these shapes:

- `contracts/examples/drone-capabilities.json`
- `contracts/examples/drone-observation.json`
- `contracts/examples/drone-ack-accepted.json`
- `contracts/examples/drone-ack-running.json`
- `contracts/examples/drone-ack-completed.json`
- `contracts/examples/drone-landing-unknown.json`
- `contracts/examples/ground-to-drone-command.json`
- `contracts/examples/ground-to-drone-hover.json`
- `contracts/examples/ground-to-drone-land.json`

`contracts/examples/ai-to-drone-proposal.json` stays with Ground and the vision teammate. The drone does not execute that file.

## What the dog app will receive

The dog app receives one leased `dog.command` chosen from a candidate it already marked safe, or one halt. It does not receive `contracts/examples/ai-to-dog-proposal.json` as a motor string. The dog stays stopped while a drone step is running, and it stays stopped until the new beacon epoch has a Pi window. RSSI is received power in dBm at the Pi on the dog. The rehearsal has no RSSI-to-meters field.

Send the dog-app teammate `contracts/dog-to-ai.md`, `contracts/ai-to-dog.md`, and these shapes:

- `contracts/examples/dog-capabilities.json`
- `contracts/examples/dog-observation.json`
- `contracts/examples/dog-navigation-candidates.json`
- `contracts/examples/dog-ack-accepted.json`
- `contracts/examples/dog-ack-running.json`
- `contracts/examples/dog-ack-completed.json`
- `contracts/examples/dog-command-rejected.json`
- `contracts/examples/ground-to-dog-command.json`
- `contracts/examples/ground-to-dog-halt.json`

A blocked planner produces a stop. Ground does not invent a candidate.

## Vision and the Pi

Send the vision teammate `contracts/vision.md`, `contracts/examples/drone-vision-request.json`, `contracts/examples/dog-vision-request.json`, `contracts/examples/drone-vision-decision.json`, `contracts/examples/dog-vision-decision.json`, plus the two proposal files above. The request JSON is not the JPEG. Resolve the `artifact://` reference and check the hash before any xAI call. Drop a stale frame. The model id in the examples is `CONFIGURE_VERIFIED_IMAGE_MODEL` until a verified image model is configured.

Send the Pi teammate `contracts/rssi-and-navigation.md`, `contracts/examples/pi-capabilities.json`, `contracts/examples/pi-rssi-window.json`, and `contracts/examples/pi-heartbeat.json`. Ground does not send the Pi a motion command. A noisy window stops the dog step.

## Halt

Halt, link loss, an expired lease, and a local obstacle stop are operator and device safety actions. They do not wait for Grok. The dog halt shape is `contracts/examples/ground-to-dog-halt.json`. The aircraft hold and land shapes are the hover and land files above.

## Goal and landing

The demo goal is a current dog-to-person range plus a current drone horizontal offset for the same person. That record is `contracts/examples/proximity-evidence.json` together with `contracts/examples/event-demo_goal_reached.json`.

Landing is the next recovery step. A goal record does not mean the aircraft is down. An unknown landing stays a fault afterward. See `contracts/examples/event-landing_unverified.json` and `contracts/examples/drone-landing-unknown.json`.

## Rehearsal command

From the ground worktree, with no robot and no model call:

```powershell
python -m patrol.ground.sim --task 32 --case all --seed 0 --report artifacts/task-32/simulation.json
```

A failed assertion still writes the rehearsal report and returns a failed command. A second run into the same directory is refused. Seed 0 is the happy-path rehearsal. Physical acceptance is a separate staffed session.
