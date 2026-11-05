import type { RssiPoint } from "./types";

export function rssiSeries(points: RssiPoint[]): RssiPoint[] {
  return points.filter((point) => typeof point.rssi_dbm === "number" && Number.isFinite(point.rssi_dbm));
}

export function mapAvailable(navigation: { map_renderable?: boolean } | null): boolean {
  return navigation?.map_renderable === true;
}
