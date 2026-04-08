#!/usr/bin/env python3
"""
aiButler Voice Client — ElevenLabs Conversational AI + Claude brain.

This is the core voice loop:
  Mic → ElevenLabs STT → Claude (via OpenClaw) → ElevenLabs TTS → Speaker

Requires:
  - ELEVENLABS_API_KEY env var
  - pip install elevenlabs

Usage:
  python voice.py
"""
import os
import sys
import json
import signal
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path.home() / ".aibutler" / "config.json"


def _load_local_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _get_saved_secret(name: str) -> str:
    try:
        from tools.secrets import get_secret

        return get_secret(name) or ""
    except Exception:
        return ""


CONFIG = _load_local_config()
ELEVENLABS_API_KEY = (
    os.environ.get("ELEVENLABS_API_KEY", "")
    or _get_saved_secret("elevenlabs")
    or CONFIG.get("ELEVENLABS_API_KEY", "")
)
AGENT_ID = (
    os.environ.get("AIBUTLER_AGENT_ID", "")
    or CONFIG.get("AIBUTLER_AGENT_ID", "")
    or CONFIG.get("ELEVENLABS_AGENT_ID", "")
)
RUNTIME_SESSION_ID = os.environ.get("AIBUTLER_RUNTIME_SESSION_ID", "") or CONFIG.get("AIBUTLER_RUNTIME_SESSION_ID", "")
RUNTIME_USER_ID = os.environ.get("AIBUTLER_USER_ID", "local-user") or CONFIG.get("AIBUTLER_USER_ID", "local-user")

# The system prompt that defines aiButler's personality and capabilities
SYSTEM_PROMPT = """You are aiButler — a voice-first AI assistant running locally on the user's machine.

You are simultaneously:
- A personal secretary (scheduling, reminders, messages)
- An admin assistant (file management, format conversion, organization)
- A strategic officer (research, analysis, planning)
- A junior employee (execute tasks precisely as instructed)
- A senior researcher (deep investigation, synthesis)

You have access to these local tools via OpenClaw:
- File conversion: jpg, png, tiff, pdf, webp, mp4, mp3, m4a, wav
- Compression: zip, tar.gz, unzip, untar
- Background removal from images (AI-powered)
- Photo editing: crop, resize, annotate, draw rectangles/arrows
- Video: extract frames, convert formats, extract audio
- Screen recording and screenshots
- Supervised computer use on macOS: inspect the screen, move the mouse, click, drag, type, and press keys when explicitly enabled
- Clipboard management
- YouTube video downloading (yt-dlp)

When the user asks you to do something:
1. Confirm what you're about to do (briefly)
2. Execute using the appropriate tool
3. Report the result

Keep responses short and natural — you're a voice assistant, not a chatbot.
Speak like a capable colleague, not a robot.
"""

