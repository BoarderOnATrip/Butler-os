#!/usr/bin/env python3
"""
aiButler Computer Use — supervised local screen inspection and input on macOS.

This is the first privileged adapter for "computer use" tasks:
  - screenshot capture
  - cursor inspection
  - mouse movement
  - click / double-click / right-click
  - typing and key presses
  - drag flows

It uses:
  - screencapture (built into macOS)
  - cliclick (Homebrew) for human-like mouse and keyboard control

Live pointer actions are disabled by default unless:
  AIBUTLER_ENABLE_COMPUTER_USE=1

Live keyboard actions are disabled by default unless:
  AIBUTLER_ENABLE_KEYBOARD_USE=1
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

AIBUTLER_HOME = Path.home() / ".aibutler"
COMPUTER_USE_DIR = AIBUTLER_HOME / "computer-use"

ACCESSIBILITY_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
SCREEN_RECORDING_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"


def _env_enabled(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _ok(output: Any) -> dict:
    return {"ok": True, "output": output, "error": None}


def _err(message: str, output: Any = "") -> dict:
    return {"ok": False, "output": output, "error": message}


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _ensure_dirs() -> None:
    COMPUTER_USE_DIR.mkdir(parents=True, exist_ok=True)


def _command_path(name: str) -> Optional[str]:
    return shutil.which(name)


def _action_enabled() -> bool:
    return _env_enabled("AIBUTLER_ENABLE_COMPUTER_USE", default=False)


def _keyboard_enabled() -> bool:
    return _env_enabled("AIBUTLER_ENABLE_KEYBOARD_USE", default=False)


def _require_macos() -> Optional[dict]:
    if platform.system() != "Darwin":
        return _err("Computer use is currently implemented only for macOS")
    return None


def _open_url(url: str) -> dict:
    result = subprocess.run(["open", url], capture_output=True, text=True)
    if result.returncode != 0:
        return _err(result.stderr.strip() or f"Failed to open {url}")
    return _ok(url)


def _maybe_capture_receipt(label: str) -> Optional[str]:
    _ensure_dirs()
    path = COMPUTER_USE_DIR / f"{_timestamp()}-{label}.png"
    result = subprocess.run(
        ["screencapture", "-x", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return str(path)


def _write_receipt(action: str, payload: dict) -> str:
    _ensure_dirs()
    path = COMPUTER_USE_DIR / f"{_timestamp()}-{action}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


def _run_cliclick(commands: list[str], *, easing: int = 0, wait_ms: int = 120, test: bool = False,
                  restore: bool = False) -> subprocess.CompletedProcess:
    cmd = ["cliclick"]
    if restore:
        cmd.append("-r")
    if test:
        cmd.extend(["-m", "test"])
    if easing:
        cmd.extend(["-e", str(easing)])
    cmd.extend(["-w", str(max(wait_ms, 20))])
    cmd.extend(commands)
    return subprocess.run(cmd, capture_output=True, text=True)


def _cliclick_available() -> bool:
    return _command_path("cliclick") is not None


def _screencapture_available() -> bool:
    return _command_path("screencapture") is not None


def _accessibility_probe() -> dict:
    if not _cliclick_available():
        return {"available": False, "enabled": False, "message": "cliclick not installed"}

    result = subprocess.run(["cliclick", "p"], capture_output=True, text=True)
    stderr = (result.stderr or "").strip()
    warning = "Accessibility privileges not enabled" in stderr

    return {
        "available": True,
        "enabled": result.returncode == 0 and not warning,
        "stdout": (result.stdout or "").strip(),
        "warning": stderr or None,
    }


def preflight_computer_use() -> dict:
    """Return platform, dependency, and permission status for computer use."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error

    return _ok({
        "platform": platform.platform(),
        "cliclick_installed": _cliclick_available(),
        "screencapture_installed": _screencapture_available(),
        "screen_read_enabled": True,
        "computer_use_enabled": _action_enabled(),
        "keyboard_use_enabled": _keyboard_enabled(),
        "accessibility": _accessibility_probe(),
        "receipt_dir": str(COMPUTER_USE_DIR),
    })


