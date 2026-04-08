#!/usr/bin/env python3
"""
aiButler Life-Data Tools — deep macOS/iOS life integration.

Read-only by default. All write operations require explicit approval.

Capabilities:
  - Calendar events (via AppleScript → Calendar.app)
  - Contacts search (via AppleScript → Contacts.app)
  - Recent photos metadata (via mdls)
  - Reminders (via AppleScript → Reminders.app)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\"", "\\\"")


def _ensure_application_running(app_name: str) -> None:
    try:
        subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
    except Exception:
        pass


def _parse_contact_rows(lines: list[str]) -> list[dict]:
    contacts: list[dict] = []
    for raw in lines:
        parts = [part.strip() for part in raw.split("|||")]
        if not parts or not parts[0]:
            continue
        cleaned = ["" if part.lower() == "missing value" else part for part in parts]
        contacts.append({
            "full_name": cleaned[0] if len(cleaned) > 0 else "",
            "company": cleaned[1] if len(cleaned) > 1 else "",
            "role": cleaned[2] if len(cleaned) > 2 else "",
            "phone": cleaned[3] if len(cleaned) > 3 else "",
            "email": cleaned[4] if len(cleaned) > 4 else "",
        })
    return contacts


# ──────────────────────────────────────────────────────────────────────────────
# Calendar
# ──────────────────────────────────────────────────────────────────────────────

def calendar_list_events(days: int = 7) -> dict:
    """List upcoming calendar events using AppleScript."""
    script = f"""
    tell application "Calendar"
        set eventList to {{}}
        set endDate to (current date) + ({days} * days)
        repeat with aCal in calendars
            set calEvents to (every event of aCal whose start date >= (current date) and start date <= endDate)
            repeat with e in calEvents
                set eventList to eventList & {{{{summary: (summary of e), startDate: ((start date of e) as string), calName: (name of aCal)}}}}
            end repeat
        end repeat
        return eventList
    end tell
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        lines = [l.strip() for l in result.stdout.strip().split(",") if l.strip()]
        return {"ok": True, "output": lines, "error": None}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": "Calendar query timed out"}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def calendar_create_event(title: str, start: str, duration_minutes: int = 60,
                           notes: str = "", calendar: str = "Calendar") -> dict:
    """Create a calendar event. Requires explicit approval (write operation)."""
    script = f"""
    tell application "Calendar"
        tell calendar "{calendar}"
            make new event with properties {{summary:"{title}", start date:(date "{start}"), end date:(date "{start}") + {duration_minutes * 60} seconds, description:"{notes}"}}
        end tell
    end tell
    """
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        return {"ok": True, "output": f"Event '{title}' created", "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Contacts
# ──────────────────────────────────────────────────────────────────────────────

def contacts_search(query: str) -> dict:
    """Search contacts by name using AppleScript."""
    safe_query = _applescript_string(query.strip())
    script = f"""
    tell application "Contacts"
        set matches to people whose name contains "{safe_query}"
        set result to {{}}
        repeat with p in matches
            set pName to name of p
            set pPhone to ""
            if (count of phones of p) > 0 then
                set pPhone to value of item 1 of phones of p
            end if
            set pEmail to ""
            if (count of emails of p) > 0 then
                set pEmail to value of item 1 of emails of p
            end if
            set result to result & {{pName & " | " & pPhone & " | " & pEmail}}
        end repeat
        return result
    end tell
    """
    try:
        _ensure_application_running("Contacts")
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        lines = [l.strip() for l in result.stdout.strip().split(",") if l.strip()]
        return {"ok": True, "output": lines, "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def contacts_list(limit: int = 200, query: str = "") -> dict:
    """List contacts with basic structured fields from macOS Contacts.app."""
    safe_query = _applescript_string(query.strip())
    script = f"""
    tell application "Contacts"
        set resultLines to {{}}
        set maxCount to {int(limit)}
        set queryText to "{safe_query}"
        set matchCount to 0
        repeat with p in people
            set pName to name of p
            if queryText is "" or pName contains queryText then
                set pCompany to ""
                try
                    set pCompany to organization of p
                end try
                set pRole to ""
                try
                    set pRole to job title of p
                end try
                set pPhone to ""
                if (count of phones of p) > 0 then
                    set pPhone to value of item 1 of phones of p
                end if
                set pEmail to ""
                if (count of emails of p) > 0 then
                    set pEmail to value of item 1 of emails of p
                end if
                set end of resultLines to pName & "|||" & pCompany & "|||" & pRole & "|||" & pPhone & "|||" & pEmail
                set matchCount to matchCount + 1
                if matchCount is greater than or equal to maxCount then
                    exit repeat
                end if
            end if
        end repeat
        set AppleScript's text item delimiters to linefeed
        return resultLines as text
    end tell
    """
    try:
        _ensure_application_running("Contacts")
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        lines = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
        return {"ok": True, "output": _parse_contact_rows(lines), "error": None}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": "", "error": "Contacts query timed out"}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Photos
# ──────────────────────────────────────────────────────────────────────────────

def photos_recent(limit: int = 10) -> dict:
    """Get metadata of recent photos using mdls on the Photos library."""
    library = Path.home() / "Pictures" / "Photos Library.photoslibrary"
    if not library.exists():
        return {"ok": False, "output": "", "error": "Photos library not found"}
    try:
        result = subprocess.run(
            ["mdls", "-name", "kMDItemFSName", "-name", "kMDItemContentCreationDate", str(library)],
            capture_output=True, text=True, timeout=10,
        )
        return {"ok": True, "output": result.stdout.strip(), "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Reminders
# ──────────────────────────────────────────────────────────────────────────────

def reminders_list(list_name: str = "Reminders") -> dict:
    """List incomplete reminders from a Reminders list."""
    script = f"""
    tell application "Reminders"
        set theList to list "{list_name}"
        set incompleteReminders to (reminders of theList whose completed is false)
        set result to {{}}
        repeat with r in incompleteReminders
            set result to result & {{name of r}}
        end repeat
        return result
    end tell
    """
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        items = [i.strip() for i in result.stdout.strip().split(",") if i.strip()]
        return {"ok": True, "output": items, "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


def reminders_add(title: str, list_name: str = "Reminders", due_date: str = "") -> dict:
    """Add a reminder. Requires explicit approval."""
    due_part = f", due date:(date \"{due_date}\")" if due_date else ""
    script = f"""
    tell application "Reminders"
        tell list "{list_name}"
            make new reminder with properties {{name:"{title}"{due_part}}}
        end tell
    end tell
    """
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"ok": False, "output": "", "error": result.stderr.strip()}
        return {"ok": True, "output": f"Reminder '{title}' added", "error": None}
    except Exception as e:
        return {"ok": False, "output": "", "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Tool Registry
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = {
    "calendar_list_events": {
        "fn": calendar_list_events,
        "description": "List upcoming calendar events from macOS Calendar.app.",
        "params": {"days": "int=7"},
    },
    "calendar_create_event": {
        "fn": calendar_create_event,
        "description": "Create a calendar event in macOS Calendar.app. Requires approval.",
        "params": {"title": "str", "start": "str (e.g. 'April 5, 2026 at 10:00 AM')", "duration_minutes": "int=60", "notes": "str=''", "calendar": "str='Calendar'"},
    },
    "contacts_search": {
        "fn": contacts_search,
        "description": "Search contacts by name in macOS Contacts.app.",
        "params": {"query": "str"},
    },
    "contacts_list": {
        "fn": contacts_list,
        "description": "List contacts from macOS Contacts.app with structured fields for CRM bootstrap.",
        "params": {"limit": "int=200", "query": "str=''"},
    },
    "photos_recent": {
        "fn": photos_recent,
        "description": "Get metadata of recent photos from the Photos library.",
        "params": {"limit": "int=10"},
    },
    "reminders_list": {
        "fn": reminders_list,
        "description": "List incomplete reminders from a Reminders list.",
        "params": {"list_name": "str='Reminders'"},
    },
    "reminders_add": {
        "fn": reminders_add,
        "description": "Add a reminder to macOS Reminders.app. Requires approval.",
        "params": {"title": "str", "list_name": "str='Reminders'", "due_date": "str=''"},
    },
}