# Tool definitions for ElevenLabs agent (Claude function calling)
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "preflight_computer_use",
            "description": "Check whether local macOS computer use tools and permissions are ready.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "secret_recovery_status",
            "description": "Check which core Butler intelligence secrets are online or recoverable from Maccy, without revealing secret values.",
            "parameters": {
                "type": "object",
                "properties": {
                    "required": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subset of secret names to inspect, such as openai or anthropic.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many recent Maccy clipboard items to inspect.",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rehydrate_missing_secrets",
            "description": "Restore missing Butler intelligence secrets from Maccy clipboard history into Keychain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "required": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional subset of secret names to restore.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "How many recent Maccy clipboard items to inspect.",
                        "default": 50,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_screen",
            "description": "Capture a screenshot of the current screen and return the saved file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dst": {"type": "string", "description": "Destination path for the screenshot"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mouse_position",
            "description": "Return the current mouse cursor position.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_mouse",
            "description": "Move the mouse to an absolute screen position on macOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Absolute x coordinate"},
                    "y": {"type": "integer", "description": "Absolute y coordinate"},
                    "dry_run": {"type": "boolean", "description": "Preview the action without executing it"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_at",
            "description": "Click at an absolute screen position on macOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Absolute x coordinate"},
                    "y": {"type": "integer", "description": "Absolute y coordinate"},
                    "button": {"type": "string", "description": "left or right", "default": "left"},
                    "clicks": {"type": "integer", "description": "1 for single click, 2 for double click", "default": 1},
                    "dry_run": {"type": "boolean", "description": "Preview the action without executing it"},
                },
                "required": ["x", "y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text into the frontmost macOS application when keyboard use is enabled.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "dry_run": {"type": "boolean", "description": "Preview the action without executing it"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press a key, optionally with modifiers like cmd, shift, or ctrl.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "A cliclick-supported key like return, tab, esc, or arrow-down"},
                    "modifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional modifiers such as cmd, shift, ctrl, alt",
                    },
                    "dry_run": {"type": "boolean", "description": "Preview the action without executing it"},
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drag_mouse",
            "description": "Drag from one screen coordinate to another on macOS.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_x": {"type": "integer", "description": "Start x coordinate"},
                    "start_y": {"type": "integer", "description": "Start y coordinate"},
                    "end_x": {"type": "integer", "description": "End x coordinate"},
                    "end_y": {"type": "integer", "description": "End y coordinate"},
                    "dry_run": {"type": "boolean", "description": "Preview the action without executing it"},
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_image",
            "description": "Convert an image between formats (jpg, png, tiff, webp, pdf). Can also resize.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source file path"},
                    "dst": {"type": "string", "description": "Destination file path"},
                    "quality": {"type": "integer", "description": "Quality 1-100", "default": 90},
                    "resize": {"type": "string", "description": "Resize dimensions e.g. '1920x1080' or '50%'"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_background",
            "description": "Remove the background from an image using AI",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source image path"},
                    "dst": {"type": "string", "description": "Output path (default: adds _nobg suffix)"},
                },
                "required": ["src"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "zip_files",
            "description": "Create a zip archive from files or folders",
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {"type": "array", "items": {"type": "string"}, "description": "Files/dirs to zip"},
                    "dst": {"type": "string", "description": "Output zip file path"},
                },
                "required": ["paths", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unzip",
            "description": "Extract a zip archive",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Zip file path"},
                    "dst_dir": {"type": "string", "description": "Extract to this directory"},
                },
                "required": ["src"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_video",
            "description": "Convert video between formats (mp4, mkv, webm, avi, mov)",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source video path"},
                    "dst": {"type": "string", "description": "Destination video path"},
                    "resolution": {"type": "string", "description": "Target resolution e.g. '1920:1080'"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_audio",
            "description": "Extract audio from a video file as mp3, m4a, wav, flac, or ogg",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source video path"},
                    "dst": {"type": "string", "description": "Output audio path"},
                    "fmt": {"type": "string", "description": "Audio format: mp3, m4a, wav, flac, ogg", "default": "mp3"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_frame",
            "description": "Extract a single frame/screenshot from a video at a specific time",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source video path"},
                    "dst": {"type": "string", "description": "Output image path"},
                    "timestamp": {"type": "string", "description": "Time in HH:MM:SS or seconds", "default": "00:00:01"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Get metadata about a file: size, format, dimensions, duration",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to inspect"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "annotate_image",
            "description": "Add text annotation to an image",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source image path"},
                    "dst": {"type": "string", "description": "Output image path"},
                    "text": {"type": "string", "description": "Text to add"},
                    "position": {"type": "array", "items": {"type": "integer"}, "description": "[x, y] position"},
                    "color": {"type": "string", "description": "Text color", "default": "red"},
                    "font_size": {"type": "integer", "description": "Font size", "default": 24},
                },
                "required": ["src", "dst", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resize_image",
            "description": "Resize an image. Maintains aspect ratio if only width or height given.",
            "parameters": {
                "type": "object",
                "properties": {
                    "src": {"type": "string", "description": "Source image path"},
                    "dst": {"type": "string", "description": "Output image path"},
                    "width": {"type": "integer", "description": "Target width in pixels"},
                    "height": {"type": "integer", "description": "Target height in pixels"},
                },
                "required": ["src", "dst"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "butler_memory_search",
            "description": "Search Butler's long-horizon memory for people, decisions, captures, and context tied to the prompt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for in Butler memory"},
                    "limit": {"type": "integer", "description": "Maximum number of matches to return", "default": 5},
                    "wing": {"type": "string", "description": "Optional memory wing filter such as people, pending, or events"},
                    "room": {"type": "string", "description": "Optional room filter within the chosen wing"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "context_review_queue",
            "description": "Return a combined review queue for pending context items and relationship follow-ups.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of review items", "default": 20},
                    "include_relationships": {"type": "boolean", "description": "Include relationship follow-ups too", "default": True},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "promote_pending_context",
            "description": "Promote a pending context item into Butler's canonical memory and mark it reviewed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pending_id": {"type": "string", "description": "Pending item id to promote"},
                    "kind": {"type": "string", "description": "Optional target kind such as person or artifact"},
                    "title": {"type": "string", "description": "Optional replacement title"},
                    "note": {"type": "string", "description": "Optional review note"},
                },
                "required": ["pending_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "defer_pending_context",
            "description": "Defer a pending context item so it leaves the active review queue until later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pending_id": {"type": "string", "description": "Pending item id to defer"},
                    "defer_until": {"type": "string", "description": "Optional ISO timestamp"},
                    "defer_for_days": {"type": "integer", "description": "Optional days to defer"},
                    "note": {"type": "string", "description": "Optional defer note"},
                },
                "required": ["pending_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dismiss_pending_context",
            "description": "Dismiss a pending context item from the active review queue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pending_id": {"type": "string", "description": "Pending item id to dismiss"},
                    "note": {"type": "string", "description": "Optional dismissal note"},
                },
                "required": ["pending_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "restore_pending_context",
            "description": "Restore a deferred or dismissed pending context item back into the active review queue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pending_id": {"type": "string", "description": "Pending item id to restore"},
                    "note": {"type": "string", "description": "Optional restore note"},
                },
                "required": ["pending_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "relationship_ingest_phone_metadata",
            "description": "Ingest structured call-log or SMS metadata into Butler's relationship graph and follow-up state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "person_name": {"type": "string", "description": "Best available person identifier"},
                    "channel": {"type": "string", "description": "call or text"},
                    "direction": {"type": "string", "description": "inbound, outbound, or two-way"},
                    "phone_number": {"type": "string", "description": "Phone number when available"},
                    "summary": {"type": "string", "description": "Short description of the phone signal"},
                    "next_action": {"type": "string", "description": "Optional suggested next action"},
                    "due_date": {"type": "string", "description": "Optional due label such as today or tomorrow"},
                    "duration_seconds": {"type": "integer", "description": "Call duration if known"},
                    "occurred_at": {"type": "string", "description": "ISO timestamp for when the signal happened"},
                    "thread_id": {"type": "string", "description": "SMS thread id when available"},
                    "external_event_id": {"type": "string", "description": "Stable source record id for deduping repeat syncs"},
                    "call_status": {"type": "string", "description": "Incoming, outgoing, missed, voicemail, or other call type"},
                    "snippet": {"type": "string", "description": "Optional SMS preview text"},
                    "source_surface": {"type": "string", "description": "Source lane such as android.call_log or android.sms"},
                },
                "required": ["person_name", "channel", "summary"],
            },
        },
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Tool Executor — bridges voice commands to file_ops
# ──────────────────────────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict) -> str:
    """Execute a tool by name with given arguments. Returns result as string."""
    from runtime.engine import get_default_runtime

    runtime = get_default_runtime()
    session = runtime.get_or_create_session(
        session_id=RUNTIME_SESSION_ID or None,
        user_id=RUNTIME_USER_ID,
        surface="voice",
        metadata={"agent_id": AGENT_ID or "unset"},
    )
    try:
        result = runtime.execute_tool(session.id, name, args, actor="voice")
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})


