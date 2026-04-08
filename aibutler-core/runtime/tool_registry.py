#!/usr/bin/env python3
"""
aiButler tool registry.

This merges the local tool modules into one typed manifest so voice, desktop,
and future phone/watch surfaces all speak to the same execution spine.
"""
from __future__ import annotations

from runtime.models import ApprovalPolicy, ToolSpec
from tools.computer_use import TOOLS as COMPUTER_USE_TOOLS
from tools.file_ops import TOOLS as FILE_TOOLS
from tools.secrets import TOOLS as SECRET_TOOLS
from tools.life_data import TOOLS as LIFE_DATA_TOOLS
from tools.context_tools import TOOLS as CONTEXT_TOOLS
from tools.relationship_tools import TOOLS as RELATIONSHIP_TOOLS
from tools.rtk_tools import TOOLS as RTK_TOOLS

DEFAULT_TOOL_META = {
    "category": "general",
    "capability": "general",
    "read_only": False,
    "risk": "low",
    "reversible": True,
    "approval": ApprovalPolicy(required=False),
}

TOOL_META = {
    "convert_image": {
        "category": "files",
        "capability": "file_ops",
    },
    "convert_video": {
        "category": "files",
        "capability": "file_ops",
    },
    "extract_audio": {
        "category": "files",
        "capability": "file_ops",
    },
    "images_to_pdf": {
        "category": "files",
        "capability": "file_ops",
    },
    "pdf_to_images": {
        "category": "files",
        "capability": "file_ops",
    },
    "zip_files": {
        "category": "files",
        "capability": "file_ops",
    },
    "unzip": {
        "category": "files",
        "capability": "file_ops",
    },
    "tar_gz": {
        "category": "files",
        "capability": "file_ops",
    },
    "untar": {
        "category": "files",
        "capability": "file_ops",
    },
    "remove_background": {
        "category": "files",
        "capability": "file_ops",
    },
    "crop_image": {
        "category": "files",
        "capability": "file_ops",
    },
    "resize_image": {
        "category": "files",
        "capability": "file_ops",
    },
    "annotate_image": {
        "category": "files",
        "capability": "file_ops",
    },
    "draw_rectangle": {
        "category": "files",
        "capability": "file_ops",
    },
    "add_arrow": {
        "category": "files",
        "capability": "file_ops",
    },
    "extract_frame": {
        "category": "files",
        "capability": "file_ops",
    },
    "file_info": {
        "category": "files",
        "capability": "file_ops",
        "read_only": True,
    },
    "save_secret": {
        "category": "secrets",
        "capability": "secrets",
        "risk": "high",
        "reversible": False,
        "approval": ApprovalPolicy(required=True, reason="writes secure credentials"),
    },
    "get_secret": {
        "category": "secrets",
        "capability": "secrets",
        "read_only": True,
        "risk": "high",
        "reversible": False,
        "approval": ApprovalPolicy(required=True, reason="reveals secure credentials"),
    },
    "delete_secret": {
        "category": "secrets",
        "capability": "secrets",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="deletes secure credentials"),
    },
    "list_secrets": {
        "category": "secrets",
        "capability": "secrets",
        "read_only": True,
        "risk": "medium",
        "approval": ApprovalPolicy(required=True, reason="enumerates secure credentials"),
    },
    "save_clipboard_as": {
        "category": "secrets",
        "capability": "secrets",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="stores clipboard contents as a secret"),
    },
    "auto_capture_keys": {
        "category": "secrets",
        "capability": "secrets",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="scans clipboard history for keys"),
    },
    "secret_recovery_status": {
        "category": "secrets",
        "capability": "secrets",
        "read_only": True,
        "risk": "medium",
    },
    "rehydrate_missing_secrets": {
        "category": "secrets",
        "capability": "secrets",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="restores missing credentials from clipboard history"),
    },
    "get_clipboard": {
        "category": "clipboard",
        "capability": "clipboard",
        "read_only": True,
        "risk": "medium",
    },
    "get_clipboard_history": {
        "category": "clipboard",
        "capability": "clipboard",
        "read_only": True,
        "risk": "medium",
    },
    "preflight_computer_use": {
        "category": "computer_use",
        "capability": "screen_read",
        "read_only": True,
        "risk": "low",
    },
    "open_accessibility_settings": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "low",
    },
    "open_screen_recording_settings": {
        "category": "computer_use",
        "capability": "screen_read",
        "risk": "low",
    },
    "get_mouse_position": {
        "category": "computer_use",
        "capability": "screen_read",
        "read_only": True,
        "risk": "low",
    },
    "capture_screen": {
        "category": "computer_use",
        "capability": "screen_read",
        "read_only": True,
        "risk": "medium",
        "reversible": False,
    },
    "move_mouse": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "medium",
    },
    "click_at": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="performs a live screen click", live_only=True),
    },
    "right_click_at": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="performs a live right-click", live_only=True),
    },
    "double_click_at": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="performs a live double-click", live_only=True),
    },
    "type_text": {
        "category": "computer_use",
        "capability": "keyboard_act",
        "risk": "high",
        "reversible": False,
        "approval": ApprovalPolicy(required=True, reason="types into the frontmost app", live_only=True),
    },
    "press_key": {
        "category": "computer_use",
        "capability": "keyboard_act",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="sends live keypresses", live_only=True),
    },
    "drag_mouse": {
        "category": "computer_use",
        "capability": "screen_act",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="performs a live drag", live_only=True),
    },
    "calendar_list_events": {
        "category": "life_data",
        "capability": "life_data",
        "read_only": True,
        "risk": "medium",
    },
    "calendar_create_event": {
        "category": "life_data",
        "capability": "life_data",
        "risk": "high",
        "approval": ApprovalPolicy(required=True, reason="creates a calendar event"),
    },
    "contacts_search": {
        "category": "life_data",
        "capability": "life_data",
        "read_only": True,
        "risk": "medium",
    },
    "contacts_list": {
        "category": "life_data",
        "capability": "life_data",
        "read_only": True,
        "risk": "medium",
    },
    "photos_recent": {
        "category": "life_data",
        "capability": "life_data",
        "read_only": True,
        "risk": "medium",
    },
    "reminders_list": {
        "category": "life_data",
        "capability": "life_data",
        "read_only": True,
        "risk": "low",
    },
    "reminders_add": {
        "category": "life_data",
        "capability": "life_data",
        "risk": "medium",
        "approval": ApprovalPolicy(required=True, reason="creates a reminder"),
    },
    "capture_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
        "reversible": False,
    },
    "capture_context_artifact": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
        "reversible": False,
    },
    "list_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "context_review_queue": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "promote_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
        "reversible": False,
    },
    "defer_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
    },
    "dismiss_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
    },
    "restore_pending_context": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
    },
    "list_context_sheets": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "context_activity_feed": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "context_graph_snapshot": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "pin_context_ref": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
    },
    "butler_memory_status": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "butler_memory_index": {
        "category": "context",
        "capability": "context_memory",
        "risk": "low",
        "reversible": False,
    },
    "butler_memory_search": {
        "category": "context",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "openscreen_status": {
        "category": "capture",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "openscreen_list_sessions": {
        "category": "capture",
        "capability": "context_memory",
        "read_only": True,
        "risk": "low",
    },
    "openscreen_launch": {
        "category": "capture",
        "capability": "context_memory",
        "risk": "low",
    },
    "openscreen_import_session": {
        "category": "capture",
        "capability": "context_memory",
        "risk": "low",
        "reversible": False,
    },
    "relationship_log_interaction": {
        "category": "relationship",
        "capability": "relationship_memory",
        "risk": "low",
        "reversible": False,
    },
    "relationship_list_followups": {
        "category": "relationship",
        "capability": "relationship_memory",
        "read_only": True,
        "risk": "low",
    },
    "relationship_get_briefing": {
        "category": "relationship",
        "capability": "relationship_memory",
        "read_only": True,
        "risk": "low",
    },
    "relationship_import_contacts": {
        "category": "relationship",
        "capability": "relationship_memory",
        "risk": "medium",
    },
    "relationship_ingest_phone_metadata": {
        "category": "relationship",
        "capability": "relationship_memory",
        "risk": "low",
        "reversible": False,
    },
    "rtk_status": {
        "category": "integrations",
        "capability": "general",
        "read_only": True,
        "risk": "low",
    },
    "rtk_rewrite_preview": {
        "category": "integrations",
        "capability": "general",
        "read_only": True,
        "risk": "low",
    },
    "rtk_gain_summary": {
        "category": "integrations",
        "capability": "general",
        "read_only": True,
        "risk": "low",
    },
    "install_rtk_openclaw_plugin": {
        "category": "integrations",
        "capability": "general",
        "risk": "medium",
        "approval": ApprovalPolicy(required=True, reason="installs OpenClaw plugin files into the local user profile"),
    },
}


def _iter_raw_tools() -> dict:
    from runtime.plugins import get_plugin_manager
    plugin_tools = get_plugin_manager().get_all_tools()
    return {
        **FILE_TOOLS,
        **SECRET_TOOLS,
        **COMPUTER_USE_TOOLS,
        **LIFE_DATA_TOOLS,
        **CONTEXT_TOOLS,
        **RELATIONSHIP_TOOLS,
        **RTK_TOOLS,
        **plugin_tools,
    }


def list_tool_specs() -> list[ToolSpec]:
    """Return the typed tool manifest for all local Butler tools."""
    specs: list[ToolSpec] = []
    for name, raw in _iter_raw_tools().items():
        meta = {**DEFAULT_TOOL_META, **TOOL_META.get(name, {})}
        approval = meta.get("approval")
        if not isinstance(approval, ApprovalPolicy):
            approval = ApprovalPolicy(**approval)

        specs.append(
            ToolSpec(
                name=name,
                category=meta["category"],
                capability=meta["capability"],
                description=raw["description"],
                params=raw["params"],
                read_only=meta["read_only"],
                risk=meta["risk"],
                reversible=meta["reversible"],
                approval=approval,
            )
        )
    return sorted(specs, key=lambda spec: (spec.category, spec.name))


def build_tool_registry() -> dict[str, dict]:
    """Return the raw callable tool registry for execution."""
    return _iter_raw_tools()
