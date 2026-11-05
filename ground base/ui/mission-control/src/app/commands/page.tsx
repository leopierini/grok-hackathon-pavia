import { Slide13 } from "@/slides/s13-commands";
import { SessionDrawer } from "@/components/session-drawer";
import { CommandsSession } from "@/components/legacy/commands-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Command session">
        <CommandsSession />
      </SessionDrawer>
      <Slide13 />
    </>
  );
}