def open_accessibility_settings() -> dict:
    """Open the macOS Accessibility privacy pane."""
    return _open_url(ACCESSIBILITY_URL)


def open_screen_recording_settings() -> dict:
    """Open the macOS Screen Recording privacy pane."""
    return _open_url(SCREEN_RECORDING_URL)


def get_mouse_position() -> dict:
    """Return the current mouse position as x/y coordinates."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")

    result = subprocess.run(["cliclick", "p"], capture_output=True, text=True)
    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to read mouse position", result.stdout.strip())

    raw = (result.stdout or "").strip()
    try:
        x_str, y_str = raw.split(",", 1)
        return _ok({"x": int(x_str), "y": int(y_str)})
    except ValueError:
        return _err(f"Unexpected mouse position format: {raw}", raw)


def capture_screen(dst: str = None, display: int = None, interactive: bool = False) -> dict:
    """Capture a screenshot and return the output path."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _screencapture_available():
        return _err("screencapture is not available on this system")

    _ensure_dirs()
    if dst is None:
        dst = str(COMPUTER_USE_DIR / f"{_timestamp()}-screen.png")

    cmd = ["screencapture"]
    if not interactive:
        cmd.append("-x")
    if display is not None:
        cmd.extend(["-D", str(display)])
    cmd.append(dst)

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to capture screen", result.stdout.strip())

    path = Path(dst)
    return _ok({
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    })


def move_mouse(x: int, y: int, easing: int = 0, wait_ms: int = 120,
               dry_run: bool = False, restore: bool = False) -> dict:
    """Move the mouse to an absolute screen position."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")
    if not dry_run and not _action_enabled():
        return _err("Computer use actions are disabled. Set AIBUTLER_ENABLE_COMPUTER_USE=1")

    result = _run_cliclick([f"m:{x},{y}"], easing=easing, wait_ms=wait_ms, test=dry_run, restore=restore)
    receipt = _write_receipt("move", {
        "action": "move_mouse",
        "x": x,
        "y": y,
        "dry_run": dry_run,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    })
    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to move mouse", {"receipt": receipt})

    return _ok({"x": x, "y": y, "dry_run": dry_run, "receipt": receipt})


def click_at(x: int, y: int, button: str = "left", clicks: int = 1, easing: int = 0,
             wait_ms: int = 120, dry_run: bool = False, restore: bool = False,
             capture_receipt: bool = False) -> dict:
    """Click at screen coordinates."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")
    if not dry_run and not _action_enabled():
        return _err("Computer use actions are disabled. Set AIBUTLER_ENABLE_COMPUTER_USE=1")

    if button == "right":
        command = f"rc:{x},{y}"
    elif clicks == 2:
        command = f"dc:{x},{y}"
    elif clicks == 3:
        command = f"tc:{x},{y}"
    else:
        command = f"c:{x},{y}"

    before = _maybe_capture_receipt("before-click") if capture_receipt else None
    result = _run_cliclick([command], easing=easing, wait_ms=wait_ms, test=dry_run, restore=restore)
    after = _maybe_capture_receipt("after-click") if capture_receipt and not dry_run else None

    receipt = _write_receipt("click", {
        "action": "click_at",
        "x": x,
        "y": y,
        "button": button,
        "clicks": clicks,
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    })

    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to click", {"receipt": receipt})

    return _ok({
        "x": x,
        "y": y,
        "button": button,
        "clicks": clicks,
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "receipt": receipt,
    })


def right_click_at(x: int, y: int, dry_run: bool = False, capture_receipt: bool = False) -> dict:
    """Right-click at screen coordinates."""
    return click_at(x=x, y=y, button="right", clicks=1, dry_run=dry_run, capture_receipt=capture_receipt)


def double_click_at(x: int, y: int, dry_run: bool = False, capture_receipt: bool = False) -> dict:
    """Double-click at screen coordinates."""
    return click_at(x=x, y=y, button="left", clicks=2, dry_run=dry_run, capture_receipt=capture_receipt)


