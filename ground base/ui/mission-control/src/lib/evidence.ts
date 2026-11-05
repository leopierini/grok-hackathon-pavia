import type { EvidenceFrame } from "./types";

export function evidenceIsStale(frame: Pick<EvidenceFrame, "stale">): "stale" | "fresh" | "unknown" {
  if (frame.stale === true) return "stale";
  if (frame.stale === false) return "fresh";
  return "unknown";
}

export function sameFrame(overlayFrameId: string | null, shownFrameId: string | null): boolean {
  return Boolean(overlayFrameId && shownFrameId && overlayFrameId === shownFrameId);
}
