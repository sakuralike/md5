import type { OperationalSettingsSnapshot } from "@password-detective/api-contract";
import { toRaw } from "vue";

export function cloneOperationalSettingsSnapshot(
  snapshot: OperationalSettingsSnapshot,
): OperationalSettingsSnapshot {
  return structuredClone(toRaw(snapshot));
}
