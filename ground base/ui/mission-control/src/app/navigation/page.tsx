import { Slide14 } from "@/slides/s14-beacon";
import { SessionDrawer } from "@/components/session-drawer";
import { NavigationSession } from "@/components/legacy/navigation-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Navigation session">
        <NavigationSession />
      </SessionDrawer>
      <Slide14 />
    </>
  );
}
