"use client";

import { formatDbm, formatUnknown } from "@/lib/format";
import { mapAvailable } from "@/lib/navigation";
import { useSession } from "@/components/provider";
import { DataTable, Panel, RssiChart, StatusText } from "@/components/ui";

export function NavigationSession() {
  const { snapshot } = useSession();
  if (!snapshot) return <p className="text-sm text-muted">The operator session has not connected. Dog navigation, candidates, and the beacon chart appear when the Ground API answers.</p>;
  const nav = snapshot.navigation;
  return (
    <div className="space-y-3">
      <Panel title="Dog navigation">
        <p className="text-sm">Mode {formatUnknown(nav.navigation_mode)}. {nav.dog_motion_note}</p>
        <p className="text-sm text-muted">{nav.map_reason}</p>
        {mapAvailable(nav) ? <StatusText status="present" detail="map data" /> : <StatusText status="missing" detail="no map to draw" />}
        <p className="mt-2 text-sm">Map {formatUnknown(nav.map_id)} epoch {formatUnknown(nav.map_epoch)}</p>
      </Panel>
      <Panel title="Candidates">
        <DataTable
          caption="Planner candidates"
          headers={["Candidate", "Safe", "Clearance", "Valid until", "Frame"]}
          rows={(nav.candidates ?? []).map((row) => [
            formatUnknown(row.candidate_id),
            formatUnknown(row.safe),
            formatUnknown(row.clearance_m),
            formatUnknown(row.valid_until),
            formatUnknown(row.frame_id),
          ])}
        />
        <p className="mt-2 text-sm">Blocked {formatUnknown(nav.blocked)}. {formatUnknown(nav.candidate_reason)}</p>
      </Panel>
      <Panel title="Beacon and RSSI">
        <p className="text-sm">Beacon epoch {formatUnknown(nav.beacon?.beacon_epoch)} · hold {formatUnknown(nav.beacon?.hold_state)}</p>
        <RssiChart points={nav.rssi_points ?? []} />
        <DataTable
          caption="RSSI windows"
          headers={["Quality", "Epoch", "Median dBm"]}
          rows={(nav.rssi_windows ?? []).map((window) => {
            const row = window as { quality?: string; beacon_epoch?: number; median_rssi_dbm?: number | null };
            return [formatUnknown(row.quality), formatUnknown(row.beacon_epoch), formatDbm(row.median_rssi_dbm ?? null)];
          })}
        />
      </Panel>
    </div>
  );
}
