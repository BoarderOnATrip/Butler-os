#!/usr/bin/env python3
"""
aiButler Secrets Layer — Maccy clipboard bridge + macOS Keychain storage.

Eliminates API key friction:
  - Reads clipboard history from Maccy's SQLite DB
  - Detects API keys by pattern (sk-*, xai-*, anthm-*, etc.)
  - Stores/retrieves secrets via macOS Keychain (encrypted, biometric)
  - Auto-injects into environment for tools that need them

All secrets are stored under the Keychain service "aibutler".
"""
import os
import re
import json
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

KEYCHAIN_SERVICE = "aibutler"
MACCY_DB = Path.home() / "Library/Containers/org.p0deje.Maccy/Data/Library/Application Support/Maccy/Storage.sqlite"

# Known API key patterns: (name, regex pattern)
KEY_PATTERNS = [
    ("elevenlabs",   r"(?:^|\s)(sk_[a-f0-9]{32,})"),
    ("openai",       r"(?:^|\s)(sk-[A-Za-z0-9_-]{20,})"),
    ("anthropic",    r"(?:^|\s)(sk-ant-[A-Za-z0-9_-]{20,})"),
    ("xai",          r"(?:^|\s)(xai-[A-Za-z0-9_-]{20,})"),
    ("github",       r"(?:^|\s)(ghp_[A-Za-z0-9]{36,})"),
    ("github",       r"(?:^|\s)(github_pat_[A-Za-z0-9_]{20,})"),
    ("twilio_sid",   r"(?:^|\s)(AC[a-f0-9]{32})"),
    ("twilio_token", r"(?:^|\s)([a-f0-9]{32})"),  # generic but matches Twilio auth tokens
    ("sendgrid",     r"(?:^|\s)(SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43})"),
    ("stripe",       r"(?:^|\s)(sk_(?:test|live)_[A-Za-z0-9]{24,})"),
    ("airtable",     r"(?:^|\s)(pat[A-Za-z0-9]{14}\.[a-f0-9]{64})"),
    ("bearer_token", r"Bearer\s+([A-Za-z0-9_\-\.]{20,})"),
]

# Map secret names to env vars that tools expect
SECRET_ENV_MAP = {
    "elevenlabs": "ELEVENLABS_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "github": "GITHUB_TOKEN",
    "twilio_sid": "TWILIO_ACCOUNT_SID",
    "twilio_token": "TWILIO_AUTH_TOKEN",
    "sendgrid": "SENDGRID_API_KEY",
    "stripe": "STRIPE_SECRET_KEY",
    "airtable": "AIRTABLE_API_KEY",
}

DEFAULT_INTELLIGENCE_SECRETS = [
    "openai",
    "anthropic",
    "elevenlabs",
    "xai",
]


# ──────────────────────────────────────────────────────────────────────────────
# macOS Keychain — secure storage
# ──────────────────────────────────────────────────────────────────────────────

def save_secret(name: str, value: str) -> dict:
    """Save a secret to macOS Keychain under the aibutler service."""
    name = name.lower().strip()
    # Delete existing entry first (update = delete + add)
    subprocess.run(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name],
        capture_output=True
    )
    result = subprocess.run(
        ["security", "add-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", name,
         "-w", value,
         "-U"],  # Update if exists
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"ok": False, "error": result.stderr.strip()}

    # Also set in current process environment
    env_var = SECRET_ENV_MAP.get(name)
    if env_var:
        os.environ[env_var] = value

    return {"ok": True, "output": f"Saved '{name}' to Keychain", "error": None}


