#!/usr/bin/env python3
"""
aiButler RTK Tools — optional token-optimization helpers for OpenClaw flows.

RTK is valuable where Butler or adjacent agent shells execute noisy terminal
commands. This module keeps the integration optional and explicit:
  - detect whether RTK is installed
  - preview rewrites for shell commands
  - surface RTK gain stats
  - install the vendored OpenClaw plugin into the local user profile
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VENDORED_PLUGIN_DIR = REPO_ROOT / "integrations" / "openclaw" / "rtk-rewrite"
OPENCLAW_PLUGIN_DIR = Path.home() / ".openclaw" / "extensions" / "rtk-rewrite"


def _ok(output):
    return {"ok": True, "output": output, "error": None}


def _err(message: str, output=""):
    return {"ok": False, "output": output, "error": message}


def _rtk_path() -> str | None:
    return shutil.which("rtk")


def _openclaw_path() -> str | None:
    return shutil.which("openclaw")


def _safe_run(cmd: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _vendored_plugin_ready() -> bool:
    return (
        (VENDORED_PLUGIN_DIR / "index.ts").exists()
        and (VENDORED_PLUGIN_DIR / "openclaw.plugin.json").exists()
    )


def rtk_status() -> dict:
    """Inspect RTK/OpenClaw availability and the vendored Butler plugin state."""
    rtk_bin = _rtk_path()
    openclaw_bin = _openclaw_path()
    plugin_dir = OPENCLAW_PLUGIN_DIR
    installed_plugin = plugin_dir.exists() and (plugin_dir / "index.ts").exists() and (plugin_dir / "openclaw.plugin.json").exists()

    version = ""
    if rtk_bin:
        try:
            result = _safe_run([rtk_bin, "--version"], timeout=5)
            if result.returncode == 0:
                version = (result.stdout or result.stderr).strip()
        except Exception:
            version = ""

    suggested_steps: list[str] = []
    if not rtk_bin:
        suggested_steps.append("Install RTK with `brew install rtk` or RTK's install.sh.")
    if not installed_plugin:
        suggested_steps.append("Install the Butler-vendored RTK OpenClaw plugin with `install_rtk_openclaw_plugin`.")
    if installed_plugin and openclaw_bin:
        suggested_steps.append("Restart OpenClaw gateway so the RTK rewrite hook is picked up.")
    elif installed_plugin:
        suggested_steps.append("OpenClaw plugin files are present. Install OpenClaw or point your OpenClaw setup at the plugin directory.")

    return _ok(
        {
            "rtk_installed": bool(rtk_bin),
            "rtk_path": rtk_bin or "",
            "rtk_version": version,
            "openclaw_installed": bool(openclaw_bin),
            "openclaw_path": openclaw_bin or "",
            "vendored_plugin_ready": _vendored_plugin_ready(),
            "vendored_plugin_dir": str(VENDORED_PLUGIN_DIR),
            "plugin_installed": installed_plugin,
            "plugin_dir": str(plugin_dir),
            "suggested_steps": suggested_steps,
        }
    )


def rtk_rewrite_preview(command: str) -> dict:
    """Show how RTK would rewrite a shell command, without executing it."""
    raw_command = (command or "").strip()
    if not raw_command:
        return _err("command is required")

    rtk_bin = _rtk_path()
    if not rtk_bin:
        return _err("RTK is not installed. Install it with `brew install rtk` first.")

    try:
        result = _safe_run([rtk_bin, "rewrite", raw_command], timeout=5)
    except Exception as exc:
        return _err(f"Failed to run RTK rewrite: {exc}")

    if result.returncode != 0:
        return _err(result.stderr.strip() or "RTK rewrite failed", result.stdout.strip())

    rewritten = (result.stdout or "").strip() or raw_command
    return _ok(
        {
            "original": raw_command,
            "rewritten": rewritten,
            "changed": rewritten != raw_command,
        }
    )


def rtk_gain_summary() -> dict:
    """Return RTK's own gain summary output if the binary is installed."""
    rtk_bin = _rtk_path()
    if not rtk_bin:
        return _err("RTK is not installed. Install it with `brew install rtk` first.")

    try:
        result = _safe_run([rtk_bin, "gain"], timeout=10)
    except Exception as exc:
        return _err(f"Failed to run `rtk gain`: {exc}")

    if result.returncode != 0:
        return _err(result.stderr.strip() or "RTK gain failed", result.stdout.strip())

    return _ok(
        {
            "summary": (result.stdout or "").strip(),
        }
    )


def install_rtk_openclaw_plugin(target_dir: str = "") -> dict:
    """Install Butler's vendored RTK OpenClaw plugin into the user's profile."""
    if not _vendored_plugin_ready():
        return _err(f"Vendored RTK plugin files are missing from {VENDORED_PLUGIN_DIR}")

    plugin_dir = Path(target_dir).expanduser() if target_dir.strip() else OPENCLAW_PLUGIN_DIR
    plugin_dir.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for name in ("index.ts", "openclaw.plugin.json"):
        src = VENDORED_PLUGIN_DIR / name
        dst = plugin_dir / name
        shutil.copy2(src, dst)
        copied.append(str(dst))

    config_snippet = {
        "plugins": {
            "entries": {
                "rtk-rewrite": {
                    "enabled": True,
                    "config": {
                        "enabled": True,
                        "verbose": False,
                    },
                }
            }
        }
    }

    return _ok(
        {
            "plugin_dir": str(plugin_dir),
            "copied_files": copied,
            "openclaw_detected": bool(_openclaw_path()),
            "next_steps": [
                "Install RTK with `brew install rtk` if it is not already on PATH.",
                "Enable the `rtk-rewrite` plugin in your OpenClaw config if needed.",
                "Restart the OpenClaw gateway after installation.",
            ],
            "config_snippet": json.dumps(config_snippet, indent=2),
        }
    )


TOOLS = {
    "rtk_status": {
        "fn": rtk_status,
        "description": "Check whether RTK and its Butler-vendored OpenClaw plugin are installed and ready.",
        "params": {},
    },
    "rtk_rewrite_preview": {
        "fn": rtk_rewrite_preview,
        "description": "Preview how RTK would rewrite a shell command to reduce token usage.",
        "params": {"command": "str"},
    },
    "rtk_gain_summary": {
        "fn": rtk_gain_summary,
        "description": "Show RTK token savings stats from the local machine.",
        "params": {},
    },
    "install_rtk_openclaw_plugin": {
        "fn": install_rtk_openclaw_plugin,
        "description": "Install Butler's vendored RTK rewrite plugin into the local OpenClaw extensions directory.",
        "params": {"target_dir": "str=''"},  # mainly useful for testing or custom setups
    },
}
