"use client";

import { useSession } from "@/components/provider";
import { KeyValue, Panel, ReadinessList, StatusText } from "@/components/ui";

export function DevicesSession() {
  const { snapshot } = useSession();
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Simultaneous links, adapter cards, and readiness appear when the Ground API answers.</p>;
  return (
    <div className="space-y-3">
      <Panel title="Simultaneous links">
        <ul className="space-y-2 text-sm">
          {snapshot.links.map((link) => (
            <li key={link.name}>
              <span className="font-medium">{link.name}</span> · {link.medium ?? "unset"}
              <p className="text-muted">{link.detail}</p>
            </li>
          ))}
        </ul>
      </Panel>
      <div className="grid gap-3 xl:grid-cols-2">
        {Object.values(snapshot.devices).map((device) => (
          <Panel key={device.role} title={device.name}>
            <p className="mb-2 flex flex-wrap gap-2">
              <StatusText status={device.connection} />
              <StatusText status={device.provenance} />
              <StatusText status={String(device.mode)} detail="adapter mode" />
            </p>
            <KeyValue
              rows={[
                { label: "Profile", value: device.profile },
                { label: "Last observation", value: device.last_observation_at },
                { label: "Error", value: device.error },
                { label: "Note", value: device.detail },
                ...Object.entries(device.telemetry ?? {}).map(([label, value]) => ({ label, value })),
              ]}
            />
          </Panel>
        ))}
      </div>
      <Panel title="Readiness">
        <ReadinessList checks={snapshot.readiness} />
      </Panel>
    </div>
  );
}
