export type PhoneMode = "home" | "capture" | "review" | "people" | "act";

export type ModuleId =
  | "hero_brief"
  | "pairing"
  | "operator_stack"
  | "room_workspace"
  | "voice"
  | "recipes"
  | "review_lane"
  | "metadata_results"
  | "relationship_ingest"
  | "phone_metadata"
  | "context_map"
  | "journal"
  | "capture_pending"
  | "conversation_memory"
  | "tool_activity";

export interface PhoneModuleManifest {
  id: ModuleId;
  title: string;
  mode: PhoneMode;
  requiresPairing?: boolean;
  platform?: "all" | "android";
}

export interface ModuleAvailabilityContext {
  desktopPaired: boolean;
  platformOS: string;
}

const PHONE_MODE_ORDER: PhoneMode[] = ["home", "capture", "review", "people", "act"];

export const MODULES: Record<ModuleId, PhoneModuleManifest> = {
  hero_brief: { id: "hero_brief", title: "Today at a glance", mode: "home" },
  pairing: { id: "pairing", title: "Secure Mac pairing", mode: "act" },
  operator_stack: { id: "operator_stack", title: "Operator stack", mode: "act", requiresPairing: true },
  room_workspace: { id: "room_workspace", title: "Canonical rooms", mode: "act", requiresPairing: true },
  voice: { id: "voice", title: "Voice layer", mode: "act" },
  recipes: { id: "recipes", title: "Recipes", mode: "home", requiresPairing: true },
  review_lane: { id: "review_lane", title: "Review lane", mode: "review", requiresPairing: true },
  metadata_results: { id: "metadata_results", title: "Metadata ingest results", mode: "review", requiresPairing: true },
  relationship_ingest: { id: "relationship_ingest", title: "Relationship ingest", mode: "people", requiresPairing: true },
  phone_metadata: { id: "phone_metadata", title: "Android phone metadata", mode: "capture", platform: "android" },
  context_map: { id: "context_map", title: "Context map", mode: "people", requiresPairing: true },
  journal: { id: "journal", title: "Journal", mode: "home", requiresPairing: true },
  capture_pending: { id: "capture_pending", title: "Capture to pending", mode: "capture", requiresPairing: true },
  conversation_memory: { id: "conversation_memory", title: "Conversation memory", mode: "act" },
  tool_activity: { id: "tool_activity", title: "Tool activity", mode: "act", requiresPairing: true },
};

export function moduleIsAvailable(moduleId: ModuleId, context: ModuleAvailabilityContext): boolean {
  const manifest = MODULES[moduleId];
  if (manifest.requiresPairing && !context.desktopPaired) {
    return false;
  }
  if (manifest.platform === "android" && context.platformOS !== "android") {
    return false;
  }
  return true;
}

export function availableModuleIds(
  moduleIds: readonly ModuleId[],
  context: ModuleAvailabilityContext
): ModuleId[] {
  return moduleIds.filter((moduleId) => moduleIsAvailable(moduleId, context));
}

export function modesForModuleIds(moduleIds: readonly ModuleId[]): PhoneMode[] {
  const enabled = new Set<PhoneMode>(moduleIds.map((moduleId) => MODULES[moduleId].mode));
  return PHONE_MODE_ORDER.filter((mode) => enabled.has(mode));
}