def get_secret(name: str) -> Optional[str]:
    """Retrieve a secret from macOS Keychain."""
    name = name.lower().strip()
    result = subprocess.run(
        ["security", "find-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def delete_secret(name: str) -> dict:
    """Remove a secret from macOS Keychain."""
    name = name.lower().strip()
    result = subprocess.run(
        ["security", "delete-generic-password",
         "-s", KEYCHAIN_SERVICE, "-a", name],
        capture_output=True, text=True
    )
    env_var = SECRET_ENV_MAP.get(name)
    if env_var and env_var in os.environ:
        del os.environ[env_var]

    if result.returncode != 0:
        return {"ok": False, "error": f"Secret '{name}' not found"}
    return {"ok": True, "output": f"Deleted '{name}'", "error": None}


def list_secrets() -> dict:
    """List all aibutler secrets stored in Keychain (names only, not values)."""
    result = subprocess.run(
        ["security", "dump-keychain"],
        capture_output=True, text=True
    )
    secrets = []
    in_aibutler = False
    current_name = None
    for line in result.stdout.split('\n'):
        if f'"svce"<blob>="{KEYCHAIN_SERVICE}"' in line:
            in_aibutler = True
        if in_aibutler and '"acct"<blob>="' in line:
            match = re.search(r'"acct"<blob>="([^"]+)"', line)
            if match:
                secrets.append(match.group(1))
            in_aibutler = False

    return {"ok": True, "output": secrets, "error": None}


def inject_all_secrets():
    """Load all stored secrets into environment variables."""
    loaded = []
    for name, env_var in SECRET_ENV_MAP.items():
        value = get_secret(name)
        if value:
            os.environ[env_var] = value
            loaded.append(f"{name} → ${env_var}")

    # Also load any custom-named secrets
    all_secrets = list_secrets()
    for name in all_secrets.get("output", []):
        if name not in SECRET_ENV_MAP:
            value = get_secret(name)
            if value:
                env_key = f"AIBUTLER_{name.upper()}"
                os.environ[env_key] = value
                loaded.append(f"{name} → ${env_key}")

    return {"ok": True, "output": loaded, "error": None}


def _normalize_secret_names(required: Optional[list[str]] = None) -> list[str]:
    names = required or DEFAULT_INTELLIGENCE_SECRETS
    normalized: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


# ──────────────────────────────────────────────────────────────────────────────
# Maccy Clipboard Bridge — read history, detect keys
# ──────────────────────────────────────────────────────────────────────────────

def get_clipboard() -> str:
    """Get current clipboard contents."""
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    return result.stdout


def get_clipboard_history(limit: int = 20) -> list:
    """Read recent clipboard entries from Maccy's SQLite database."""
    if not MACCY_DB.exists():
        return []

    try:
        conn = sqlite3.connect(f"file:{MACCY_DB}?mode=ro", uri=True)
        cursor = conn.execute("""
            SELECT h.Z_PK, h.ZTITLE, h.ZAPPLICATION,
                   datetime(h.ZLASTCOPIEDAT + 978307200, 'unixepoch', 'localtime') as copied_at
            FROM ZHISTORYITEM h
            ORDER BY h.ZLASTCOPIEDAT DESC
            LIMIT ?
        """, (limit,))
        entries = []
        for row in cursor:
            entries.append({
                "id": row[0],
                "preview": (row[1] or "")[:200],
                "app": row[2] or "",
                "time": row[3],
            })
        conn.close()
        return entries
    except Exception as e:
        return [{"error": str(e)}]


def detect_keys_in_clipboard(limit: int = 50) -> list:
    """Scan Maccy clipboard history for anything that looks like an API key."""
    history = get_clipboard_history(limit)
    found = []

    for entry in history:
        text = entry.get("preview", "")
        for key_name, pattern in KEY_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                # Filter out obviously non-key matches (too short, common words)
                if len(match) < 20:
                    continue
                found.append({
                    "type": key_name,
                    "value_preview": match[:8] + "..." + match[-4:],
                    "full_value": match,
                    "source_app": entry.get("app", ""),
                    "copied_at": entry.get("time", ""),
                })

    # Deduplicate by value
    seen = set()
    unique = []
    for f in found:
        if f["full_value"] not in seen:
            seen.add(f["full_value"])
            unique.append(f)

    return unique


def save_clipboard_as(name: str) -> dict:
    """Save current clipboard contents as a named secret in Keychain."""
    value = get_clipboard()
    if not value.strip():
        return {"ok": False, "error": "Clipboard is empty"}
    return save_secret(name, value.strip())


def auto_capture_keys() -> dict:
    """Scan clipboard history, detect API keys, and offer to save them."""
    detected = detect_keys_in_clipboard()
    if not detected:
        return {"ok": True, "output": "No API keys detected in clipboard history", "error": None}

    saved = []
    for key in detected:
        # Check if already stored
        existing = get_secret(key["type"])
        if existing == key["full_value"]:
            continue  # Already saved

        result = save_secret(key["type"], key["full_value"])
        if result["ok"]:
            saved.append(f"{key['type']}: {key['value_preview']}")

    if not saved:
        return {"ok": True, "output": f"Found {len(detected)} key(s), all already saved", "error": None}

    return {
        "ok": True,
        "output": f"Auto-captured {len(saved)} key(s): " + ", ".join(saved),
        "error": None,
    }


def secret_recovery_status(required: Optional[list[str]] = None, limit: int = 50) -> dict:
    """Report whether Butler's core intelligence secrets are present or recoverable."""
    names = _normalize_secret_names(required)
    detected = detect_keys_in_clipboard(limit)
    detected_types = {entry["type"] for entry in detected if entry.get("type")}

    statuses = []
    for name in names:
        env_var = SECRET_ENV_MAP.get(name, f"AIBUTLER_{name.upper()}")
        stored = get_secret(name) is not None
        env_present = bool(os.environ.get(env_var))
        recoverable = name in detected_types
        statuses.append(
            {
                "name": name,
                "env_var": env_var,
                "stored": stored,
                "env_present": env_present,
                "recoverable_from_maccy": recoverable,
                "ready": stored or env_present,
            }
        )

    ready_count = sum(1 for item in statuses if item["ready"])
    recoverable_count = sum(1 for item in statuses if item["recoverable_from_maccy"])
    missing = [item["name"] for item in statuses if not item["ready"]]
    recoverable_missing = [
        item["name"]
        for item in statuses
        if not item["ready"] and item["recoverable_from_maccy"]
    ]

    if not missing:
        label = "online"
    elif recoverable_missing:
        label = "recoverable"
    else:
        label = "missing-secrets"

    return {
        "ok": True,
        "output": {
            "status_label": label,
            "required": names,
            "ready_count": ready_count,
            "missing_count": len(missing),
            "recoverable_count": recoverable_count,
            "missing": missing,
            "recoverable_missing": recoverable_missing,
            "statuses": statuses,
        },
        "error": None,
    }


def rehydrate_missing_secrets(required: Optional[list[str]] = None, limit: int = 50) -> dict:
    """Restore missing secrets from Maccy history into Keychain without revealing values."""
    names = _normalize_secret_names(required)
    detected = detect_keys_in_clipboard(limit)

    latest_by_type: dict[str, str] = {}
    for entry in detected:
        key_type = entry.get("type")
        full_value = entry.get("full_value")
        if not key_type or not full_value:
            continue
        latest_by_type.setdefault(key_type, full_value)

    restored: list[str] = []
    already_ready: list[str] = []
    still_missing: list[str] = []

    for name in names:
        env_var = SECRET_ENV_MAP.get(name, f"AIBUTLER_{name.upper()}")
        if get_secret(name) is not None or os.environ.get(env_var):
            already_ready.append(name)
            continue

        recovered_value = latest_by_type.get(name)
        if not recovered_value:
            still_missing.append(name)
            continue

        result = save_secret(name, recovered_value)
        if result.get("ok"):
            restored.append(name)
        else:
            still_missing.append(name)

    injected = inject_all_secrets().get("output", [])

    return {
        "ok": True,
        "output": {
            "restored": restored,
            "already_ready": already_ready,
            "still_missing": still_missing,
            "restored_count": len(restored),
            "injected_env": injected,
            "status_label": "online" if not still_missing else ("partial" if restored else "missing-secrets"),
        },
        "error": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tool Registry
# ──────────────────────────────────────────────────────────────────────────────

TOOLS = {
    "save_secret": {
        "fn": save_secret,
        "description": "Save a named secret to macOS Keychain (encrypted).",
        "params": {"name": "str", "value": "str"},
    },
    "get_secret": {
        "fn": lambda name: {"ok": True, "output": get_secret(name) or "not found", "error": None},
        "description": "Retrieve a secret by name from Keychain.",
        "params": {"name": "str"},
    },
    "delete_secret": {
        "fn": delete_secret,
        "description": "Delete a secret from Keychain.",
        "params": {"name": "str"},
    },
    "list_secrets": {
        "fn": list_secrets,
        "description": "List all stored secret names (not values).",
        "params": {},
    },
    "save_clipboard_as": {
        "fn": save_clipboard_as,
        "description": "Save current clipboard contents as a named secret.",
        "params": {"name": "str"},
    },
    "auto_capture_keys": {
        "fn": auto_capture_keys,
        "description": "Scan clipboard history for API keys and auto-save them to Keychain.",
        "params": {},
    },
    "secret_recovery_status": {
        "fn": secret_recovery_status,
        "description": "Check whether Butler's core intelligence secrets are online or recoverable from Maccy without revealing values.",
        "params": {"required": "list[str]=None", "limit": "int=50"},
    },
    "rehydrate_missing_secrets": {
        "fn": rehydrate_missing_secrets,
        "description": "Restore missing Butler secrets from Maccy clipboard history into Keychain.",
        "params": {"required": "list[str]=None", "limit": "int=50"},
    },
    "get_clipboard": {
        "fn": lambda: {"ok": True, "output": get_clipboard()[:500], "error": None},
        "description": "Get current clipboard contents.",
        "params": {},
    },
    "get_clipboard_history": {
        "fn": lambda limit=20: {"ok": True, "output": get_clipboard_history(limit), "error": None},
        "description": "Get recent clipboard history from Maccy.",
        "params": {"limit": "int=20"},
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# CLI for quick management
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("""
  aiButler Secrets Manager

  Usage:
    python secrets.py scan          Scan clipboard for API keys & auto-save
    python secrets.py list          List stored secrets
    python secrets.py get <name>    Retrieve a secret
    python secrets.py save <name>   Save clipboard as named secret
    python secrets.py delete <name> Delete a secret
    python secrets.py inject        Load all secrets into environment
    python secrets.py history       Show recent clipboard history
    python secrets.py status        Show intelligence secret recovery status
    python secrets.py rehydrate     Restore missing intelligence secrets from Maccy
        """)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "scan":
        result = auto_capture_keys()
        print(json.dumps(result, indent=2))

    elif cmd == "list":
        result = list_secrets()
        print("Stored secrets:")
        for name in result.get("output", []):
            print(f"  - {name}")

    elif cmd == "get" and len(sys.argv) > 2:
        val = get_secret(sys.argv[2])
        if val:
            print(f"{sys.argv[2]}: {val[:8]}...{val[-4:]}")
        else:
            print("Not found")

    elif cmd == "save" and len(sys.argv) > 2:
        result = save_clipboard_as(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif cmd == "delete" and len(sys.argv) > 2:
        result = delete_secret(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif cmd == "inject":
        result = inject_all_secrets()
        print("Injected into environment:")
        for item in result.get("output", []):
            print(f"  {item}")

    elif cmd == "history":
        entries = get_clipboard_history(20)
        for e in entries:
            preview = e.get("preview", "")[:80].replace("\n", " ")
            print(f"  [{e.get('time', '')}] {e.get('app', '')}: {preview}")

    elif cmd == "status":
        result = secret_recovery_status()
        print(json.dumps(result, indent=2))

    elif cmd == "rehydrate":
        result = rehydrate_missing_secrets()
        print(json.dumps(result, indent=2))

    else:
        print(f"Unknown command: {cmd}")
