import type { CommandRow } from "./types";

export function executionLabel(command: Pick<CommandRow, "lifecycle" | "execution_note">): string {
  if (command.lifecycle === "accepted") return "Accepted by the device. Execution is not complete.";
  return command.execution_note;
}
