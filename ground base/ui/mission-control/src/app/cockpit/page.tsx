import { Slide02 } from "@/slides/s02-cockpit";
import { SessionDrawer } from "@/components/session-drawer";
import { HomeSession } from "@/components/legacy/home-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Patrol, cable check, and dog steps">
        <HomeSession />
      </SessionDrawer>
      <Slide02 />
    </>
  );
}
