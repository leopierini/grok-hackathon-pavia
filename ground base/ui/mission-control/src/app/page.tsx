import { Slide01 } from "@/slides/s01-mission";
import { SessionDrawer } from "@/components/session-drawer";
import { HomeSession } from "@/components/legacy/home-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Patrol, cable check, and dog steps">
        <HomeSession />
      </SessionDrawer>
      <Slide01 />
    </>
  );
}