def type_text(text: str, wait_ms: int = 40, dry_run: bool = False, capture_receipt: bool = False) -> dict:
    """Type text into the frontmost application."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")
    if not dry_run and not _keyboard_enabled():
        return _err("Keyboard use is disabled. Set AIBUTLER_ENABLE_KEYBOARD_USE=1")

    before = _maybe_capture_receipt("before-type") if capture_receipt else None
    result = _run_cliclick([f"t:{text}"], wait_ms=wait_ms, test=dry_run)
    after = _maybe_capture_receipt("after-type") if capture_receipt and not dry_run else None

    receipt = _write_receipt("type", {
        "action": "type_text",
        "text_length": len(text),
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    })

    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to type text", {"receipt": receipt})

    return _ok({
        "typed_length": len(text),
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "receipt": receipt,
    })


def press_key(key: str, modifiers: list[str] = None, wait_ms: int = 120, dry_run: bool = False) -> dict:
    """Press a key, optionally while holding modifiers."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")
    if not dry_run and not _keyboard_enabled():
        return _err("Keyboard use is disabled. Set AIBUTLER_ENABLE_KEYBOARD_USE=1")

    commands = []
    if modifiers:
        commands.append(f"kd:{','.join(modifiers)}")
    commands.append(f"kp:{key}")
    if modifiers:
        commands.append(f"ku:{','.join(modifiers)}")

    result = _run_cliclick(commands, wait_ms=wait_ms, test=dry_run)
    receipt = _write_receipt("keypress", {
        "action": "press_key",
        "key": key,
        "modifiers": modifiers or [],
        "dry_run": dry_run,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    })

    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to press key", {"receipt": receipt})

    return _ok({
        "key": key,
        "modifiers": modifiers or [],
        "dry_run": dry_run,
        "receipt": receipt,
    })


def drag_mouse(start_x: int, start_y: int, end_x: int, end_y: int, easing: int = 0,
               wait_ms: int = 120, dry_run: bool = False, capture_receipt: bool = False) -> dict:
    """Perform a drag action from start to end coordinates."""
    macos_error = _require_macos()
    if macos_error:
        return macos_error
    if not _cliclick_available():
        return _err("cliclick is not installed. Run: brew install cliclick")
    if not dry_run and not _action_enabled():
        return _err("Computer use actions are disabled. Set AIBUTLER_ENABLE_COMPUTER_USE=1")

    before = _maybe_capture_receipt("before-drag") if capture_receipt else None
    result = _run_cliclick(
        [f"dd:{start_x},{start_y}", f"dm:{end_x},{end_y}", f"du:{end_x},{end_y}"],
        easing=easing,
        wait_ms=wait_ms,
        test=dry_run,
    )
    after = _maybe_capture_receipt("after-drag") if capture_receipt and not dry_run else None

    receipt = _write_receipt("drag", {
        "action": "drag_mouse",
        "start_x": start_x,
        "start_y": start_y,
        "end_x": end_x,
        "end_y": end_y,
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    })

    if result.returncode != 0:
        return _err(result.stderr.strip() or "Failed to drag mouse", {"receipt": receipt})

    return _ok({
        "start": {"x": start_x, "y": start_y},
        "end": {"x": end_x, "y": end_y},
        "dry_run": dry_run,
        "before_screenshot": before,
        "after_screenshot": after,
        "receipt": receipt,
    })


