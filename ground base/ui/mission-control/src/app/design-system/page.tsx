import { Slide24 } from "@/slides/s24-system";
import { SessionDrawer } from "@/components/session-drawer";
import { CoverageSession } from "@/components/legacy/coverage-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Task coverage">
        <CoverageSession />
      </SessionDrawer>
      <Slide24 />
    </>
  );
}
