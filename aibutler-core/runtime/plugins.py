#!/usr/bin/env python3
"""
aiButler Plugin Manager — community tools with full hooks parity.

Plugin structure (a plugin is a single .py file in ~/.aibutler/plugins/):

  def register_tools() -> dict:
      '''Return tool registry entries in the same format as TOOLS in file_ops.py.'''
      return {"my_tool": {"fn": my_fn, "description": "...", "params": {...}}}

  def register_hooks(hooks: dict) -> None:
      '''Optionally register pre/post tool hooks.'''
      hooks["pre_tool"].append(my_pre_hook)

Hooks:
  pre_tool(tool_name: str, args: dict, session_id: str) → dict | None
    Return {"block": True, "reason": "..."} to veto a tool call.

  post_tool(tool_name: str, args: dict, result: dict, session_id: str) → None
    Observe results (e.g. for logging, alerts, side effects).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable

PLUGIN_DIR = Path.home() / ".aibutler" / "plugins"


class PluginManager:
    def __init__(self, plugin_dir: Path | str = PLUGIN_DIR):
        self.plugin_dir = Path(plugin_dir).expanduser()
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self.plugins: dict[str, Any] = {}
        self.tools: dict[str, dict] = {}
        self.hooks: dict[str, list[Callable]] = {
            "pre_tool": [],
            "post_tool": [],
            "post_tool_error": [],
        }

    def load_all(self) -> list[str]:
        """Load all plugins from the plugin directory. Returns list of loaded names."""
        loaded = []
        for py_file in sorted(self.plugin_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                self._load_plugin(py_file)
                loaded.append(py_file.stem)
            except Exception as e:
                print(f"[plugins] Failed to load {py_file.name}: {e}")
        return loaded

    def _load_plugin(self, path: Path) -> None:
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"aibutler_plugin_{name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.plugins[name] = module

        # Register tools
        if hasattr(module, "register_tools"):
            new_tools = module.register_tools()
            self.tools.update(new_tools)

        # Register hooks
        if hasattr(module, "register_hooks"):
            module.register_hooks(self.hooks)

    def run_pre_tool_hooks(self, tool_name: str, args: dict, session_id: str) -> dict | None:
        """
        Run all pre_tool hooks. If any returns {"block": True}, return that dict.
        Returns None to allow execution to proceed.
        """
        for hook in self.hooks["pre_tool"]:
            try:
                result = hook(tool_name=tool_name, args=args, session_id=session_id)
                if isinstance(result, dict) and result.get("block"):
                    return result
            except Exception as e:
                print(f"[plugins] pre_tool hook error: {e}")
        return None

    def run_post_tool_hooks(self, tool_name: str, args: dict, result: dict, session_id: str) -> None:
        """Run all post_tool hooks (observational only)."""
        for hook in self.hooks["post_tool"]:
            try:
                hook(tool_name=tool_name, args=args, result=result, session_id=session_id)
            except Exception as e:
                print(f"[plugins] post_tool hook error: {e}")

    def run_post_tool_error_hooks(self, tool_name: str, args: dict, result: dict, session_id: str) -> None:
        """Run observational hooks for failed tool executions."""
        for hook in self.hooks["post_tool_error"]:
            try:
                hook(tool_name=tool_name, args=args, result=result, session_id=session_id)
            except Exception as e:
                print(f"[plugins] post_tool_error hook error: {e}")

    def get_all_tools(self) -> dict[str, dict]:
        """Return merged tool registry from all loaded plugins."""
        return self.tools

    def list_plugins(self) -> list[str]:
        return list(self.plugins.keys())


# Module-level singleton
_manager: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _manager
    if _manager is None:
        _manager = PluginManager()
        _manager.load_all()
    return _manager