TOOLS = {
    "preflight_computer_use": {
        "fn": preflight_computer_use,
        "description": "Check whether macOS computer use dependencies and permissions are ready.",
        "params": {},
    },
    "open_accessibility_settings": {
        "fn": open_accessibility_settings,
        "description": "Open macOS Accessibility privacy settings for enabling mouse/keyboard control.",
        "params": {},
    },
    "open_screen_recording_settings": {
        "fn": open_screen_recording_settings,
        "description": "Open macOS Screen Recording privacy settings for enabling screenshots.",
        "params": {},
    },
    "get_mouse_position": {
        "fn": get_mouse_position,
        "description": "Return the current mouse cursor position.",
        "params": {},
    },
    "capture_screen": {
        "fn": capture_screen,
        "description": "Capture a screenshot of the current screen.",
        "params": {"dst": "str=None", "display": "int=None", "interactive": "bool=False"},
    },
    "move_mouse": {
        "fn": move_mouse,
        "description": "Move the mouse to a coordinate on screen.",
        "params": {"x": "int", "y": "int", "easing": "int=0", "dry_run": "bool=False"},
    },
    "click_at": {
        "fn": click_at,
        "description": "Click, double-click, or right-click at a coordinate on screen.",
        "params": {"x": "int", "y": "int", "button": "str=left", "clicks": "int=1", "dry_run": "bool=False"},
    },
    "right_click_at": {
        "fn": right_click_at,
        "description": "Right-click at a coordinate on screen.",
        "params": {"x": "int", "y": "int", "dry_run": "bool=False"},
    },
    "double_click_at": {
        "fn": double_click_at,
        "description": "Double-click at a coordinate on screen.",
        "params": {"x": "int", "y": "int", "dry_run": "bool=False"},
    },
    "type_text": {
        "fn": type_text,
        "description": "Type text into the frontmost app.",
        "params": {"text": "str", "dry_run": "bool=False"},
    },
    "press_key": {
        "fn": press_key,
        "description": "Press a key, optionally with modifiers like cmd or shift.",
        "params": {"key": "str", "modifiers": "list[str]=None", "dry_run": "bool=False"},
    },
    "drag_mouse": {
        "fn": drag_mouse,
        "description": "Drag the mouse from one coordinate to another.",
        "params": {"start_x": "int", "start_y": "int", "end_x": "int", "end_y": "int", "dry_run": "bool=False"},
    },
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="aiButler computer use tools")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight")
    sub.add_parser("open-accessibility")
    sub.add_parser("open-screen-recording")
    sub.add_parser("mouse")

    screenshot = sub.add_parser("screenshot")
    screenshot.add_argument("dst", nargs="?")

    click = sub.add_parser("click")
    click.add_argument("x", type=int)
    click.add_argument("y", type=int)
    click.add_argument("--button", default="left")
    click.add_argument("--clicks", type=int, default=1)
    click.add_argument("--dry-run", action="store_true")

    move = sub.add_parser("move")
    move.add_argument("x", type=int)
    move.add_argument("y", type=int)
    move.add_argument("--dry-run", action="store_true")

    typing = sub.add_parser("type")
    typing.add_argument("text")
    typing.add_argument("--dry-run", action="store_true")

    key = sub.add_parser("key")
    key.add_argument("key")
    key.add_argument("--modifiers")
    key.add_argument("--dry-run", action="store_true")

    drag = sub.add_parser("drag")
    drag.add_argument("start_x", type=int)
    drag.add_argument("start_y", type=int)
    drag.add_argument("end_x", type=int)
    drag.add_argument("end_y", type=int)
    drag.add_argument("--dry-run", action="store_true")

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "preflight":
        result = preflight_computer_use()
    elif args.command == "open-accessibility":
        result = open_accessibility_settings()
    elif args.command == "open-screen-recording":
        result = open_screen_recording_settings()
    elif args.command == "mouse":
        result = get_mouse_position()
    elif args.command == "screenshot":
        result = capture_screen(dst=args.dst)
    elif args.command == "click":
        result = click_at(
            x=args.x,
            y=args.y,
            button=args.button,
            clicks=args.clicks,
            dry_run=args.dry_run,
        )
    elif args.command == "move":
        result = move_mouse(x=args.x, y=args.y, dry_run=args.dry_run)
    elif args.command == "type":
        result = type_text(text=args.text, dry_run=args.dry_run)
    elif args.command == "key":
        modifiers = args.modifiers.split(",") if args.modifiers else None
        result = press_key(key=args.key, modifiers=modifiers, dry_run=args.dry_run)
    elif args.command == "drag":
        result = drag_mouse(
            start_x=args.start_x,
            start_y=args.start_y,
            end_x=args.end_x,
            end_y=args.end_y,
            dry_run=args.dry_run,
        )
    else:
        result = _err(f"Unknown command: {args.command}")

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
