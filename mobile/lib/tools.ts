/**
 * ElevenLabs tool definitions — mirrors voice.py TOOL_DEFINITIONS.
 * Used by ConversationProvider to declare callable tools to the agent.
 */
export const TOOL_DEFINITIONS = [
  {
    type: "function",
    function: {
      name: "preflight_computer_use",
      description: "Check whether local macOS computer use tools and permissions are ready.",
      parameters: { type: "object", properties: {} },
    },
  },
  {
    type: "function",
    function: {
      name: "secret_recovery_status",
      description: "Check which core Butler intelligence secrets are online or recoverable from Maccy, without revealing secret values.",
      parameters: {
        type: "object",
        properties: {
          required: {
            type: "array",
            items: { type: "string" },
            description: "Optional subset of secret names to inspect.",
          },
          limit: {
            type: "integer",
            description: "How many recent Maccy clipboard items to inspect.",
            default: 50,
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "rehydrate_missing_secrets",
      description: "Restore missing Butler intelligence secrets from Maccy clipboard history into Keychain.",
      parameters: {
        type: "object",
        properties: {
          required: {
            type: "array",
            items: { type: "string" },
            description: "Optional subset of secret names to restore.",
          },
          limit: {
            type: "integer",
            description: "How many recent Maccy clipboard items to inspect.",
            default: 50,
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "rtk_status",
      description: "Check whether RTK and Butler's vendored OpenClaw rewrite plugin are installed and ready.",
      parameters: {
        type: "object",
        properties: {},
      },
    },
  },
  {
    type: "function",
    function: {
      name: "install_rtk_openclaw_plugin",
      description: "Install Butler's vendored RTK rewrite plugin into the local OpenClaw extensions directory.",
      parameters: {
        type: "object",
        properties: {
          target_dir: {
            type: "string",
            description: "Optional override for the destination plugin directory.",
          },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "capture_screen",
      description: "Capture a screenshot of the current screen and return the saved file path.",
      parameters: {
        type: "object",
        properties: {
          dst: { type: "string", description: "Destination path for the screenshot" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "get_mouse_position",
      description: "Return the current mouse cursor position.",
      parameters: { type: "object", properties: {} },
    },
  },
  {
    type: "function",
    function: {
      name: "move_mouse",
      description: "Move the mouse to an absolute screen position on macOS.",
      parameters: {
        type: "object",
        properties: {
          x: { type: "integer", description: "Absolute x coordinate" },
          y: { type: "integer", description: "Absolute y coordinate" },
          dry_run: { type: "boolean", description: "Preview without executing" },
        },
        required: ["x", "y"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "click_at",
      description: "Click at an absolute screen position on macOS.",
      parameters: {
        type: "object",
        properties: {
          x: { type: "integer" },
          y: { type: "integer" },
          button: { type: "string", default: "left" },
          clicks: { type: "integer", default: 1 },
          dry_run: { type: "boolean" },
        },
        required: ["x", "y"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "type_text",
      description: "Type text into the frontmost macOS application when keyboard use is enabled.",
      parameters: {
        type: "object",
        properties: {
          text: { type: "string", description: "Text to type" },
          dry_run: { type: "boolean" },
        },
        required: ["text"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "press_key",
      description: "Press a key with optional modifiers (cmd, shift, ctrl).",
      parameters: {
        type: "object",
        properties: {
          key: { type: "string" },
          modifiers: { type: "array", items: { type: "string" } },
          dry_run: { type: "boolean" },
        },
        required: ["key"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "drag_mouse",
      description: "Drag from one screen coordinate to another on macOS.",
      parameters: {
        type: "object",
        properties: {
          start_x: { type: "integer" },
          start_y: { type: "integer" },
          end_x: { type: "integer" },
          end_y: { type: "integer" },
          dry_run: { type: "boolean" },
        },
        required: ["start_x", "start_y", "end_x", "end_y"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "convert_image",
      description: "Convert an image between formats (jpg, png, tiff, webp, pdf). Can also resize.",
      parameters: {
        type: "object",
        properties: {
          src: { type: "string" },
          dst: { type: "string" },
          quality: { type: "integer", default: 90 },
          resize: { type: "string" },
        },
        required: ["src", "dst"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "remove_background",
      description: "Remove the background from an image using AI.",
      parameters: {
        type: "object",
        properties: {
          src: { type: "string" },
          dst: { type: "string" },
        },
        required: ["src"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "zip_files",
      description: "Create a zip archive from files or folders.",
      parameters: {
        type: "object",
        properties: {
          paths: { type: "array", items: { type: "string" } },
          dst: { type: "string" },
        },
        required: ["paths", "dst"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "convert_video",
      description: "Convert video between formats (mp4, mkv, webm, avi, mov).",
      parameters: {
        type: "object",
        properties: {
          src: { type: "string" },
          dst: { type: "string" },
          resolution: { type: "string" },
        },
        required: ["src", "dst"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "extract_audio",
      description: "Extract audio from a video file as mp3, m4a, wav, flac, or ogg.",
      parameters: {
        type: "object",
        properties: {
          src: { type: "string" },
          dst: { type: "string" },
          fmt: { type: "string", default: "mp3" },
        },
        required: ["src", "dst"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "extract_frame",
      description: "Extract a single frame/screenshot from a video at a specific time.",
      parameters: {
        type: "object",
        properties: {
          src: { type: "string" },
          dst: { type: "string" },
          timestamp: { type: "string", default: "00:00:01" },
        },
        required: ["src", "dst"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "file_info",
      description: "Get metadata about a file: size, format, dimensions, duration.",
      parameters: {
        type: "object",
        properties: { path: { type: "string" } },
        required: ["path"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "calendar_list_events",
      description: "List upcoming calendar events.",
      parameters: {
        type: "object",
        properties: { days: { type: "integer", default: 7 } },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "contacts_search",
      description: "Search contacts by name.",
      parameters: {
        type: "object",
        properties: { query: { type: "string" } },
        required: ["query"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "capture_pending_context",
      description: "Capture a receipt, note, or ambiguous item into the pending context queue for later review.",
      parameters: {
        type: "object",
        properties: {
          capture_kind: { type: "string", description: "receipt, note, person, place, artifact, or other capture type" },
          title: { type: "string", description: "Short label for the captured item" },
          content: { type: "string", description: "Optional notes, OCR, or quick context" },
          confidence: { type: "number", description: "Model or user confidence from 0 to 1" },
          place_ref: { type: "string", description: "Optional linked place reference" },
        },
        required: ["capture_kind", "title"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "list_pending_context",
      description: "List the latest pending context items that still need clarification or review.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 10 },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "context_review_queue",
      description: "Return a combined review queue for pending context items and relationship follow-ups.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 20 },
          include_relationships: { type: "boolean", default: true },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "promote_pending_context",
      description: "Promote a pending context item into Butler's canonical memory and mark it reviewed.",
      parameters: {
        type: "object",
        properties: {
          pending_id: { type: "string", description: "The pending item id to promote" },
          kind: { type: "string", description: "Optional explicit target kind such as person, artifact, or task" },
          title: { type: "string", description: "Optional replacement title for the promoted item" },
          note: { type: "string", description: "Optional review note to preserve with the promotion" },
        },
        required: ["pending_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "defer_pending_context",
      description: "Defer a pending context item until later so it drops out of the active review lane.",
      parameters: {
        type: "object",
        properties: {
          pending_id: { type: "string", description: "The pending item id to defer" },
          defer_until: { type: "string", description: "Optional ISO timestamp to revisit the item" },
          defer_for_days: { type: "integer", description: "Optional number of days to defer the item" },
          note: { type: "string", description: "Optional note about why the item was deferred" },
        },
        required: ["pending_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "dismiss_pending_context",
      description: "Dismiss a pending context item from the active review lane.",
      parameters: {
        type: "object",
        properties: {
          pending_id: { type: "string", description: "The pending item id to dismiss" },
          note: { type: "string", description: "Optional note about why the item was dismissed" },
        },
        required: ["pending_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "restore_pending_context",
      description: "Restore a deferred or dismissed pending context item back into the active review lane.",
      parameters: {
        type: "object",
        properties: {
          pending_id: { type: "string", description: "The pending item id to restore" },
          note: { type: "string", description: "Optional note about the restore decision" },
        },
        required: ["pending_id"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "context_activity_feed",
      description: "Return a diary-style LIFO activity feed built from Butler context events and pinned records.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 25 },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "context_graph_snapshot",
      description: "Return a relationship-first context map snapshot that connects people, pending review, and recent signals.",
      parameters: {
        type: "object",
        properties: {
          relationship_limit: { type: "integer", default: 6 },
          pending_limit: { type: "integer", default: 4 },
          signal_limit: { type: "integer", default: 5 },
          pin_limit: { type: "integer", default: 4 },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "butler_memory_search",
      description: "Search Butler's long-horizon memory for people, decisions, captures, and context tied to the prompt.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "What to search for in Butler memory" },
          limit: { type: "integer", default: 5 },
          wing: { type: "string", description: "Optional memory wing filter such as people, pending, or events" },
          room: { type: "string", description: "Optional room filter within the chosen wing" },
        },
        required: ["query"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "pin_context_ref",
      description: "Pin or unpin a person, pending item, or other context ref so it stays easy to find.",
      parameters: {
        type: "object",
        properties: {
          ref: { type: "string", description: "Context ref such as people/sarah-chen or pending/item-id" },
          pinned: { type: "boolean", default: true },
          label: { type: "string", description: "Optional display label for the pin" },
          note: { type: "string", description: "Optional note to keep with the pin" },
        },
        required: ["ref"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "relationship_ingest_phone_metadata",
      description: "Ingest structured call-log or SMS metadata into Butler's relationship graph and follow-up state.",
      parameters: {
        type: "object",
        properties: {
          person_name: { type: "string", description: "Resolved person name, phone number, or best identifier" },
          channel: { type: "string", description: "call or text" },
          direction: { type: "string", description: "inbound, outbound, or two-way" },
          phone_number: { type: "string", description: "Phone number for the signal when available" },
          summary: { type: "string", description: "Human-readable summary of the phone signal" },
          next_action: { type: "string", description: "Optional suggested next action" },
          due_date: { type: "string", description: "Optional due label such as today or tomorrow" },
          duration_seconds: { type: "integer", description: "Call duration when available" },
          occurred_at: { type: "string", description: "ISO timestamp for when the signal happened" },
          thread_id: { type: "string", description: "SMS thread id when available" },
          external_event_id: { type: "string", description: "Stable source record id for deduping repeat syncs" },
          call_status: { type: "string", description: "Incoming, outgoing, missed, voicemail, or other call type" },
          snippet: { type: "string", description: "Optional preview text from an SMS thread" },
          source_surface: { type: "string", description: "Source lane such as android.call_log or android.sms" },
        },
        required: ["person_name", "channel", "summary"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "relationship_log_interaction",
      description: "Record a relationship interaction and update the CRM follow-up graph.",
      parameters: {
        type: "object",
        properties: {
          person_name: { type: "string", description: "The person you interacted with" },
          company: { type: "string", description: "Optional company or org" },
          role: { type: "string", description: "Optional role or title" },
          channel: { type: "string", description: "How the interaction happened, for example call, text, email, or in-person" },
          summary: { type: "string", description: "What happened in the interaction" },
          next_action: { type: "string", description: "The next task or reply to take" },
          due_date: { type: "string", description: "Optional ISO date or human-readable due date" },
          urgency: { type: "string", description: "Optional urgency label such as low, medium, high, or critical" },
          place_name: { type: "string", description: "Optional place name for where the interaction happened" },
          place_ref: { type: "string", description: "Optional canonical place ref if already known" },
          conversation_label: { type: "string", description: "Optional thread, deal, meeting, or conversation label" },
          conversation_ref: { type: "string", description: "Optional canonical conversation ref if already known" },
        },
        required: ["person_name", "channel", "summary", "next_action"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "relationship_list_followups",
      description: "List relationship follow-up items in priority order.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 10 },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "relationship_get_briefing",
      description: "Return a relationship briefing object for today's priorities and follow-ups.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 8 },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "relationship_import_contacts",
      description: "Import trusted desktop contacts into Butler's canonical people graph to bootstrap the CRM.",
      parameters: {
        type: "object",
        properties: {
          limit: { type: "integer", default: 200 },
          query: { type: "string", description: "Optional filter by contact name" },
        },
      },
    },
  },
];

export const SYSTEM_PROMPT = `You are aiButler — a voice-first AI assistant running locally on the user's Mac.

You are simultaneously:
- A personal secretary (scheduling, reminders, messages)
- An admin assistant (file management, format conversion, organization)
- A strategic officer (research, analysis, planning)
- A junior employee (execute tasks precisely as instructed)
- A senior researcher (deep investigation, synthesis)

You have access to local tools via the desktop bridge:
- Computer use (mouse, keyboard, screen capture) — requires explicit approval
- File conversion and compression (images, video, audio, PDF)
- Background removal from images (AI-powered)
- Photo editing: crop, resize, annotate
- Clipboard and secrets management
- Calendar events and contacts
- YouTube video downloading

When the user asks you to do something:
1. Confirm what you're about to do (briefly)
2. Execute using the appropriate tool
3. Report the result

Keep responses short and natural — you're a voice assistant.
Speak like a capable colleague, not a robot.`;
