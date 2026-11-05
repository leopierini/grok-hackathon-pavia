# Ground Mission Control operator guide

This console runs on the operator laptop. Simulation does not need a robot, a
Pi, an xAI key, or a network connection after the packages are installed.

## Install

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
cd ui\mission-control
npm install
cd ..\..
```

Python 3.11 or newer and Node.js 20 or newer are required. The first `npm install`
downloads the UI packages. After that, the simulated interface does not call the
network. Fonts are bundled.

## Start both services

```powershell
.\scripts\ground-mission-control.ps1
```

The script starts the Python API on `127.0.0.1:8765` and the Next.js UI on
`http://127.0.0.1:3000`. Closing the script stops both process trees.

Open `http://127.0.0.1:3000`. The browser talks only to the Next.js origin.
The operator token stays in the server process and is not placed in the page.

## Rehearse

1. Open Rehearsal.
2. Choose `happy_path`.
3. Arm this session. Arm does not move the dog or the drone.
4. Start. One worker runs. A second start, another tab, or a reload does not
   create another mission.
5. Watch Mission, Vision, Navigation, and Commands. Phases change only when
   Ground reports them.
6. When the run is finished, goal and landing are separate. `DONE` means both
   were verified in the simulation.

Other scenarios inject one fault through the same API. Examples: stale frame,
slow Grok, moving beacon, empty RSSI, blocked planner, ambiguous target,
rejected dog command, missing proximity, link loss, and an unknown landing.

## Halt

Halt is in the header on every screen. It does not ask for confirmation.
The API accepts the request immediately and schedules the existing safety
path. The page then says whether delivery is still unknown. A successful
response does not mean the robots stopped.

Halt remains available while a dialog is open. Reset is the action that asks
for a recovery token.

## Recovery

Unknown landing keeps the goal and sets recovery required. Dismissing the
text does not clear it. Reset asks for a recovery token, opens a new disarmed
session, and leaves the old run in Runs.

Reset without a token is available only when the goal and the landing are both
verified and recovery is not required.

## Logs

Runs lists completed reports. A run detail exports the summary. The journal
distinguishes the operator feed, which is enqueued as it is observed, from
task 29 records that are queued, flushed, or published. The team log schema
remains `proposed-1` / `proposed_pending_team`.

## Live dog demo

The Mission page has the controls for the current demo. Check Ethernet only
looks for the dog on port 8081. Start live dog demo arms the session and runs
`happy_path`. The one approved dog step is sent on Ethernet. The drone,
pictures, and RSSI stay scripts. Halt stays in the header and, while that
session is open, also asks the dog for StopMove and a soft lie-down.

Rehearse on simulated dog runs the same step against the simulated body, with
no cable. A full live mode that would command the drone still stays refused.

## Live devices

Choosing live mode, or saving a real adapter mode, refuses arm and start.
The console does not substitute a fake device. The refusal names the missing
teammate transports and the lack of physical acceptance. The Ethernet dog
demo above is the one live path, and it does not open a drone socket.

## Settings

Dog transport is ethernet or wifi. There is no automatic handover. The 4 m
flight profile stays disabled. Venue range thresholds stay null until set, and
null is not zero. A secret field in the JSON is rejected and is not echoed.
