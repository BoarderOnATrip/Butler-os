import type { ModuleId, PhoneMode } from "./modules";
import type { RecipeId } from "./recipes";

export type { PhoneMode } from "./modules";
export type { QuickActionRecipe } from "./recipes";

export interface PhoneSkinManifest {
  id: string;
  name: string;
  tagline: string;
  accent: string;
  defaultMode: PhoneMode;
  moduleIds: ModuleId[];
  recipeIds: RecipeId[];
}

export const PHONE_MODE_META: Record<
  PhoneMode,
  {
    label: string;
    title: string;
    description: string;
  }
> = {
  home: {
    label: "Home",
    title: "Living Brief",
    description: "The one-screen brief. What matters now, who needs you, and what Butler is still unsure about.",
  },
  capture: {
    label: "Capture",
    title: "Low-Friction Ingress",
    description: "Voice, note, photo, and phone-native metadata should enter Butler faster than forgetting does.",
  },
  review: {
    label: "Review",
    title: "Trust Layer",
    description: "Uncertainty stays visible here until it is promoted, deferred, dismissed, or corrected.",
  },
  people: {
    label: "People",
    title: "Relationship Memory",
    description: "People, follow-ups, linked context, and the CRM spine live here without feeling like CRM software.",
  },
  act: {
    label: "Act",
    title: "Execution Surface",
    description: "Pairing, voice, approvals, delegation, and recipes belong here when it is time to move.",
  },
};

const CORE_MODULES: ModuleId[] = [
  "hero_brief",
  "pairing",
  "voice",
  "recipes",
  "review_lane",
  "metadata_results",
  "relationship_ingest",
  "phone_metadata",
  "context_map",
  "journal",
  "capture_pending",
  "conversation_memory",
  "tool_activity",
];

const CORE_RECIPES: RecipeId[] = [
  "daily-brief",
  "pipeline-sweep",
  "inbox-triage",
  "bring-butler-online",
];

export const RAVEN_SKIN: PhoneSkinManifest = {
  id: "raven",
  name: "Raven",
  tagline: "Calm, fast, and slightly uncanny. The phone should feel like a living executive brief.",
  accent: "#7dffd2",
  defaultMode: "home",
  moduleIds: CORE_MODULES,
  recipeIds: CORE_RECIPES,
};

export const FOUNDER_SKIN: PhoneSkinManifest = {
  id: "founder",
  name: "Founder",
  tagline: "Momentum-first. Follow-up, inbox pressure, and pipeline movement rise to the top.",
  accent: "#ff9a62",
  defaultMode: "home",
  moduleIds: [
    "hero_brief",
    "pairing",
    "voice",
    "recipes",
    "review_lane",
    "metadata_results",
    "relationship_ingest",
    "context_map",
    "journal",
    "conversation_memory",
    "tool_activity",
  ],
  recipeIds: CORE_RECIPES,
};

export const BUTLER_LITE_SKIN: PhoneSkinManifest = {
  id: "butler-lite",
  name: "Butler Lite",
  tagline: "Minimal and dependable. Brief, capture, review, then get out of the way.",
  accent: "#9bb7ff",
  defaultMode: "home",
  moduleIds: [
    "hero_brief",
    "pairing",
    "recipes",
    "review_lane",
    "capture_pending",
    "conversation_memory",
  ],
  recipeIds: ["daily-brief", "bring-butler-online"],
};

export const PHONE_SKINS = [RAVEN_SKIN, FOUNDER_SKIN, BUTLER_LITE_SKIN];
export const DEFAULT_PHONE_SKIN = RAVEN_SKIN;
