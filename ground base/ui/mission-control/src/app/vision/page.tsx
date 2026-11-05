import { Slide09 } from "@/slides/s09-vision";
import { SessionDrawer } from "@/components/session-drawer";
import { VisionSession } from "@/components/legacy/vision-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Vision session">
        <VisionSession />
      </SessionDrawer>
      <Slide09 />
    </>
  );
}
