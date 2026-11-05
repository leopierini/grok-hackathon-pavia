"use client";

import Link from "next/link";
import { DogSensors } from "@/components/dog-sensors";
import { useSession } from "@/components/provider";
import { DataTable, KeyValue, Panel, ReadinessList, StatusText } from "@/components/ui";
import { MotionControls } from "@/components/legacy/motion-controls";

const PHASES = ["IDLE", "CONNECT", "SCOUT", "TRACK", "HOLD", "HOME", "DOG_VISION", "PROXIMITY", "LAND", "DONE", "ABORTED", "FAULT"];

const PHASE_LINKS: Record<string, string> = {
  IDLE: "/cockpit",
  CONNECT: "/devices",
  SCOUT: "/vision",
  TRACK: "/commands",
  HOLD: "/navigation",
  HOME: "/dog",
  DOG_VISION: "/handoff",
  PROXIMITY: "/proximity",
  LAND: "/recovery",
  DONE: "/runs",
  ABORTED: "/halt",
  FAULT: "/halt",
};

function dogStatus(last: Record<string, unknown> | null | undefined): string {
  if (!last) return "No dog command has been sent in this session.";
  if (typeof last.detail === "string") return last.detail;
  const probe = last.probe;
  if (probe && typeof probe === "object" && "reachable" in probe) {
    return probe.reachable === true
      ? "Ethernet answered. No motion was sent."
      : "Ethernet did not answer. The cable check is in the message above.";
  }
  return last.sent === true ? "The dog step was sent." : "The dog step was not sent.";
}

export function HomeSession() {
  const session = useSession();
  const { snapshot, error } = session;
  if (!snapshot) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-muted">The operator session has not connected. These controls send through the Ground API once it answers.</p>
        <MotionControls session={session} />
      </div>
    );
  }
  const mission = snapshot.mission;
  const seen = new Set(mission.phase_history.map((item) => item.phase));
  const demo = snapshot.dog_demo;
  const last = demo?.last;
  return (
    <div className="space-y-3">
      <Panel title="Patrol">
        <p className="text-sm">
          Start patrol runs the whole live demo by itself: the drone takes off and scans, Grok finds the person, the drone hovers and tracks, the dog stands, warns, walks to the person and holds a standoff, and when the person has left the drone lands and the dog lies down. Watch it on <a className="font-semibold underline" href="/live">Live patrol</a>. Halt stops everything at once.
        </p>
        <p className="mt-2 text-sm">{snapshot.patrol?.detail ?? "Patrol is idle."}</p>
        <p className="mt-1 text-sm text-muted">Situation {snapshot.patrol?.situation ?? "awaiting_ai"}. {snapshot.patrol?.summary}</p>
        <ul className="mt-3 space-y-1 text-sm">
          {(snapshot.patrol?.calls ?? []).map((call, index) => (
            <li key={`${call.name}-${index}`}>
              {call.target} {call.name}: {call.sent ? "sent" : "held"}. {call.reason}
            </li>
          ))}
        </ul>
      </Panel>
        <Panel title="Cable check">
        <p className="text-sm">
          These are the cable checks. They send a short <span className="font-mono">move_local</span> step, which is not patrol. The dog step goes out on Ethernet to {demo?.dog ?? "192.168.123.161"} from this laptop at {demo?.laptop ?? "192.168.123.222"}. The drone, pictures, and RSSI stay scripts.
        </p>
        <p className="mt-2 text-sm text-muted">{demo?.pi}</p>
        <MotionControls session={session} />
        <p className="mt-2 text-sm text-muted">The cable check only looks. The step buttons use the speeds above, and those speeds stay under the dog&apos;s own limits. Practice does not use the cable.</p>
        {error ? <p className="mt-3 rounded bg-bad-bg px-3 py-2 text-sm text-bad">{error}</p> : null}
        <p className="mt-3 text-sm">{dogStatus(last)}</p>
        <StepList last={last} />
      </Panel>
      <DogSensors />
      <div className="space-y-6">
      <Panel title="Where the run is">
        <ol className="flex flex-wrap gap-2">
          {PHASES.map((phase) => (
            <li key={phase}>
              <Link href={PHASE_LINKS[phase]} className="inline-flex min-h-11 items-center rounded-full px-1" aria-label={`Open ${phase}`}>
                <StatusText status={phase === mission.phase ? "pass" : seen.has(phase) ? "present" : "missing"} detail={phase} />
              </Link>
            </li>
          ))}
          <li>
            <Link href="/runs" className="inline-flex min-h-11 items-center rounded-full border border-line px-3 text-sm font-semibold">
              Log
            </Link>
          </li>
        </ol>
        <DataTable
          caption="Phase history"
          headers={["Phase", "Reason", "Time"]}
          rows={mission.phase_history.map((item) => [item.phase, item.reason, item.at ?? "unknown"])}
        />
      </Panel>
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="What Ground is doing">
          <KeyValue
            rows={[
              { label: "Run", value: mission.run_id },
              { label: "Worker", value: mission.worker },
              { label: "Scenario", value: mission.scenario },
              { label: "Foundation phase", value: mission.foundation_phase },
              { label: "Waiting", value: mission.waiting_for },
              { label: "Operation", value: mission.active_operation },
              { label: "Command", value: mission.active_command_id },
              { label: "Mission clock", value: mission.observed_at },
              { label: "Live calls", value: mission.live_call_count },
              { label: "Outcome", value: mission.outcome },
              { label: "Reason", value: mission.reason },
            ]}
          />
          <p className="mt-3 text-sm">{snapshot.next_action}</p>
        </Panel>
        <Panel title="Goal and recovery">
          <p className="text-sm">Goal {mission.goal_reached ? "reached" : "unresolved"}.</p>
          <p className="text-sm">Landing {mission.landing_verified ? "verified" : "not verified"}.</p>
          <p className="text-sm">Recovery {mission.recovery_required ? "required" : "not required"}.</p>
          <p className="mt-2 text-sm text-muted">A reached goal does not mean the drone has landed. Halt acceptance does not mean the robots stopped.</p>
        </Panel>
      </div>
      <Panel title="Readiness blockers">
        <ReadinessList checks={snapshot.readiness} />
      </Panel>
      <Panel title="Activity">
        <DataTable
          caption="Recent activity"
          headers={["Summary", "Severity", "Writer"]}
          rows={snapshot.activity.map((row) => [row.summary ?? "event", row.severity ?? "info", `${row.ledger ?? "feed"} ${row.writer_state ?? "enqueued"}`])}
        />
      </Panel>
      </div>
    </div>
  );
}

function StepList({ last }: { last: Record<string, unknown> | null | undefined }) {
  const steps = last?.steps;
  if (!Array.isArray(steps) || steps.length === 0) return null;
  return (
    <ol className="mt-2 space-y-1 text-sm">
      {steps.map((step, index) => {
        const row = step && typeof step === "object" ? (step as Record<string, unknown>) : {};
        const segment = row.segment && typeof row.segment === "object" ? (row.segment as Record<string, unknown>) : {};
        const name = String(segment.command_id ?? `step ${index + 1}`);
        const stopped = row.stopped === true ? "stopped" : "not stopped";
        return (
          <li key={`${name}-${index}`}>
            {name}: {String(row.detail ?? stopped)}
          </li>
        );
      })}
    </ol>
  );
}
