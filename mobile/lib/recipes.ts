interface QuickActionRecipeBase {
  id: string;
  label: string;
  summary: string;
  requiresPairing?: boolean;
}

export type QuickActionRecipe =
  | (QuickActionRecipeBase & {
      mode: "agentic";
      objective: string;
    })
  | (QuickActionRecipeBase & {
      mode: "assist";
      prompt: string;
    });

export const RECIPES = {
  "daily-brief": {
    id: "daily-brief",
    label: "Daily Brief",
    summary: "Calendar, pending work, and the highest-priority follow-ups in one pass.",
    requiresPairing: true,
    mode: "agentic",
    objective: "Generate my daily executive briefing with calendar events, pending tasks, and highest-priority follow-ups.",
  },
  "pipeline-sweep": {
    id: "pipeline-sweep",
    label: "Pipeline Sweep",
    summary: "Review the best people to move today and surface the next recommended touch.",
    requiresPairing: true,
    mode: "agentic",
    objective: "Review my contacts and open threads, then identify the next best people to follow up with today.",
  },
  "inbox-triage": {
    id: "inbox-triage",
    label: "Inbox Triage",
    summary: "Show messages that need replies, approvals, or delegation instead of dumping a generic summary.",
    requiresPairing: true,
    mode: "agentic",
    objective: "Draft a concise inbox triage plan with messages that need replies, approvals, or delegation.",
  },
  "bring-butler-online": {
    id: "bring-butler-online",
    label: "Bring Butler Online",
    summary: "Check what intelligence is offline and stage safe recovery from local secrets and Maccy history.",
    requiresPairing: true,
    mode: "assist",
    prompt: "Bring Butler back online by checking core secret status and restoring recoverable intelligence credentials from Maccy.",
  },
  "enable-operator-stack": {
    id: "enable-operator-stack",
    label: "Enable Operator Stack",
    summary: "Check OpenClaw on the paired Mac, install it if needed, and bring the gateway online for Butler.",
    requiresPairing: true,
    mode: "assist",
    prompt: "Get OpenClaw online on this Mac by checking the operator stack, installing OpenClaw if needed, and installing the gateway.",
  },
} satisfies Record<string, QuickActionRecipe>;

export type RecipeId = keyof typeof RECIPES;
