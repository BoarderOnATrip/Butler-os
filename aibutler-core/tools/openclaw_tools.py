#!/usr/bin/env python3
"""
aiButler OpenClaw Tools — Butler-managed operator stack helpers.

These tools make OpenClaw a first-class local subsystem instead of an implicit
dependency. The scope is intentionally practical:
  - inspect local OpenClaw readiness
  - install the CLI from the official npm package
  - install the gateway service
  - run OpenClaw's built-in doctor command
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.rtk_tools import OPENCLAW_PLUGIN_DIR


OPENCLAW_USER_DIR = Path.home() / ".openclaw"
OPENCLAW_EXTENSIONS_DIR = OPENCLAW_USER_DIR / "extensions"
OFFICIAL_INSTALL_COMMAND = "curl -fsSL https://openclaw.ai/install.sh | bash"
AUTOMATION_INSTALL_COMMAND = "SHARP_IGNORE_GLOBAL_LIBVIPS=1 npm install -g openclaw@latest"


def _ok(output: Any) -> dict:
    return {"ok": True, "output": output, "error": None}


def _err(message: str, output: Any = "") -> dict:
    return {"ok": False, "output": output, "error": message}


def _safe_run(
    cmd: list[str],
    *,
    timeout: int = 20,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _command_exists(name: str) -> str | None:
    return shutil.which(name)


def _command_version(cmd: str, *args: str) -> str:
    try:
        result = _safe_run([cmd, *args], timeout=8)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or result.stderr).strip()


def _npm_prefix(npm_bin: str | None) -> str:
    if not npm_bin:
        return ""
    try:
        result = _safe_run([npm_bin, "prefix", "-g"], timeout=8)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _npm_global_bin(prefix: str) -> str:
    if not prefix:
        return ""
    return str(Path(prefix).expanduser() / "bin")


def _path_contains(directory: str) -> bool:
    if not directory:
        return False
    try:
        wanted = Path(directory).expanduser().resolve()
    except Exception:
        return False
    for chunk in os.environ.get("PATH", "").split(os.pathsep):
        if not chunk.strip():
            continue
        try:
            if Path(chunk).expanduser().resolve() == wanted:
                return True
        except Exception:
            continue
    return False


def _safe_json_loads(raw: str) -> Any | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _infer_gateway_running(payload: Any, raw: str, returncode: int) -> bool | None:
    if isinstance(payload, dict):
        rpc = payload.get("rpc")
        if isinstance(rpc, dict):
            rpc_ok = rpc.get("ok")
            if isinstance(rpc_ok, bool):
                return rpc_ok
        for key in ("running", "healthy", "ready", "reachable"):
            value = payload.get(key)
            if isinstance(value, bool):
                return value
        status_value = payload.get("status")
        if isinstance(status_value, str):
            normalized = status_value.strip().lower()
            if normalized in {"running", "ready", "healthy", "ok", "online"}:
                return True
            if normalized in {"stopped", "offline", "not running", "error", "failed"}:
                return False

    combined = raw.strip().lower()
    if "running" in combined or "healthy" in combined or "online" in combined:
        return True
    if "not running" in combined or "offline" in combined or "stopped" in combined:
        return False
    if returncode == 0 and combined:
        return True
    return None


def _gateway_status(openclaw_bin: str | None) -> dict[str, Any]:
    if not openclaw_bin:
        return {
            "ok": False,
            "running": False,
            "summary": "OpenClaw is not installed yet.",
            "raw": "",
            "payload": None,
        }

    try:
        result = _safe_run([openclaw_bin, "gateway", "status", "--json"], timeout=12)
        raw = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
        payload = _safe_json_loads(result.stdout or "") or _safe_json_loads(raw)
        running = _infer_gateway_running(payload, raw, result.returncode)
        rpc_probe = _safe_run([openclaw_bin, "gateway", "status", "--require-rpc"], timeout=12)
        rpc_running = rpc_probe.returncode == 0
        effective_running = rpc_running if isinstance(running, bool) and not running else (bool(running) or rpc_running)
        if result.returncode == 0:
            return {
                "ok": True,
                "running": effective_running,
                "summary": "Gateway looks online." if effective_running else "Gateway status is available, but it does not look online yet.",
                "raw": raw,
                "payload": payload,
            }

        fallback = _safe_run([openclaw_bin, "gateway", "status"], timeout=12)
        fallback_raw = ((fallback.stdout or "") + ("\n" + fallback.stderr if fallback.stderr else "")).strip()
        fallback_running = _infer_gateway_running(None, fallback_raw, fallback.returncode)
        return {
            "ok": fallback.returncode == 0,
            "running": rpc_running or (bool(fallback_running) if fallback_running is not None else False),
            "summary": "Gateway looks online." if (rpc_running or fallback_running) else (fallback_raw or raw or "Gateway status is unavailable."),
            "raw": fallback_raw or raw,
            "payload": payload,
        }
    except Exception as exc:
        return {
            "ok": False,
            "running": False,
            "summary": f"Gateway status failed: {exc}",
            "raw": "",
            "payload": None,
        }


def _installed_rtk_plugin() -> bool:
    return (
        OPENCLAW_PLUGIN_DIR.exists()
        and (OPENCLAW_PLUGIN_DIR / "index.ts").exists()
        and (OPENCLAW_PLUGIN_DIR / "openclaw.plugin.json").exists()
    )


def openclaw_status() -> dict:
    """Inspect whether OpenClaw is installed and whether the gateway looks healthy."""
    node_bin = _command_exists("node")
    npm_bin = _command_exists("npm")
    openclaw_bin = _command_exists("openclaw")
    node_version = _command_version(node_bin, "--version") if node_bin else ""
    npm_version = _command_version(npm_bin, "--version") if npm_bin else ""
    openclaw_version = _command_version(openclaw_bin, "--version") if openclaw_bin else ""
    npm_prefix = _npm_prefix(npm_bin)
    npm_global_bin = _npm_global_bin(npm_prefix)
    gateway = _gateway_status(openclaw_bin)

    suggested_steps: list[str] = []
    if not npm_bin:
        suggested_steps.append("Install Node.js so Butler can install OpenClaw from the official npm package.")
    elif not openclaw_bin:
        suggested_steps.append(
            f"Install OpenClaw with the official installer `{OFFICIAL_INSTALL_COMMAND}` or Butler's automation-safe path `{AUTOMATION_INSTALL_COMMAND}`."
        )
    elif not gateway.get("running"):
        gateway_payload = gateway.get("payload") or {}
        gateway_last_error = ""
        if isinstance(gateway_payload, dict):
            gateway_last_error = str(gateway_payload.get("lastError") or "")
        if "gateway.mode" in gateway_last_error:
            suggested_steps.append("Set `gateway.mode=local` with `openclaw_configure_local_gateway`, then restart the gateway.")
        suggested_steps.append(
            "Install or repair the OpenClaw gateway with `openclaw_gateway_install`, `openclaw_gateway_restart`, or `openclaw_doctor`."
        )

    if npm_global_bin and not _path_contains(npm_global_bin):
        suggested_steps.append(f"Add {npm_global_bin} to PATH so shells can find the global `openclaw` binary.")

    if not _installed_rtk_plugin():
        suggested_steps.append("Optional: install Butler's RTK OpenClaw plugin with `install_rtk_openclaw_plugin`.")

    return _ok(
        {
            "openclaw_installed": bool(openclaw_bin),
            "openclaw_path": openclaw_bin or "",
            "openclaw_version": openclaw_version,
            "node_installed": bool(node_bin),
            "node_version": node_version,
            "npm_installed": bool(npm_bin),
            "npm_version": npm_version,
            "npm_global_prefix": npm_prefix,
            "npm_global_bin": npm_global_bin,
            "npm_global_bin_on_path": _path_contains(npm_global_bin),
            "gateway": gateway,
            "openclaw_user_dir": str(OPENCLAW_USER_DIR),
            "extensions_dir": str(OPENCLAW_EXTENSIONS_DIR),
            "rtk_plugin_installed": _installed_rtk_plugin(),
            "rtk_plugin_dir": str(OPENCLAW_PLUGIN_DIR),
            "suggested_steps": suggested_steps,
        }
    )


def install_openclaw(force: bool = False) -> dict:
    """Install OpenClaw from the official npm package."""
    existing = openclaw_status()["output"]
    if existing.get("openclaw_installed") and not force:
        return _ok(
            {
                "changed": False,
                "message": "OpenClaw is already installed on this Mac.",
                "official_install_command": OFFICIAL_INSTALL_COMMAND,
                "automation_install_command": AUTOMATION_INSTALL_COMMAND,
                "status": existing,
            }
        )

    npm_bin = _command_exists("npm")
    if not npm_bin:
        return _err(
            "npm is not installed. Install Node.js first so Butler can install OpenClaw from the official npm package.",
            {
                "official_install_command": OFFICIAL_INSTALL_COMMAND,
                "automation_install_command": AUTOMATION_INSTALL_COMMAND,
            },
        )

    env = dict(os.environ)
    env["SHARP_IGNORE_GLOBAL_LIBVIPS"] = "1"
    try:
        result = _safe_run([npm_bin, "install", "-g", "openclaw@latest"], timeout=900, env=env)
    except Exception as exc:
        return _err(f"Failed to install OpenClaw: {exc}")

    combined = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    status = openclaw_status()["output"]
    if result.returncode != 0:
        return _err(
            result.stderr.strip() or "OpenClaw install failed.",
            {
                "official_install_command": OFFICIAL_INSTALL_COMMAND,
                "automation_install_command": AUTOMATION_INSTALL_COMMAND,
                "raw": combined,
                "status": status,
            },
        )

    return _ok(
        {
            "changed": True,
            "message": "OpenClaw install completed.",
            "official_install_command": OFFICIAL_INSTALL_COMMAND,
            "automation_install_command": AUTOMATION_INSTALL_COMMAND,
            "raw": combined,
            "status": status,
            "next_steps": status.get("suggested_steps") or [],
        }
    )


def openclaw_gateway_install() -> dict:
    """Install the OpenClaw gateway service."""
    openclaw_bin = _command_exists("openclaw")
    if not openclaw_bin:
        return _err("OpenClaw is not installed yet. Run `install_openclaw` first.")

    try:
        result = _safe_run([openclaw_bin, "gateway", "install"], timeout=180)
    except Exception as exc:
        return _err(f"Failed to install the OpenClaw gateway: {exc}")

    combined = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    status = openclaw_status()["output"]
    if result.returncode != 0:
        return _err(
            result.stderr.strip() or "OpenClaw gateway install failed.",
            {
                "raw": combined,
                "status": status,
            },
        )

    return _ok(
        {
            "message": "OpenClaw gateway install completed.",
            "raw": combined,
            "status": status,
            "next_steps": status.get("suggested_steps") or [],
        }
    )


def openclaw_configure_local_gateway() -> dict:
    """Set gateway.mode=local and restart the gateway."""
    openclaw_bin = _command_exists("openclaw")
    if not openclaw_bin:
        return _err("OpenClaw is not installed yet. Run `install_openclaw` first.")

    try:
        config_result = _safe_run([openclaw_bin, "config", "set", "gateway.mode", "local"], timeout=60)
    except Exception as exc:
        return _err(f"Failed to set `gateway.mode=local`: {exc}")

    config_raw = ((config_result.stdout or "") + ("\n" + config_result.stderr if config_result.stderr else "")).strip()
    if config_result.returncode != 0:
        return _err(
            config_result.stderr.strip() or "Failed to set `gateway.mode=local`.",
            {"raw": config_raw},
        )

    try:
        restart_result = _safe_run([openclaw_bin, "gateway", "restart"], timeout=180)
    except Exception as exc:
        return _err(f"Local gateway mode was set, but restart failed: {exc}", {"raw": config_raw})

    restart_raw = ((restart_result.stdout or "") + ("\n" + restart_result.stderr if restart_result.stderr else "")).strip()
    status = openclaw_status()["output"]
    if restart_result.returncode != 0:
        return _err(
            restart_result.stderr.strip() or "Gateway restart failed after setting local mode.",
            {
                "config_raw": config_raw,
                "restart_raw": restart_raw,
                "status": status,
            },
        )

    return _ok(
        {
            "message": "OpenClaw gateway is configured for local mode.",
            "config_raw": config_raw,
            "restart_raw": restart_raw,
            "status": status,
            "next_steps": status.get("suggested_steps") or [],
        }
    )


def openclaw_gateway_restart() -> dict:
    """Restart the OpenClaw gateway service."""
    openclaw_bin = _command_exists("openclaw")
    if not openclaw_bin:
        return _err("OpenClaw is not installed yet. Run `install_openclaw` first.")

    try:
        result = _safe_run([openclaw_bin, "gateway", "restart"], timeout=180)
    except Exception as exc:
        return _err(f"Failed to restart the OpenClaw gateway: {exc}")

    combined = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    status = openclaw_status()["output"]
    if result.returncode != 0:
        return _err(
            result.stderr.strip() or "OpenClaw gateway restart failed.",
            {
                "raw": combined,
                "status": status,
            },
        )

    return _ok(
        {
            "message": "OpenClaw gateway restart completed.",
            "raw": combined,
            "status": status,
            "next_steps": status.get("suggested_steps") or [],
        }
    )


def openclaw_doctor(apply_fixes: bool = False) -> dict:
    """Run OpenClaw's built-in doctor command."""
    openclaw_bin = _command_exists("openclaw")
    if not openclaw_bin:
        return _err("OpenClaw is not installed yet. Run `install_openclaw` first.")

    cmd = [openclaw_bin, "doctor"]
    if apply_fixes:
        cmd.append("--fix")

    try:
        result = _safe_run(cmd, timeout=240)
    except Exception as exc:
        return _err(f"Failed to run `openclaw doctor`: {exc}")

    combined = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    status = openclaw_status()["output"]
    if result.returncode != 0:
        return _err(
            result.stderr.strip() or "OpenClaw doctor reported a failure.",
            {
                "raw": combined,
                "status": status,
            },
        )

    return _ok(
        {
            "message": "OpenClaw doctor completed." if not apply_fixes else "OpenClaw doctor completed with fixes applied.",
            "raw": combined,
            "status": status,
            "next_steps": status.get("suggested_steps") or [],
        }
    )


TOOLS = {
    "openclaw_status": {
        "fn": openclaw_status,
        "description": "Check whether OpenClaw and its gateway are installed and ready on the local Mac.",
        "params": {},
    },
    "install_openclaw": {
        "fn": install_openclaw,
        "description": "Install OpenClaw from the official npm package on the local Mac.",
        "params": {"force": "bool=False"},
    },
    "openclaw_gateway_install": {
        "fn": openclaw_gateway_install,
        "description": "Install or repair the OpenClaw gateway service on the local Mac.",
        "params": {},
    },
    "openclaw_configure_local_gateway": {
        "fn": openclaw_configure_local_gateway,
        "description": "Set OpenClaw's gateway mode to local and restart the gateway.",
        "params": {},
    },
    "openclaw_gateway_restart": {
        "fn": openclaw_gateway_restart,
        "description": "Restart the OpenClaw gateway service on the local Mac.",
        "params": {},
    },
    "openclaw_doctor": {
        "fn": openclaw_doctor,
        "description": "Run OpenClaw's built-in doctor command to repair or diagnose the local install.",
        "params": {"apply_fixes": "bool=False"},
    },
}
