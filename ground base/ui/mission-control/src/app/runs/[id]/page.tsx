import { Slide21 } from "@/slides/s21-runs";
import { SessionDrawer } from "@/components/session-drawer";
import { RunDetailSession } from "@/components/legacy/run-detail-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Run report">
        <RunDetailSession />
      </SessionDrawer>
      <Slide21 />
    </>
  );
}