# ──────────────────────────────────────────────────────────────────────────────
# Voice Loop — ElevenLabs Conversational AI
# ──────────────────────────────────────────────────────────────────────────────

def start_voice_loop():
    """Start the ElevenLabs conversational voice loop."""
    global RUNTIME_SESSION_ID
    if not ELEVENLABS_API_KEY:
        print("\n  No ElevenLabs API key found.")
        print("  Save it in Keychain with the desktop onboarding flow or set:")
        print("  export ELEVENLABS_API_KEY='your-key-here'")
        print()
        print("  Get one at: https://elevenlabs.io/app/settings/api-keys")
        print()
        sys.exit(1)

    from elevenlabs.client import ElevenLabs
    from elevenlabs.conversational_ai.conversation import Conversation
    from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface
    from runtime.engine import get_default_runtime

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    runtime = get_default_runtime()
    voice_session = runtime.get_or_create_session(
        session_id=RUNTIME_SESSION_ID or None,
        user_id=RUNTIME_USER_ID,
        surface="voice",
        metadata={"agent_id": AGENT_ID or "unset"},
    )
    RUNTIME_SESSION_ID = voice_session.id

    # If no agent ID, we need to create one or use the API directly
    if not AGENT_ID:
        print("\n  No ElevenLabs agent configured.")
        print("  Save AIBUTLER_AGENT_ID in ~/.aibutler/config.json through the desktop onboarding flow,")
        print("  or set it manually:")
        print("  export AIBUTLER_AGENT_ID='your-agent-id'")
        print()
        print("  Configure the agent with:")
        print("  - System prompt (see SYSTEM_PROMPT in this file)")
        print("  - Claude as the LLM")
        print("  - Tools defined in TOOL_DEFINITIONS")
        print()
        sys.exit(1)

    def on_tool_call(tool_name: str, tool_args: dict) -> str:
        """Handle tool calls from the AI during conversation."""
        print(f"  [tool] {tool_name}({json.dumps(tool_args, default=str)[:100]}...)")
        result = execute_tool(tool_name, tool_args)
        print(f"  [result] {result[:100]}...")
        return result

    conversation = Conversation(
        client=client,
        agent_id=AGENT_ID,
        requires_auth=False,
        audio_interface=DefaultAudioInterface(),
        callback_tools={name: on_tool_call for name in
                       [t["function"]["name"] for t in TOOL_DEFINITIONS]},
        on_connect=lambda conv_id: print(f"\n  aiButler voice active. (conversation: {conv_id})\n  Speak naturally. Ctrl+C to quit.\n"),
        on_disconnect=lambda: print("\n  Voice session ended."),
        on_error=lambda error: print(f"\n  [error] {error}"),
    )

    # Graceful shutdown
    signal.signal(signal.SIGINT, lambda *_: conversation.end_session())

    print("""
  ┌──────────────────────────────────────┐
  │       aiButler Voice Assistant       │
  │                                      │
  │   Powered by ElevenLabs + Claude     │
  │   Ctrl+C to quit                     │
  └──────────────────────────────────────┘
    """)

    conversation.start_session()
    conversation.wait_for_session_end()


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Add parent dir to path so tools module is importable
    sys.path.insert(0, str(os.path.dirname(os.path.abspath(__file__))))
    start_voice_loop()
