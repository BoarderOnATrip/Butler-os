"""aiButler runtime spine: typed models, persistence, engine, and registry."""

from __future__ import annotations

from importlib import import_module

from .models import (
    ApprovalPolicy,
    ApprovalRequest,
    ButlerSession,
    ButlerTask,
    CapabilityGrant,
    ContextEvent,
    ContextPendingItem,
    ContextSheet,
    MemoryRecord,
    ToolCallReceipt,
    ToolSpec,
)

_LAZY_EXPORTS = {
    "ButlerCoreAgent": (".core_agent", "ButlerCoreAgent"),
    "ButlerRuntime": (".engine", "ButlerRuntime"),
    "get_default_runtime": (".engine", "get_default_runtime"),
    "build_tool_registry": (".tool_registry", "build_tool_registry"),
    "list_tool_specs": (".tool_registry", "list_tool_specs"),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        module_name, attr_name = _LAZY_EXPORTS[name]
        module = import_module(module_name, __name__)
        return getattr(module, attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ApprovalPolicy",
    "ApprovalRequest",
    "ButlerCoreAgent",
    "ButlerRuntime",
    "ButlerSession",
    "ButlerTask",
    "CapabilityGrant",
    "ContextEvent",
    "ContextPendingItem",
    "ContextSheet",
    "MemoryRecord",
    "ToolSpec",
    "ToolCallReceipt",
    "build_tool_registry",
    "get_default_runtime",
    "list_tool_specs",
]
