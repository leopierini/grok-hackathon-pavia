"use client";

import { executionLabel } from "@/lib/commands";
import { formatUnknown } from "@/lib/format";
import { useSession } from "@/components/provider";
import { DataTable, Panel, StatusText } from "@/components/ui";

export function CommandsSession() {
  const { snapshot, run } = useSession();
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. The command chain, acknowledgements, and step controls appear when the Ground API answers.</p>;
  const steps = snapshot.safety.step_control?.steps ?? [];
  const active = steps.find((step) => step.step_id === snapshot.safety.step_control?.active_step_id) ?? steps.at(-1);
  return (
    <div className="space-y-3">
      <Panel title="Command chain">
        <ol className="flex flex-wrap gap-2">
          {snapshot.chain.map((step) => (
            <li key={step.id}>
              <StatusText status={step.state} detail={step.label} />
            </li>
          ))}
        </ol>
      </Panel>
      <Panel title="Commands">
        <DataTable
          caption="Command lifecycle"
          headers={["Command", "Action", "Lease ms", "Lifecycle", "Note", "ACKs"]}
          rows={snapshot.commands.map((command) => [
            formatUnknown(command.command_id),
            formatUnknown(command.action),
            formatUnknown(command.lease_ms),
            command.lifecycle,
            executionLabel(command),
            command.acks.map((ack) => ack.state).join(", ") || "none",
          ])}
        />
      </Panel>
      <Panel title="Step controller">
        <p className="text-sm text-muted">Soft wait and hard deadline come from the Ground step session. Retry does not invent a motor command.</p>
        {active ? (
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-line px-3 py-2 text-sm"
              disabled={!active.allowed_actions?.wait_more}
              onClick={() =>
                void run("status").then(() =>
                  fetch("/api/ground/steps/command", {
                    method: "POST",
                    headers: { "content-type": "application/json" },
                    body: JSON.stringify({
                      action: "wait_more",
                      request_id: `wait-${snapshot.cursor}`,
                      expected_revision: snapshot.safety.step_control?.revision,
                      step_id: active.step_id,
                      attempt_id: active.attempts?.at(-1)?.attempt_id,
                      seconds: 2,
                      session_epoch: snapshot.session_epoch,
                    }),
                  }),
                )
              }
            >
              Wait longer
            </button>
            <button
              type="button"
              className="rounded border border-line px-3 py-2 text-sm"
              disabled={!active.allowed_actions?.retry}
              onClick={() =>
                void fetch("/api/ground/steps/command", {
                  method: "POST",
                  headers: { "content-type": "application/json" },
                  body: JSON.stringify({
                    action: "retry",
                    request_id: `retry-${snapshot.cursor}`,
                    expected_revision: snapshot.safety.step_control?.revision,
                    step_id: active.step_id,
                    attempt_id: active.attempts?.at(-1)?.attempt_id,
                    session_epoch: snapshot.session_epoch,
                  }),
                })
              }
            >
              Retry if allowed
            </button>
          </div>
        ) : (
          <p className="text-sm text-muted">No step is active.</p>
        )}
        <DataTable
          caption="Steps"
          headers={["Step", "Status", "Reason"]}
          rows={steps.map((step) => [step.label, step.status, step.reason || "none"])}
        />
      </Panel>
      <Panel title="Safety">
        <p className="text-sm">Halt latched: {snapshot.safety.halt_latched ? "yes" : "no"}. Accepted: {snapshot.safety.halt_accepted ? "yes" : "no"}. Delivered: {formatUnknown(snapshot.safety.halt_delivered)}.</p>
        <p className="text-sm text-muted">{snapshot.safety.reason || "No safety reason recorded."}</p>
        <ul className="mt-2 text-sm">
          {snapshot.safety.late_model.map((note, index) => (
            <li key={index}>{note.detail}</li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
