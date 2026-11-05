import { Slide23 } from "@/slides/s23-rehearsal";
import { SessionDrawer } from "@/components/session-drawer";
import { RehearsalSession } from "@/components/legacy/rehearsal-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Rehearsal controls">
        <RehearsalSession />
      </SessionDrawer>
      <Slide23 />
    </>
  );
}
