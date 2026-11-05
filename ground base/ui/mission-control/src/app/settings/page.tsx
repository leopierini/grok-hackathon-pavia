import { Slide05 } from "@/slides/s05-settings";
import { SessionDrawer } from "@/components/session-drawer";
import { SettingsSession } from "@/components/legacy/settings-session";

export default function Page() {
  return (
    <>
      <SessionDrawer title="Connection settings session">
        <SettingsSession />
      </SessionDrawer>
      <Slide05 />
    </>
  );
}
