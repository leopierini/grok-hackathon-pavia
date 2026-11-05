import type { ActionState, Snapshot } from "./types";

export function haltSkipsConfirmation(): boolean {
  return true;
}

export function requiresRecoveryToken(mission: Snapshot["mission"]): boolean {
  return !(mission.goal_reached && mission.landing_verified && !mission.recovery_required);
}

export function controlState(actions: Snapshot["actions"] | undefined, name: string): ActionState {
  const state = actions?.[name];
  if (!state) return { enabled: false, reason: "The operator API has not reported this action." };
  return state;
}
