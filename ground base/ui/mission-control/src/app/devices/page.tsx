import { Slide04 } from "@/slides/s04-devices";
import { SessionDrawer } from "@/components/session-drawer";
import { DevicesSession } from "@/components/legacy/devices-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Device session">
        <DevicesSession />
      </SessionDrawer>
      <Slide04 />
    </>
  );
}
