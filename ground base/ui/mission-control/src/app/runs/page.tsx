import { Slide21 } from "@/slides/s21-runs";
import { SessionDrawer } from "@/components/session-drawer";
import { RunsSession } from "@/components/legacy/runs-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Run journal session">
        <RunsSession />
      </SessionDrawer>
      <Slide21 />
    </>
  );
}
