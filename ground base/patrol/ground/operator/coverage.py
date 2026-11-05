"""Task 01–32 coverage rows for the operator console.

Status values stay distinct. A row is not verified on hardware.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from patrol.ground.kernel.paths import repo_root

Json = dict[str, Any]

ROWS: tuple[Json, ...] = (
    {
        "id": "01",
        "title": "Freeze the Ground kernel, interfaces, extension loader, and simulation foundation",
        "ui": "Mission header and Rehearsal coverage",
        "data": "Provider inventory, contract v1.0, protocol 2.0-draft, kernel schema, missing providers",
        "actions": "None. Inventory is observational.",
        "provider": "patrol.ground.kernel.loader.discover",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g01",
        "blocker": "Live teammate transports are not supplied. Not verified on hardware.",
    },
    {
        "id": "02",
        "title": "Implement configuration loading and normalized connection settings",
        "ui": "Settings",
        "data": "Transport, profiles, modes, redacted vision identity, rejected secrets",
        "actions": "Validate and save while idle. Real modes do not fall back to fake.",
        "provider": "patrol.ground.kernel.settings.make_settings and operator config validation",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g02",
        "blocker": "Physical profile files and credentials are not in this checkout.",
    },
    {
        "id": "03",
        "title": "Implement session state, event reduction, and admission fencing",
        "ui": "Mission header",
        "data": "v2 phase, foundation reducer phase, session epoch, arming, halt latch",
        "actions": "Arm, start, and reset send the session epoch. Stale epochs are rejected.",
        "provider": "Ground session snapshot plus operator session epoch",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g03",
        "blocker": "The foundation reducer still uses the v1 phase vocabulary. v2 phases come from the composed rehearsal.",
    },
    {
        "id": "04",
        "title": "Implement asynchronous artifacts and the ordered event journal",
        "ui": "Runs and logs",
        "data": "Operator feed versus task 29 queued, flushed, and published records",
        "actions": "Export a run summary. No arbitrary filesystem read.",
        "provider": "Task 04 journal through the composed rehearsal and task 29 ledger",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g04",
        "blocker": "The team log list is still proposed-1 / proposed_pending_team.",
    },
    {
        "id": "05",
        "title": "Implement bounded asynchronous operation execution",
        "ui": "Mission control and Commands",
        "data": "Active step, soft wait, hard deadline, pending worker, cleanup",
        "actions": "Extend a wait or retry only when the step controller allows it.",
        "provider": "patrol.ground.steps.StepSession",
        "status": "Verified using simulation",
        "evidence": "tests/ground/integration/test_step_control.py",
        "blocker": "Deadlines are simulation-clock values unless a live transport exists.",
    },
    {
        "id": "06",
        "title": "Implement JPEG evidence and provenance validation",
        "ui": "Vision and evidence",
        "data": "Frame hash, JPEG check, provenance, rejection. Phone incident image is not the primary camera.",
        "actions": "Open an allowlisted JPEG only.",
        "provider": "Task 06 evidence port and task 14 frame checks",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g06",
        "blocker": "Live camera bytes are not connected.",
    },
    {
        "id": "07",
        "title": "Implement responsive command input and scoped confirmation primitives",
        "ui": "Persistent header",
        "data": "Status, arm, start, supervised, halt, reset, quit, and why each is enabled",
        "actions": "Those seven commands. Halt has no confirmation dialog.",
        "provider": "Operator policy rechecked on every mutation",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g07",
        "blocker": "v1 arrived and flight-ready confirmations are not v2 controls.",
    },
    {
        "id": "08",
        "title": "Implement adapter selection, guarded calls, and connection lifecycle gateway",
        "ui": "Devices and readiness",
        "data": "Fake, real, unavailable, or disarmed for dog, drone, Pi, and Grok",
        "actions": "No connect button that opens hardware from the browser.",
        "provider": "Base adapter gateway inside the composed rehearsal",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g08",
        "blocker": "Real adapter factories are not supplied. Real mode stays refused.",
    },
    {
        "id": "09",
        "title": "Implement the fixed mission workflow and extension composition",
        "ui": "Mission control",
        "data": "One active worker, provider trace, and v2 phase history",
        "actions": "Start is rejected while a worker is active.",
        "provider": "patrol.ground.demo composed providers",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g09 and tests/ground/integration/test_composed_demo.py",
        "blocker": "Task 09's v1 phone workflow is not the active drone-first phase source.",
    },
    {
        "id": "10",
        "title": "Implement halt supervision, cleanup, shutdown, and safe reset primitives",
        "ui": "Header on every screen",
        "data": "Halt latch, safety schedule, cleanup, recovery token, disarmed reset",
        "actions": "Halt immediately. Reset only under the recovery rule.",
        "provider": "Task 10 safety.request",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g10",
        "blocker": "A safety schedule is not proof of a physical stop.",
    },
    {
        "id": "11",
        "title": "Validate v2 envelopes and keep the v1 robot contract unchanged",
        "ui": "Logs inspector",
        "data": "Protocol 2.0-draft, message id, epoch, per-publisher seq, correlation, rejection",
        "actions": "None. Invalid envelopes remain provider rejections.",
        "provider": "feature.v2_envelope",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g11",
        "blocker": "Protocol 2.0-draft is not the legacy Python v1 contract.",
    },
    {
        "id": "12",
        "title": "Admit device capabilities and arm only reported features",
        "ui": "Devices and readiness",
        "data": "Reported features, admission result, motion_permission false at admission",
        "actions": "Arm is a separate operator action and still does not grant motors.",
        "provider": "feature.v2_capabilities",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g12",
        "blocker": "Capability flags in fixtures are synthetic and not physical acceptance.",
    },
    {
        "id": "13",
        "title": "Ingest drone observations and preserve height reference",
        "ui": "Mission control and Devices",
        "data": "Flight state, altitude, height reference, beacon, battery when present",
        "actions": "None.",
        "provider": "feature.v2_drone_observation",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g13",
        "blocker": "No live Tello telemetry. Unknown height stays unknown.",
    },
    {
        "id": "14",
        "title": "Check camera epoch, frame provenance, and image bytes",
        "ui": "Vision and evidence",
        "data": "Camera, frame id, camera epoch, capture time, calibration id, hash, simulated flag",
        "actions": "Inspect the JPEG for that frame id.",
        "provider": "feature.v2_frame",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g14",
        "blocker": "Downward camera support is not hardware-verified.",
    },
    {
        "id": "15",
        "title": "Schedule vision requests and drop stale frames",
        "ui": "Vision and evidence",
        "data": "Latest request, in-flight wait, dropped or stale frame, timeout budget",
        "actions": "None. The scheduler decides. The page does not invent a request.",
        "provider": "feature.v2_vision_schedule",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g15",
        "blocker": "Live frame rate is not measured here.",
    },
    {
        "id": "16",
        "title": "Validate xAI decisions and withhold motor authority",
        "ui": "Vision and evidence",
        "data": "Model id, prompt, decision, uncertainty or reason, track, proposal, rejection",
        "actions": "None. A decision cannot move a motor from this screen.",
        "provider": "feature.v2_vision_decision",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g16",
        "blocker": "The model id is a placeholder until a verified model is configured. No live xAI call.",
    },
    {
        "id": "17",
        "title": "Approve one bounded drone primitive at a time",
        "ui": "Commands and safety",
        "data": "One approved primitive, guard result, supervised withhold",
        "actions": "Supervised mode withholds the primitive when controlled motion is false.",
        "provider": "feature.v2_drone_command",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g17",
        "blocker": "Directional drone control is unverified. No raw motor control is exposed.",
    },
    {
        "id": "18",
        "title": "Track drone acknowledgements and preserve unknown landing",
        "ui": "Commands and safety",
        "data": "Accepted, running, and completed ACKs, unknown landing, no automatic repeat",
        "actions": "None.",
        "provider": "feature.v2_drone_ack",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g18",
        "blocker": "An accepted ACK is not completed execution and is not a physical landing.",
    },
    {
        "id": "19",
        "title": "Require a stable beacon hold and advance beacon epoch after motion",
        "ui": "Navigation and RSSI",
        "data": "Beacon id, epoch, hold, stability, dog motion blocked while the drone moves",
        "actions": "None.",
        "provider": "feature.v2_beacon",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g19",
        "blocker": "Beacon measurements in rehearsal are synthetic.",
    },
    {
        "id": "20",
        "title": "Accept dog navigation health and safe local candidates",
        "ui": "Navigation and RSSI",
        "data": "Navigation mode, pose, map identity, candidates, blocks, clearance. No drawn map without map data.",
        "actions": "None. Ground does not run a new SLAM stack.",
        "provider": "feature.v2_dog_navigation",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g20",
        "blocker": "Map rasters are not published. Candidate lists are not a map.",
    },
    {
        "id": "21",
        "title": "Validate Raspberry Pi RSSI windows sampled on the dog",
        "ui": "Navigation and RSSI",
        "data": "Heartbeat, dBm samples, quality, age, comparability, clock bounds",
        "actions": "None.",
        "provider": "feature.v2_rssi",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g21",
        "blocker": "The Pi path is not a live radio. RSSI is not distance.",
    },
    {
        "id": "22",
        "title": "Choose an RSSI step only from safe dog candidates",
        "ui": "Navigation and RSSI",
        "data": "Selected candidate, explanation, stop reason, no-progress and budgets when reported",
        "actions": "None.",
        "provider": "feature.v2_rssi_homing",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g22",
        "blocker": "Selection in simulation is not a field homing trial.",
    },
    {
        "id": "23",
        "title": "Issue leased dog commands and a priority halt",
        "ui": "Commands and safety",
        "data": "Lease, expiry, candidate id, halt priority",
        "actions": "Header halt uses the priority safety path.",
        "provider": "feature.v2_dog_command and task 10",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g23",
        "blocker": "Lease expiry does not by itself prove the dog stopped.",
    },
    {
        "id": "24",
        "title": "Track dog acknowledgements and rejected steps",
        "ui": "Commands and safety",
        "data": "Accepted, running, completed, rejected, and verified stationary",
        "actions": "None. Expired motion is not repeated from the UI.",
        "provider": "feature.v2_dog_ack",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g24",
        "blocker": "Verified stationary in a fixture is not a hardware measurement.",
    },
    {
        "id": "25",
        "title": "Hand the dog from RSSI to its own camera",
        "ui": "Vision and Navigation",
        "data": "Same track, handoff mode, review when the target is ambiguous",
        "actions": "None.",
        "provider": "feature.v2_dog_acquire",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g25",
        "blocker": "Dog-camera identity is not hardware-verified.",
    },
    {
        "id": "26",
        "title": "Accept the demo goal only from separate proximity evidence",
        "ui": "Mission control",
        "data": "Dog range, drone horizontal offset, thresholds, missing evidence, goal decision",
        "actions": "None. RSSI is not used as arrival.",
        "provider": "feature.v2_proximity",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g26",
        "blocker": "Venue thresholds are unset. Fixture numbers are illustrations.",
    },
    {
        "id": "27",
        "title": "Separate demo-goal completion from landing recovery",
        "ui": "Mission header",
        "data": "Goal reached, landing verified, recovery required, unknown landing",
        "actions": "Reset cannot clear an unknown landing without the recovery path.",
        "provider": "feature.v2_recovery",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g27",
        "blocker": "Goal reached does not mean landed.",
    },
    {
        "id": "28",
        "title": "Halt, drop the link, and expire leases without waiting for Grok",
        "ui": "Commands and safety",
        "data": "Halt, link loss, stale evidence, lease expiry, late model result",
        "actions": "Halt does not wait for vision.",
        "provider": "feature.v2_safety",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g28",
        "blocker": "A late model result cannot clear the latch.",
    },
    {
        "id": "29",
        "title": "Journal v2 messages and keep the proposed team log schema",
        "ui": "Runs and logs",
        "data": "Correlation fields, proposed-1 schema, pending team status, writer failure",
        "actions": "Filter and export. Schema status stays provisional.",
        "provider": "feature.v2_logs",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g29",
        "blocker": "The final team log list has not arrived.",
    },
    {
        "id": "30",
        "title": "Check Ethernet, Wi-Fi, and the Pi data path before arming",
        "ui": "Devices and readiness",
        "data": "Selected profile, tether or Wi-Fi acceptance, simultaneous link notes, Pi path",
        "actions": "Choose ethernet or wifi in settings. No automatic handover.",
        "provider": "feature.v2_links",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g30",
        "blocker": "Ethernet is the available dog connection in this project. Acceptance files are synthetic.",
    },
    {
        "id": "31",
        "title": "Compute demo timings and leave unknown values empty",
        "ui": "Runs and mission metrics",
        "data": "Measured intervals and null metrics with reasons, including model accuracy",
        "actions": "None. Missing values are not drawn as zero.",
        "provider": "feature.v2_metrics",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g31",
        "blocker": "Timings from simulation are not hardware acceptance.",
    },
    {
        "id": "32",
        "title": "Rehearse the drone-first demo offline and write the operator script",
        "ui": "Rehearsal and task coverage",
        "data": "Scenario result, artifacts, runbook links, fault injections",
        "actions": "Select a scenario, start, inspect, and reset. Replay is read-only.",
        "provider": "Composed rehearsal and feature.v2_rehearsal fixtures",
        "status": "Verified using simulation",
        "evidence": "tests/ground/g32 and demo/script.md",
        "blocker": "Offline rehearsal does not establish robot or flight readiness.",
    },
)


def coverage_payload() -> Json:
    return {
        "states": [
            "Specified",
            "Implemented",
            "Independently tested",
            "Integrated into the composed application",
            "Verified using simulation",
            "Verified using real hardware",
        ],
        "hardware": "Not verified using real hardware.",
        "rows": list(ROWS),
    }


def render_markdown() -> str:
    header = """# Ground Mission Control coverage

This matrix is the operator-console coverage of Tasks 01–32. A screen existing
is not the same thing as a completed task. Status values stay distinct:

- Specified.
- Implemented.
- Independently tested.
- Integrated into the composed application.
- Verified using simulation.
- Verified using real hardware.

No row is verified on hardware. Live v2 transports are not supplied, and the
operator API refuses real mode instead of substituting simulation.
`tests/ground/operator` runs the composed providers in simulation. That is not
hardware acceptance.

| Task ID | Actual task title | UI location | Data displayed | Allowed actions | Backend provider | Current integration status | Verification evidence | Remaining blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
"""
    lines = [header.rstrip(), ""]
    for row in ROWS:
        cells = [
            row["id"],
            row["title"],
            row["ui"],
            row["data"],
            row["actions"],
            row["provider"],
            row["status"],
            row["evidence"],
            row["blocker"],
        ]
        lines.append("| " + " | ".join(str(cell).replace("|", "/") for cell in cells) + " |")
    lines.append("")
    return "\n".join(lines)


def write_coverage(path: Path | None = None) -> Path:
    target = path or (repo_root() / "docs" / "ground" / "ui-coverage.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_markdown(), encoding="utf-8")
    return target
