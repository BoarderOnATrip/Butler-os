#!/usr/bin/env python3
"""
aiButler runtime engine.

This is the first persistent ButlerRuntime:
  - sessions
  - tasks
  - approvals
  - memories
  - tool execution receipts
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from uuid import uuid4

from runtime.context_repository import ContextRepository
from runtime.models import (
    ApprovalRequest,
    ButlerSession,
    ButlerTask,
    CapabilityGrant,
    ContinuityPacket,
    ContextEvent,
    ContextPendingItem,
    ContextSheet,
    MemoryRecord,
    ToolCallReceipt,
    utc_now,
)
from runtime.plugins import get_plugin_manager
from runtime.security import (
    arm_token_ttl_minutes,
    full_access_feature_enabled,
    future_expiry_iso,
    hash_token,
    is_expired,
    issue_arm_token,
    trusted_local_session,
)
from runtime.store import RuntimeStore
from runtime.tool_registry import build_tool_registry, list_tool_specs

DEFAULT_RUNTIME_DIR = Path.home() / ".aibutler" / "runtime"
_DEFAULT_RUNTIME: "ButlerRuntime | None" = None


def _make_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class ButlerRuntime:
    """Open-source local runtime for Butler sessions and action execution."""

    def __init__(self, base_dir: str | Path = DEFAULT_RUNTIME_DIR):
        self.base_dir = Path(base_dir).expanduser()
        self.store = RuntimeStore(self.base_dir)
        self.context_repository = ContextRepository(self.base_dir.parent / "context")
        self.plugin_manager = get_plugin_manager()
        self.tool_registry = build_tool_registry()
        self.tool_specs = {spec.name: spec for spec in list_tool_specs()}

    # ──────────────────────────────────────────────────────────────────────
    # Persistence helpers
    # ──────────────────────────────────────────────────────────────────────

    def _load_sessions(self) -> list[ButlerSession]:
        data = self.store.load_json("sessions.json", [])
        return [ButlerSession.from_dict(row) for row in data]

    def _save_sessions(self, sessions: list[ButlerSession]) -> None:
        self.store.save_json("sessions.json", [session.to_dict() for session in sessions])

    def _load_tasks(self) -> list[ButlerTask]:
        data = self.store.load_json("tasks.json", [])
        return [ButlerTask.from_dict(row) for row in data]

    def _save_tasks(self, tasks: list[ButlerTask]) -> None:
        self.store.save_json("tasks.json", [task.to_dict() for task in tasks])

    def _load_approvals(self) -> list[ApprovalRequest]:
        data = self.store.load_json("approvals.json", [])
        return [ApprovalRequest.from_dict(row) for row in data]

    def _save_approvals(self, approvals: list[ApprovalRequest]) -> None:
        self.store.save_json("approvals.json", [approval.to_dict() for approval in approvals])

    def _load_continuity_packets(self) -> list[ContinuityPacket]:
        data = self.store.load_json("continuity_packets.json", [])
        return [ContinuityPacket.from_dict(row) for row in data]

    def _save_continuity_packets(self, packets: list[ContinuityPacket]) -> None:
        self.store.save_json("continuity_packets.json", [packet.to_dict() for packet in packets])

    def _write_continuity_event(self, payload: dict) -> str:
        path = self.store.append_jsonl("continuity_events.jsonl", payload)
        return str(path)

    def _write_receipt(self, receipt: ToolCallReceipt) -> str:
        path = self.store.append_jsonl("receipts.jsonl", receipt.to_dict())
        return str(path)

    def _write_memory(self, memory: MemoryRecord) -> str:
        path = self.store.append_jsonl("memories.jsonl", memory.to_dict())
        return str(path)

    def _write_security_event(self, payload: dict) -> str:
        path = self.store.append_jsonl("security_events.jsonl", payload)
        return str(path)

    def _load_arm_state(self) -> dict:
        return self.store.load_json("arm_state.json", {})

    def _save_arm_state(self, data: dict) -> None:
        self.store.save_json("arm_state.json", data)

    def _continuity_packet_expired(self, packet: ContinuityPacket) -> bool:
        return is_expired(packet.expires_at)

    def _consume_arm_token(self, token: str | None) -> dict | None:
        if not token:
            return None

        state = self._load_arm_state()
        if not state or not state.get("token_hash"):
            return None
        if is_expired(state.get("expires_at")):
            self._save_arm_state({})
            return None
        if hash_token(token) != state["token_hash"]:
            return None

        consumed = dict(state)
        consumed["used_at"] = utc_now()
        self._save_arm_state({})
        return consumed

    # ──────────────────────────────────────────────────────────────────────
    # Sessions
    # ──────────────────────────────────────────────────────────────────────

    def create_session(
        self,
        user_id: str = "local-user",
        surface: str = "local",
        metadata: dict | None = None,
        capability_grants: list[CapabilityGrant] | None = None,
    ) -> ButlerSession:
        session = ButlerSession(
            id=_make_id("session"),
            user_id=user_id,
            surface=surface,
            metadata=metadata or {},
            capability_grants=capability_grants or [],
        )
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session

    def get_session(self, session_id: str) -> ButlerSession | None:
        for session in self._load_sessions():
            if session.id == session_id:
                return session
        return None

    def get_or_create_session(
        self,
        session_id: str | None = None,
        *,
        user_id: str = "local-user",
        surface: str = "local",
        metadata: dict | None = None,
    ) -> ButlerSession:
        if session_id:
            existing = self.get_session(session_id)
            if existing:
                return existing
        return self.create_session(user_id=user_id, surface=surface, metadata=metadata)

    def list_sessions(self, limit: int = 20) -> list[ButlerSession]:
        return self._load_sessions()[-limit:]

    def touch_session(self, session_id: str) -> ButlerSession | None:
        sessions = self._load_sessions()
        target = None
        for index, session in enumerate(sessions):
            if session.id == session_id:
                session.updated_at = utc_now()
                sessions[index] = session
                target = session
                break
        if target:
            self._save_sessions(sessions)
        return target

    def close_session(self, session_id: str) -> ButlerSession | None:
        sessions = self._load_sessions()
        target = None
        for index, session in enumerate(sessions):
            if session.id == session_id:
                session.status = "closed"
                session.updated_at = utc_now()
                sessions[index] = session
                target = session
                break
        if target:
            self._save_sessions(sessions)
        return target

    def set_permission_mode(
        self,
        session_id: str,
        mode: str,
        *,
        actor: str = "user",
        note: str = "",
        duration_minutes: int | None = None,
        arm_token: str | None = None,
    ) -> ButlerSession | None:
        sessions = self._load_sessions()
        target = None
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"locked", "standard", "full-access"}:
            raise ValueError(f"Unsupported permission mode: {mode}")
        consumed_arm_state = None

        for index, session in enumerate(sessions):
            if session.id != session_id:
                continue

            if normalized_mode == "full-access":
                if not full_access_feature_enabled():
                    raise PermissionError(
                        "Full access is disabled. Set AIBUTLER_ENABLE_FULL_ACCESS=1 on this machine."
                    )
                if not trusted_local_session(session):
                    raise PermissionError(
                        "Full access can only be enabled for trusted local sessions."
                    )
                consumed_arm_state = self._consume_arm_token(arm_token)
                if not consumed_arm_state:
                    raise PermissionError(
                        "A valid local arm token is required before enabling full access."
                    )
                unique_capabilities = sorted({spec.capability for spec in self.tool_specs.values()})
                session.permission_mode = "full-access"
                session.full_access_expires_at = future_expiry_iso(duration_minutes)
                session.capability_grants = [
                    CapabilityGrant(capability=capability, granted=True, scope="full", reason="full-access mode")
                    for capability in unique_capabilities
                ]
            elif normalized_mode == "locked":
                session.permission_mode = "locked"
                session.full_access_expires_at = None
                session.capability_grants = []
            else:
                session.permission_mode = "standard"
                session.full_access_expires_at = None
                session.capability_grants = []

            session.updated_at = utc_now()
            sessions[index] = session
            target = session
            break

        if target:
            self._save_sessions(sessions)
            self._write_security_event(
                {
                    "event": "permission_mode_change",
                    "session_id": target.id,
                    "user_id": target.user_id,
                    "mode": target.permission_mode,
                    "expires_at": target.full_access_expires_at,
                    "actor": actor,
                    "note": note,
                    "armed_by": consumed_arm_state.get("actor") if consumed_arm_state else None,
                    "created_at": utc_now(),
                }
            )
        return target

    def arm_full_access(
        self,
        *,
        actor: str = "user",
        note: str = "",
        duration_minutes: int | None = None,
    ) -> dict:
        ttl = duration_minutes if duration_minutes is not None else arm_token_ttl_minutes()
        token = issue_arm_token()
        expires_at = future_expiry_iso(ttl)
        self._save_arm_state(
            {
                "token_hash": hash_token(token),
                "expires_at": expires_at,
                "actor": actor,
                "note": note,
                "created_at": utc_now(),
            }
        )
        self._write_security_event(
            {
                "event": "full_access_armed",
                "actor": actor,
                "note": note,
                "expires_at": expires_at,
                "created_at": utc_now(),
            }
        )
        return {
            "ok": True,
            "output": {
                "arm_token": token,
                "expires_at": expires_at,
                "actor": actor,
                "note": note,
            },
            "error": None,
        }

    def get_permission_state(self, session_id: str) -> dict:
        session = self.get_session(session_id)
        if not session:
            return {"ok": False, "error": f"Unknown session: {session_id}"}
        active_full_access = (
            session.permission_mode == "full-access"
            and not is_expired(session.full_access_expires_at)
            and trusted_local_session(session)
            and full_access_feature_enabled()
        )
        return {
            "ok": True,
            "output": {
                "session_id": session.id,
                "surface": session.surface,
                "trusted_local": trusted_local_session(session),
                "permission_mode": session.permission_mode,
                "full_access_enabled": full_access_feature_enabled(),
                "full_access_active": active_full_access,
                "full_access_expires_at": session.full_access_expires_at,
                "arm_token_required": True,
                "capability_grants": [grant.to_dict() for grant in session.capability_grants],
            },
            "error": None,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Tasks
    # ──────────────────────────────────────────────────────────────────────

    def create_task(
        self,
        session_id: str,
        title: str,
        kind: str = "general",
        payload: dict | None = None,
    ) -> ButlerTask:
        task = ButlerTask(
            id=_make_id("task"),
            session_id=session_id,
            title=title,
            kind=kind,
            payload=payload or {},
        )
        tasks = self._load_tasks()
        tasks.append(task)
        self._save_tasks(tasks)
        self.touch_session(session_id)
        return task

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> ButlerTask | None:
        tasks = self._load_tasks()
        target = None
        for index, task in enumerate(tasks):
            if task.id == task_id:
                if status:
                    task.status = status
                if result is not None:
                    task.result = result
                if error is not None:
                    task.error = error
                task.updated_at = utc_now()
                tasks[index] = task
                target = task
                break
        if target:
            self._save_tasks(tasks)
            self.touch_session(target.session_id)
        return target

    def list_tasks(self, session_id: str | None = None, limit: int = 50) -> list[ButlerTask]:
        tasks = self._load_tasks()
        if session_id:
            tasks = [task for task in tasks if task.session_id == session_id]
        return tasks[-limit:]

    # ──────────────────────────────────────────────────────────────────────
    # Approvals
    # ──────────────────────────────────────────────────────────────────────

    def request_approval(
        self,
        session_id: str,
        tool_name: str,
        reason: str,
        args: dict | None = None,
    ) -> ApprovalRequest:
        approval = ApprovalRequest(
            id=_make_id("approval"),
            session_id=session_id,
            tool_name=tool_name,
            reason=reason,
            args=args or {},
        )
        approvals = self._load_approvals()
        approvals.append(approval)
        self._save_approvals(approvals)
        self.touch_session(session_id)
        return approval

    def resolve_approval(
        self,
        approval_id: str,
        *,
        approved: bool,
        actor: str = "user",
        note: str = "",
    ) -> ApprovalRequest | None:
        approvals = self._load_approvals()
        target = None
        for index, approval in enumerate(approvals):
            if approval.id == approval_id:
                approval.status = "approved" if approved else "rejected"
                approval.actor = actor
                approval.note = note
                approval.resolved_at = utc_now()
                approvals[index] = approval
                target = approval
                break
        if target:
            self._save_approvals(approvals)
            self.touch_session(target.session_id)
        return target

    def list_approvals(self, session_id: str | None = None, status: str | None = None) -> list[ApprovalRequest]:
        approvals = self._load_approvals()
        if session_id:
            approvals = [approval for approval in approvals if approval.session_id == session_id]
        if status:
            approvals = [approval for approval in approvals if approval.status == status]
        return approvals

    # ──────────────────────────────────────────────────────────────────────
    # Memory
    # ──────────────────────────────────────────────────────────────────────

    def write_memory(
        self,
        session_id: str,
        kind: str,
        content: str,
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> MemoryRecord:
        memory = MemoryRecord(
            id=_make_id("memory"),
            session_id=session_id,
            kind=kind,
            content=content,
            tags=tags or [],
            metadata=metadata or {},
        )
        self._write_memory(memory)
        self.touch_session(session_id)
        return memory

    def list_memories(self, session_id: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        rows = self.store.load_jsonl("memories.jsonl", limit=limit * 4)
        memories = [MemoryRecord.from_dict(row) for row in rows]
        if session_id:
            memories = [memory for memory in memories if memory.session_id == session_id]
        return memories[-limit:]

    # ──────────────────────────────────────────────────────────────────────
    # Continuity
    # ──────────────────────────────────────────────────────────────────────

    def create_continuity_packet(
        self,
        *,
        kind: str,
        title: str,
        content: str = "",
        source_device: str = "",
        target_device: str = "",
        source_surface: str = "",
        metadata: dict | None = None,
        expires_in_minutes: int | None = 60,
        session_id: str | None = None,
    ) -> ContinuityPacket:
        packet = ContinuityPacket(
            id=_make_id("handoff"),
            kind=kind.strip() or "text",
            title=title.strip() or "Continuity handoff",
            content=content,
            source_device=source_device.strip(),
            target_device=target_device.strip(),
            source_surface=source_surface.strip(),
            metadata=copy.deepcopy(metadata or {}),
            expires_at=future_expiry_iso(expires_in_minutes) if expires_in_minutes else None,
            session_id=session_id,
        )
        packets = self._load_continuity_packets()
        packets.append(packet)
        self._save_continuity_packets(packets)
        self._write_continuity_event(
            {
                "event": "continuity_packet_created",
                "packet": packet.to_dict(),
                "created_at": utc_now(),
            }
        )
        if session_id:
            self.touch_session(session_id)
        return packet

    def list_continuity_packets(
        self,
        *,
        target_device: str | None = None,
        status: str | None = None,
        limit: int = 20,
        include_consumed: bool = False,
    ) -> list[ContinuityPacket]:
        packets = self._load_continuity_packets()
        if target_device:
            packets = [packet for packet in packets if packet.target_device == target_device]
        if status:
            packets = [packet for packet in packets if packet.status == status]
        elif not include_consumed:
            packets = [packet for packet in packets if packet.status != "consumed"]
        packets = [packet for packet in packets if not self._continuity_packet_expired(packet)]
        packets.sort(key=lambda packet: packet.updated_at or packet.created_at, reverse=True)
        return packets[:limit]

    def claim_continuity_packet(
        self,
        packet_id: str,
        *,
        actor_device: str,
        lease_minutes: int = 15,
    ) -> ContinuityPacket | None:
        packets = self._load_continuity_packets()
        target = None
        now = utc_now()
        for index, packet in enumerate(packets):
            if packet.id != packet_id:
                continue
            if packet.status == "consumed" or self._continuity_packet_expired(packet):
                return None
            if (
                packet.lease_owner
                and packet.lease_owner != actor_device
                and not is_expired(packet.lease_expires_at)
            ):
                raise ValueError(f"Packet is currently claimed by {packet.lease_owner}")
            packet.status = "claimed"
            packet.lease_owner = actor_device.strip()
            packet.lease_expires_at = future_expiry_iso(lease_minutes)
            packet.updated_at = now
            packets[index] = packet
            target = packet
            break
        if target:
            self._save_continuity_packets(packets)
            self._write_continuity_event(
                {
                    "event": "continuity_packet_claimed",
                    "packet_id": target.id,
                    "actor_device": actor_device,
                    "lease_expires_at": target.lease_expires_at,
                    "created_at": now,
                }
            )
        return target

    def acknowledge_continuity_packet(
        self,
        packet_id: str,
        *,
        actor_device: str,
        note: str = "",
    ) -> ContinuityPacket | None:
        packets = self._load_continuity_packets()
        target = None
        now = utc_now()
        for index, packet in enumerate(packets):
            if packet.id != packet_id:
                continue
            packet.status = "consumed"
            packet.lease_owner = actor_device.strip()
            packet.lease_expires_at = None
            packet.consumed_at = now
            packet.updated_at = now
            packet.metadata = dict(packet.metadata)
            if note:
                packet.metadata["ack_note"] = note
            packets[index] = packet
            target = packet
            break
        if target:
            self._save_continuity_packets(packets)
            self._write_continuity_event(
                {
                    "event": "continuity_packet_consumed",
                    "packet_id": target.id,
                    "actor_device": actor_device,
                    "note": note,
                    "created_at": now,
                }
            )
        return target

    # ──────────────────────────────────────────────────────────────────────
    # Context repository
    # ──────────────────────────────────────────────────────────────────────

    def init_context_repo(self) -> dict:
        return self.context_repository.ensure_layout()

    def append_context_event(
        self,
        *,
        event_type: str,
        summary: str,
        payload: dict | None = None,
        source: dict | None = None,
        entity_refs: list[str] | None = None,
        session_id: str | None = None,
    ) -> ContextEvent:
        event = self.context_repository.append_event(
            event_id=_make_id("ctxevent"),
            event_type=event_type,
            summary=summary,
            payload=payload or {},
            source=source or {},
            entity_refs=entity_refs or [],
            session_id=session_id,
        )
        if session_id:
            self.touch_session(session_id)
        return event

    def create_context_sheet(
        self,
        *,
        kind: str,
        name: str,
        body: str = "",
        slug: str | None = None,
        links: list[str] | None = None,
        source_refs: list[str] | None = None,
        metadata: dict | None = None,
        status: str = "active",
        confidence: float = 1.0,
    ) -> ContextSheet:
        return self.context_repository.create_sheet(
            sheet_id=_make_id("ctxsheet"),
            kind=kind,
            name=name,
            body=body,
            slug=slug,
            links=links or [],
            source_refs=source_refs or [],
            metadata=metadata or {},
            status=status,
            confidence=confidence,
        )

    def list_context_sheets(self, *, kind: str | None = None, limit: int = 50) -> list[ContextSheet]:
        return self.context_repository.list_sheets(kind=kind, limit=limit)

    def capture_pending_context(
        self,
        *,
        capture_kind: str,
        title: str,
        content: str = "",
        metadata: dict | None = None,
        source: dict | None = None,
        confidence: float = 0.0,
        session_id: str | None = None,
    ) -> ContextPendingItem:
        item = self.context_repository.create_pending_item(
            pending_id=_make_id("pending"),
            capture_kind=capture_kind,
            title=title,
            content=content,
            metadata=metadata or {},
            source=source or {},
            confidence=confidence,
            session_id=session_id,
        )
        if session_id:
            self.touch_session(session_id)
        return item

    def list_pending_context(self, *, limit: int = 50) -> list[ContextPendingItem]:
        return self.context_repository.list_pending_items(limit=limit)

    def get_pending_context_item(self, pending_id: str) -> ContextPendingItem | None:
        return self.context_repository.get_pending_item(pending_id)

    def update_pending_context_item(
        self,
        pending_id: str,
        *,
        status: str | None = None,
        title: str | None = None,
        content: str | None = None,
        metadata: dict | None = None,
        source: dict | None = None,
        confidence: float | None = None,
        session_id: str | None = None,
    ) -> ContextPendingItem | None:
        return self.context_repository.update_pending_item(
            pending_id,
            status=status,
            title=title,
            content=content,
            metadata=metadata or None,
            source=source or None,
            confidence=confidence,
            session_id=session_id,
        )

    def list_context_events(self, *, limit: int = 50) -> list[ContextEvent]:
        return self.context_repository.list_events(limit=limit)

    # ──────────────────────────────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────────────────────────────

    def _normalize_tool_args(self, tool_name: str, args: dict) -> dict:
        normalized = copy.deepcopy(args)
        for key in ("position", "box", "start", "end"):
            if key in normalized and isinstance(normalized[key], list):
                normalized[key] = tuple(normalized[key])

        params = self.tool_specs[tool_name].params
        if "position" in normalized and "x" in params and "y" in params:
            position = normalized.pop("position")
            if isinstance(position, tuple) and len(position) == 2:
                normalized.setdefault("x", position[0])
                normalized.setdefault("y", position[1])

        if "start" in normalized and "start_x" in params and "start_y" in params:
            start = normalized.pop("start")
            if isinstance(start, tuple) and len(start) == 2:
                normalized.setdefault("start_x", start[0])
                normalized.setdefault("start_y", start[1])

        if "end" in normalized and "end_x" in params and "end_y" in params:
            end = normalized.pop("end")
            if isinstance(end, tuple) and len(end) == 2:
                normalized.setdefault("end_x", end[0])
                normalized.setdefault("end_y", end[1])
        return normalized

    def _approval_required(self, tool_name: str, args: dict, approved: bool) -> bool:
        spec = self.tool_specs[tool_name]
        if not spec.approval.required or approved:
            return False
        if spec.approval.live_only and args.get("dry_run"):
            return False
        return True

    def _has_full_access(self, session: ButlerSession) -> bool:
        return (
            session.permission_mode == "full-access"
            and full_access_feature_enabled()
            and trusted_local_session(session)
            and not is_expired(session.full_access_expires_at)
        )

    def _capability_allowed(self, session: ButlerSession, capability: str) -> bool:
        if self._has_full_access(session):
            return True
        if session.permission_mode == "locked":
            return False

        grants = [grant for grant in session.capability_grants if grant.capability == capability]
        grants = [grant for grant in grants if grant.scope != "full"]
        if not grants:
            return True
        return any(grant.granted for grant in grants)

    def execute_tool(
        self,
        session_id: str,
        tool_name: str,
        args: dict | None = None,
        *,
        approved: bool = False,
        actor: str = "runtime",
        note: str = "",
    ) -> dict:
        args = args or {}
        session = self.get_session(session_id)
        if not session:
            return {"ok": False, "output": "", "error": f"Unknown session: {session_id}"}
        if tool_name not in self.tool_registry:
            return {"ok": False, "output": "", "error": f"Unknown tool: {tool_name}"}

        tool_args = self._normalize_tool_args(tool_name, args)
        approval_id = tool_args.pop("_approval_id", None) or tool_args.pop("approval_id", None)
        approved = approved or bool(tool_args.pop("_approved", False))
        spec = self.tool_specs[tool_name]

        pre_hook_result = self.plugin_manager.run_pre_tool_hooks(
            tool_name=tool_name,
            args=tool_args,
            session_id=session_id,
        )
        if isinstance(pre_hook_result, dict) and pre_hook_result.get("block"):
            return {
                "ok": False,
                "output": "",
                "error": pre_hook_result.get("reason", f"Blocked by pre-tool hook: {tool_name}"),
                "tool": spec.to_dict(),
                "hook_blocked": True,
            }

        if not self._capability_allowed(session, spec.capability):
            return {
                "ok": False,
                "output": "",
                "error": f"Capability denied for {tool_name}: {spec.capability}",
                "tool": spec.to_dict(),
            }

        approved = approved or self._has_full_access(session)

        if self._approval_required(tool_name, tool_args, approved):
            approval = self.request_approval(
                session_id=session_id,
                tool_name=tool_name,
                reason=spec.approval.reason or f"{tool_name} requires approval",
                args=tool_args,
            )
            return {
                "ok": False,
                "output": "",
                "error": f"Approval required before running {tool_name}",
                "approval_request_id": approval.id,
                "approval_reason": approval.reason,
                "tool": spec.to_dict(),
            }

        if approval_id and approved:
            self.resolve_approval(approval_id, approved=True, actor=actor, note=note)

        fn = self.tool_registry[tool_name]["fn"]
        try:
            result = fn(**tool_args)
        except Exception as exc:
            result = {"ok": False, "output": "", "error": str(exc)}

        if result.get("ok"):
            self.plugin_manager.run_post_tool_hooks(
                tool_name=tool_name,
                args=tool_args,
                result=result,
                session_id=session_id,
            )
        else:
            self.plugin_manager.run_post_tool_error_hooks(
                tool_name=tool_name,
                args=tool_args,
                result=result,
                session_id=session_id,
            )

        receipt = ToolCallReceipt(
            session_id=session_id,
            tool_name=tool_name,
            args=tool_args,
            ok=bool(result.get("ok")),
            tool_category=spec.category,
            risk=spec.risk,
            output=result.get("output"),
            error=result.get("error"),
            approval_request_id=approval_id,
        )
        receipt_path = self._write_receipt(receipt)
        self.touch_session(session_id)

        enriched = dict(result)
        enriched["runtime_receipt"] = receipt.to_dict()
        enriched["runtime_receipt_path"] = receipt_path
        return enriched

    def list_receipts(self, session_id: str | None = None, limit: int = 50) -> list[ToolCallReceipt]:
        rows = self.store.load_jsonl("receipts.jsonl", limit=limit * 4)
        receipts = [ToolCallReceipt(**row) for row in rows]
        if session_id:
            receipts = [receipt for receipt in receipts if receipt.session_id == session_id]
        return receipts[-limit:]

    def list_security_events(self, limit: int = 50) -> list[dict]:
        return self.store.load_jsonl("security_events.jsonl", limit=limit)


def get_default_runtime(base_dir: str | Path = DEFAULT_RUNTIME_DIR) -> ButlerRuntime:
    """Return a process-global ButlerRuntime instance."""
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = ButlerRuntime(base_dir=base_dir)
    return _DEFAULT_RUNTIME
