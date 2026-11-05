"use client";

import { evidenceIsStale, sameFrame } from "@/lib/evidence";
import { formatAge, formatUnknown } from "@/lib/format";
import { groundPath } from "@/lib/api";
import { DogSensors } from "@/components/dog-sensors";
import { useSession } from "@/components/provider";
import { DataTable, Panel, StatusText } from "@/components/ui";

export function VisionSession() {
  const { snapshot } = useSession();
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Vision requests, decisions, and snapshots appear when the Ground API answers.</p>;
  const decisionFrame = typeof snapshot.vision.decision?.frame_id === "string" ? snapshot.vision.decision.frame_id : null;
  return (
    <div className="space-y-3">
      <DogSensors />
      <Panel title="Current vision">
        <p className="text-sm">Model {formatUnknown(snapshot.vision.model_id)} · prompt {formatUnknown(snapshot.vision.prompt_version)}</p>
        <p className="text-sm">{snapshot.vision.waiting ? "Grok response is outstanding." : "No vision request is marked in flight."}</p>
        <p className="text-sm text-muted">{snapshot.vision.latency_note}</p>
        <pre className="mt-2 overflow-auto rounded bg-surface-2 p-2 text-xs">{JSON.stringify({ request: snapshot.vision.request, decision: snapshot.vision.decision, proposal: snapshot.vision.proposal }, null, 2)}</pre>
      </Panel>
      <div className="grid gap-3 lg:grid-cols-2">
        {snapshot.evidence.length === 0 ? <p className="text-sm text-muted">No camera snapshots in this session.</p> : null}
        {snapshot.evidence.map((frame) => {
          const stale = evidenceIsStale(frame);
          const related = sameFrame(decisionFrame, frame.frame_id);
          return (
            <Panel key={frame.frame_id} title={`${frame.camera_id ?? "camera"} snapshot`}>
              <p className="mb-2 flex flex-wrap gap-2">
                <StatusText status={stale} />
                <StatusText status={frame.provenance ?? "unknown"} detail={frame.media ?? "snapshot"} />
                {related ? <StatusText status="present" detail="matches the decision frame" /> : null}
              </p>
              {frame.image_ref ? (
                // Evidence is a same-origin artifact, not an optimized remote image.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={groundPath(`evidence?artifact_id=${encodeURIComponent(frame.image_ref)}`)}
                  alt={`${frame.source ?? "device"} ${frame.camera_id ?? "camera"} snapshot ${frame.frame_id}`}
                  className="mb-2 max-h-60 border border-line"
                />
              ) : (
                <p className="text-sm text-muted">No image reference for this frame. No bounding box is drawn.</p>
              )}
              <DataTable
                caption={`Frame ${frame.frame_id}`}
                headers={["Field", "Value"]}
                rows={[
                  ["Source", formatUnknown(frame.source)],
                  ["Frame", frame.frame_id],
                  ["Camera epoch", formatUnknown(frame.camera_epoch)],
                  ["Captured", formatUnknown(frame.captured_at)],
                  ["Age", formatAge(frame.age_ms)],
                  ["Stale reason", frame.stale_reason],
                  ["Calibration", formatUnknown(frame.calibration_id)],
                  ["SHA-256", formatUnknown(frame.sha256)],
                  ["Validation", frame.validation_status],
                ]}
              />
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
